"""Deterministic risk classification, table-driven from risk_rules.yaml."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).with_name("risk_rules.yaml")

TIER_ORDER = ["info", "write", "exec", "network", "sensitive"]


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    with RULES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify(tool: str, arguments_text: str, result_text: str = "") -> tuple[str, list[str]]:
    """Return (risk_tier, reasons) for a tool call given its args and (once
    available) its result, both as text.

    Arguments are skipped for search_only_tools (Grep/Glob/WebSearch) — their
    whole argument is a search query, so matching against it just means
    someone searched *for* a risky word, not that anything risky happened.
    The result is always scanned regardless of tool, since a search result
    reflects real content, not intent.
    """
    rules = _load_rules()
    tier = rules.get("tool_tiers", {}).get(tool, rules.get("default_tier", "exec"))
    reasons: list[str] = []
    seen: set[str] = set()

    search_only = tool in rules.get("search_only_tools", [])
    texts = [t for t in (("" if search_only else arguments_text), result_text) if t]

    for pattern in rules.get("patterns", []):
        try:
            if not any(re.search(pattern["regex"], t) for t in texts):
                continue
        except re.error:
            continue

        reason = pattern["reason"]
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)

        pattern_tier = pattern.get("tier", "sensitive")
        if TIER_ORDER.index(pattern_tier) > TIER_ORDER.index(tier):
            tier = pattern_tier

    return tier, reasons
