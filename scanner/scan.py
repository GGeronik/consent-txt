#!/usr/bin/env python3
"""
consent.txt — AI Policy Scanner v0.1

Scans a domain for AI content access posture:
  - robots.txt AI bot rules (RFC 9309 groups)
  - AIPREF Content-Usage header and robots.txt directives
  - Cloudflare Content-Signal line and header
  - X-Robots-Tag headers
  - TDMRep: tdm-reservation / tdm-policy headers, tdmrep.json and the <meta> tag
  - Google-Extended controls
  - Consent Manifest presence

Produces a scorecard on four axes:
  1. Access Controls
  2. Usage Declarations
  3. Preview Controls
  4. Identity Confidence

Usage:
    python scan.py example.com
    python scan.py https://example.com
    python scan.py example.com --json
    python scan.py example.com --emit-fix

Zero external dependencies.
"""

import json
import os
import sys
import re
import argparse
import urllib.request
import urllib.error
import ssl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robots_eval import can_fetch, groups_for, parse  # noqa: E402

# Disable SSL verification warnings for scanning (many sites have cert issues).
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Known AI bots ─────────────────────────────────────────────────────────────

TRAINING_BOTS = [
    "GPTBot", "ClaudeBot", "CCBot", "Google-Extended", "FacebookBot",
    "Bytespider", "Diffbot", "Omgilibot", "Amazonbot", "cohere-ai",
    "AI2Bot", "Applebot-Extended", "PerplexityBot",
]

SEARCH_BOTS = ["OAI-SearchBot", "Claude-SearchBot", "Bingbot"]

AI_INPUT_BOTS = ["ChatGPT-User", "Claude-User"]

ALL_AI_BOTS = TRAINING_BOTS + SEARCH_BOTS + AI_INPUT_BOTS

# ── HTTP fetcher ──────────────────────────────────────────────────────────────

def fetch(url, timeout=10):
    """Fetch URL and return (status_code, headers_dict, body_text)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "consent-txt-scanner/0.1"})
        resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        body = resp.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, headers, body
    except Exception as e:
        return None, {}, str(e)

# ── Scanners ──────────────────────────────────────────────────────────────────

def _directive(text, name):
    """Value of the first 'name:' line in robots.txt that is not a comment, or None."""
    m = re.search(rf"(?im)^[ \t]*{name}[ \t]*:(.*)$", text)
    return (m.group(1).split("#", 1)[0].strip() or None) if m else None


def scan_robots_txt(base_url):
    """Scan robots.txt for AI bot rules, AIPREF directives and the Content-Signal line."""
    url = base_url.rstrip("/") + "/robots.txt"
    status, headers, body = fetch(url)

    result = {
        "found": status == 200 and bool(body.strip()),
        "url": url,
        "bots_blocked": [],
        "bots_allowed": [],
        "bots_unmentioned": [],
        "has_google_extended": False,
        "has_aipref_content_usage": False,
        "content_signal": None,
        "raw_lines": 0,
    }

    if not result["found"]:
        result["bots_unmentioned"] = ALL_AI_BOTS[:]
        return result

    result["raw_lines"] = len(body.splitlines())
    groups = parse(body)
    for bot in ALL_AI_BOTS:
        if not groups_for(groups, bot):
            result["bots_unmentioned"].append(bot)
        elif can_fetch(body, bot, "/"):
            result["bots_allowed"].append(bot)
        else:
            result["bots_blocked"].append(bot)
    result["has_google_extended"] = any("google-extended" in g["agents"] for g in groups)
    result["has_aipref_content_usage"] = _directive(body, "content-usage") is not None
    result["content_signal"] = _directive(body, "content-signal")
    return result


def scan_headers(base_url):
    """Scan the home page response headers for AI-relevant directives, plus the TDMRep surfaces."""
    status, headers, body = fetch(base_url)

    result = {
        "reachable": status is not None,
        "status": status,
        "content_usage": headers.get("content-usage"),
        "content_signal": headers.get("content-signal"),
        "x_robots_tag": headers.get("x-robots-tag"),
        "consent_manifest_version": headers.get("x-consent-manifest-version"),
    }
    result.update(scan_tdmrep(base_url, headers, body))
    return result


# Any of these means the site declares TDMRep as the W3C protocol defines it.
TDMREP_KEYS = ("tdm_reservation", "tdm_policy", "tdm_meta", "tdmrep_json")


def scan_tdmrep(base_url, headers, body):
    """TDMRep signals: the tdm-reservation and tdm-policy headers (section 6.2), the <meta> tag
    (6.3), /.well-known/tdmrep.json (6.4), and the non-standard Link header older consent.txt
    releases emitted."""
    result = {
        "tdm_reservation": headers.get("tdm-reservation"),
        "tdm_policy": headers.get("tdm-policy"),
        "tdm_meta": None,
        "tdmrep_json": None,
        "link_tdmrep": None,
    }

    tag = re.search(r'<meta\b[^>]*\bname=["\']tdm-reservation["\'][^>]*>', body, re.I)
    content = re.search(r'\bcontent=["\']([^"\']*)', tag.group(0), re.I) if tag else None
    if content:
        result["tdm_meta"] = content.group(1)

    status, _, body = fetch(base_url.rstrip("/") + "/.well-known/tdmrep.json")
    if status == 200:
        try:
            entries = json.loads(body)
        except json.JSONDecodeError:
            entries = None
        if isinstance(entries, list) and all(isinstance(e, dict) and "tdm-reservation" in e for e in entries):
            result["tdmrep_json"] = len(entries)

    link_header = headers.get("link", "")
    if "tdm-policy" in link_header.lower():
        result["link_tdmrep"] = link_header

    return result


def scan_consent_manifest(base_url):
    """Check for consent-manifest.json at well-known path."""
    url = base_url.rstrip("/") + "/.well-known/consent-manifest.json"
    status, headers, body = fetch(url)

    result = {
        "found": False,
        "url": url,
        "version": None,
        "publisher": None,
        "standard_categories": {},
        "experimental_categories": {},
        "has_fallbacks": False,
        "has_endpoints": False,
        "has_interop": False,
        "rules_count": 0,
    }

    if status != 200:
        return result

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return result

    if not isinstance(data, dict) or "version" not in data:
        return result

    result["found"] = True
    result["version"] = data.get("version")
    result["publisher"] = data.get("publisher", {}).get("name")

    defaults = data.get("defaults", {})
    result["has_fallbacks"] = "fallbacks" in defaults

    for cat, val in defaults.get("standard", {}).items():
        if isinstance(val, dict):
            result["standard_categories"][cat] = val.get("state", "unknown")

    for cat, val in defaults.get("experimental", {}).items():
        if isinstance(val, dict):
            result["experimental_categories"][cat] = val.get("state", "unknown")

    result["rules_count"] = len(data.get("rules", []))
    result["has_endpoints"] = bool(data.get("endpoints"))
    result["has_interop"] = bool(data.get("interop", {}).get("emit"))

    return result


def scan_well_known_alt(base_url):
    """Check for other AI policy files (llms.txt, ai.txt)."""
    results = {}
    for path in ["/llms.txt", "/ai.txt", "/.well-known/ai-plugin.json"]:
        url = base_url.rstrip("/") + path
        status, _, body = fetch(url)
        results[path] = status == 200 and len(body.strip()) > 10
    return results

# ── Scoring ───────────────────────────────────────────────────────────────────

def score(robots, headers, manifest, alt_files):
    """Score domain on four axes (0-100 each)."""

    # Axis 1: Access Controls (robots.txt coverage)
    access_score = 0
    total_bots = len(ALL_AI_BOTS)
    mentioned_bots = len(robots["bots_blocked"]) + len(robots["bots_allowed"])
    if robots["found"]:
        access_score += 20  # Has robots.txt
        access_score += min(50, int(50 * mentioned_bots / total_bots))  # Bot coverage
        if robots["has_google_extended"]:
            access_score += 15
        if mentioned_bots >= 10:
            access_score += 15  # Comprehensive

    # Axis 2: Usage Declarations
    usage_score = 0
    if headers.get("content_usage"):
        usage_score += 40  # Has AIPREF header
    if robots.get("has_aipref_content_usage"):
        usage_score += 20  # AIPREF in robots.txt
    if headers.get("content_signal") or robots.get("content_signal"):
        usage_score += 10  # Cloudflare Content Signals
    if manifest["found"]:
        usage_score += 25  # Has consent manifest
        if manifest["has_fallbacks"]:
            usage_score += 10
        if manifest["has_interop"]:
            usage_score += 5
    if any(headers.get(k) for k in TDMREP_KEYS):
        usage_score += 15  # TDMRep headers, tdmrep.json or <meta> tag
    elif headers.get("link_tdmrep"):
        usage_score += 5  # the non-standard Link header older consent.txt releases emitted

    # Axis 3: Preview Controls
    preview_score = 0
    xrt = headers.get("x_robots_tag") or ""
    if "nosnippet" in xrt.lower() or "max-snippet" in xrt.lower():
        preview_score += 40
    if "noai" in xrt.lower() or "noimageai" in xrt.lower():
        preview_score += 30
    if manifest["found"] and any(
        manifest["standard_categories"].get(c) in ("conditional", "charge")
        for c in ("ai-input", "train-ai", "train-genai")
    ):
        preview_score += 30

    # Axis 4: Identity Confidence
    identity_score = 0
    if manifest["found"] and manifest["has_endpoints"]:
        identity_score += 30
    if manifest["found"] and manifest["has_fallbacks"]:
        identity_score += 20
    # Having specific bot rules (not just wildcard) shows intentional identity awareness.
    if mentioned_bots >= 5:
        identity_score += 25
    if mentioned_bots >= 10:
        identity_score += 15
    if headers.get("content_usage"):
        identity_score += 10

    return {
        "access_controls": min(100, access_score),
        "usage_declarations": min(100, usage_score),
        "preview_controls": min(100, preview_score),
        "identity_confidence": min(100, identity_score),
        "overall": min(100, int((access_score + usage_score + preview_score + identity_score) / 4)),
    }

# ── Report generation ─────────────────────────────────────────────────────────

def grade(pct):
    if pct >= 80: return "A"
    if pct >= 60: return "B"
    if pct >= 40: return "C"
    if pct >= 20: return "D"
    return "F"


def generate_report(domain, robots, headers, manifest, alt_files, scores):
    """Generate a human-readable report."""
    lines = []
    ln = lines.append

    ln(f"\n{'='*64}")
    ln(f"  AI Policy Readiness Report — {domain}")
    ln(f"{'='*64}\n")

    overall = scores["overall"]
    ln(f"  Overall Score: {overall}/100  Grade: {grade(overall)}\n")

    ln(f"  ┌──────────────────────────┬───────┬───────┐")
    ln(f"  │ Axis                     │ Score │ Grade │")
    ln(f"  ├──────────────────────────┼───────┼───────┤")
    for axis, key in [
        ("Access Controls", "access_controls"),
        ("Usage Declarations", "usage_declarations"),
        ("Preview Controls", "preview_controls"),
        ("Identity Confidence", "identity_confidence"),
    ]:
        s = scores[key]
        ln(f"  │ {axis:<24s} │ {s:>4d}  │   {grade(s)}   │")
    ln(f"  └──────────────────────────┴───────┴───────┘\n")

    # Detailed findings.
    ln("  ROBOTS.TXT")
    if robots["found"]:
        ln(f"    Found: Yes ({robots['raw_lines']} lines)")
        ln(f"    AI bots blocked:     {len(robots['bots_blocked'])} — {', '.join(robots['bots_blocked'][:6])}{'...' if len(robots['bots_blocked']) > 6 else ''}")
        ln(f"    AI bots allowed:     {len(robots['bots_allowed'])}")
        ln(f"    AI bots unmentioned: {len(robots['bots_unmentioned'])} — {', '.join(robots['bots_unmentioned'][:6])}{'...' if len(robots['bots_unmentioned']) > 6 else ''}")
        ln(f"    Google-Extended:     {'Yes' if robots['has_google_extended'] else 'No'}")
        ln(f"    AIPREF in robots:    {'Yes' if robots['has_aipref_content_usage'] else 'No'}")
        ln(f"    Content-Signal:      {robots['content_signal'] or 'No'}")
    else:
        ln("    Found: No")
    ln("")

    ln("  HTTP HEADERS")
    ln(f"    Content-Usage:          {headers.get('content_usage') or 'Not present'}")
    ln(f"    Content-Signal:         {headers.get('content_signal') or 'Not present'}")
    ln(f"    X-Robots-Tag:           {headers.get('x_robots_tag') or 'Not present'}")
    ln(f"    tdm-reservation:        {headers.get('tdm_reservation') or 'Not present'}")
    ln(f"    tdm-policy:             {headers.get('tdm_policy') or 'Not present'}")
    ln("")

    ln("  TDMREP")
    ln(f"    tdmrep.json:            {'Found' if headers.get('tdmrep_json') else 'Not found'}")
    ln(f"    <meta> tag:             {'tdm-reservation=' + headers['tdm_meta'] if headers.get('tdm_meta') else 'Not present'}")
    if headers.get("link_tdmrep"):
        ln(f"    Legacy Link header:     {headers['link_tdmrep']}")
    ln("")

    ln("  CONSENT MANIFEST")
    if manifest["found"]:
        ln(f"    Found: Yes (v{manifest['version']})")
        ln(f"    Publisher: {manifest['publisher']}")
        ln(f"    Standard: {', '.join(k + '=' + v for k, v in manifest['standard_categories'].items())}")
        if manifest["experimental_categories"]:
            ln(f"    Experimental: {', '.join(k + '=' + v for k, v in manifest['experimental_categories'].items())}")
        ln(f"    Rules: {manifest['rules_count']} path-specific")
        ln(f"    Fallbacks: {'Yes' if manifest['has_fallbacks'] else 'No'}")
        ln(f"    Endpoints: {'Yes' if manifest['has_endpoints'] else 'No'}")
    else:
        ln("    Found: No")
    ln("")

    ln("  OTHER AI FILES")
    for path, found in alt_files.items():
        ln(f"    {path}: {'Found' if found else 'Not found'}")
    ln("")

    # Gaps and recommendations.
    gaps = []
    if not robots["found"]:
        gaps.append("No robots.txt found. AI crawlers will access all content by default.")
    elif len(robots["bots_unmentioned"]) > 5:
        gaps.append(f"{len(robots['bots_unmentioned'])} AI bots have no rules in robots.txt. Missing: {', '.join(robots['bots_unmentioned'][:5])}...")
    if not robots.get("has_google_extended") and robots["found"]:
        gaps.append("No Google-Extended rules. Google may use content for Gemini training.")
    if not headers.get("content_usage"):
        gaps.append("No AIPREF Content-Usage header. Usage preferences are not expressed in HTTP responses.")
    if not headers.get("x_robots_tag"):
        gaps.append("No X-Robots-Tag header. Search preview controls are not set.")
    if not any(headers.get(k) for k in TDMREP_KEYS):
        gaps.append("No TDMRep declaration (tdm-reservation header, tdmrep.json or <meta> tag). EU text/data mining rights are not declared.")
    if not manifest["found"]:
        gaps.append("No consent manifest found. No unified AI policy declaration exists.")
    elif not manifest["has_fallbacks"]:
        gaps.append("Consent manifest has no fallback rules. Compilers cannot lower rich states safely.")

    if gaps:
        ln("  GAPS")
        for i, gap in enumerate(gaps, 1):
            ln(f"    {i}. {gap}")
        ln("")

    # Propagation note.
    ln("  NOTE: robots.txt changes may take ~24 hours to propagate to")
    ln("  OpenAI crawlers. AIPREF headers take effect immediately.")
    ln("")

    return "\n".join(lines)


def generate_json_report(domain, robots, headers, manifest, alt_files, scores):
    """Generate machine-readable JSON report."""
    return json.dumps({
        "domain": domain,
        "scores": scores,
        "grade": grade(scores["overall"]),
        "robots": {
            "found": robots["found"],
            "bots_blocked": len(robots["bots_blocked"]),
            "bots_unmentioned": len(robots["bots_unmentioned"]),
            "has_google_extended": robots["has_google_extended"],
            "has_aipref": robots["has_aipref_content_usage"],
            "content_signal": robots["content_signal"],
        },
        "headers": {
            "content_usage": headers.get("content_usage"),
            "content_signal": headers.get("content_signal"),
            "x_robots_tag": headers.get("x_robots_tag"),
            "tdm_reservation": headers.get("tdm_reservation"),
            "tdm_policy": headers.get("tdm_policy"),
            "tdm_meta": headers.get("tdm_meta"),
            "tdmrep_json": headers.get("tdmrep_json"),
            "tdmrep": any(headers.get(k) for k in TDMREP_KEYS),
        },
        "manifest": {
            "found": manifest["found"],
            "version": manifest.get("version"),
            "standard": manifest.get("standard_categories", {}),
            "has_fallbacks": manifest.get("has_fallbacks", False),
        },
        "alt_files": alt_files,
    }, indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scan a domain for AI content access policy posture.",
        epilog="Example: python scan.py example.com",
    )
    parser.add_argument("domain", help="Domain to scan (e.g., example.com or https://example.com)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    domain = args.domain
    if not domain.startswith("http"):
        domain = "https://" + domain
    base_url = domain.rstrip("/")

    print(f"\n  Scanning {base_url} ...\n")

    robots = scan_robots_txt(base_url)
    headers = scan_headers(base_url)
    manifest = scan_consent_manifest(base_url)
    alt_files = scan_well_known_alt(base_url)
    scores = score(robots, headers, manifest, alt_files)

    if args.json:
        print(generate_json_report(base_url, robots, headers, manifest, alt_files, scores))
    else:
        print(generate_report(base_url, robots, headers, manifest, alt_files, scores))


if __name__ == "__main__":
    main()
