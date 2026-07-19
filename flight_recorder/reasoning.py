"""Reasoning-window extraction from a live Codex transcript (F2).

Defensive by design (per spec: "verbatim > clever", never trust the
shape). This has NOT yet been validated against real transcript
payloads — that's the Day 1 spike task (dump raw samples to
docs/payloads/ and adjust this parser against them). Until then,
capture_gap=True is a legitimate, expected outcome, not a bug.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_TAIL_BYTES = 64 * 1024
MAX_REASONING_LEN = 8 * 1024


def _tail_lines(path: Path, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()  # drop the partial first line
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore")
    return [line for line in text.split("\n") if line.strip()]


def _parse_entries(lines: list[str]) -> list[dict]:
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def extract_reasoning(transcript_path: str | None) -> tuple[str | None, bool]:
    """Returns (reasoning_text, capture_gap)."""
    if not transcript_path:
        return None, True

    path = Path(transcript_path)
    if not path.exists():
        return None, True

    try:
        entries = _parse_entries(_tail_lines(path, MAX_TAIL_BYTES))
    except Exception:
        return None, True

    if not entries:
        return None, True

    collected: list[str] = []  # accumulated newest-first, reversed at the end

    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else entry
        role = entry.get("type") or message.get("role")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue

        if role == "assistant":
            texts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and block.get("text"):
                    texts.append(block["text"])
                elif block_type == "thinking" and block.get("thinking"):
                    texts.append(block["thinking"])
            if texts:
                collected.append("\n".join(texts))
        elif role == "user":
            has_tool_result = any(
                isinstance(block, dict) and block.get("type") == "tool_result" for block in content
            )
            if has_tool_result:
                break  # boundary: the prior action's result — reasoning window ends here

    if not collected:
        return None, True

    reasoning = "\n\n".join(reversed(collected)).strip()
    if not reasoning:
        return None, True

    if len(reasoning) > MAX_REASONING_LEN:
        reasoning = "[...truncated...]\n" + reasoning[-MAX_REASONING_LEN:]

    return reasoning, False


def snapshot_transcript(transcript_path: str | None, session_id: str, snapshots_dir: Path) -> Path | None:
    """PreCompact shield: copy the transcript before Codex compacts it."""
    if not transcript_path:
        return None
    src = Path(transcript_path)
    if not src.exists():
        return None

    import shutil
    import time

    dest_dir = snapshots_dir / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{int(time.time() * 1000)}.jsonl"
    try:
        shutil.copy2(src, dest)
        return dest
    except Exception:
        return None
