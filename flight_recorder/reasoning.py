"""Defensive, verbatim reasoning-window extraction for F2."""
from __future__ import annotations

import json
from pathlib import Path

MAX_TAIL_BYTES = 64 * 1024
MAX_REASONING_LEN = 8 * 1024


def _tail_lines(path: Path, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        raw = handle.read()
    return [line for line in raw.decode("utf-8", errors="ignore").split("\n") if line.strip()]


def _parse_entries(lines: list[str]) -> list[dict]:
    entries = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


def _message(entry: dict) -> tuple[str | None, object]:
    message = entry.get("message") if isinstance(entry.get("message"), dict) else entry
    return message.get("role") or entry.get("type"), message.get("content")


def _block_id(block: dict) -> str | None:
    return block.get("id") or block.get("tool_use_id") or block.get("call_id")


def extract_reasoning_from_entries(
    entries: list[dict], action_id: str | None = None
) -> tuple[str | None, bool]:
    """Return the assistant text/thinking immediately before one tool call."""
    collected: list[str] = []
    found_current_action = False

    for entry in reversed(entries):
        role, content = _message(entry)
        if role == "user" and isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                break
            continue
        if role != "assistant":
            continue
        if isinstance(content, str):
            if content.strip():
                collected.append(content)
            continue
        if not isinstance(content, list):
            continue

        tool_indexes = [
            i for i, block in enumerate(content)
            if isinstance(block, dict) and block.get("type") in ("tool_use", "function_call")
        ]
        cutoff = len(content)
        if tool_indexes:
            matching = [
                i for i in tool_indexes
                if action_id is not None and _block_id(content[i]) == action_id
            ]
            if matching:
                cutoff = matching[-1]
                found_current_action = True
            elif not found_current_action:
                cutoff = tool_indexes[-1]
                found_current_action = True
            else:
                break

        texts = [
            block.get("text", "")
            for block in content[:cutoff]
            if isinstance(block, dict)
            and block.get("type") in ("text", "thinking", "reasoning", "reasoning_summary")
            and block.get("text")
        ]
        if texts:
            collected.append("\n".join(texts))

    if not collected:
        return None, True
    reasoning = "\n\n".join(reversed(collected)).strip()
    if not reasoning:
        return None, True
    if len(reasoning) > MAX_REASONING_LEN:
        reasoning = "[...truncated...]\n" + reasoning[-MAX_REASONING_LEN:]
    return reasoning, False


def extract_reasoning(
    transcript_path: str | None, action_id: str | None = None
) -> tuple[str | None, bool]:
    """Return ``(reasoning_text, capture_gap)`` from a JSONL transcript."""
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
    return extract_reasoning_from_entries(entries, action_id)


def snapshot_transcript(transcript_path: str | None, session_id: str, snapshots_dir: Path) -> Path | None:
    """Copy a transcript before compaction can destroy the reasoning source."""
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
