#!/usr/bin/env python3
"""
consent.txt — Consent Manifest Validator v0.1

Validates a consent-manifest.json against the v0.1 specification.
Zero external dependencies.

Usage:
    python validate.py manifest.json
    python validate.py https://example.com/.well-known/consent-manifest.json
"""

import json
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
}
CONDITION_FIELDS = {
    "identity", "citation_required", "link_required", "attribution_required",
    "max_excerpt_chars", "max_tokens", "verbatim_allowed",
    "freshness_delay_seconds", "rate_limit_per_day", "region_scope",
    "payment_plan",
}


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
        err(f"version must be '0.1', got '{data['version']}'.")

    # publisher
    if "publisher" not in data:
        err("Missing required field: 'publisher'.")
    else:
        pub = data["publisher"]
        if not isinstance(pub, dict):
            err("publisher must be an object.")
        else:
            if "name" not in pub or not pub.get("name", "").strip():
                err("publisher.name is required and must be non-empty.")
            if "contact" not in pub or not pub.get("contact", "").strip():
                err("publisher.contact is required and must be non-empty.")
            if "url" in pub and not pub["url"].startswith("https://"):
                warn("publisher.url should use HTTPS.")
            if "jurisdictions" in pub:
                if not isinstance(pub["jurisdictions"], list):
                    err("publisher.jurisdictions must be an array.")

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
                if "standard" in rule:
                    validate_standard_policies(rule["standard"], f"{label}.standard", errors, warnings)
                if "experimental" in rule:
                    validate_experimental_policies(rule["experimental"], f"{label}.experimental", errors, warnings)

    # endpoints
    if "endpoints" in data:
        if not isinstance(data["endpoints"], dict):
            err("endpoints must be an object.")
        else:
            for key, val in data["endpoints"].items():
                if not isinstance(val, str):
                    err(f"endpoints.{key}: must be a URI string.")

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
                    if target not in VALID_EMIT_TARGETS:
                        warn(f"interop.emit: unrecognized target '{target}'.")

    # Semantic checks
    check_semantics(data, warnings)

    # Unknown top-level fields
    known = {"version", "publisher", "defaults", "rules", "endpoints", "interop", "signature", "extensions"}
    for key in data:
        if key not in known:
            warn(f"Unknown top-level field: '{key}'.")

    return errors, warnings


def validate_policy_block(block, label, errors, warnings):
    if not isinstance(block, dict):
        errors.append(f"{label}: must be an object.")
        return

    if "fallbacks" in block:
        fb = block["fallbacks"]
        if isinstance(fb, dict):
            for key in ("unexpressible_state", "unknown_identity"):
                if key in fb and fb[key] not in VALID_FALLBACK_STATES:
                    errors.append(f"{label}.fallbacks.{key}: must be one of {VALID_FALLBACK_STATES}.")
        else:
            errors.append(f"{label}.fallbacks: must be an object.")

    if "standard" in block:
        validate_standard_policies(block["standard"], f"{label}.standard", errors, warnings)
    if "experimental" in block:
        validate_experimental_policies(block["experimental"], f"{label}.experimental", errors, warnings)


def validate_standard_policies(std, label, errors, warnings):
    if not isinstance(std, dict):
        errors.append(f"{label}: must be an object.")
        return
    for cat, val in std.items():
        if cat not in STANDARD_CATEGORIES:
            errors.append(f"{label}.{cat}: not a recognized standard category. Valid: {STANDARD_CATEGORIES}.")
        validate_policy_value(val, f"{label}.{cat}", errors, warnings)


def validate_experimental_policies(exp, label, errors, warnings):
    if not isinstance(exp, dict):
        errors.append(f"{label}: must be an object.")
        return
    for cat, val in exp.items():
        if cat in STANDARD_CATEGORIES:
            warnings.append(f"{label}.{cat}: this is a standard category — move it to 'standard'.")
        validate_policy_value(val, f"{label}.{cat}", errors, warnings)


def validate_policy_value(val, label, errors, warnings):
    if not isinstance(val, dict):
        errors.append(f"{label}: must be an object.")
        return
    if "state" not in val:
        errors.append(f"{label}: missing required field 'state'.")
        return
    if val["state"] not in VALID_STATES:
        errors.append(f"{label}.state: '{val['state']}' is not valid. Must be one of {VALID_STATES}.")

    state = val["state"]
    has_conditions = "conditions" in val and val["conditions"]

    if state in ("charge", "conditional") and not has_conditions:
        warnings.append(f"{label}: state is '{state}' but no conditions are defined.")
    if state in ("allow", "deny") and has_conditions:
        warnings.append(f"{label}: state is '{state}' but conditions are present — they will be ignored by most consumers.")

    if has_conditions:
        validate_conditions(val["conditions"], f"{label}.conditions", errors, warnings)


def validate_conditions(cond, label, errors, warnings):
    if not isinstance(cond, dict):
        errors.append(f"{label}: must be an object.")
        return

    if "identity" in cond and cond["identity"] not in VALID_IDENTITY:
        errors.append(f"{label}.identity: must be one of {VALID_IDENTITY}.")
    for bool_field in ("citation_required", "link_required", "attribution_required", "verbatim_allowed"):
        if bool_field in cond and not isinstance(cond[bool_field], bool):
            errors.append(f"{label}.{bool_field}: must be a boolean.")
    for int_field in ("max_excerpt_chars", "max_tokens", "freshness_delay_seconds", "rate_limit_per_day"):
        if int_field in cond:
            if not isinstance(cond[int_field], int) or cond[int_field] < 0:
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
    if not match:
        warnings.append(f"{label}: empty match block — this rule matches nothing.")
    valid_keys = {"path", "hostname", "content_types", "languages", "labels"}
    for key in match:
        if key not in valid_keys:
            warnings.append(f"{label}: unknown match field '{key}'.")


def check_semantics(data, warnings):
    defaults = data.get("defaults", {})
    # Check: charge/conditional in standard but no fallbacks defined
    has_rich = False
    for cat, val in defaults.get("standard", {}).items():
        if isinstance(val, dict) and val.get("state") in ("charge", "conditional"):
            has_rich = True
            break
    if not has_rich:
        for cat, val in defaults.get("experimental", {}).items():
            if isinstance(val, dict) and val.get("state") in ("charge", "conditional"):
                has_rich = True
                break
    if has_rich and "fallbacks" not in defaults:
        warnings.append(
            "defaults: manifest uses 'charge' or 'conditional' states but no "
            "fallbacks are defined. Compilers will not know how to lower these "
            "to surfaces that only support allow/deny."
        )

    # Check: charge state but no payment endpoint
    has_charge = False
    for block in [defaults] + [r for r in data.get("rules", [])]:
        for tier in ("standard", "experimental"):
            for cat, val in block.get(tier, {}).items():
                if isinstance(val, dict) and val.get("state") == "charge":
                    has_charge = True
                    break
    if has_charge and "payment" not in data.get("endpoints", {}):
        warnings.append("Manifest uses 'charge' state but no endpoints.payment is defined.")


def load_file(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        import urllib.request
        with urllib.request.urlopen(path_or_url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    else:
        with open(path_or_url, "r") as f:
            return json.load(f)


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <manifest.json or URL>")
        sys.exit(1)

    target = sys.argv[1]
    try:
        data = load_file(target)
    except json.JSONDecodeError as e:
        print(f"\nFAIL: Invalid JSON — {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFAIL: Could not load — {e}")
        sys.exit(1)

    errors, warnings = validate(data)
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

    # Summary
    pub = data.get("publisher", {}) if isinstance(data, dict) else {}
    defs = data.get("defaults", {}) if isinstance(data, dict) else {}
    std = defs.get("standard", {})
    exp = defs.get("experimental", {})
    emit = data.get("interop", {}).get("emit", []) if isinstance(data, dict) else []

    print(f"  Publisher:     {pub.get('name', 'N/A')}")
    print(f"  Contact:       {pub.get('contact', 'N/A')}")
    print(f"  Jurisdictions: {', '.join(pub.get('jurisdictions', [])) or 'N/A'}")
    std_summary = ", ".join(k + "=" + v.get("state", "?") for k, v in std.items() if isinstance(v, dict))
    exp_summary = ", ".join(k + "=" + v.get("state", "?") for k, v in exp.items() if isinstance(v, dict))
    print(f"  Standard:      {std_summary or 'None'}")
    print(f"  Experimental:  {exp_summary or 'None'}")
    print(f"  Rules:         {len(data.get('rules', []))} path-specific rule(s)")
    print(f"  Emit targets:  {', '.join(emit) or 'None specified'}")
    print()

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
