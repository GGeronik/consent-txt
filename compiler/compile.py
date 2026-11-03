#!/usr/bin/env python3
"""
consent.txt: Consent Manifest Compiler v0.2

Compiles a consent-manifest.json into deployable protocol surfaces:
  - robots.txt user-agent groups (agents from compiler/agents.json)
  - AIPREF Content-Usage HTTP header and robots.txt rules (draft-ietf-aipref-attach)
  - X-Robots-Tag HTTP headers
  - Google-Extended robots.txt block
  - TDMRep: /.well-known/tdmrep.json plus tdm-reservation / tdm-policy headers
  - Cloudflare Content-Signal line and header
  - Human-readable policy summary

Usage:
    python compile.py manifest.json                          # Emit all targets
    python compile.py manifest.json --emit robots-txt        # Emit specific target
    python compile.py manifest.json --emit all --out build/  # Write to directory

Zero external dependencies.
"""

import argparse
import json
import os
import re
import sys
from collections import namedtuple
from itertools import combinations

__version__ = "0.2"

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_FILE = os.path.join(HERE, "agents.json")

# Categories any emitter consumes. Other experimental categories are declarative only.
CATEGORIES = ("train-ai", "train-genai", "search", "ai-input")
TRAIN_CATS = ("train-ai", "train-genai")

WARNINGS = []
_WARNED = set()


class CompileError(Exception):
    """Manifest content the compiler refuses to lower."""


def _warn(msg):
    if msg not in _WARNED:
        _WARNED.add(msg)
        WARNINGS.append(msg)


def _reset_warnings():
    WARNINGS.clear()
    _WARNED.clear()


# ── Agents table ──────────────────────────────────────────────────────────────

def load_agents():
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    by_category = {"train": [], "search": [], "ai-input": []}
    for agent in data["agents"]:
        by_category[agent["category"]].append(agent)
    return data, by_category


AGENTS_DATA, AGENTS = load_agents()


# ── Lowering ──────────────────────────────────────────────────────────────────

def lower_state(state, fallbacks):
    """Lower a rich authoring state to 'allow', 'deny' or None (unknown)."""
    if state in ("allow", "deny"):
        return state
    if state == "unknown":
        return None
    if state in ("charge", "conditional"):
        fb = fallbacks.get("unexpressible_state", "deny")
        return None if fb == "unknown" else fb
    raise CompileError(f"unknown policy state {state!r}")


def get_fallbacks(manifest):
    defaults = manifest.get("defaults") if isinstance(manifest.get("defaults"), dict) else {}
    fb = defaults.get("fallbacks")
    return fb if isinstance(fb, dict) else {"unexpressible_state": "deny", "unknown_identity": "deny"}


def _raw_states(block):
    """{category: state} for every category a defaults or rule block declares."""
    out = {}
    if not isinstance(block, dict):
        return out
    for tier in ("standard", "experimental"):
        tier_block = block.get(tier)
        if not isinstance(tier_block, dict):
            continue
        for cat, val in tier_block.items():
            if isinstance(val, dict) and val.get("state", "unknown") != "unknown":
                out.setdefault(cat, val["state"])  # standard wins over experimental, and unknown declares nothing
    return out


def training_decision(policy):
    """'deny' if either training category denies, else 'allow' if either allows, else None."""
    states = (policy["train-ai"], policy["train-genai"])
    if "deny" in states:
        return "deny"
    if "allow" in states:
        return "allow"
    return None


# ── Paths ─────────────────────────────────────────────────────────────────────

_BAD_PATH_CHARS = re.compile(r"[\s#?\[\]]")
MAX_DOUBLESTAR = 4  # each '/**/' doubles the number of lowered patterns


def to_robots_paths(pattern):
    """Lower a manifest path glob to RFC 9309 patterns: '/x/*' and '/x/**' become '/x/', and a
    middle '/**/' becomes two patterns, one without the segment and one with '/*/'."""
    # validate.py explains a bad path. This only stops --force from writing one into robots.txt.
    if (not isinstance(pattern, str) or not pattern.startswith("/") or _BAD_PATH_CHARS.search(pattern)
            or "$" in pattern[:-1]):
        raise CompileError(f"rule path is not a valid RFC 9309 pattern: {pattern!r}")
    pattern = re.sub(r"(/\*\*)+/", "/**/", pattern)
    if pattern.count("/**/") > MAX_DOUBLESTAR:
        raise CompileError(f"rule path has more than {MAX_DOUBLESTAR} '/**/' segments: {pattern!r}")
    variants = [pattern]
    while any("/**/" in v for v in variants):
        expanded = []
        for v in variants:
            if "/**/" in v:
                i = v.index("/**/")
                expanded += [v[:i] + "/" + v[i + 4:], v[:i] + "/*/" + v[i + 4:]]
            else:
                expanded.append(v)
        variants = expanded
    out = []
    for v in variants:
        v = re.sub(r"\*+", "*", v)
        if v.endswith("/*"):
            v = v[:-1]
        if v not in out:
            out.append(v)
    return out


# ── Plan ──────────────────────────────────────────────────────────────────────

# mentioned: the categories this rule or an enclosing one names. declared: those that lower
# to allow or deny, the only ones emitted per path.
Rule = namedtuple("Rule", "path raw policy declared mentioned")


def _is_prefix(path):
    return "*" not in path and "$" not in path


class Plan:
    """The manifest resolved once (spec 6.6): `default` and one Rule per lowered path,
    each policy mapping CATEGORIES to 'allow', 'deny' or None."""

    def __init__(self, manifest):
        _reset_warnings()  # shortcut: one plan per process, give Plan its own list if two must coexist
        self.manifest = manifest
        self.fallbacks = get_fallbacks(manifest)
        defaults_raw = _raw_states(manifest.get("defaults", {}))

        own = {}  # lowered path -> raw states, in manifest order
        for i, rule in enumerate(manifest.get("rules", [])):
            match = rule.get("match", {}) if isinstance(rule, dict) else {}
            if not match.get("path"):
                raise CompileError(f"rules[{i}]: match.path is required (other matchers are not compiled)")
            raw = _raw_states(rule)
            unsupported = sorted(k for k in match if k != "path")
            if unsupported:
                raw = self._denies_only(raw, i, unsupported)
            for path in to_robots_paths(match["path"]):
                if path == "/":
                    _warn(f"rules[{i}]: a rule on '/' covers the whole site, so it is merged into the defaults")
                    defaults_raw.update(raw)
                elif path in own:
                    if not unsupported:
                        _warn(f"rules[{i}]: path {path!r} is already used by an earlier rule "
                              f"(merged, later values win per category)")
                    own[path].update(raw)
                else:
                    own[path] = dict(raw)

        self.default_raw = defaults_raw
        self.default = {cat: lower_state(defaults_raw.get(cat, "unknown"), self.fallbacks) for cat in CATEGORIES}

        resolved = {}
        for path in sorted(own, key=len):  # parents before children
            parents = [p for p in resolved if path.startswith(p) and _is_prefix(p)]
            base = resolved[max(parents, key=len)] if parents else None
            own_low = {cat: lower_state(state, self.fallbacks) for cat, state in own[path].items()}
            declared_own = {cat for cat, low in own_low.items() if low is not None}
            inherited = base.policy if base else self.default
            policy = {cat: own_low[cat] if cat in declared_own else inherited[cat] for cat in CATEGORIES}
            declared = declared_own | (base.declared if base else set())
            mentioned = set(own[path]) | (base.mentioned if base else set())
            raw = dict(base.raw if base else defaults_raw, **own[path])
            for cat in CATEGORIES:
                if cat in own[path] and own_low[cat] is None and policy[cat] is not None:
                    _warn(f"rule {path!r}: {cat} lowers to unknown, so the enclosing value ({policy[cat]}) applies there")
            resolved[path] = Rule(path, raw, policy, declared, mentioned)
        self.rules = [resolved[p] for p in own]
        self._warn_ties()

    def _denies_only(self, raw, i, unsupported):
        """The deny decisions of a rule whose matchers no target compiles."""
        matchers = ", ".join(unsupported)
        kept = {}
        for cat, state in raw.items():
            if lower_state(state, self.fallbacks) == "deny":
                kept[cat] = state
            else:
                _warn(f"rules[{i}].{cat}: {state!r} ignored, since no target compiles matcher(s) {matchers} "
                      f"and the decision could relax the policy on part of the path (only denies are kept)")
        return kept

    def _warn_ties(self):
        """Equal-length patterns with different decisions. Crawlers resolve the tie as allow
        while AIPREF takes the most restrictive value, so the surfaces can differ. Two plain
        prefixes of equal length cannot match the same URL and are skipped."""
        for cat in CATEGORIES:
            by_len = {}
            for r in self.rules:
                if cat in r.declared and r.policy[cat]:
                    by_len.setdefault(len(r.path), []).append((r.path, r.policy[cat]))
            for group in by_len.values():
                for (p1, d1), (p2, d2) in combinations(group, 2):
                    if d1 != d2 and not (_is_prefix(p1) and _is_prefix(p2)):
                        _warn(f"rules {p1!r} and {p2!r} have equal length and different {cat} decisions. "
                              f"On a URL both match, robots.txt and TDMRep resolve the tie as allow while "
                              f"AIPREF takes the most restrictive value")

    def declaring(self, cats):
        """Rules that declare (or inherit from an enclosing rule) any of `cats`."""
        return [r for r in self.rules if r.declared & set(cats)]

    def sitewide(self, decide, cats):
        """(decision, overrides) for a site-wide surface: the default's decision, or None if a rule overrides it."""
        d = decide(self.default)
        overrides = [(r.path, decide(r.policy)) for r in self.declaring(cats) if decide(r.policy) != d]
        return (None if overrides else d), overrides


def _plan(x):
    return x if isinstance(x, Plan) else Plan(x)


def _by_specificity(items):
    """(path, decision) pairs, most specific pattern first and Allow before Disallow on
    equal length, so first-match and longest-match parsers agree with RFC 9309."""
    return sorted(items, key=lambda pd: (-len(pd[0]), pd[1] != "allow", pd[0]))


# ── robots.txt ────────────────────────────────────────────────────────────────

_DIRECTIVE = {"allow": "Allow", "deny": "Disallow"}


def _group_lines(plan, tokens, decide, cats):
    """Lines for one user-agent group, or [] when nothing is restricted."""
    default = decide(plan.default)
    per_path = [(r.path, decide(r.policy)) for r in plan.declaring(cats)]
    if default != "deny" and not any(d == "deny" for _, d in per_path):
        return []
    lines = [f"User-Agent: {t}" for t in tokens]
    lines += [f"{_DIRECTIVE[d]}: {path}" for path, d in _by_specificity(per_path) if d]
    if default == "deny":
        lines.append("Disallow: /")
    lines.append("")
    return lines


def compile_robots_txt(plan):
    """Compile manifest into robots.txt user-agent groups."""
    plan = _plan(plan)
    pub = plan.manifest.get("publisher", {})
    lines = [
        "# robots.txt",
        f"# Generated from consent-manifest.json by consent.txt compiler v{__version__}",
        f"# Agents table: {AGENTS_DATA['updated']}",
        f"# Publisher: {pub.get('name', 'Unknown')}",
        "",
        "User-Agent: *",
    ]
    # Under a search-deny default noindex carries the policy, and a Disallow would stop crawlers reading it.
    search_paths = [(r.path, r.policy["search"]) for r in plan.declaring(("search",))]
    if plan.default["search"] != "deny" and any(d == "deny" for _, d in search_paths):
        lines += [f"{_DIRECTIVE[d]}: {path}" for path, d in _by_specificity(search_paths) if d]
    lines.append("Allow: /")
    lines.append("")

    if training_decision(plan.default) == "deny" and plan.default["ai-input"] == "allow":
        lines.append("# Note: Google-Extended also governs Gemini grounding, and Google has no separate ai-input token.")
    open_grounding = [path for path, policy in [("/", plan.default)] + [(r.path, r.policy) for r in plan.rules]
                      if policy["ai-input"] == "deny" and training_decision(policy) != "deny"]
    if open_grounding:
        note = (f"Gemini grounding stays open on {', '.join(open_grounding)}: ai-input is denied there but "
                f"training is not, and Google-Extended controls both")
        _warn(note)
        lines.append(f"# Note: {note}.")
    lines += _group_lines(plan, [a["token"] for a in AGENTS["train"]], training_decision, TRAIN_CATS)

    ai_group = _group_lines(plan, [a["token"] for a in AGENTS["ai-input"]], lambda p: p["ai-input"], ("ai-input",))
    if ai_group:
        lines.append("# User-triggered fetchers: several operators say robots.txt may not apply to these.")
        lines += ai_group

    pub_url = pub.get("url", "")
    if pub_url:
        lines.append(f"Sitemap: {pub_url.rstrip('/')}/sitemap.xml")
        lines.append("")
    return "\n".join(lines)


def compile_google_extended(plan):
    """Google-Extended block alone, for sites that do not use the generated robots.txt."""
    return "\n".join(_group_lines(_plan(plan), ["Google-Extended"], training_decision, TRAIN_CATS))


# ── AIPREF ────────────────────────────────────────────────────────────────────

def _yn(decision):
    return {"allow": "y", "deny": "n"}.get(decision)


_AIPREF_LABELS = (("train-ai", training_decision, TRAIN_CATS), ("search", lambda p: p["search"], ("search",)))
_AIPREF_CATS = TRAIN_CATS + ("search",)


def _content_usage(policy):
    """RFC 9651 dictionary value with the labels that lower to y or n."""
    parts = [f"{label}={_yn(decide(policy))}" for label, decide, _ in _AIPREF_LABELS if _yn(decide(policy))]
    return ", ".join(parts)


def compile_aipref_header(plan):
    """AIPREF Content-Usage HTTP header (draft-ietf-aipref-attach, RFC 9651 dictionary).
    Site-wide: labels that a rule overrides are omitted and listed as comments."""
    plan = _plan(plan)
    parts, notes = [], []
    for label, decide, cats in _AIPREF_LABELS:
        d, overrides = plan.sitewide(decide, cats)
        if _yn(d):
            parts.append(f"{label}={_yn(d)}")
        elif overrides:
            notes.append(f"# {label} omitted because the default is {_yn(decide(plan.default)) or 'unknown'} but "
                         + ", ".join(f"{p} is {_yn(v) or 'unknown'}" for p, v in overrides)
                         + " (see aipref-robots.txt for per-path values)")
    out = []
    if parts:
        out.append("Content-Usage: " + ", ".join(parts))
    out += notes
    return "\n".join(out)


def compile_aipref_robots(plan):
    """AIPREF Content-Usage rules for the robots.txt 'User-Agent: *' group."""
    plan = _plan(plan)
    body = []
    default = _content_usage(plan.default)
    if default:
        body.append(f"Content-Usage: {default}")
    # attach-05 applies the single longest matching rule, so each line carries every
    # label the policy knows at that path, inherited ones included.
    for r in sorted(plan.declaring(_AIPREF_CATS),
                    key=lambda r: (-len(r.path), training_decision(r.policy) != "allow", r.path)):
        value = _content_usage(r.policy)
        if value:
            body.append(f"Content-Usage: {r.path} {value}")
    if not body:
        return ""
    return "\n".join([
        "# AIPREF Content-Usage rules for robots.txt (draft-ietf-aipref-attach)",
        "# Generated from consent-manifest.json. Merge these lines into the 'User-Agent: *' group.",
        "",
        "User-Agent: *",
    ] + body + [""])


# ── X-Robots-Tag ──────────────────────────────────────────────────────────────

def compile_x_robots_tag(plan):
    """X-Robots-Tag header values. The header is site-wide, so per-path differences are listed as comments."""
    plan = _plan(plan)
    tags = []
    search, overrides = plan.sitewide(lambda p: p["search"], ("search",))
    if search == "deny":
        return "X-Robots-Tag: noindex, nofollow"
    if overrides:
        tags.append("# search differs by path, so set the header per path (the longest matching path wins):")
        rows = _by_specificity([(r.path, r.policy["search"]) for r in plan.declaring(("search",))
                                if r.policy["search"]]) + [("/", plan.default["search"])]
        for path, v in rows:
            label = {"deny": "X-Robots-Tag: noindex, nofollow", "allow": "no noindex"}.get(v, "unknown, no header")
            if v == "deny" and path != "/" and plan.default["search"] != "deny":
                label += " (robots.txt disallows this path, so crawlers never read the header)"
            tags.append(f"#   {path}: {label}")

    defaults = plan.manifest.get("defaults", {})
    ai_input = (defaults.get("standard") or {}).get("ai-input") or (defaults.get("experimental") or {}).get("ai-input") or {}
    conditions = ai_input.get("conditions") if isinstance(ai_input, dict) else None
    conditions = conditions if isinstance(conditions, dict) else {}
    max_chars = conditions.get("max_excerpt_chars")
    if isinstance(max_chars, int):
        tags.append(f"X-Robots-Tag: max-snippet:{max_chars}")
    if conditions.get("verbatim_allowed") is False:
        tags.append("X-Robots-Tag: nosnippet")
    if training_decision(plan.default) == "deny":
        tags.append("X-Robots-Tag: googlebot: noai, noimageai")
    return "\n".join(tags)


# ── TDMRep ────────────────────────────────────────────────────────────────────

def _reservation(raw, policy):
    """TDMRep can express 'reserved, see the policy', so charge and conditional are 1."""
    if any(raw.get(cat) in ("charge", "conditional") for cat in TRAIN_CATS):
        return 1
    return {"deny": 1, "allow": 0}.get(training_decision(policy))


def compile_tdmrep(plan):
    """TDMRep (W3C CG Final Report 2024-05-10): tdmrep.json, plus headers and <meta> tags
    when the whole site shares one value."""
    plan = _plan(plan)
    policy_url = plan.manifest.get("endpoints", {}).get("tdm_policy", "")

    entries = []
    for r in plan.rules:
        if not (r.mentioned & set(TRAIN_CATS)):
            continue  # nothing declared about training here: the enclosing entry applies
        res = _reservation(r.raw, r.policy)
        if res is not None:
            entries.append({"location": r.path, "tdm-reservation": res})
    entries.sort(key=lambda e: (-len(e["location"]), e["tdm-reservation"]))  # most specific first, ties as in RFC 9309
    default_r = _reservation(plan.default_raw, plan.default)
    if default_r is not None:
        entries.append({"location": "/", "tdm-reservation": default_r})
    if policy_url:
        for e in entries:
            if e["tdm-reservation"] == 1:
                e["tdm-policy"] = policy_url
    else:
        for path, raw, policy in [("/", plan.default_raw, plan.default)] + [(r.path, r.raw, r.policy) for r in plan.rules]:
            if _reservation(raw, policy) == 1 and training_decision(policy) == "allow":
                _warn(f"{path}: TDMRep reserves charge/conditional training that the other surfaces allow, "
                      f"and without endpoints.tdm_policy TDM agents cannot find the terms")
    if not entries:
        return {"tdmrep-headers.txt": "# TDMRep: the training preference is unknown everywhere, so there is nothing to declare.\n"}

    uniform = default_r is not None and all(e["tdm-reservation"] == default_r for e in entries)
    headers = ["# TDMRep HTTP response headers (W3C TDMRep CG Final Report, section 6.2)."]
    if uniform:
        headers.append(f"tdm-reservation: {default_r}")
        if default_r == 1 and policy_url:
            headers.append(f"tdm-policy: {policy_url}")
        headers += ["", "# HTML <head> equivalent (section 6.3):",
                    f'<meta name="tdm-reservation" content="{default_r}">']
        if default_r == 1 and policy_url:
            headers.append(f'<meta name="tdm-policy" content="{policy_url}">')
    else:
        headers += [
            "# Per-path reservations differ, and headers or <meta> tags supersede the file (section 6.7).",
            "# Serve only /.well-known/tdmrep.json, or set these headers per path:",
        ] + [f"#   {e['location']}: tdm-reservation: {e['tdm-reservation']}" for e in entries]
    return {
        "tdmrep.json": json.dumps(entries, indent=2) + "\n",
        "tdmrep-headers.txt": "\n".join(headers) + "\n",
    }


# ── Content-Signal ────────────────────────────────────────────────────────────

_CONTENT_SIGNAL_LABELS = (("search", lambda p: p["search"], ("search",)),
                          ("ai-input", lambda p: p["ai-input"], ("ai-input",)),
                          ("ai-train", training_decision, TRAIN_CATS))


def compile_content_signal(plan):
    """Cloudflare Content Signals line (robots.txt) and header. Site-wide: labels that a
    rule overrides are omitted and listed as comments."""
    plan = _plan(plan)
    yesno = {"allow": "yes", "deny": "no"}
    parts, notes = [], []
    for label, decide, cats in _CONTENT_SIGNAL_LABELS:
        d, overrides = plan.sitewide(decide, cats)
        if d in yesno:
            parts.append(f"{label}={yesno[d]}")
        elif overrides:
            notes.append(f"# {label} omitted because the default is {yesno.get(decide(plan.default), 'unknown')} but "
                         + ", ".join(f"{p} is {yesno.get(v, 'unknown')}" for p, v in overrides))
    if not parts and not notes:
        return ""
    out = ["# Content Signals (contentsignals.org) apply to the whole site, so labels that a path rule overrides are left out."]
    out += notes
    if parts:
        value = ", ".join(parts)
        out += ["# robots.txt: add this line inside the 'User-Agent: *' group.",
                f"Content-Signal: {value}",
                "",
                "# HTTP response header with the same value (Cloudflare's Markdown for Agents keeps an origin header):",
                f"Content-Signal: {value}"]
    out.append("")
    return "\n".join(out)


# ── Summary ───────────────────────────────────────────────────────────────────

def compile_summary(plan):
    """Compile a human-readable policy summary."""
    manifest = _plan(plan).manifest
    pub = manifest.get("publisher", {})
    defaults = manifest.get("defaults", {})
    defaults = defaults if isinstance(defaults, dict) else {}
    std = defaults.get("standard") if isinstance(defaults.get("standard"), dict) else {}
    exp = defaults.get("experimental") if isinstance(defaults.get("experimental"), dict) else {}
    fallbacks = get_fallbacks(manifest)

    lines = [
        "=" * 60,
        f"  AI Content Policy — {pub.get('name', 'Unknown')}",
        "=" * 60,
        "",
        f"  Site:          {pub.get('url', 'N/A')}",
        f"  Contact:       {pub.get('contact', 'N/A')}",
        f"  Jurisdictions: {', '.join(map(str, pub.get('jurisdictions') or [])) or 'N/A'}",
        f"  Terms:         {pub.get('terms_url', 'N/A')}",
        "",
        "  Standard (AIPREF-aligned):",
    ]

    state_icons = {"allow": "✓", "deny": "✗", "charge": "$", "conditional": "?", "unknown": "—"}

    def _format_policy(cat, val):
        if not isinstance(val, dict):
            return None
        state = val.get("state", "unknown")
        icon = state_icons.get(state, "?")
        line = f"    {icon} {cat}: {state}"
        cond = val.get("conditions", {})
        if cond:
            cond_parts = []
            if cond.get("citation_required"): cond_parts.append("citation")
            if cond.get("link_required"): cond_parts.append("link-back")
            if cond.get("attribution_required"): cond_parts.append("attribution")
            if cond.get("identity"): cond_parts.append(f"identity={cond['identity']}")
            if cond.get("max_excerpt_chars"): cond_parts.append(f"max {cond['max_excerpt_chars']} chars")
            if cond.get("max_tokens"): cond_parts.append(f"max {cond['max_tokens']} tokens")
            if cond.get("rate_limit_per_day"): cond_parts.append(f"{cond['rate_limit_per_day']}/day")
            if cond.get("payment_plan"): cond_parts.append(f"plan={cond['payment_plan']}")
            if cond_parts:
                line += f" ({', '.join(cond_parts)})"
        return line

    for cat, val in std.items():
        formatted = _format_policy(cat, val)
        if formatted:
            lines.append(formatted)

    if exp:
        lines.append("")
        lines.append("  Extended (project-defined):")
        for cat, val in exp.items():
            formatted = _format_policy(cat, val)
            if formatted:
                lines.append(formatted)

    rules = manifest.get("rules", [])
    if rules:
        lines.append("")
        lines.append(f"  Path Rules ({len(rules)}):")
        for rule in rules:
            path = rule["match"]["path"]  # Plan has already refused rules without one
            parts = []
            for tier in ("standard", "experimental"):
                tier_block = rule.get(tier)
                for cat, val in (tier_block.items() if isinstance(tier_block, dict) else []):
                    if isinstance(val, dict):
                        parts.append(f"{cat}={val.get('state', '?')}")
            lines.append(f"    {path} → {', '.join(parts) if parts else 'no overrides'}")

    lines.append("")
    lines.append("  Fallback Behavior:")
    lines.append(f"    Unexpressible states → {fallbacks.get('unexpressible_state', 'deny')}")
    lines.append(f"    Unknown identity     → {fallbacks.get('unknown_identity', 'deny')}")

    endpoints = manifest.get("endpoints", {})
    if endpoints:
        lines.append("")
        lines.append("  Endpoints:")
        for key, url in endpoints.items():
            lines.append(f"    {key}: {url}")

    lines.append("")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# target -> (default filename, compiler). A compiler returns a string, or a
# {filename: content} dict when a target produces several files.
COMPILERS = {
    "robots-txt":      ("robots.txt",            compile_robots_txt),
    "aipref-header":   ("aipref-header.txt",     compile_aipref_header),
    "aipref-robots":   ("aipref-robots.txt",     compile_aipref_robots),
    "x-robots-tag":    ("x-robots-tag.txt",      compile_x_robots_tag),
    "google-extended": ("google-extended.txt",   compile_google_extended),
    "tdmrep":          (None,                    compile_tdmrep),
    "content-signal":  ("content-signal.txt",    compile_content_signal),
    "summary":         ("policy-summary.txt",    compile_summary),
}


def compile_all(manifest, targets):
    """{filename: content} for every requested target. Raises CompileError."""
    unknown = [t for t in targets if t not in COMPILERS]
    if unknown:
        raise CompileError(f"unknown emit target(s) {', '.join(unknown)} (valid: {', '.join(COMPILERS)})")
    plan = Plan(manifest)
    outputs = {}
    for target in dict.fromkeys(targets):
        filename, fn = COMPILERS[target]
        result = fn(plan)
        if isinstance(result, dict):
            outputs.update({k: v for k, v in result.items() if v.strip()})
        elif result and result.strip():
            outputs[filename] = result
    return outputs


def _validate(manifest):
    sys.path.insert(0, os.path.join(HERE, "..", "tools"))
    from validate import validate  # tools/validate.py, zero dependencies
    return validate(manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compile a consent-manifest.json into deployable protocol surfaces.",
        epilog="Example: python compile.py manifest.json --emit robots-txt aipref-header",
    )
    parser.add_argument("manifest", help="Path to consent-manifest.json")
    parser.add_argument("--emit", nargs="*", default=["all"],
                        help="Targets to emit. Options: " + ", ".join(list(COMPILERS.keys()) + ["all"]))
    parser.add_argument("--out", default=None, help="Output directory (default: print to stdout)")
    parser.add_argument("--force", action="store_true",
                        help="Compile even if the manifest fails validation")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON — {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Error: File not found — {args.manifest}", file=sys.stderr)
        return 1

    errors, warnings = _validate(manifest)
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        if not args.force:
            print(f"Refusing to compile an invalid manifest ({len(errors)} error(s)). "
                  f"Use --force to override.", file=sys.stderr)
            return 2

    if "all" in args.emit:
        emit_list = [t for t in manifest.get("interop", {}).get("emit", []) if t in COMPILERS] or list(COMPILERS)
        if "summary" not in emit_list:
            emit_list.append("summary")
    else:
        emit_list = args.emit

    try:
        outputs = compile_all(manifest, emit_list)
    except CompileError as e:
        for w in WARNINGS:
            print(f"Warning: {w}", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        return 3
    for w in WARNINGS:
        print(f"Warning: {w}", file=sys.stderr)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for filename, content in outputs.items():
            filepath = os.path.join(args.out, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  Wrote: {filepath}")
        print(f"\n  {len(outputs)} file(s) compiled to {args.out}/")
    else:
        for filename, content in outputs.items():
            print(f"\n{'─' * 60}")
            print(f"  {filename}")
            print(f"{'─' * 60}")
            print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
