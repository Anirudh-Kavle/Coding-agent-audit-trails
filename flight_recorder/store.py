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


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    conn = get_conn()
    try:
        # Existing hackathon databases predate the Codex correlation fields.
        # Run the base schema, then migrate in place without deleting events.
        conn.executescript(SCHEMA_PATH.read_text())
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        for name in ("tool_kind", "tool_use_id", "turn_id", "provider", "model", "notification_sent", "token_count", "usage_json", "action_id", "completed_at"):
            if name not in columns:
                conn.execute(f"ALTER TABLE events ADD COLUMN {name} TEXT")
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        for name, definition in (("token_limit", "INTEGER"), ("time_limit_s", "INTEGER"), ("token_used", "INTEGER NOT NULL DEFAULT 0")):
            if name not in session_columns:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_tool_kind ON events(tool_kind)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_tool_use_id "
            "ON events(session_id, tool_use_id) WHERE tool_use_id IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_action_id "
            "ON events(session_id, action_id) WHERE action_id IS NOT NULL"
        )
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


def update_session_usage(conn: sqlite3.Connection, session_id: str, tokens: int) -> None:
    conn.execute("UPDATE sessions SET token_used = COALESCE(token_used, 0) + ? WHERE id = ?", (tokens, session_id))


def get_daily_usage(conn: sqlite3.Connection, day: str) -> int:
    row = conn.execute("SELECT token_count FROM api_usage WHERE day = ?", (day,)).fetchone()
    return int(row[0]) if row else 0


def add_daily_usage(conn: sqlite3.Connection, day: str, tokens: int, updated_at: int) -> None:
    conn.execute(
        """INSERT INTO api_usage(day, token_count, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(day) DO UPDATE SET token_count = api_usage.token_count + excluded.token_count,
           updated_at = excluded.updated_at""",
        (day, tokens, updated_at),
    )


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


def find_pre_event_by_tool_use_id(
    conn: sqlite3.Connection, session_id: str, tool_use_id: str
) -> sqlite3.Row | None:
    """Find the exact tool invocation awaiting its result."""
    return conn.execute(
        """
        SELECT * FROM events
        WHERE session_id = ? AND tool_use_id = ? AND phase = 'pre'
          AND (result_json IS NULL OR result_json = '')
        ORDER BY id DESC LIMIT 1
        """,
        (session_id, tool_use_id),
    ).fetchone()


def update_event_result(conn: sqlite3.Connection, event_id: int, result_json: str, exit_ok: int | None) -> None:
    conn.execute(
        "UPDATE events SET result_json = ?, exit_ok = ? WHERE id = ?",
        (result_json, exit_ok, event_id),
    )


def complete_event(conn: sqlite3.Connection, *, session_id: str, action_id: str,
                   tool: str, completed_at: int, result_json: str,
                   exit_ok: int) -> int | None:
    row = conn.execute(
        """SELECT id FROM events
           WHERE session_id = ? AND action_id = ? AND tool = ? AND phase = 'pre'
             AND (result_json IS NULL OR result_json = '')
           ORDER BY id DESC LIMIT 1""",
        (session_id, action_id, tool),
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE events SET completed_at = ?, result_json = ?, exit_ok = ? WHERE id = ?",
        (completed_at, result_json, exit_ok, row["id"]),
    )
    return row["id"]


def get_event(conn: sqlite3.Connection, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row else {}


def insert_event(conn: sqlite3.Connection, event: dict) -> int:
    cols = [
        "session_id", "ts", "phase", "tool", "action_id", "completed_at",
        "tool_kind", "tool_use_id",
        "turn_id", "provider", "model", "notification_sent", "token_count", "usage_json", "arguments_json", "result_json",
        "exit_ok", "reasoning_text", "risk", "risk_reasons", "capture_gap",
        "git_branch", "git_head", "git_dirty", "files_touched",
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
