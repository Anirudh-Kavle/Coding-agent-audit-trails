"""Local, deterministic API usage and session-budget helpers."""
from __future__ import annotations

from datetime import date
import time


def usage_tokens(usage) -> int:
    if usage is None:
        return 0
    for name in ("total_tokens", "totalTokens"):
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if isinstance(value, int):
            return value
    total = 0
    for name in ("input_tokens", "output_tokens", "inputTokens", "outputTokens"):
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if isinstance(value, int):
            total += value
    return total


def today() -> str:
    return date.today().isoformat()


def elapsed_seconds(started: float) -> int:
    return max(0, int(time.monotonic() - started))
