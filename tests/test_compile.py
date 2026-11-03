"""Golden-file, decision and unit tests for compiler/compile.py and tools/validate.py.

    python -m unittest discover -s tests -v
    UPDATE_GOLDEN=1 python -m unittest discover -s tests     # regenerate tests/golden/

Every example manifest and every valid manifest in tests/manifests/ is compiled
with every emit target and compared to tests/golden/<name>/<file>. Crawl
decisions are also checked with a small RFC 9309 evaluator (robots_eval.py), so
a regression cannot hide behind a regenerated snapshot.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPILE_PY = os.path.join(ROOT, "compiler", "compile.py")
VALIDATE_PY = os.path.join(ROOT, "tools", "validate.py")
GOLDEN = os.path.join(ROOT, "tests", "golden")
MANIFESTS = os.path.join(ROOT, "tests", "manifests")
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


compile_mod = _load("consent_compile", COMPILE_PY)
validate_mod = _load("consent_validate", VALIDATE_PY)
robots_eval = _load("robots_eval", os.path.join(ROOT, "tests", "robots_eval.py"))


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fixture(name):
    for folder in (MANIFESTS, os.path.join(ROOT, "examples")):
        path = os.path.join(folder, name + ".json")
        if os.path.exists(path):
            return read_json(path)
    raise FileNotFoundError(name)


def manifests():
    for folder in ("examples", os.path.join("tests", "manifests")):
        d = os.path.join(ROOT, folder)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json") and not fn.endswith("-invalid.json"):
                yield fn[:-5], os.path.join(d, fn)


def compile_target(manifest, target):
    return compile_mod.compile_all(manifest, [target])


class GoldenTests(unittest.TestCase):
    def test_all_targets_match_golden(self):
        seen = set()
        for name, path in manifests():
            seen.add(name)
            with self.subTest(manifest=name):
                manifest = read_json(path)
                errors, _ = validate_mod.validate(manifest)
                self.assertEqual(errors, [], f"{name} must validate")
                outputs = compile_mod.compile_all(manifest, list(compile_mod.COMPILERS))
                gdir = os.path.join(GOLDEN, name)
                if UPDATE:
                    shutil.rmtree(gdir, ignore_errors=True)
                    os.makedirs(gdir)
                    for fn, content in outputs.items():
                        with open(os.path.join(gdir, fn), "w", encoding="utf-8") as f:
                            f.write(content)
                    continue
                self.assertTrue(os.path.isdir(gdir), f"no golden dir for {name}. Run with UPDATE_GOLDEN=1")
                present = sorted(f for f in os.listdir(gdir) if not f.startswith("."))
                self.assertEqual(sorted(outputs), present, f"{name}: output file set changed")
                for fn, content in outputs.items():
                    with open(os.path.join(gdir, fn), encoding="utf-8") as f:
                        expected = f.read()
                    self.assertEqual(content, expected, f"{name}/{fn} differs from golden")
        dirs = {d for d in os.listdir(GOLDEN) if not d.startswith(".")}
        if UPDATE:
            for stale in dirs - seen:
                shutil.rmtree(os.path.join(GOLDEN, stale))
        else:
            self.assertEqual(dirs, seen, "stale golden directories")


# (fixture, agent, path, expected allowed) checked against the compiled robots.txt
DECISIONS = [
    ("nested", "GPTBot", "/docs/page", True),
    ("nested", "GPTBot", "/docs/private/x", False),
    ("nested", "ChatGPT-User", "/docs/private/x", False),
    ("nested", "Googlebot", "/docs/private/x", True),
    ("search-nested", "Googlebot", "/account/settings", False),
    ("search-nested", "Googlebot", "/account/help/faq", True),
    ("search-nested", "Bingbot", "/account/help/faq", True),
    ("search-nested", "GPTBot", "/account/help/faq", True),
    ("search-deny-sitewide", "Googlebot", "/premium/story", True),   # noindex handles it, not Disallow
    ("search-deny-sitewide", "GPTBot", "/premium/story", False),
    ("globs", "GPTBot", "/a/report.pdf", True),
    ("globs", "GPTBot", "/drafts/x", False),
    ("globs", "GPTBot", "/press/x", True),
    ("globs", "GPTBot", "/contact", False),
    ("ai-input-path-deny", "ChatGPT-User", "/premium/x", False),
    ("ai-input-path-deny", "ChatGPT-User", "/paid/x", False),
    ("ai-input-path-deny", "ChatGPT-User", "/free", True),
    ("ai-input-path-deny", "GPTBot", "/premium/x", True),
    ("genai-only", "GPTBot", "/anything", False),
    ("inherit-genai", "GPTBot", "/open/x", False),
    ("unknown-default", "GPTBot", "/private/x", False),
    ("unknown-default", "GPTBot", "/public", True),
    ("hostname-matcher", "GPTBot", "/members/x", False),              # allow with a matcher is dropped
    ("dup-path-merge", "GPTBot", "/members/x", False),
    ("dup-path-merge", "ChatGPT-User", "/members/x", False),
    ("root-rule", "GPTBot", "/anything", False),
    ("doublestar-middle", "GPTBot", "/report.pdf", False),
    ("doublestar-middle", "GPTBot", "/a/b/report.pdf", False),
    ("doublestar-middle", "GPTBot", "/docs/secret", False),
    ("doublestar-middle", "GPTBot", "/docs/a/secret", False),
    ("doublestar-middle", "GPTBot", "/docs/readme", True),
    ("news-publisher", "ChatGPT-User", "/press-releases/x", True),
    ("news-publisher", "ChatGPT-User", "/premium/x", False),
    ("news-publisher", "Meta-ExternalAgent", "/story", False),
    ("news-publisher", "OAI-SearchBot", "/story", True),
    ("saas-platform", "Googlebot", "/app/x", False),
    ("saas-platform", "Googlebot", "/docs/x", True),
    ("matcher-vs-rules", "GPTBot", "/members/x", False),            # same-path matcher allow dropped
    ("matcher-vs-rules", "GPTBot", "/members/public/x", False),     # nested matcher allow dropped
    ("matcher-vs-rules", "ChatGPT-User", "/paid/x", False),         # matcher deny kept
    ("matcher-vs-rules", "GPTBot", "/free", True),
    ("matcher-root", "GPTBot", "/blog/report.pdf", False),          # root deny beats matcher allow
    ("doublestar-allow", "GPTBot", "/docs/public/a", True),
    ("doublestar-allow", "GPTBot", "/docs/x/public/a", True),
    ("doublestar-allow", "GPTBot", "/docs/notpublic/a", False),
    ("doublestar-allow", "GPTBot", "/docs/secret-public/a", False),
    ("nested-inherit", "GPTBot", "/premium/archive/x", False),      # inherits the enclosing deny
    ("nested-inherit", "ChatGPT-User", "/premium/archive/x", False),
    ("nested-inherit", "Googlebot", "/premium/archive/x", False),
    ("nested-inherit", "Googlebot", "/premium/x", True),
    ("unknown-under-parent", "GPTBot", "/x/page", False),            # parent deny applies
    ("unknown-under-parent", "GPTBot", "/premium/page", False),
    ("tie-order", "GPTBot", "/docs/a.pdf", True),                    # Allow wins the tie, as RFC 9309 says
    ("search-deny-allow-deny", "Googlebot", "/blog/drafts/x", True), # noindex route, robots stays open
    ("declarative-only-rule", "GPTBot", "/reports/q3.pdf", False),   # no training line for a transform-only rule
    ("declarative-only-rule", "ChatGPT-User", "/drafts/a.pdf", False),
    ("declarative-only-rule", "GPTBot", "/reports/q3.html", True),
    ("wildcard-sibling", "GPTBot", "/m/report.pdf", False),          # search-only sibling adds no training line
    ("wildcard-sibling", "ChatGPT-User", "/m/report.pdf", False),
    ("wildcard-sibling", "Googlebot", "/m/report.pdf", False),       # '*' search Disallow on /*.pdf
    ("matcher-vs-wildcard", "GPTBot", "/reports/r.pdf", False),
    ("matcher-vs-wildcard", "GPTBot", "/docs/public/a.pdf", False),
    ("matcher-vs-wildcard", "GPTBot", "/reports/r.html", True),
    ("matcher-parent-child", "GPTBot", "/m/x/page", False),          # child inherits the matcher deny
    ("matcher-parent-child", "GPTBot", "/a/b/x", False),             # order-independent
    ("matcher-root-deny", "GPTBot", "/page", False),
    ("matcher-root-deny", "GPTBot", "/open/x", True),
]


class DecisionTests(unittest.TestCase):
    def test_robots_decisions(self):
        for name, agent, path, expected in DECISIONS:
            with self.subTest(manifest=name, agent=agent, path=path):
                robots = compile_target(fixture(name), "robots-txt")["robots.txt"]
                self.assertEqual(robots_eval.can_fetch(robots, agent, path), expected, robots)

    def test_google_extended_matches_robots(self):
        for name, path in manifests():
            manifest = read_json(path)
            out = compile_target(manifest, "google-extended")
            robots = compile_target(manifest, "robots-txt")["robots.txt"]
            if "google-extended.txt" in out:
                for probe in ("/", "/docs/x", "/premium/x", "/report.pdf"):
                    self.assertEqual(robots_eval.can_fetch(out["google-extended.txt"], "Google-Extended", probe),
                                     robots_eval.can_fetch(robots, "Google-Extended", probe), (name, probe))


class ResolverTests(unittest.TestCase):
    def test_rule_inherits_unmentioned_categories(self):
        plan = compile_mod.Plan(fixture("inherit-genai"))
        pol = plan.rules[0].policy
        self.assertEqual(pol["train-ai"], "allow")
        self.assertEqual(pol["train-genai"], "deny")   # inherited from defaults (spec 6.6)
        self.assertEqual(compile_mod.training_decision(pol), "deny")

    def test_fallback_lowering(self):
        fb = {"unexpressible_state": "allow"}
        self.assertEqual(compile_mod.lower_state("charge", fb), "allow")
        self.assertEqual(compile_mod.lower_state("conditional", {}), "deny")
        self.assertIsNone(compile_mod.lower_state("unknown", fb))
        self.assertIsNone(compile_mod.lower_state("charge", {"unexpressible_state": "unknown"}))
        with self.assertRaises(compile_mod.CompileError):
            compile_mod.lower_state("alow", fb)

    def test_one_training_predicate(self):
        m = fixture("genai-only")
        self.assertEqual(compile_mod.compile_aipref_header(m), "Content-Usage: train-ai=n, search=y")
        self.assertIn('"tdm-reservation": 1', compile_mod.compile_tdmrep(m)["tdmrep.json"])
        self.assertIn("ai-train=no", compile_mod.compile_content_signal(m))

    def test_duplicate_paths_are_merged_with_warning(self):
        plan = compile_mod.Plan(fixture("dup-path-merge"))
        self.assertEqual([r.path for r in plan.rules], ["/members/"])
        self.assertEqual(plan.rules[0].policy["train-ai"], "deny")
        self.assertEqual(plan.rules[0].policy["ai-input"], "deny")
        self.assertTrue(any("merged" in w for w in compile_mod.WARNINGS))

    def test_root_rule_overrides_defaults_everywhere(self):
        m = fixture("root-rule")
        compile_mod.Plan(m)
        self.assertTrue(any("covers the whole site" in w for w in compile_mod.WARNINGS))
        self.assertEqual(compile_mod.compile_aipref_header(m), "Content-Usage: train-ai=n, search=y")
        self.assertIn("ai-train=no", compile_mod.compile_content_signal(m))
        self.assertIn("tdm-reservation: 1", compile_mod.compile_tdmrep(m)["tdmrep-headers.txt"])

    def test_sitewide_surfaces_drop_overridden_labels(self):
        m = fixture("allow-default-path-deny")
        header = compile_mod.compile_aipref_header(m)
        self.assertNotIn("train-ai=y", header)
        self.assertIn("train-ai omitted", header)
        cs = compile_mod.compile_content_signal(m)
        self.assertNotIn("ai-train=yes", cs)
        self.assertNotIn("ai-input=yes", cs)
        self.assertIn("search=yes", cs)
        tdm = compile_mod.compile_tdmrep(m)
        header_lines = [l for l in tdm["tdmrep-headers.txt"].splitlines() if not l.startswith("#")]
        self.assertFalse(any(l.startswith("tdm-reservation") or l.startswith("<meta") for l in header_lines), tdm["tdmrep-headers.txt"])
        self.assertIn("supersede", tdm["tdmrep-headers.txt"])
        entries = json.loads(tdm["tdmrep.json"])
        self.assertEqual([(e["location"], e["tdm-reservation"]) for e in entries], [("/private/", 1), ("/", 0)])
        self.assertIn("tdm-policy", entries[0])
        self.assertNotIn("tdm-policy", entries[1])

    def test_no_bare_noindex_with_path_allow(self):
        out = compile_mod.compile_x_robots_tag(fixture("search-deny-sitewide"))
        self.assertNotIn("\nX-Robots-Tag: noindex", "\n" + out.replace("# ", "#"))
        self.assertIn("/blog/", out)
        self.assertEqual(compile_mod.compile_x_robots_tag(fixture("tier-conflict-invalid")).count("noindex"), 0)

    def test_tdmrep_reserves_charge(self):
        tdm = compile_mod.compile_tdmrep(fixture("charge-unknown-rule"))
        self.assertIn('"location": "/premium/",\n    "tdm-reservation": 1', tdm["tdmrep.json"])
        self.assertTrue(any("lowers to unknown" in w for w in compile_mod.WARNINGS))

    def test_unknown_under_parent_inherits_everywhere(self):
        m = fixture("unknown-under-parent")
        self.assertEqual(compile_mod.compile_x_robots_tag(m), "X-Robots-Tag: noindex, nofollow")
        self.assertEqual(compile_mod.compile_aipref_header(m), "Content-Usage: train-ai=n, search=n")
        self.assertIn("Content-Signal: search=no, ai-input=no, ai-train=no", compile_mod.compile_content_signal(m))
        robots = compile_mod.compile_aipref_robots(m)
        self.assertNotIn("/x/", robots)                       # declares nothing, so no line: the default applies
        self.assertNotIn("=u", robots)
        tdm = json.loads(compile_mod.compile_tdmrep(m)["tdmrep.json"])
        self.assertIn({"location": "/premium/", "tdm-reservation": 1}, tdm)   # charge is reservable

    def test_matcher_rules_contribute_denies_only(self):
        plan = compile_mod.Plan(fixture("matcher-vs-rules"))
        by_path = {r.path: r.policy for r in plan.rules}
        self.assertEqual(by_path["/members/"]["train-ai"], "deny")
        self.assertEqual(by_path["/members/public/"]["train-ai"], "deny")
        self.assertEqual(by_path["/paid/"]["ai-input"], "deny")
        self.assertEqual(sum("could relax" in w for w in compile_mod.WARNINGS), 2)
        plan = compile_mod.Plan(fixture("matcher-vs-wildcard"))
        self.assertTrue(all(r.policy["train-ai"] != "allow" or "train-ai" not in r.declared for r in plan.rules))

    def test_declared_only_emission(self):
        plan = compile_mod.Plan(fixture("declarative-only-rule"))
        by_path = {r.path: r for r in plan.rules}
        self.assertNotIn("train-ai", by_path["/reports/"].declared)
        self.assertNotIn("train-ai", by_path["/drafts/"].declared)
        robots = compile_mod.compile_robots_txt(plan)
        self.assertNotIn("/reports/", robots)
        self.assertNotIn("/drafts/", robots)
        tdm = json.loads(compile_mod.compile_tdmrep(plan)["tdmrep.json"])
        self.assertEqual([e["location"] for e in tdm], ["/*.pdf", "/"])

    def test_tie_warning(self):
        compile_mod.Plan(fixture("tie-order"))
        self.assertTrue(any("equal length" in w for w in compile_mod.WARNINGS))
        m = fixture("minimal")  # two plain prefixes of equal length can never tie
        m["rules"] = [{"match": {"path": "/docs/*"}, "standard": {"train-ai": {"state": "allow"}}},
                      {"match": {"path": "/blog/*"}, "standard": {"train-ai": {"state": "deny"}}}]
        compile_mod.Plan(m)
        self.assertFalse(any("equal length" in w for w in compile_mod.WARNINGS))

    def test_explicit_unknown_overrides_nothing(self):
        m = fixture("minimal")  # train-ai deny by default
        m["rules"] = [{"match": {"path": "/*"}, "standard": {"train-ai": {"state": "unknown"}}}]
        self.assertEqual(compile_mod.compile_aipref_header(m), "Content-Usage: train-ai=n, search=y")
        self.assertIn("Disallow: /", compile_mod.compile_robots_txt(m))

    def test_tdmrep_policy_url_warning(self):
        m = fixture("open-permissive")   # train-ai conditional, fallback allow
        compile_mod.compile_tdmrep(m)
        self.assertTrue(any("reserves charge/conditional" in w for w in compile_mod.WARNINGS))
        m["endpoints"] = {"tdm_policy": "https://opendata.example.edu/tdm/policy.json"}
        compile_mod.compile_tdmrep(m)
        self.assertFalse(any("reserves charge/conditional" in w for w in compile_mod.WARNINGS))

    def test_nested_inherit(self):
        plan = compile_mod.Plan(fixture("nested-inherit"))
        archive = {r.path: r for r in plan.rules}["/premium/archive/"]
        self.assertEqual(archive.policy["train-ai"], "deny")
        self.assertEqual(archive.policy["ai-input"], "deny")
        self.assertEqual(archive.policy["search"], "deny")
        self.assertIn('"location": "/premium/archive/",\n    "tdm-reservation": 1', compile_mod.compile_tdmrep(plan)["tdmrep.json"])

    def test_search_deny_everywhere_and_empty_defaults(self):
        self.assertEqual(compile_mod.compile_x_robots_tag(fixture("search-deny-everywhere")), "X-Robots-Tag: noindex, nofollow")
        out = compile_mod.compile_all(fixture("empty-defaults"), list(compile_mod.COMPILERS))
        self.assertIn("nothing to declare", out["tdmrep-headers.txt"])
        self.assertNotIn("aipref-header.txt", out)
        self.assertNotIn("content-signal.txt", out)

    def test_grounding_note_per_path(self):
        robots = compile_mod.compile_robots_txt(fixture("grounding-path"))
        self.assertIn("Gemini grounding stays open", robots)
        self.assertIn("/premium/", [w for w in compile_mod.WARNINGS if "grounding" in w][0])
        compile_mod.compile_robots_txt(fixture("grounding-inherit"))
        note = [w for w in compile_mod.WARNINGS if "grounding" in w][0]
        self.assertIn("/blog/premium/", note)      # charge -> unknown inherits the parent's allow: open
        self.assertNotIn("/p/q/", note)            # unknown inherits the parent's deny: closed

    def test_x_robots_lists_nested_exceptions(self):
        out = compile_mod.compile_x_robots_tag(fixture("search-nested"))
        self.assertIn("/account/help/: no noindex", out)
        self.assertIn("/account/: X-Robots-Tag: noindex, nofollow", out)
        out = compile_mod.compile_x_robots_tag(fixture("search-deny-allow-deny"))
        self.assertIn("/blog/drafts/: X-Robots-Tag: noindex, nofollow", out)
        self.assertIn("/blog/: no noindex", out)
        self.assertIn("/: X-Robots-Tag: noindex, nofollow", out)

    def test_nosnippet_and_grounding_note(self):
        m = fixture("verbatim-nosnippet")
        self.assertIn("X-Robots-Tag: nosnippet", compile_mod.compile_x_robots_tag(m))
        self.assertIn("Gemini grounding", compile_mod.compile_robots_txt(m))


class PathTests(unittest.TestCase):
    def test_glob_lowering(self):
        tp = compile_mod.to_robots_paths
        for glob, lowered in (("/docs/*", "/docs/"), ("/docs/**", "/docs/"), ("/*.pdf$", "/*.pdf$"),
                              ("/about", "/about"), ("/drafts*", "/drafts*"), ("/", "/")):
            self.assertEqual(tp(glob), [lowered])
        self.assertEqual(tp("/**/*.pdf"), ["/*.pdf", "/*/*.pdf"])
        self.assertEqual(tp("/docs/**/secret"), ["/docs/secret", "/docs/*/secret"])
        self.assertEqual(tp("/docs/**/public/*"), ["/docs/public/", "/docs/*/public/"])
        self.assertEqual(tp("/**/**"), ["/", "/*/"])
        self.assertEqual(tp("/x/**/**/y/*"), ["/x/y/", "/x/*/y/"])   # repeated '/**/' collapses
        with self.assertRaises(compile_mod.CompileError):
            tp("/a/**/b/**/c/**/d/**/e/**/f")
        for bad in ("press/*", "", None, "/a b", "/x#y", "/img?.png", "/[ab]/", "/a$/b"):
            with self.assertRaises(compile_mod.CompileError):
                tp(bad)

    def test_tie_order_matches_rfc(self):
        robots = compile_mod.compile_robots_txt(fixture("tie-order"))
        group = robots.split("User-Agent: GPTBot")[1]
        self.assertLess(group.index("Allow: /docs/"), group.index("Disallow: /*.pdf"))
        entries = json.loads(compile_mod.compile_tdmrep(fixture("tie-order"))["tdmrep.json"])
        self.assertEqual([e["location"] for e in entries[:2]], ["/docs/", "/*.pdf"])

    def test_most_specific_line_first(self):
        robots = compile_mod.compile_robots_txt(fixture("nested"))
        group = robots.split("User-Agent: GPTBot")[1]
        self.assertLess(group.index("Disallow: /docs/private/"), group.index("Allow: /docs/"))
        self.assertLess(group.index("Allow: /docs/"), group.index("Disallow: /\n"))


class ValidatorTests(unittest.TestCase):
    def test_invalid_fixtures(self):
        for name, needle in (("typo-invalid", "alow"), ("nopath-invalid", "path"), ("badglob-invalid", "brackets"),
                             ("newline-invalid", "control characters"), ("tier-conflict-invalid", "different states")):
            with self.subTest(name=name):
                errors, _ = validate_mod.validate(fixture(name))
                self.assertTrue(any(needle in e for e in errors), (name, errors))

    def test_warnings(self):
        m = fixture("minimal")
        m["defaults"]["experimental"]["trian-genai"] = {"state": "deny"}
        m["defaults"]["experimental"]["x-custom"] = {"state": "deny"}
        errors, warnings = validate_mod.validate(m)
        self.assertEqual(errors, [])
        self.assertTrue(any("trian-genai" in w for w in warnings))
        self.assertFalse(any("x-custom" in w for w in warnings))

    def test_path_grammar_and_endpoint_checks(self):
        for bad in ("press/*", "/a b", "/x#y", "/img?.png", "/[ab]/", "/a$/b", "/n\x85l"):
            m = fixture("minimal")
            m["rules"] = [{"match": {"path": bad}, "standard": {"train-ai": {"state": "deny"}}}]
            self.assertTrue(validate_mod.validate(m)[0], bad)
        for bad_url in ("ftp://x.example/p", "https://x.example/p\" onload=\"x", "https://x.example/a b"):
            m = fixture("minimal")
            m["endpoints"] = {"tdm_policy": bad_url}
            self.assertTrue(validate_mod.validate(m)[0], bad_url)
        m = fixture("minimal")
        m["publisher"]["name"] = "Acme\x85User-Agent: *"
        self.assertTrue(validate_mod.validate(m)[0])

    def test_malformed_shapes_do_not_crash(self):
        ok = {"version": "0.1", "publisher": {"name": "x", "contact": "y"}, "defaults": {"standard": {"search": {"state": "allow"}}}}
        singles = [
            (("publisher", "jurisdictions"), [1]),
            (("defaults", "fallbacks"), {"unexpressible_state": []}),
            (("defaults", "standard", "search"), {"state": "conditional", "conditions": None}),
            (("defaults", "standard", "search"), {"state": "conditional", "conditions": {"identity": []}}),
        ]
        for keys, value in singles:
            m = json.loads(json.dumps(ok))
            d = m
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = value
            errors, _ = validate_mod.validate(m)
            self.assertEqual(len(errors), 1, (keys, errors))
        m = json.loads(json.dumps(ok))
        m["rules"] = [{"match": {"path": "/a\x01b"}, "standard": {"train-ai": {"state": "deny"}}}]
        self.assertTrue(validate_mod.validate(m)[0])
        for broken in ({"version": "0.1", "publisher": {"name": "x", "contact": "y", "url": 5}, "defaults": None},
                       {"version": "0.1", "publisher": {"name": "x", "contact": "y"}, "defaults": {"standard": None}},
                       {"version": "0.1", "publisher": {"name": "x", "contact": "y"}, "defaults": [], "rules": ["oops"]},
                       {"version": "0.1", "publisher": {"name": "x", "contact": "y"}, "defaults": {"standard": {"search": {"state": ["deny"]}}}, "interop": {"emit": [["robots-txt"]]}}):
            errors, _ = validate_mod.validate(broken)
            self.assertTrue(errors)


class EvaluatorTests(unittest.TestCase):
    """robots_eval must follow RFC 9309 2.2.2 and Google's documented precedence examples."""
    def test_precedence(self):
        txt = "User-Agent: *\nAllow: /p\nDisallow: /\n\nUser-Agent: Bot\nAllow: /$\nDisallow: /\n\nUser-Agent: Other\nAllow: /folder\nDisallow: /folder\nAllow: /*.htm\nDisallow: /page\n"
        f = robots_eval.can_fetch
        self.assertTrue(f(txt, "Googlebot", "/page"))          # /p (longest) allows
        self.assertFalse(f(txt, "Googlebot", "/x"))
        self.assertTrue(f(txt, "bot", "/"))                    # case-insensitive token, '$' anchor
        self.assertFalse(f(txt, "Bot", "/page.htm"))
        self.assertTrue(f(txt, "Other", "/folder/page"))       # equal length: Allow wins
        self.assertTrue(f(txt, "Other", "/page.htm"))          # /*.htm (6) beats /page (5)
        self.assertFalse(f(txt, "Other", "/pages"))
        self.assertTrue(f("User-Agent: *\nDisallow:\n", "Any", "/x"))   # empty Disallow allows


class CliTests(unittest.TestCase):
    def run_compile(self, *args):
        return subprocess.run([sys.executable, "-I", COMPILE_PY, *args], capture_output=True, text=True)

    def run_compile_json(self, manifest, *args):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manifest.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            return self.run_compile(path, *args)

    def test_invalid_manifest_refused(self):
        path = os.path.join(MANIFESTS, "typo-invalid.json")
        r = self.run_compile(path)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("noindex", r.stdout)
        self.assertIn("alow", r.stderr)
        self.assertEqual(self.run_compile(path, "--force").returncode, 3)

    def test_unsupported_matcher_drops_the_allow_and_warns_once(self):
        r = self.run_compile(os.path.join(MANIFESTS, "hostname-matcher.json"), "--emit", "robots-txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Allow: /members/", r.stdout)
        self.assertEqual(r.stderr.count("only denies are kept"), 1, r.stderr)

    def test_warnings_printed_on_compile_error(self):
        m = fixture("dup-path-merge")
        m["defaults"]["standard"]["search"] = {"state": "alow"}
        r = self.run_compile_json(m, "--force", "--emit", "robots-txt")
        self.assertEqual(r.returncode, 3)
        self.assertIn("merged, later values win", r.stderr)

    def test_force_on_malformed_shape(self):
        m = {"version": "0.1", "publisher": {"name": "x", "contact": "y"}, "defaults": {"standard": None}}
        r = self.run_compile_json(m, "--force", "--emit", "all")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_emit_target(self):
        r = self.run_compile(os.path.join(ROOT, "examples", "minimal.json"), "--emit", "robot-txt")
        self.assertEqual(r.returncode, 3)
        self.assertIn("robot-txt", r.stderr)

    def test_validator_takes_several_files(self):
        paths = [p for _, p in manifests()]
        r = subprocess.run([sys.executable, "-I", VALIDATE_PY] + paths, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout.count("RESULT: VALID"), len(paths))


if __name__ == "__main__":
    unittest.main()
