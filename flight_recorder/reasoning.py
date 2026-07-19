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


def _find_tool_use_index(entries: list[dict], tool_use_id: str) -> int | None:
    """Index of the entry containing a tool_use block with this id, if any."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else entry
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id") == tool_use_id:
                return i
    return None


def extract_reasoning(transcript_path: str | None, tool_use_id: str | None = None) -> tuple[str | None, bool]:
    """Returns (reasoning_text, capture_gap).

    The hook payload (tool_name, tool_input, tool_use_id) comes from Claude
    Code's live in-memory dispatch; the transcript *file* write can lag
    behind it. If the file doesn't yet contain this exact tool_use_id,
    anything sitting at its tail belongs to an earlier, already-finished
    turn — attaching it here would misattribute stale reasoning to this
    action. An honest gap beats a confident wrong answer.
    """
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

    if tool_use_id:
        idx = _find_tool_use_index(entries, tool_use_id)
        if idx is None:
            return None, True  # freshness gate: file hasn't caught up to this call yet
        # Anchor the walk to this call's position — ignore anything appended
        # after it (its own tool_result almost always lands here by the time
        # a PostToolUse self-heal retry runs), so the search isn't blocked by
        # a boundary that belongs to a *later* point than the call itself.
        entries = entries[: idx + 1]

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
            # Boundary: a tool result (the prior action's output) or a fresh
            # human prompt both end the window — either way, anything
            # earlier belongs to a different action or a different turn.
            break

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
