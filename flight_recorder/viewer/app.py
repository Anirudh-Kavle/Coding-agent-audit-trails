"""fr-viewer: read-only FastAPI app over the SQLite store. No daemon
writes here — the hook is the only writer. This process just reads."""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import store

app = FastAPI(title="Flight Recorder")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.started_at, s.ended_at, s.cwd, s.git_repo, s.source,
                   COUNT(e.id) as event_count, MAX(e.ts) as last_event_ts
            FROM sessions s
            LEFT JOIN events e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY COALESCE(MAX(e.ts), s.started_at) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}/events")
def session_events(session_id: str, risk: str | None = None, limit: int = 500) -> list[dict]:
    conn = _conn()
    try:
        sql = "SELECT * FROM events WHERE session_id = ?"
        params: list = [session_id]
        if risk:
            sql += " AND risk = ?"
            params.append(risk)
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
        conditions = []
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


@app.get("/api/stream")
async def stream():
    async def gen():
        conn = _conn()
        try:
            last_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
            while True:
                rows = conn.execute(
                    "SELECT * FROM events WHERE id > ? ORDER BY id ASC", (last_id,)
                ).fetchall()
                for row in rows:
                    d = _event_to_dict(row)
                    last_id = d["id"]
                    yield f"data: {json.dumps(d, default=str)}\n\n"
                await asyncio.sleep(1.0)
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream")
