"""Tests for scanner/scan.py: RFC 9309 group parsing, TDMRep and Content-Signal
detection, and a scan of the compiler's own output served from a local HTTP server.

    python -m unittest discover -s tests -v
"""
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_PY = os.path.join(ROOT, "scanner", "scan.py")
BASE = "https://example.test"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan = _load("consent_scan", SCAN_PY)
compile_mod = _load("consent_compile", os.path.join(ROOT, "compiler", "compile.py"))

with mock.patch.object(scan, "fetch", return_value=(404, {}, "")):
    NO_ROBOTS = scan.scan_robots_txt(BASE)
    NO_MANIFEST = scan.scan_consent_manifest(BASE)

COMPILED_STYLE = """\
# Generated from consent-manifest.json
User-Agent: *
Content-Signal: search=yes, ai-input=no, ai-train=no
Content-Usage: train-ai=n, search=y
Allow: /

User-Agent: GPTBot
User-Agent: claudebot
User-Agent: Google-Extended
Disallow: /

User-Agent: ChatGPT-User
Allow: /press-releases/
Disallow: /premium/
Disallow: /
"""

TDMREP_JSON = json.dumps([{"location": "/", "tdm-reservation": 1, "tdm-policy": BASE + "/tdm"}])


def robots_from(text):
    with mock.patch.object(scan, "fetch", return_value=(200, {}, text)):
        return scan.scan_robots_txt(BASE)


def site(pages):
    """Stub fetch with {url: (status, headers, body)} and a 404 everywhere else."""
    return mock.patch.object(scan, "fetch", side_effect=lambda url, timeout=10: pages.get(url, (404, {}, "")))


class RobotsTests(unittest.TestCase):
    def test_consecutive_user_agent_lines_share_one_group(self):
        r = robots_from(COMPILED_STYLE)
        self.assertEqual(r["bots_blocked"], ["GPTBot", "ClaudeBot", "Google-Extended", "ChatGPT-User"])
        self.assertIn("PerplexityBot", r["bots_allowed"])  # falls to the * group
        self.assertEqual(r["bots_unmentioned"], [])
        self.assertTrue(r["has_google_extended"])

    def test_tokens_match_case_insensitively(self):
        r = robots_from("user-agent: gptbot\ndisallow: /\n")
        self.assertEqual(r["bots_blocked"], ["GPTBot"])
        self.assertIn("ClaudeBot", r["bots_unmentioned"])  # no * group to fall back on

    def test_allow_wins_a_tie_at_the_root(self):
        r = robots_from("User-Agent: GPTBot\nDisallow: /\nAllow: /\n")
        self.assertEqual(r["bots_allowed"], ["GPTBot"])

    def test_content_signal_and_aipref_lines(self):
        r = robots_from(COMPILED_STYLE)
        self.assertEqual(r["content_signal"], "search=yes, ai-input=no, ai-train=no")
        self.assertTrue(r["has_aipref_content_usage"])
        r = robots_from("User-Agent: *\n# Content-Signal: search=yes\nAllow: /\n")
        self.assertIsNone(r["content_signal"])
        self.assertFalse(r["has_aipref_content_usage"])

    def test_missing_robots(self):
        self.assertIs(NO_ROBOTS["found"], False)
        self.assertEqual(NO_ROBOTS["bots_unmentioned"], scan.ALL_AI_BOTS)


class TdmrepTests(unittest.TestCase):
    def test_headers_meta_and_json(self):
        pages = {
            BASE: (200, {"tdm-reservation": "1", "tdm-policy": BASE + "/tdm", "content-signal": "search=yes, ai-train=no"},
                   '<html><head><meta content="1" name="tdm-reservation"></head></html>'),
            BASE + "/.well-known/tdmrep.json": (200, {}, TDMREP_JSON),
        }
        with site(pages):
            h = scan.scan_headers(BASE)
        self.assertEqual(h["tdm_reservation"], "1")
        self.assertEqual(h["tdm_policy"], BASE + "/tdm")
        self.assertEqual(h["tdm_meta"], "1")
        self.assertEqual(h["tdmrep_json"], 1)
        self.assertEqual(h["content_signal"], "search=yes, ai-train=no")
        self.assertIsNone(h["link_tdmrep"])

    def test_tdmrep_json_must_be_a_list_of_rules(self):
        for body in ("not json", '{"tdm-reservation": 1}', '[{"location": "/"}]', "[]"):
            with site({BASE: (200, {}, ""), BASE + "/.well-known/tdmrep.json": (200, {}, body)}):
                self.assertFalse(scan.scan_headers(BASE)["tdmrep_json"], body)

    def test_usage_points_per_signal(self):
        def usage(pages):
            with site(pages):
                h = scan.scan_headers(BASE)
            return scan.score(NO_ROBOTS, h, NO_MANIFEST, {})["usage_declarations"]

        self.assertEqual(usage({BASE: (200, {}, "")}), 0)
        self.assertEqual(usage({BASE: (200, {"tdm-reservation": "0"}, "")}), 15)
        self.assertEqual(usage({BASE: (200, {}, '<meta name="tdm-reservation" content="1">')}), 15)
        self.assertEqual(usage({BASE: (200, {}, ""), BASE + "/.well-known/tdmrep.json": (200, {}, TDMREP_JSON)}), 15)
        self.assertEqual(usage({BASE: (200, {"link": '<' + BASE + '/tdm>; rel="tdm-policy"'}, "")}), 5)
        self.assertEqual(usage({BASE: (200, {"content-signal": "ai-train=no"}, "")}), 10)

    def test_report_names_each_tdmrep_surface(self):
        with site({BASE: (200, {}, "")}):
            h = scan.scan_headers(BASE)
        text = scan.generate_report(BASE, NO_ROBOTS, h, NO_MANIFEST, {}, scan.score(NO_ROBOTS, h, NO_MANIFEST, {}))
        self.assertIn("tdmrep.json:            Not found", text)
        self.assertIn("No TDMRep declaration", text)
        report = json.loads(scan.generate_json_report(BASE, NO_ROBOTS, h, NO_MANIFEST, {}, scan.score(NO_ROBOTS, h, NO_MANIFEST, {})))
        self.assertIs(report["headers"]["tdmrep"], False)
        self.assertIs(report["robots"]["found"], False)


class CompilerOutputTests(unittest.TestCase):
    """The compiler's own output, served the way its files say to deploy them, must scan as present."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "examples", "news-publisher.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        out = compile_mod.compile_all(manifest, list(compile_mod.COMPILERS))
        # Merge the Content-Signal and Content-Usage lines into the 'User-Agent: *' group as instructed.
        extra = dict.fromkeys(line for fn in ("content-signal.txt", "aipref-robots.txt") for line in out[fn].splitlines()
                              if line.lower().startswith(("content-signal:", "content-usage:")))
        robots = out["robots.txt"].replace("User-Agent: *\n", "User-Agent: *\n" + "\n".join(extra) + "\n", 1)
        header_lines = [line for fn in ("aipref-header.txt", "x-robots-tag.txt", "tdmrep-headers.txt", "content-signal.txt")
                        for line in out[fn].splitlines() if line and not line.startswith(("#", "<"))]
        response_headers = [tuple(part.strip() for part in line.split(":", 1)) for line in dict.fromkeys(header_lines)]
        metas = [line for line in out["tdmrep-headers.txt"].splitlines() if line.startswith("<meta")]
        files = {
            "/": "<html><head>" + "".join(metas) + "</head><body>Hello</body></html>",
            "/robots.txt": robots,
            "/.well-known/tdmrep.json": out["tdmrep.json"],
            "/.well-known/consent-manifest.json": json.dumps(manifest),
        }

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files.get(self.path)
                self.send_response(200 if body is not None else 404)
                for name, value in response_headers:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write((body or "").encode("utf-8"))

            def log_message(self, *args):
                pass

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_every_surface_is_seen(self):
        robots = scan.scan_robots_txt(self.base)
        headers = scan.scan_headers(self.base)
        manifest = scan.scan_consent_manifest(self.base)
        for bot in ("GPTBot", "ClaudeBot", "Google-Extended", "ChatGPT-User", "Claude-User"):
            self.assertIn(bot, robots["bots_blocked"])
        self.assertIn("Bingbot", robots["bots_allowed"])
        self.assertEqual(robots["bots_unmentioned"], [])
        self.assertTrue(robots["has_google_extended"])
        self.assertTrue(robots["has_aipref_content_usage"])
        self.assertEqual(robots["content_signal"], "search=yes, ai-train=no")
        self.assertEqual(headers["content_usage"], "train-ai=n, search=y")
        self.assertEqual(headers["content_signal"], "search=yes, ai-train=no")
        self.assertEqual(headers["tdm_reservation"], "1")
        self.assertEqual(headers["tdm_policy"], "https://example.com/tdm/policy.json")
        self.assertEqual(headers["tdm_meta"], "1")
        self.assertEqual(headers["tdmrep_json"], 3)
        self.assertTrue(manifest["found"])
        scores = scan.score(robots, headers, manifest, {})
        self.assertEqual(scores["usage_declarations"], 100)
        self.assertEqual(scores["access_controls"], 100)
        self.assertNotIn("TDMRep", scan.generate_report(self.base, robots, headers, manifest, {}, scores).split("GAPS")[-1])

    def test_cli_json_report(self):
        out = subprocess.run([sys.executable, SCAN_PY, self.base, "--json"], capture_output=True, text=True, check=True).stdout
        report = json.loads(out[out.index("{"):])
        self.assertTrue(report["headers"]["tdmrep"])
        self.assertEqual(report["headers"]["tdmrep_json"], 3)
        self.assertEqual(report["robots"]["content_signal"], "search=yes, ai-train=no")
        self.assertIs(report["robots"]["found"], True)


if __name__ == "__main__":
    unittest.main()
