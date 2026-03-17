#!/usr/bin/env python3
"""
consent.txt — Badge Generator v0.1

Generates embeddable SVG badges showing a domain's AI policy readiness grade.
Outputs both the SVG and an HTML embed snippet that links back to the scanner.

Usage:
    python badge.py --domain example.com --grade A --score 85
    python badge.py --domain example.com --grade A --score 85 --style flat
    python badge.py --domain example.com --grade A --score 85 --out badge.svg

Zero external dependencies.
"""

import argparse
import sys

SCANNER_URL = "https://consenttxt.org/scan"

GRADE_COLORS = {
    "A": {"bg": "#0F6E56", "label": "Excellent"},
    "B": {"bg": "#3B6D11", "label": "Good"},
    "C": {"bg": "#854F0B", "label": "Partial"},
    "D": {"bg": "#993C1D", "label": "Weak"},
    "F": {"bg": "#A32D2D", "label": "Missing"},
}


def generate_badge_svg(domain, grade, score, style="flat"):
    """Generate an SVG badge showing AI policy grade."""
    g = GRADE_COLORS.get(grade.upper(), GRADE_COLORS["F"])
    bg = g["bg"]

    left_width = 90
    right_width = 72
    total_width = left_width + right_width
    height = 20

    if style == "flat":
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="AI Consent: Grade {grade}">
  <title>AI Consent: Grade {grade} ({score}/100)</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="{height}" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_width}" height="{height}" fill="#555"/>
    <rect x="{left_width}" width="{right_width}" height="{height}" fill="{bg}"/>
    <rect width="{total_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{left_width / 2}" y="14" fill="#010101" fill-opacity=".3">AI Consent</text>
    <text x="{left_width / 2}" y="13">AI Consent</text>
    <text x="{left_width + right_width / 2}" y="14" fill="#010101" fill-opacity=".3">Grade {grade}</text>
    <text x="{left_width + right_width / 2}" y="13">Grade {grade}</text>
  </g>
</svg>'''

    elif style == "detailed":
        left_width = 90
        right_width = 100
        total_width = left_width + right_width
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="AI Consent: Grade {grade} — {score}/100">
  <title>AI Consent: Grade {grade} ({score}/100) — {g["label"]}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="{height}" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_width}" height="{height}" fill="#555"/>
    <rect x="{left_width}" width="{right_width}" height="{height}" fill="{bg}"/>
    <rect width="{total_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{left_width / 2}" y="14" fill="#010101" fill-opacity=".3">AI Consent</text>
    <text x="{left_width / 2}" y="13">AI Consent</text>
    <text x="{left_width + right_width / 2}" y="14" fill="#010101" fill-opacity=".3">{grade} — {score}/100</text>
    <text x="{left_width + right_width / 2}" y="13">{grade} — {score}/100</text>
  </g>
</svg>'''


def generate_embed_snippet(domain, grade, score, style="flat"):
    """Generate HTML embed snippet for the badge."""
    svg = generate_badge_svg(domain, grade, score, style)
    scan_url = f"{SCANNER_URL}?domain={domain}"

    snippet = f'''<!-- AI Policy Badge — powered by consent.txt -->
<a href="{scan_url}" target="_blank" rel="noopener" title="AI content policy: Grade {grade} ({score}/100)">
  {svg}
</a>'''

    # Also generate a simpler image-tag version for sites that host the SVG
    img_snippet = f'''<!-- Alternative: host badge.svg on your server -->
<a href="{scan_url}" target="_blank" rel="noopener" title="AI content policy: Grade {grade} ({score}/100)">
  <img src="/badge.svg" alt="AI Consent: Grade {grade}" height="20">
</a>'''

    # Markdown version
    md_snippet = f"[![AI Consent: Grade {grade}]({scan_url}/badge.svg)]({scan_url})"

    return svg, snippet, img_snippet, md_snippet


def main():
    parser = argparse.ArgumentParser(description="Generate AI policy readiness badges.")
    parser.add_argument("--domain", required=True, help="Domain name")
    parser.add_argument("--grade", required=True, choices=["A", "B", "C", "D", "F"], help="Policy grade")
    parser.add_argument("--score", required=True, type=int, help="Overall score (0-100)")
    parser.add_argument("--style", default="flat", choices=["flat", "detailed"], help="Badge style")
    parser.add_argument("--out", default=None, help="Write SVG to file")
    args = parser.parse_args()

    svg, html_snippet, img_snippet, md_snippet = generate_embed_snippet(
        args.domain, args.grade, args.score, args.style
    )

    if args.out:
        with open(args.out, "w") as f:
            f.write(svg)
        print(f"  Badge written to {args.out}")
        print()

    print("=" * 60)
    print(f"  AI Policy Badge — {args.domain}")
    print(f"  Grade: {args.grade}  Score: {args.score}/100")
    print("=" * 60)
    print()
    print("── HTML embed (inline SVG) ──")
    print(html_snippet)
    print()
    print("── HTML embed (hosted SVG) ──")
    print(img_snippet)
    print()
    print("── Markdown ──")
    print(md_snippet)
    print()


if __name__ == "__main__":
    main()
