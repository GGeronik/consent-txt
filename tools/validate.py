#!/usr/bin/env python3
"""
consent.txt — Consent Manifest Validator v0.1

Validates consent-manifest.json files against the v0.1 specification.
Zero external dependencies.

Usage:
    python validate.py manifest.json [more.json ...]
    python validate.py https://example.com/.well-known/consent-manifest.json
"""

import argparse
import json
import re
import sys

VALID_STATES = {"allow", "deny", "unknown", "charge", "conditional"}
VALID_FALLBACK_STATES = {"allow", "deny", "unknown"}
VALID_IDENTITY = {"none", "verified", "signed"}
STANDARD_CATEGORIES = {"train-ai", "search"}
# These are widely used (Cloudflare Content Signals, AIPREF discussions) but not
# yet formally standardized by AIPREF. They belong in the experimental block.
NEAR_STANDARD = {"train-genai", "ai-input"}
KNOWN_EXPERIMENTAL = {"train-genai", "ai-input", "agentic-access", "transform", "generate-media", "embedding"}
VALID_EMIT_TARGETS = {
    "robots-txt", "aipref-header", "aipref-robots",
    "x-robots-tag", "google-extended", "tdmrep",
    "content-signal", "summary",
}
CONDITION_FIELDS = {
    "identity", "citation_required", "link_required", "attribution_required",
    "max_excerpt_chars", "max_tokens", "verbatim_allowed",
    "freshness_delay_seconds", "rate_limit_per_day", "region_scope",
    "payment_plan",
}
MATCH_KEYS = {"path", "hostname", "content_types", "languages", "labels"}
CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")  # C0, DEL, C1 (incl. NEL) and the Unicode line separators
URL_RE = re.compile(r"^https?://[^\s\"'<>]+$")
BAD_PATH_CHARS = re.compile(r"[\s#?\[\]]")
MAX_DOUBLESTAR = 4  # same limit as compiler/compile.py, since each '/**/' doubles the compiled patterns


def _fmt(values):
    return ", ".join(sorted(values))


def validate(data):
    errors = []
    warnings = []

    def err(msg): errors.append(msg)
    def warn(msg): warnings.append(msg)

    if not isinstance(data, dict):
        err("Root must be a JSON object.")
        return errors, warnings

    # version
    if "version" not in data:
        err("Missing required field: 'version'.")
    elif data["version"] != "0.1":
        err(f"version must be '0.1', got {data['version']!r}.")

    # publisher
    if "publisher" not in data:
        err("Missing required field: 'publisher'.")
    else:
        pub = data["publisher"]
        if not isinstance(pub, dict):
            err("publisher must be an object.")
        else:
            for key in ("name", "contact"):
                if not isinstance(pub.get(key), str) or not pub[key].strip():
                    err(f"publisher.{key} is required and must be a non-empty string.")
            if "url" in pub:
                if not isinstance(pub["url"], str):
                    err("publisher.url must be a string.")
                elif not pub["url"].startswith("https://"):
                    warn("publisher.url should use HTTPS.")
            if "jurisdictions" in pub and (not isinstance(pub["jurisdictions"], list)
                                           or not all(isinstance(j, str) for j in pub["jurisdictions"])):
                err("publisher.jurisdictions must be an array of strings.")
            for key in ("name", "url", "contact", "terms_url"):
                if isinstance(pub.get(key), str) and CONTROL_CHARS.search(pub[key]):
                    err(f"publisher.{key}: control characters are not allowed (they would be copied into robots.txt or headers).")

    # defaults
    if "defaults" not in data:
        err("Missing required field: 'defaults'.")
    else:
        validate_policy_block(data["defaults"], "defaults", errors, warnings)

    # rules
    if "rules" in data:
        if not isinstance(data["rules"], list):
            err("rules must be an array.")
        else:
            for i, rule in enumerate(data["rules"]):
                label = f"rules[{i}]"
                if not isinstance(rule, dict):
                    err(f"{label}: must be an object.")
                    continue
                if "match" not in rule:
                    err(f"{label}: missing required field 'match'.")
                else:
                    validate_match(rule["match"], f"{label}.match", errors, warnings)
                validate_policy_block(rule, label, errors, warnings, allow_fallbacks=False)

    # endpoints
    if "endpoints" in data:
        if not isinstance(data["endpoints"], dict):
            err("endpoints must be an object.")
        else:
            for key, val in data["endpoints"].items():
                if not isinstance(val, str) or not URL_RE.match(val) or CONTROL_CHARS.search(val):
                    err(f"endpoints.{key}: must be an absolute http(s) URL without spaces, quotes or angle brackets.")

    # interop
    if "interop" in data:
        interop = data["interop"]
        if not isinstance(interop, dict):
            err("interop must be an object.")
        elif "emit" in interop:
            if not isinstance(interop["emit"], list):
                err("interop.emit must be an array.")
            else:
                for target in interop["emit"]:
                    if not isinstance(target, str):
                        err("interop.emit: entries must be strings.")
                    elif target not in VALID_EMIT_TARGETS:
                        warn(f"interop.emit: unknown target '{target}' (valid: {_fmt(VALID_EMIT_TARGETS)}).")

    # Semantic checks
    check_semantics(data, warnings)

    # Unknown top-level fields
    known = {"version", "publisher", "defaults", "rules", "endpoints", "interop", "signature", "extensions"}
    for key in data:
        if key not in known:
            warn(f"Unknown top-level field: '{key}'.")

    return errors, warnings


def validate_policy_block(block, label, errors, warnings, allow_fallbacks=True):
    if not isinstance(block, dict):
        errors.append(f"{label}: must be an object.")
        return

    if "fallbacks" in block:
        fb = block["fallbacks"]
        if not allow_fallbacks:
            warnings.append(f"{label}.fallbacks: ignored, because fallbacks are only read from defaults.")
        elif isinstance(fb, dict):
            for key in ("unexpressible_state", "unknown_identity"):
                if key in fb and not (isinstance(fb[key], str) and fb[key] in VALID_FALLBACK_STATES):
                    errors.append(f"{label}.fallbacks.{key}: must be one of {_fmt(VALID_FALLBACK_STATES)}.")
        else:
            errors.append(f"{label}.fallbacks: must be an object.")

    std = block.get("standard")
    exp = block.get("experimental")
    if "standard" in block:
        validate_standard_policies(std, f"{label}.standard", errors, warnings)
    if "experimental" in block:
        validate_experimental_policies(exp, f"{label}.experimental", errors, warnings)
    if isinstance(std, dict) and isinstance(exp, dict):
        for cat in sorted(set(std) & set(exp)):
            s, e = std[cat], exp[cat]
            if isinstance(s, dict) and isinstance(e, dict) and s.get("state") != e.get("state"):
                errors.append(f"{label}.{cat}: declared in both standard and experimental with different states.")


def validate_standard_policies(std, label, errors, warnings):
    if not isinstance(std, dict):
        errors.append(f"{label}: must be an object.")
        return
    for cat, val in std.items():
        if cat not in STANDARD_CATEGORIES:
            errors.append(f"{label}.{cat}: not a recognized standard category. Valid: {_fmt(STANDARD_CATEGORIES)}.")
        validate_policy_value(val, f"{label}.{cat}", errors, warnings)


def validate_experimental_policies(exp, label, errors, warnings):
    if not isinstance(exp, dict):
        errors.append(f"{label}: must be an object.")
        return
    for cat, val in exp.items():
        if cat in STANDARD_CATEGORIES:
            warnings.append(f"{label}.{cat}: this is a standard category — move it to 'standard'.")
        elif cat not in KNOWN_EXPERIMENTAL and not cat.startswith("x-"):
            warnings.append(f"{label}.{cat}: unknown experimental category (known: "
                            f"{_fmt(KNOWN_EXPERIMENTAL)}). Custom categories need an 'x-' prefix.")
        validate_policy_value(val, f"{label}.{cat}", errors, warnings)


def validate_policy_value(val, label, errors, warnings):
    if not isinstance(val, dict):
        errors.append(f"{label}: must be an object.")
        return
    if "state" not in val:
        errors.append(f"{label}: missing required field 'state'.")
        return
    state = val["state"]
    if not isinstance(state, str) or state not in VALID_STATES:
        errors.append(f"{label}.state: {state!r} is not valid. Must be one of {_fmt(VALID_STATES)}.")
        return

    if "conditions" in val and not isinstance(val["conditions"], dict):
        errors.append(f"{label}.conditions: must be an object.")
        return
    has_conditions = bool(val.get("conditions"))

    if state in ("charge", "conditional") and not has_conditions:
        warnings.append(f"{label}: state is '{state}' but no conditions are defined.")
    if state in ("allow", "deny") and has_conditions:
        warnings.append(f"{label}: state is '{state}' but conditions are present — they will be ignored by most consumers.")

    if has_conditions:
        validate_conditions(val["conditions"], f"{label}.conditions", errors, warnings)


def validate_conditions(cond, label, errors, warnings):
    if "identity" in cond and not (isinstance(cond["identity"], str) and cond["identity"] in VALID_IDENTITY):
        errors.append(f"{label}.identity: must be one of {_fmt(VALID_IDENTITY)}.")
    for bool_field in ("citation_required", "link_required", "attribution_required", "verbatim_allowed"):
        if bool_field in cond and not isinstance(cond[bool_field], bool):
            errors.append(f"{label}.{bool_field}: must be a boolean.")
    for int_field in ("max_excerpt_chars", "max_tokens", "freshness_delay_seconds", "rate_limit_per_day"):
        if int_field in cond:
            if not isinstance(cond[int_field], int) or isinstance(cond[int_field], bool) or cond[int_field] < 0:
                errors.append(f"{label}.{int_field}: must be a non-negative integer.")
    if "region_scope" in cond and not isinstance(cond["region_scope"], list):
        errors.append(f"{label}.region_scope: must be an array.")

    for key in cond:
        if key not in CONDITION_FIELDS:
            warnings.append(f"{label}: unknown condition field '{key}'.")


def validate_match(match, label, errors, warnings):
    if not isinstance(match, dict):
        errors.append(f"{label}: must be an object.")
        return
    for key in match:
        if key not in MATCH_KEYS:
            warnings.append(f"{label}: unknown match field '{key}'.")
        elif key != "path":
            warnings.append(f"{label}.{key}: no emit target compiles this matcher, so the compiler applies "
                            f"the rule to its whole path and keeps only its denies.")
    path = match.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        errors.append(f"{label}.path: required, and must be a string starting with '/'.")
        return
    if BAD_PATH_CHARS.search(path):
        errors.append(f"{label}.path: must not contain whitespace, '#', '?' or brackets (RFC 9309 patterns support only '*' and a trailing '$').")
    if "$" in path[:-1]:
        errors.append(f"{label}.path: '$' is only allowed at the end of the pattern.")
    if path.count("/**/") > MAX_DOUBLESTAR:
        errors.append(f"{label}.path: at most four '/**/' segments are allowed (each one doubles the compiled patterns).")
    if CONTROL_CHARS.search(path):
        errors.append(f"{label}.path: control characters are not allowed.")


def _states_in(block):
    out = []
    if not isinstance(block, dict):
        return out
    for tier in ("standard", "experimental"):
        tier_block = block.get(tier)
        if isinstance(tier_block, dict):
            for val in tier_block.values():
                if isinstance(val, dict) and isinstance(val.get("state"), str):
                    out.append(val["state"])
    return out


def check_semantics(data, warnings):
    defaults = data.get("defaults", {})
    rules = data.get("rules", []) if isinstance(data.get("rules"), list) else []
    rich = {"charge", "conditional"}

    if any(s in rich for s in _states_in(defaults)) and isinstance(defaults, dict) and "fallbacks" not in defaults:
        warnings.append(
            "defaults: manifest uses 'charge' or 'conditional' states but no "
            "fallbacks are defined. Compilers will not know how to lower these "
            "to surfaces that only support allow/deny."
        )

    has_charge = any("charge" in _states_in(block) for block in [defaults] + rules)
    endpoints = data.get("endpoints") if isinstance(data.get("endpoints"), dict) else {}
    if has_charge and "payment" not in endpoints:
        warnings.append("Manifest uses 'charge' state but no endpoints.payment is defined.")


def load_file(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        import urllib.request
        with urllib.request.urlopen(path_or_url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    else:
        with open(path_or_url, "r", encoding="utf-8") as f:
            return json.load(f)


def report(target, data, errors, warnings):
    is_valid = len(errors) == 0

    print(f"\n{'='*60}")
    print(f"  Consent Manifest Validator v0.1")
    print(f"  Target: {target}")
    print(f"{'='*60}\n")

    if is_valid:
        print("  RESULT: VALID\n")
    else:
        print("  RESULT: INVALID\n")
        print(f"  {len(errors)} error(s):\n")
        for i, e in enumerate(errors, 1):
            print(f"    {i}. {e}")
        print()

    if warnings:
        print(f"  {len(warnings)} warning(s):\n")
        for i, w in enumerate(warnings, 1):
            print(f"    {i}. {w}")
        print()

    if not isinstance(data, dict):
        return is_valid
    pub = data.get("publisher", {}) if isinstance(data.get("publisher"), dict) else {}
    defs = data.get("defaults", {}) if isinstance(data.get("defaults"), dict) else {}
    std = defs.get("standard", {}) if isinstance(defs.get("standard"), dict) else {}
    exp = defs.get("experimental", {}) if isinstance(defs.get("experimental"), dict) else {}
    interop = data.get("interop", {}) if isinstance(data.get("interop"), dict) else {}
    emit = interop.get("emit", []) if isinstance(interop.get("emit"), list) else []
    rules = data.get("rules", []) if isinstance(data.get("rules"), list) else []

    print(f"  Publisher:     {pub.get('name', 'N/A')}")
    print(f"  Contact:       {pub.get('contact', 'N/A')}")
    print(f"  Jurisdictions: {', '.join(map(str, pub.get('jurisdictions', []))) if isinstance(pub.get('jurisdictions'), list) else 'N/A'}")
    std_summary = ", ".join(k + "=" + str(v.get("state", "?")) for k, v in std.items() if isinstance(v, dict))
    exp_summary = ", ".join(k + "=" + str(v.get("state", "?")) for k, v in exp.items() if isinstance(v, dict))
    print(f"  Standard:      {std_summary or 'None'}")
    print(f"  Experimental:  {exp_summary or 'None'}")
    print(f"  Rules:         {len(rules)} path-specific rule(s)")
    print(f"  Emit targets:  {', '.join(map(str, emit)) or 'None specified'}")
    print()
    return is_valid


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate consent-manifest.json files against the v0.1 specification.")
    parser.add_argument("targets", nargs="+", help="File path(s) or URL(s)")
    args = parser.parse_args(argv)

    all_valid = True
    for target in args.targets:
        try:
            data = load_file(target)
        except json.JSONDecodeError as e:
            print(f"\nFAIL: {target}: invalid JSON ({e})")
            all_valid = False
            continue
        except Exception as e:
            print(f"\nFAIL: {target}: could not load ({e})")
            all_valid = False
            continue
        errors, warnings = validate(data)
        if not report(target, data, errors, warnings):
            all_valid = False
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
