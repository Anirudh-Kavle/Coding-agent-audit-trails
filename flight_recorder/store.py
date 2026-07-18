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
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply small, idempotent migrations to databases made by older builds."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "action_id" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN action_id TEXT")
    if "completed_at" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN completed_at INTEGER")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_action "
        "ON events(session_id, action_id) WHERE action_id IS NOT NULL"
    )


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


def insert_event(conn: sqlite3.Connection, event: dict) -> int:
    cols = [
        "session_id", "action_id", "ts", "completed_at", "phase", "tool", "arguments_json", "result_json",
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


def complete_event(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    action_id: str | None,
    tool: str | None,
    completed_at: int,
    result_json: str,
    exit_ok: int,
) -> int | None:
    """Pair a result with its pre-action row and return that row's id."""
    row = None
    if action_id:
        row = conn.execute(
            "SELECT id FROM events WHERE session_id = ? AND action_id = ?",
            (session_id, action_id),
        ).fetchone()
    if row is None:
        row = conn.execute(
            """
            SELECT id FROM events
            WHERE session_id = ? AND tool IS ? AND completed_at IS NULL
                  AND phase = 'pre'
            ORDER BY id DESC LIMIT 1
            """,
            (session_id, tool),
        ).fetchone()
    if row is None:
        return None
    event_id = int(row[0])
    conn.execute(
        """
        UPDATE events
        SET phase = 'post', completed_at = ?, result_json = ?, exit_ok = ?
        WHERE id = ?
        """,
        (completed_at, result_json, exit_ok, event_id),
    )
    return event_id


def get_event(conn: sqlite3.Connection, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise KeyError(event_id)
    return dict(row)


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
