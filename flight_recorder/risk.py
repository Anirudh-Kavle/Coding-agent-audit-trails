"""Deterministic risk classification, table-driven from risk_rules.yaml."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

try:
    import yaml
except ImportError:  # F1/F2 stay usable before optional app dependencies are installed.
    yaml = None

RULES_PATH = Path(__file__).with_name("risk_rules.yaml")

TIER_ORDER = ["info", "write", "exec", "network", "sensitive"]

FALLBACK_RULES = {
    "tool_tiers": {
        "Read": "info", "Glob": "info", "Grep": "info", "LS": "info",
        "Edit": "write", "Write": "write", "NotebookEdit": "write",
        "Bash": "exec", "WebFetch": "network", "WebSearch": "network",
    },
    "default_tier": "exec",
    "patterns": [],
}


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    if yaml is None:
        return FALLBACK_RULES
    with RULES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify(tool: str, arguments_text: str) -> tuple[str, list[str]]:
    """Return (risk_tier, reasons) for a tool call given its args as text."""
    rules = _load_rules()
    tier = rules.get("tool_tiers", {}).get(tool, rules.get("default_tier", "exec"))
    reasons: list[str] = []

    for pattern in rules.get("patterns", []):
        try:
            if re.search(pattern["regex"], arguments_text or ""):
                reasons.append(pattern["reason"])
        except re.error:
            continue

    if reasons:
        tier = "sensitive"

    return tier, reasons
