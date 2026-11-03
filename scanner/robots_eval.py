"""Minimal RFC 9309 evaluator: groups of consecutive User-Agent lines,
case-insensitive product tokens, '*' wildcard, trailing '$' anchor, longest match
wins, Allow wins a tie, no match means allowed. Shared by the scanner and the compiler tests."""
import re


def parse(text):
    groups, current = [], None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if current is None or current["rules"]:
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            current["rules"].append((key, value))
    return groups


def groups_for(groups, agent):
    """Groups that apply to agent: those naming it, else those naming '*' (RFC 9309 2.2.1)."""
    agent = agent.lower()
    return [g for g in groups if agent in g["agents"]] or [g for g in groups if "*" in g["agents"]]


def _matches(pattern, path):
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.match("^" + rx + ("$" if anchored else ""), path) is not None


def can_fetch(text, agent, path):
    best = None  # (length, is_allow)
    for g in groups_for(parse(text), agent):
        for kind, pattern in g["rules"]:
            if pattern == "" and kind == "disallow":
                continue  # empty Disallow allows everything
            if _matches(pattern, path):
                cand = (len(pattern), kind == "allow")
                if best is None or cand > best:
                    best = cand
    return True if best is None else best[1]
