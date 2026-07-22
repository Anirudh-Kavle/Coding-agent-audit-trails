"""Local storage layer: SQLite (WAL) + JSONL mirror.

No daemon. Every writer (the hook) opens, writes, closes. WAL mode
makes concurrent writers from multiple sessions safe.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

STORE_DIR = Path.home() / ".zetesis"
_LEGACY_STORE_DIR = Path.home() / ".flight-recorder"
DB_PATH = STORE_DIR / "recorder.db"
EVENTS_DIR = STORE_DIR / "events"
SNAPSHOTS_DIR = STORE_DIR / "snapshots"
DEBUG_LOG = STORE_DIR / "debug.log"
RAW_PAYLOADS_LOG = STORE_DIR / "debug" / "raw_payloads.jsonl"
PAUSE_FLAG = STORE_DIR / "paused"

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def ensure_dirs() -> None:
    if _LEGACY_STORE_DIR.is_dir() and not STORE_DIR.exists():
        _LEGACY_STORE_DIR.rename(STORE_DIR)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PAYLOADS_LOG.parent.mkdir(parents=True, exist_ok=True)


def is_paused() -> bool:
    return PAUSE_FLAG.exists()


def set_paused(paused: bool) -> None:
    """Toggled from the viewer's record button. A bare marker file, not a DB
    row — the hook must be able to check this before it ever touches SQLite,
    including while the DB is mid-wipe."""
    ensure_dirs()
    if paused:
        PAUSE_FLAG.touch()
    else:
        PAUSE_FLAG.unlink(missing_ok=True)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return  # fresh DB — init_db()'s schema.sql already has the column
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns to pre-existing DBs from before these fields existed.
    CREATE TABLE IF NOT EXISTS (in init_db) never alters an existing table,
    so installs from before tool_use_id/title were added need this to keep
    working."""
    _add_column_if_missing(conn, "events", "tool_use_id", "TEXT")
    _add_column_if_missing(conn, "sessions", "title", "TEXT")


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
        # Existing hackathon databases predate the Codex correlation fields.
        # Run the base schema, then migrate in place without deleting events.
        had_update_trigger = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='events_au'"
        ).fetchone() is not None
        conn.executescript(SCHEMA_PATH.read_text())
        if not had_update_trigger:
            # Rows updated before the AFTER UPDATE trigger existed (paired
            # results, healed reasoning) are stale in the FTS index; repopulate
            # once from the content table. (FTS5's 'rebuild' command can't be
            # used here: the index column names don't match the events table's.)
            conn.execute("INSERT INTO events_fts(events_fts) VALUES('delete-all')")
            conn.execute(
                "INSERT INTO events_fts(rowid, arguments_text, reasoning_text) "
                "SELECT id, arguments_json, reasoning_text FROM events"
            )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        for name in ("tool_kind", "tool_use_id", "turn_id", "provider", "model", "notification_sent", "token_count", "usage_json", "action_id", "completed_at"):
            if name not in columns:
                conn.execute(f"ALTER TABLE events ADD COLUMN {name} TEXT")
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        for name, definition in (("token_limit", "INTEGER"), ("time_limit_s", "INTEGER"), ("token_used", "INTEGER NOT NULL DEFAULT 0"), ("current_turn_id", "TEXT")):
            if name not in session_columns:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_tool_kind ON events(tool_kind)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS budget_settings (scope TEXT PRIMARY KEY, token_limit INTEGER, time_limit_s INTEGER, updated_at INTEGER NOT NULL)"
        )
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


def apply_provider_budget(conn: sqlite3.Connection, session_id: str, provider: str) -> None:
    """Seed a new native-agent session from its configured provider cap.

    Existing usage and limits are never overwritten. This makes a fresh chat
    inherit the current Claude/Codex/API budget while resumed chats keep the
    cap they started with.
    """
    scope = "openai-api" if provider == "api" else provider
    conn.execute(
        """UPDATE sessions
           SET token_limit = COALESCE(token_limit, (SELECT token_limit FROM budget_settings WHERE scope = ?)),
               time_limit_s = COALESCE(time_limit_s, (SELECT time_limit_s FROM budget_settings WHERE scope = ?))
           WHERE id = ?""",
        (scope, scope, session_id),
    )


def mark_session_ended(conn: sqlite3.Connection, session_id: str, ts: int) -> None:
    conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ts, session_id))


def set_session_turn(conn: sqlite3.Connection, session_id: str, turn_id: str) -> None:
    """Record the id of the turn currently in progress for this session.

    Claude Code's hook payloads carry no per-turn identifier of their own
    (unlike Codex, which sometimes does), so the hook mints one itself on
    every UserPromptSubmit/SessionStart and every subsequent tool-use event
    in that session is stamped with whatever this currently holds — that's
    what lets the viewer group "everything from one prompt" together."""
    conn.execute("UPDATE sessions SET current_turn_id = ? WHERE id = ?", (turn_id, session_id))


def get_session_turn(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute("SELECT current_turn_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row["current_turn_id"] if row else None


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


def session_needs_title(conn: sqlite3.Connection, session_id: str) -> bool:
    """Whether this session still lacks a sidebar title — gates the hook
    from re-deriving one on every single call once it's already been found."""
    row = conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row is not None and not row["title"]


def set_session_title(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))


def title_from_text(text: str, max_len: int = 80) -> str:
    """First line of a prompt/task, capped for the sidebar — the fallback
    title source for Codex and the API agent, neither of which write a
    Claude-style "ai-title" transcript entry for extract_session_title()."""
    first_line = text.strip().splitlines()[0].strip()
    return first_line if len(first_line) <= max_len else first_line[:max_len - 1].rstrip() + "…"


def get_budget(conn: sqlite3.Connection, scope: str) -> sqlite3.Row | None:
    return conn.execute("SELECT scope, token_limit, time_limit_s, updated_at FROM budget_settings WHERE scope = ?", (scope,)).fetchone()


def set_budget(conn: sqlite3.Connection, scope: str, token_limit: int | None,
               time_limit_s: int | None, updated_at: int) -> None:
    conn.execute(
        """INSERT INTO budget_settings(scope, token_limit, time_limit_s, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(scope) DO UPDATE SET token_limit = excluded.token_limit,
           time_limit_s = excluded.time_limit_s, updated_at = excluded.updated_at""",
        (scope, token_limit, time_limit_s, updated_at),
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


def update_event_result(
    conn: sqlite3.Connection, event_id: int, result_json: str, exit_ok: int | None,
    risk_tier: str, risk_reasons_json: str,
) -> None:
    """risk/risk_reasons are re-passed here (not just result_json/exit_ok)
    because the row was first classified from arguments alone at PreToolUse
    time — the result can carry its own risk signal (e.g. a secret in the
    output) that only exists once the tool has actually run."""
    conn.execute(
        "UPDATE events SET result_json = ?, exit_ok = ?, risk = ?, risk_reasons = ? WHERE id = ?",
        (result_json, exit_ok, risk_tier, risk_reasons_json, event_id),
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
