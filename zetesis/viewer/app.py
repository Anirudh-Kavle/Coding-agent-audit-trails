"""fr-viewer: read-only FastAPI app over the SQLite store. No daemon
writes here — the hook is the only writer. This process just reads."""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import store

app = FastAPI(title="Zetesis")

# Claude/Codex providers can occasionally deliver PreToolUse and PostToolUse
# as separate rows. Do not show the empty pre-row when a completed post-row is
# already present; the selected UI action should expose its actual result.
COMPLETED_ACTION_FILTER = """(
    phase != 'pre'
    OR (result_json IS NOT NULL AND result_json != '')
    OR NOT EXISTS (
        SELECT 1 FROM events completed
        WHERE completed.session_id = events.session_id
          AND completed.tool = events.tool
          AND completed.phase = 'post'
          AND completed.ts >= events.ts
          AND (events.tool_use_id IS NULL OR completed.tool_use_id = events.tool_use_id)
    )
)"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(store.DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _event_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["risk_reasons"] = json.loads(d.get("risk_reasons") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["risk_reasons"] = []
    return d


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.started_at, s.ended_at, s.cwd, s.git_repo, s.source,
                   s.token_limit, s.time_limit_s, s.token_used,
                   COUNT(e.id) as event_count, MAX(e.ts) as last_event_ts,
                   COALESCE(
                       (SELECT provider FROM events
                        WHERE session_id = s.id AND provider IS NOT NULL
                        ORDER BY ts ASC LIMIT 1),
                       CASE WHEN s.source IN ('claude', 'codex', 'openai-api') THEN s.source END
                   ) as provider
            FROM sessions s
            LEFT JOIN events e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY COALESCE(MAX(e.ts), s.started_at) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/usage")
def usage() -> dict:
    conn = _conn()
    try:
        row = conn.execute("SELECT day, token_count, updated_at FROM api_usage WHERE day = ?", (date.today().isoformat(),)).fetchone()
        return dict(row) if row else {"day": date.today().isoformat(), "token_count": 0, "updated_at": None}
    finally:
        conn.close()


def _budget_value(raw, name: str):
    if raw in (None, "", 0, "0"):
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be a positive integer or null")
    if number < 1:
        raise HTTPException(400, f"{name} must be a positive integer or null")
    return number


@app.get("/api/budgets")
def budgets() -> list[dict]:
    conn = _conn()
    try:
        scopes = ["global", "claude", "codex", "openai-api"]
        out = []
        for scope in scopes:
            row = store.get_budget(conn, scope)
            if scope == "global":
                used = conn.execute("SELECT COALESCE(SUM(token_used), 0) FROM sessions").fetchone()[0]
            else:
                used = conn.execute(
                    """SELECT COALESCE(SUM(s.token_used), 0) FROM sessions s
                       WHERE COALESCE((SELECT provider FROM events e WHERE e.session_id = s.id AND e.provider IS NOT NULL ORDER BY e.ts DESC LIMIT 1), s.source) = ?""",
                    (scope,),
                ).fetchone()[0]
            out.append({"scope": scope, "token_limit": row["token_limit"] if row else None,
                        "time_limit_s": row["time_limit_s"] if row else None,
                        "token_used": int(used or 0)})
        return out
    finally:
        conn.close()


@app.patch("/api/budgets/{scope}")
def update_scope_budget(scope: str, payload: dict) -> dict:
    if scope not in {"global", "claude", "codex", "openai-api"}:
        raise HTTPException(400, "Unknown budget scope")
    token_limit = _budget_value(payload.get("token_limit"), "token_limit")
    time_limit_s = _budget_value(payload.get("time_limit_s"), "time_limit_s")
    conn = _conn()
    try:
        store.set_budget(conn, scope, token_limit, time_limit_s, int(__import__("time").time() * 1000))
        conn.commit()
        return {"scope": scope, "token_limit": token_limit, "time_limit_s": time_limit_s}
    finally:
        conn.close()


@app.patch("/api/sessions/{session_id}/budget")
def update_budget(session_id: str, payload: dict) -> dict:
    """Update the shared API session limits used by the terminal agent."""
    token_limit = _budget_value(payload.get("token_limit"), "token_limit")
    time_limit_s = _budget_value(payload.get("time_limit_s"), "time_limit_s")
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
            raise HTTPException(404, "Session not found")
        conn.execute("UPDATE sessions SET token_limit = ?, time_limit_s = ? WHERE id = ?",
                     (token_limit, time_limit_s, session_id))
        conn.commit()
        row = conn.execute("SELECT id, token_limit, time_limit_s, token_used FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}/events")
def session_events(session_id: str, risk: str | None = None, limit: int = 500) -> list[dict]:
    conn = _conn()
    try:
        # session_id "all" means no session filter — the viewer's full-history load.
        # tool IS NOT NULL excludes toolless lifecycle bookkeeping (SessionStart/
        # End, Stop, PreCompact) — real audit rows, just not "actions" the
        # timeline has a WHAT/WHY to show; they'd otherwise render as a bare
        # "null" tool badge with nothing else in it.
        where: list[str] = ["tool IS NOT NULL", COMPLETED_ACTION_FILTER]
        params: list = []
        if session_id != "all":
            where.append("session_id = ?")
            params.append(session_id)
        if risk:
            where.append("risk = ?")
            params.append(risk)
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [_event_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/events/{event_id}")
def event_detail(event_id: int) -> dict | None:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _event_to_dict(row) if row else None
    finally:
        conn.close()


QUALIFIER_RE = re.compile(r"(\w+):(\S+)")


@app.get("/api/search")
def search(q: str = "", limit: int = 200) -> list[dict]:
    qualifiers = dict(QUALIFIER_RE.findall(q))
    free_text = QUALIFIER_RE.sub("", q).strip()

    conn = _conn()
    try:
        conditions = ["tool IS NOT NULL", COMPLETED_ACTION_FILTER]
        params: list = []

        if free_text:
            fts_ids = conn.execute(
                "SELECT rowid FROM events_fts WHERE events_fts MATCH ?", (free_text + "*",)
            ).fetchall()
            ids = [r[0] for r in fts_ids]
            if not ids:
                return []
            conditions.append(f"id IN ({','.join('?' for _ in ids)})")
            params.extend(ids)

        if "risk" in qualifiers:
            conditions.append("risk = ?")
            params.append(qualifiers["risk"])
        if "tool" in qualifiers:
            conditions.append("LOWER(tool) = LOWER(?)")
            params.append(qualifiers["tool"])
        if "kind" in qualifiers:
            conditions.append("LOWER(tool_kind) = LOWER(?)")
            params.append(qualifiers["kind"])
        if "session" in qualifiers:
            conditions.append("session_id LIKE ?")
            params.append(qualifiers["session"] + "%")
        if "file" in qualifiers:
            conditions.append("arguments_json LIKE ?")
            params.append(f"%{qualifiers['file']}%")

        sql = "SELECT * FROM events"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_event_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/recording")
def get_recording() -> dict:
    return {"paused": store.is_paused()}


@app.post("/api/recording/pause")
def pause_recording() -> dict:
    store.set_paused(True)
    return {"paused": True}


@app.post("/api/recording/resume")
def resume_recording() -> dict:
    store.set_paused(False)
    return {"paused": False}


@app.get("/api/stream")
async def stream():
    async def gen():
        conn = _conn()
        try:
            last_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
            while True:
                rows = conn.execute(
                    f"SELECT * FROM events WHERE id > ? AND tool IS NOT NULL AND {COMPLETED_ACTION_FILTER} ORDER BY id ASC", (last_id,)
                ).fetchall()
                for row in rows:
                    d = _event_to_dict(row)
                    last_id = d["id"]
                    yield f"data: {json.dumps(d, default=str)}\n\n"
                await asyncio.sleep(1.0)
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


# The React viewer, mounted last so /api/* routes always win.
# ponytail: repo-relative dist path; breaks for pip-installed wheels — package
# the dist as data files if we ever ship one.
DIST_DIR = Path(__file__).resolve().parents[2] / "viewer" / "dist"
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="ui")
else:

    @app.get("/")
    def index() -> dict:
        return {
            "app": "zetesis",
            "api": "/api/sessions",
            "ui": "cd viewer && npm run build, or npm run dev (:5173 proxies /api)",
        }
