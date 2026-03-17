#!/usr/bin/env python3
"""
consent.txt — Consent Manifest Compiler v0.1

Compiles a consent-manifest.json into deployable protocol surfaces:
  - robots.txt user-agent groups
  - AIPREF Content-Usage HTTP headers
  - AIPREF Content-Usage rules for robots.txt
  - X-Robots-Tag HTTP headers
  - Google-Extended robots.txt rules
  - TDMRep references
  - Human-readable policy summary

Usage:
    python compile.py manifest.json                    # Emit all targets
    python compile.py manifest.json --emit robots-txt  # Emit specific target
    python compile.py manifest.json --emit all --out build/  # Write to directory

Zero external dependencies.
"""

import json
import sys
import os
import argparse

# ── Known AI crawler user-agents ──────────────────────────────────────────────

TRAINING_BOTS = [
    "GPTBot",
    "ClaudeBot",
    "CCBot",
    "Google-Extended",
    "FacebookBot",
    "Bytespider",
    "Diffbot",
    "Omgilibot",
    "Amazonbot",
    "cohere-ai",
    "AI2Bot",
    "Applebot-Extended",
]

SEARCH_BOTS = [
    "OAI-SearchBot",
    "Claude-SearchBot",
    "PerplexityBot",
]

AI_INPUT_BOTS = [
    "ChatGPT-User",
    "Claude-User",
]

# ── State lowering ────────────────────────────────────────────────────────────

def lower_state(state, fallbacks):
    """Lower a rich authoring state to allow/deny for wire formats."""
    if state in ("allow", "deny"):
        return state
    if state == "unknown":
        return None  # Omit from output.
    # charge, conditional → use fallback
    fb = fallbacks.get("unexpressible_state", "deny")
    return fb


def get_fallbacks(manifest):
    return manifest.get("defaults", {}).get("fallbacks", {
        "unexpressible_state": "deny",
        "unknown_identity": "deny",
    })


# ── Resolve policy for a path ─────────────────────────────────────────────────

def resolve_policy(manifest, path=None):
    """Resolve the effective policy for a given path, merging defaults + rules.
    Returns (standard_dict, experimental_dict)."""
    defaults = manifest.get("defaults", {})
    std = dict(defaults.get("standard", {}))
    exp = dict(defaults.get("experimental", {}))

    if path and "rules" in manifest:
        # Find the longest matching rule (specificity).
        best_rule = None
        best_len = -1
        for rule in manifest["rules"]:
            rule_path = rule.get("match", {}).get("path", "")
            if _path_matches(path, rule_path) and len(rule_path) > best_len:
                best_rule = rule
                best_len = len(rule_path)

        if best_rule:
            # Rule policies completely override defaults for matched categories.
            if "standard" in best_rule:
                std.update(best_rule["standard"])
            if "experimental" in best_rule:
                exp.update(best_rule["experimental"])

    return std, exp


def _path_matches(test_path, pattern):
    """Simple glob match: /foo/* matches /foo/bar, /foo/bar/baz."""
    if not pattern:
        return False
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return test_path == prefix or test_path.startswith(prefix + "/")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return test_path == prefix or test_path.startswith(prefix + "/")
    return test_path == pattern


# ── Compiler: robots.txt ──────────────────────────────────────────────────────

def compile_robots_txt(manifest):
    """Compile manifest into robots.txt user-agent groups."""
    fallbacks = get_fallbacks(manifest)
    lines = [
        "# robots.txt",
        "# Generated from consent-manifest.json by consent.txt compiler v0.1",
        f"# Publisher: {manifest.get('publisher', {}).get('name', 'Unknown')}",
        "",
    ]

    # Read effective states from both standard and experimental blocks.
    train_state = _get_default_state(manifest, "train-ai")
    train_genai_state = _get_default_state(manifest, "train-genai")
    search_state = _get_default_state(manifest, "search")
    ai_input_state = _get_default_state(manifest, "ai-input")

    train_lowered = lower_state(train_state, fallbacks)
    train_genai_lowered = lower_state(train_genai_state, fallbacks)
    block_training = (train_lowered == "deny" or train_genai_lowered == "deny")
    ai_input_lowered = lower_state(ai_input_state, fallbacks)

    # ── Default: allow all crawling ──
    lines.append("User-Agent: *")
    lines.append("Allow: /")
    lines.append("")

    # ── Training bots ──
    if block_training:
        allow_paths = []
        for rule in manifest.get("rules", []):
            rule_path = rule.get("match", {}).get("path", "")
            rule_train = _get_rule_state(rule, "train-ai")
            rule_train_genai = _get_rule_state(rule, "train-genai")
            if (rule_train == "allow" or rule_train_genai == "allow") and rule_path:
                clean = rule_path.rstrip("*").rstrip("/")
                allow_paths.append(clean + "/")

        for bot in TRAINING_BOTS:
            lines.append(f"User-Agent: {bot}")
        for ap in allow_paths:
            lines.append(f"Allow: {ap}")
        lines.append("Disallow: /")
        lines.append("")

    # ── AI-input bots (ChatGPT-User, Claude-User) ──
    if ai_input_lowered == "deny":
        ai_allow_paths = []
        for rule in manifest.get("rules", []):
            rule_path = rule.get("match", {}).get("path", "")
            rule_ai = _get_rule_state(rule, "ai-input")
            if rule_ai == "allow" and rule_path:
                clean = rule_path.rstrip("*").rstrip("/")
                ai_allow_paths.append(clean + "/")

        for bot in AI_INPUT_BOTS:
            lines.append(f"User-Agent: {bot}")
        for ap in ai_allow_paths:
            lines.append(f"Allow: {ap}")
        lines.append("Disallow: /")
        lines.append("")

    # ── Path-specific blocks ──
    for rule in manifest.get("rules", []):
        rule_path = rule.get("match", {}).get("path", "")
        if not rule_path:
            continue
        clean_path = rule_path.rstrip("*").rstrip("/")

        rule_train = lower_state(_get_rule_state(rule, "train-ai"), fallbacks)
        rule_train_genai = lower_state(_get_rule_state(rule, "train-genai"), fallbacks)
        rule_blocks_training = (rule_train == "deny" or rule_train_genai == "deny")
        if rule_blocks_training and not block_training:
            for bot in TRAINING_BOTS:
                lines.append(f"User-Agent: {bot}")
            lines.append(f"Disallow: {clean_path}/")
            lines.append("")

        rule_search = lower_state(_get_rule_state(rule, "search"), fallbacks)
        if rule_search == "deny":
            lines.append("User-Agent: *")
            lines.append(f"Disallow: {clean_path}/")
            lines.append("")

    # ── Sitemap (if publisher URL known) ──
    pub_url = manifest.get("publisher", {}).get("url", "")
    if pub_url:
        lines.append(f"Sitemap: {pub_url.rstrip('/')}/sitemap.xml")
        lines.append("")

    return "\n".join(lines)


# ── Compiler: AIPREF headers ─────────────────────────────────────────────────

def compile_aipref_header(manifest, path=None):
    """Compile AIPREF Content-Usage HTTP header value."""
    fallbacks = get_fallbacks(manifest)
    std, _ = resolve_policy(manifest, path)

    parts = []
    for cat in ("train-ai", "search"):
        state = _get_state(std, cat)
        lowered = lower_state(state, fallbacks)
        if lowered == "allow":
            parts.append(f"{cat}=y")
        elif lowered == "deny":
            parts.append(f"{cat}=n")
        # unknown → omit

    if not parts:
        return ""
    return "Content-Usage: " + ", ".join(parts)


# ── Compiler: AIPREF robots.txt rules ────────────────────────────────────────

def compile_aipref_robots(manifest):
    """Compile AIPREF Content-Usage directives for robots.txt."""
    fallbacks = get_fallbacks(manifest)
    lines = [
        "# AIPREF Content-Usage rules for robots.txt",
        "# Generated from consent-manifest.json",
        "",
    ]

    # Default
    defaults = manifest.get("defaults", {})
    std = defaults.get("standard", {})
    parts = []
    for cat in ("train-ai", "search"):
        state = _get_state(std, cat)
        lowered = lower_state(state, fallbacks)
        if lowered == "allow":
            parts.append(f"{cat}=y")
        elif lowered == "deny":
            parts.append(f"{cat}=n")
    if parts:
        lines.append("User-Agent: *")
        lines.append(f"Content-Usage: {', '.join(parts)}")
        lines.append("")

    # Path overrides
    for rule in manifest.get("rules", []):
        rule_path = rule.get("match", {}).get("path", "")
        if not rule_path:
            continue
        rule_std = rule.get("standard", {})
        parts = []
        for cat in ("train-ai", "search"):
            state = _get_state(rule_std, cat)
            if state:
                lowered = lower_state(state, fallbacks)
                if lowered == "allow":
                    parts.append(f"{cat}=y")
                elif lowered == "deny":
                    parts.append(f"{cat}=n")
        if parts:
            clean_path = rule_path.rstrip("*").rstrip("/")
            lines.append(f"Content-Usage: {clean_path}/ {', '.join(parts)}")

    lines.append("")
    return "\n".join(lines)


# ── Compiler: X-Robots-Tag ───────────────────────────────────────────────────

def compile_x_robots_tag(manifest, path=None):
    """Compile X-Robots-Tag HTTP header values.
    Uses preview controls (max-snippet, nosnippet, noai) which are standard
    search mechanisms, not AIPREF-specific."""
    fallbacks = get_fallbacks(manifest)
    std, exp = resolve_policy(manifest, path)
    # Merge both blocks for effective policy
    merged = {}
    merged.update(exp)
    merged.update(std)
    tags = []

    search_state = _get_state(merged, "search")
    if lower_state(search_state, fallbacks) == "deny":
        tags.append("X-Robots-Tag: noindex, nofollow")
        return "\n".join(tags)

    # Snippet restrictions from ai-input conditions (may be in experimental)
    ai_input = merged.get("ai-input", {})
    if isinstance(ai_input, dict):
        conditions = ai_input.get("conditions", {})
        max_chars = conditions.get("max_excerpt_chars")
        if max_chars is not None and isinstance(max_chars, int):
            tags.append(f"X-Robots-Tag: max-snippet:{max_chars}")
        if conditions.get("verbatim_allowed") is False:
            tags.append("X-Robots-Tag: nosnippet")

    # noai/noimageai when training is denied
    train_state = _get_state(merged, "train-ai")
    train_genai_state = _get_state(merged, "train-genai")
    if (lower_state(train_state, fallbacks) == "deny" or
        lower_state(train_genai_state, fallbacks) == "deny"):
        tags.append("X-Robots-Tag: googlebot: noai, noimageai")

    return "\n".join(tags)


# ── Compiler: Google-Extended robots.txt block ───────────────────────────────

def compile_google_extended(manifest):
    """Compile Google-Extended specific robots.txt rules."""
    fallbacks = get_fallbacks(manifest)
    lines = []

    train_state = _get_default_state(manifest, "train-ai")
    train_genai_state = _get_default_state(manifest, "train-genai")
    block = (lower_state(train_state, fallbacks) == "deny" or
             lower_state(train_genai_state, fallbacks) == "deny")

    if block:
        allow_paths = []
        for rule in manifest.get("rules", []):
            rule_path = rule.get("match", {}).get("path", "")
            rule_train = _get_rule_state(rule, "train-ai")
            rule_train_genai = _get_rule_state(rule, "train-genai")
            if (rule_train == "allow" or rule_train_genai == "allow") and rule_path:
                clean = rule_path.rstrip("*").rstrip("/")
                allow_paths.append(clean + "/")

        lines.append("User-Agent: Google-Extended")
        for ap in allow_paths:
            lines.append(f"Allow: {ap}")
        lines.append("Disallow: /")
        lines.append("")

    return "\n".join(lines)


# ── Compiler: TDMRep reference ───────────────────────────────────────────────

def compile_tdmrep(manifest):
    """Compile TDMRep HTTP-header reference."""
    endpoints = manifest.get("endpoints", {})
    tdm_url = endpoints.get("tdm_policy", "")
    if not tdm_url:
        return "# No TDMRep policy endpoint configured."

    lines = [
        "# TDMRep HTTP header (add to server responses)",
        f"Link: <{tdm_url}>; rel=\"tdm-policy\"",
    ]
    return "\n".join(lines)


# ── Compiler: Human-readable summary ─────────────────────────────────────────

def compile_summary(manifest):
    """Compile a human-readable policy summary."""
    pub = manifest.get("publisher", {})
    defaults = manifest.get("defaults", {})
    std = defaults.get("standard", {})
    exp = defaults.get("experimental", {})
    fallbacks = get_fallbacks(manifest)

    lines = [
        "=" * 60,
        f"  AI Content Policy — {pub.get('name', 'Unknown')}",
        "=" * 60,
        "",
        f"  Site:          {pub.get('url', 'N/A')}",
        f"  Contact:       {pub.get('contact', 'N/A')}",
        f"  Jurisdictions: {', '.join(pub.get('jurisdictions', [])) or 'N/A'}",
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

    # Rules
    rules = manifest.get("rules", [])
    if rules:
        lines.append("")
        lines.append(f"  Path Rules ({len(rules)}):")
        for rule in rules:
            path = rule.get("match", {}).get("path", "?")
            rule_std = rule.get("standard", {})
            parts = []
            for cat, val in rule_std.items():
                if isinstance(val, dict):
                    parts.append(f"{cat}={val.get('state', '?')}")
            lines.append(f"    {path} → {', '.join(parts) if parts else 'no standard overrides'}")

    # Fallback behavior
    lines.append("")
    lines.append("  Fallback Behavior:")
    lines.append(f"    Unexpressible states → {fallbacks.get('unexpressible_state', 'deny')}")
    lines.append(f"    Unknown identity     → {fallbacks.get('unknown_identity', 'deny')}")

    # Endpoints
    endpoints = manifest.get("endpoints", {})
    if endpoints:
        lines.append("")
        lines.append("  Endpoints:")
        for key, url in endpoints.items():
            lines.append(f"    {key}: {url}")

    lines.append("")
    return "\n".join(lines)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _get_state(policies, category):
    """Get the state string from a policies dict for a given category."""
    val = policies.get(category, {})
    if isinstance(val, dict):
        return val.get("state", "unknown")
    return "unknown"


def _get_effective_state(manifest, category, path=None):
    """Get the effective state for a category, checking both standard and experimental.
    Used for enforcement decisions (robots.txt) where both blocks matter."""
    defaults = manifest.get("defaults", {})
    std = defaults.get("standard", {})
    exp = defaults.get("experimental", {})

    # Check standard first, then experimental
    state = _get_state(std, category)
    if state == "unknown":
        state = _get_state(exp, category)

    # Apply path-level overrides
    if path and "rules" in manifest:
        best_rule = None
        best_len = -1
        for rule in manifest["rules"]:
            rule_path = rule.get("match", {}).get("path", "")
            if _path_matches(path, rule_path) and len(rule_path) > best_len:
                best_rule = rule
                best_len = len(rule_path)
        if best_rule:
            rule_state = _get_state(best_rule.get("standard", {}), category)
            if rule_state == "unknown":
                rule_state = _get_state(best_rule.get("experimental", {}), category)
            if rule_state != "unknown":
                state = rule_state

    return state


def _get_default_state(manifest, category):
    """Get state from defaults (standard then experimental), no path resolution."""
    defaults = manifest.get("defaults", {})
    state = _get_state(defaults.get("standard", {}), category)
    if state == "unknown":
        state = _get_state(defaults.get("experimental", {}), category)
    return state


def _get_rule_state(rule, category):
    """Get state from a rule (standard then experimental)."""
    state = _get_state(rule.get("standard", {}), category)
    if state == "unknown":
        state = _get_state(rule.get("experimental", {}), category)
    return state


def load_manifest(path):
    with open(path, "r") as f:
        return json.load(f)


# ── CLI ───────────────────────────────────────────────────────────────────────

COMPILERS = {
    "robots-txt":      ("robots.txt",              compile_robots_txt),
    "aipref-header":   ("aipref-header.txt",       lambda m: compile_aipref_header(m)),
    "aipref-robots":   ("aipref-robots.txt",       compile_aipref_robots),
    "x-robots-tag":    ("x-robots-tag.txt",        lambda m: compile_x_robots_tag(m)),
    "google-extended": ("google-extended.txt",      compile_google_extended),
    "tdmrep":          ("tdmrep-header.txt",       compile_tdmrep),
    "summary":         ("policy-summary.txt",       compile_summary),
}


def main():
    parser = argparse.ArgumentParser(
        description="Compile a consent-manifest.json into deployable protocol surfaces.",
        epilog="Example: python compile.py manifest.json --emit robots-txt aipref-header",
    )
    parser.add_argument("manifest", help="Path to consent-manifest.json")
    parser.add_argument(
        "--emit", nargs="*", default=["all"],
        help="Targets to emit. Options: " + ", ".join(list(COMPILERS.keys()) + ["all"]),
    )
    parser.add_argument("--out", default=None, help="Output directory (default: print to stdout)")

    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File not found — {args.manifest}", file=sys.stderr)
        sys.exit(1)

    # Determine which targets to emit.
    if "all" in args.emit:
        # Use manifest's interop.emit list, or all if not specified.
        emit_list = manifest.get("interop", {}).get("emit", [])
        if not emit_list:
            emit_list = list(COMPILERS.keys())
        # Always include summary.
        if "summary" not in emit_list:
            emit_list.append("summary")
    else:
        emit_list = args.emit

    outputs = {}
    for target in emit_list:
        if target not in COMPILERS:
            print(f"Warning: Unknown emit target '{target}', skipping.", file=sys.stderr)
            continue
        filename, compiler_fn = COMPILERS[target]
        result = compiler_fn(manifest)
        if result and result.strip():
            outputs[target] = (filename, result)

    # Output
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for target, (filename, content) in outputs.items():
            filepath = os.path.join(args.out, filename)
            with open(filepath, "w") as f:
                f.write(content)
            print(f"  Wrote: {filepath}")
        print(f"\n  {len(outputs)} file(s) compiled to {args.out}/")
    else:
        for target, (filename, content) in outputs.items():
            print(f"\n{'─'*60}")
            print(f"  [{target}] → {filename}")
            print(f"{'─'*60}")
            print(content)


if __name__ == "__main__":
    main()
