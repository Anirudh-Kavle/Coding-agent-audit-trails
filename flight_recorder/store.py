"""Local storage layer: SQLite (WAL) + JSONL mirror.

No daemon. Every writer (the hook) opens, writes, closes. WAL mode
makes concurrent writers from multiple sessions safe.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

STORE_DIR = Path.home() / ".flight-recorder"
DB_PATH = STORE_DIR / "recorder.db"
EVENTS_DIR = STORE_DIR / "events"
SNAPSHOTS_DIR = STORE_DIR / "snapshots"
DEBUG_LOG = STORE_DIR / "debug.log"
RAW_PAYLOADS_LOG = STORE_DIR / "debug" / "raw_payloads.jsonl"

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def ensure_dirs() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PAYLOADS_LOG.parent.mkdir(parents=True, exist_ok=True)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns to pre-existing DBs from before this field existed.
    CREATE TABLE IF NOT EXISTS (in init_db) never alters an existing table,
    so installs from before tool_use_id was added need this to keep working."""
    if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
        return  # fresh DB — init_db()'s schema.sql already has the column
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "tool_use_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN tool_use_id TEXT")
        conn.commit()


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def init_db() -> None:
    ensure_dirs()
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()


def upsert_session(conn: sqlite3.Connection, session_id: str, ts: int, cwd: str | None,
                    git_repo: str | None, source: str | None) -> None:
    conn.execute(
        """
        INSERT INTO sessions (id, started_at, cwd, git_repo, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            cwd=excluded.cwd,
            git_repo=COALESCE(excluded.git_repo, sessions.git_repo)
        """,
        (session_id, ts, cwd, git_repo, source),
    )


def mark_session_ended(conn: sqlite3.Connection, session_id: str, ts: int) -> None:
    conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ts, session_id))


def find_pending_pre_event(conn: sqlite3.Connection, session_id: str, tool: str) -> sqlite3.Row | None:
    """The most recent unpaired 'pre' row for this session+tool, if any.

    Matched by session + tool + monotonic ordering (last one wins), per spec
    3.4. An empty result_json means PostToolUse hasn't paired with it yet.
    """
    return conn.execute(
        """
        SELECT * FROM events
        WHERE session_id = ? AND tool = ? AND phase = 'pre' AND (result_json IS NULL OR result_json = '')
        ORDER BY id DESC LIMIT 1
        """,
        (session_id, tool),
    ).fetchone()


def update_event_result(conn: sqlite3.Connection, event_id: int, result_json: str, exit_ok: int | None) -> None:
    conn.execute(
        "UPDATE events SET result_json = ?, exit_ok = ? WHERE id = ?",
        (result_json, exit_ok, event_id),
    )


def update_event_reasoning(conn: sqlite3.Connection, event_id: int, reasoning_text: str) -> None:
    """Self-heal path: a PreToolUse capture that came back as a gap because
    the transcript file hadn't caught up yet gets a second, later chance at
    PostToolUse time — patched in only when that retry actually succeeds."""
    conn.execute(
        "UPDATE events SET reasoning_text = ?, capture_gap = 0 WHERE id = ?",
        (reasoning_text, event_id),
    )


def find_stale_gaps(conn: sqlite3.Connection, session_id: str, now_ms: int, max_age_ms: int = 30 * 60 * 1000, limit: int = 5):
    """Still-gapped pre-events in this session, if any, bounded to a recency
    window. PostToolUse isn't guaranteed to fire (Claude Code can skip it —
    seen in practice), so self-heal there isn't a sure second look; any later
    hook in the same session is another opportunity to retry.

    Returns several candidates, not just the newest one: a batch of
    sequential calls with no narration between them (legitimate gaps) can
    sit in front of an older call that genuinely does have recoverable
    reasoning — checking only the single most recent gap lets that newer,
    permanently-unhealable one mask the older, healable one forever (seen in
    practice: three sequential Read calls where the newest two were
    legitimate gaps and permanently blocked the oldest, recoverable one from
    ever being retried). The age bound keeps a long run of unrecoverable
    gaps from costing every subsequent hook call an unbounded amount of work."""
    return conn.execute(
        """
        SELECT * FROM events
        WHERE session_id = ? AND phase = 'pre' AND capture_gap = 1
          AND tool IS NOT NULL AND tool_use_id IS NOT NULL AND ts >= ?
        ORDER BY id DESC LIMIT ?
        """,
        (session_id, now_ms - max_age_ms, limit),
    ).fetchall()


def insert_event(conn: sqlite3.Connection, event: dict) -> int:
    cols = [
        "session_id", "ts", "phase", "tool", "arguments_json", "result_json",
        "exit_ok", "reasoning_text", "risk", "risk_reasons", "capture_gap",
        "git_branch", "git_head", "git_dirty", "files_touched", "tool_use_id",
    ]
    values = [event.get(c) for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO events ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    return cur.lastrowid


def append_jsonl(event: dict) -> None:
    ensure_dirs()
    day = time.strftime("%Y-%m-%d", time.localtime(event.get("ts", time.time() * 1000) / 1000))
    path = EVENTS_DIR / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def append_raw_payload(hook_event_name: str, payload: dict) -> None:
    """Debug-only: dump every raw hook payload for later parser inspection."""
    ensure_dirs()
    record = {"_captured_at": time.time(), "_hook_event_name": hook_event_name, "payload": payload}
    try:
        with RAW_PAYLOADS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def log_debug(message: str) -> None:
    try:
        ensure_dirs()
        with DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass
