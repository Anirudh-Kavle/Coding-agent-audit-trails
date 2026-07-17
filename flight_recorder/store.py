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


def insert_event(conn: sqlite3.Connection, event: dict) -> int:
    cols = [
        "session_id", "ts", "phase", "tool", "arguments_json", "result_json",
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
