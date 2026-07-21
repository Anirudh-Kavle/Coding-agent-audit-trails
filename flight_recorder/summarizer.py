"""Local, grounded session summaries via llama-cpp-python.

Design: the model is a writer, not a source of truth. Packaging of events is
deterministic, the prompt forbids outside knowledge, and every [event N]
citation the model emits is validated against the packaged set — invalid ones
are stripped. Summaries are cached in sessions.summary; generation only ever
happens on explicit request (it costs ~30s of CPU on a laptop).

Fully optional: without llama-cpp-python or a model file the rest of Flight
Recorder works unchanged. Set FLIGHT_RECORDER_MODEL to a .gguf path to
override discovery; FLIGHT_RECORDER_SUMMARY=0 disables the feature.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from . import store

MODELS_DIR = store.STORE_DIR / "models"
MAX_PACKED_CHARS = 7000   # keep prompt eval tolerable on CPU
MAX_LINE_CHARS = 300
MAX_SUMMARY_TOKENS = 256

CITATION_RE = re.compile(r"\[event\s+(\d+)\]", re.IGNORECASE)
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

SYSTEM_PROMPT = (
    "You summarize audit logs of AI coding-agent sessions. Use ONLY the "
    "numbered records provided. Never use outside knowledge and never guess "
    "beyond what the records show. Cite supporting records inline as "
    "[event ID]. If the records are insufficient to answer, say so plainly."
)

_llm = None
_llm_path: str | None = None
_llm_lock = threading.Lock()


def find_model() -> Path | None:
    override = os.environ.get("FLIGHT_RECORDER_MODEL")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    if MODELS_DIR.is_dir():
        candidates = sorted(MODELS_DIR.glob("*.gguf"))
        if candidates:
            return candidates[0]
    return None


def enabled() -> bool:
    if os.environ.get("FLIGHT_RECORDER_SUMMARY", "1").lower() in {"0", "false", "no", "off"}:
        return False
    if find_model() is None:
        return False
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        return False
    return True


def _fmt_ts(ts_ms: int) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts_ms / 1000))


def _compact_args(arguments_json: str | None) -> str:
    if not arguments_json:
        return ""
    try:
        args = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        return str(arguments_json)
    if not isinstance(args, dict):
        return str(args)
    # Surface the human-meaningful argument, not the whole JSON blob.
    for key in ("command", "file_path", "path", "pattern", "url", "prompt"):
        if isinstance(args.get(key), str):
            return f"{key}={args[key]}"
    return json.dumps(args, ensure_ascii=False)


def _event_line(row: dict) -> str:
    status = ""
    if row.get("exit_ok") == 0:
        status = " FAILED"
    risk = row.get("risk") or "info"
    parts = [
        f"[event {row['id']}] {_fmt_ts(row['ts'])} {row.get('tool')} ({risk}{status})",
        _compact_args(row.get("arguments_json")),
    ]
    reasoning = (row.get("reasoning_text") or "").strip()
    if reasoning:
        parts.append(f"why: {reasoning[:150]}")
    line = " | ".join(p for p in parts if p)
    return line[:MAX_LINE_CHARS]


def package_session(conn, session_id: str) -> tuple[str, set[int]]:
    """Deterministically render a session's actions as numbered log lines.

    Returns (packed_text, event_ids) — the ids let callers validate citations.
    When over budget, keeps the chronological head and tail and says how many
    middle events were omitted, so the story's start and outcome both survive.
    """
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM events WHERE session_id = ? AND tool IS NOT NULL ORDER BY ts ASC",
        (session_id,),
    ).fetchall()]
    if not rows:
        return "", set()

    lines = [_event_line(r) for r in rows]
    ids = {r["id"] for r in rows}
    total = sum(len(line) + 1 for line in lines)
    if total > MAX_PACKED_CHARS:
        head_budget = MAX_PACKED_CHARS // 4
        tail_budget = MAX_PACKED_CHARS - head_budget
        head: list[str] = []
        used = 0
        for line in lines:
            if used + len(line) + 1 > head_budget:
                break
            head.append(line)
            used += len(line) + 1
        tail: list[str] = []
        used = 0
        for line in reversed(lines[len(head):]):
            if used + len(line) + 1 > tail_budget:
                break
            tail.insert(0, line)
            used += len(line) + 1
        omitted = len(lines) - len(head) - len(tail)
        middle = [f"... {omitted} events omitted ..."] if omitted > 0 else []
        lines = head + middle + tail
    return "\n".join(lines), ids


def _strip_invalid_citations(text: str, valid_ids: set[int]) -> str:
    def repl(match: re.Match) -> str:
        return match.group(0) if int(match.group(1)) in valid_ids else ""
    return CITATION_RE.sub(repl, text).strip()


def _dedupe_repeated_citations(text: str) -> str:
    """The model sometimes cites the same event on every sentence when one
    record explains the whole session — correct, but [event 104] four times
    over reads as noise, not rigor. Keep the citation on its first mention
    and drop the marker (never the surrounding prose) on repeats."""
    seen: set[int] = set()

    def repl(match: re.Match) -> str:
        event_id = int(match.group(1))
        if event_id in seen:
            return ""
        seen.add(event_id)
        return match.group(0)

    deduped = CITATION_RE.sub(repl, text)
    # A removed marker can leave "ran the tests ." or "the code ," behind —
    # collapse the space that used to separate it from the citation.
    deduped = re.sub(r"[ \t]+([.,;:!?])", r"\1", deduped)
    deduped = re.sub(r"[ \t]{2,}", " ", deduped)
    return deduped.strip()


def _load_llm(model_path: Path):
    global _llm, _llm_path
    if _llm is not None and _llm_path == str(model_path):
        return _llm
    from llama_cpp import Llama

    _llm = Llama(model_path=str(model_path), n_ctx=8192, verbose=False)
    _llm_path = str(model_path)
    return _llm


def summarize_session(session_id: str, *, llm=None) -> dict | None:
    """Generate, validate, and cache a summary. Returns the summary record,
    or None when the session has no recorded actions."""
    conn = store.get_conn()
    try:
        packed, valid_ids = package_session(conn, session_id)
    finally:
        conn.close()
    if not packed:
        return None

    model_path = find_model()
    model_name = model_path.name if model_path else "injected"
    if llm is None:
        if model_path is None:
            raise RuntimeError(f"no .gguf model found in {MODELS_DIR} (or FLIGHT_RECORDER_MODEL)")
        llm = _load_llm(model_path)

    user_prompt = (
        f"Audit records for session {session_id}:\n{packed}\n\n"
        "Write a 3-5 sentence summary of this session: what the agent worked "
        "on (inferred only from the visible actions), what it changed or ran, "
        "and any failures or sensitive actions.\n"
        "REQUIRED FORMAT: every sentence must include at least one inline "
        "citation like [event 12] pointing at a record above. Example "
        "sentence: 'The agent installed dependencies [event 12] and ran the "
        "tests, which failed [event 15].' Citations go inside the sentences, "
        "never in a list at the end. Cite each record at most once in the "
        "whole summary — if one record covers several sentences, cite it "
        "only the first time. /no_think"
    )

    with _llm_lock:  # one llama.cpp context; concurrent calls would corrupt it
        result = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=MAX_SUMMARY_TOKENS,
        )

    text = result["choices"][0]["message"]["content"] or ""
    text = THINK_RE.sub("", text).strip()
    text = _strip_invalid_citations(text, valid_ids)
    text = _dedupe_repeated_citations(text)
    if not text:
        return None

    record = {"text": text, "model": model_name, "generated_at": int(time.time() * 1000)}
    conn = store.get_conn()
    try:
        conn.execute(
            "UPDATE sessions SET summary = ? WHERE id = ?",
            (json.dumps(record, ensure_ascii=False), session_id),
        )
        conn.commit()
    finally:
        conn.close()
    return record


def load_cached_summary(conn, session_id: str) -> dict | None:
    row = conn.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row or not row["summary"]:
        return None
    try:
        parsed = json.loads(row["summary"])
        if isinstance(parsed, dict) and "text" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass
    # Plain-string summaries predate this pipeline (no citations, unknown
    # provenance) — flag them so the UI can suggest regenerating.
    return {"text": str(row["summary"]), "model": None, "generated_at": None, "legacy": True}
