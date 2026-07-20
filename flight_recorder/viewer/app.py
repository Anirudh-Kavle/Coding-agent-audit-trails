"""fr-viewer: read-only FastAPI app over the SQLite store. No daemon
writes here — the hook is the only writer. This process just reads."""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import store

app = FastAPI(title="Flight Recorder")


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
        # Deterministic per-session stat line: plain SQL counts, no inference.
        # tool_kind can be NULL on rows from before normalization existed, so
        # edit/bash counts also fall back to the raw tool name.
        rows = conn.execute(
            """
            SELECT s.id, s.started_at, s.ended_at, s.cwd, s.git_repo, s.source,
                   s.token_limit, s.time_limit_s, s.token_used,
                   COUNT(e.id) as event_count, MAX(e.ts) as last_event_ts,
                   COUNT(e.id) FILTER (WHERE e.tool IS NOT NULL) AS action_count,
                   COUNT(e.id) FILTER (WHERE e.tool_kind IN ('edit', 'write')
                       OR LOWER(e.tool) IN ('edit', 'write', 'notebookedit', 'apply_patch', 'write_file')) AS edit_count,
                   COUNT(e.id) FILTER (WHERE e.tool_kind = 'bash'
                       OR LOWER(e.tool) IN ('bash', 'run_command')) AS bash_count,
                   COUNT(e.id) FILTER (WHERE e.exit_ok = 0) AS failed_count,
                   COUNT(e.id) FILTER (WHERE e.risk = 'sensitive') AS sensitive_count,
                   MAX(e.git_branch) AS git_branch
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


@app.get("/api/sessions/{session_id}/events")
def session_events(session_id: str, risk: str | None = None, limit: int = 500) -> list[dict]:
    conn = _conn()
    try:
        # session_id "all" means no session filter — the viewer's full-history load.
        # tool IS NOT NULL excludes toolless lifecycle bookkeeping (SessionStart/
        # End, Stop, PreCompact) — real audit rows, just not "actions" the
        # timeline has a WHAT/WHY to show; they'd otherwise render as a bare
        # "null" tool badge with nothing else in it.
        where: list[str] = ["tool IS NOT NULL"]
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


def _day_to_ms(value: str) -> int | None:
    """Parse a YYYY-MM-DD qualifier value to local-midnight epoch millis."""
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return None


def _fts_match(free_text: str) -> str:
    """Quote each term so user punctuation can't be parsed as FTS5 operators;
    the final term matches as a prefix for search-as-you-type."""
    terms = [t.replace('"', '""') for t in free_text.split()]
    return " ".join(f'"{t}"*' for t in terms)


@app.get("/api/search")
def search(q: str = "", limit: int = 200) -> list[dict]:
    qualifiers = dict(QUALIFIER_RE.findall(q))
    free_text = QUALIFIER_RE.sub("", q).strip()

    conn = _conn()
    try:
        conditions = ["tool IS NOT NULL"]
        params: list = []

        if free_text:
            fts_ids = conn.execute(
                "SELECT rowid FROM events_fts WHERE events_fts MATCH ?", (_fts_match(free_text),)
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
        if "provider" in qualifiers:
            conditions.append("LOWER(provider) = LOWER(?)")
            params.append(qualifiers["provider"])
        if "exit" in qualifiers:
            # exit:fail finds every action that errored; exit:ok the inverse.
            conditions.append("exit_ok = ?")
            params.append(1 if qualifiers["exit"].lower() in {"ok", "pass", "success"} else 0)
        if "after" in qualifiers and (after_ms := _day_to_ms(qualifiers["after"])) is not None:
            conditions.append("ts >= ?")
            params.append(after_ms)
        if "before" in qualifiers and (before_ms := _day_to_ms(qualifiers["before"])) is not None:
            conditions.append("ts < ?")
            params.append(before_ms)

        sql = "SELECT * FROM events"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_event_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}/summary")
def get_summary(session_id: str) -> dict:
    """Cached local-LLM summary plus whether generation is possible here."""
    from .. import summarizer

    conn = _conn()
    try:
        cached = summarizer.load_cached_summary(conn, session_id)
    finally:
        conn.close()
    return {"summary": cached, "available": summarizer.enabled()}


@app.post("/api/sessions/{session_id}/summary")
def generate_summary(session_id: str) -> dict:
    """Generate (or regenerate) a summary with the local model. Slow on CPU —
    tens of seconds — which is why it only ever runs on explicit request.
    Sync endpoint on purpose: FastAPI runs it in a worker thread."""
    from .. import summarizer

    if not summarizer.enabled():
        return {"summary": None, "available": False,
                "error": f"no local model — put a .gguf in {summarizer.MODELS_DIR}"}
    try:
        record = summarizer.summarize_session(session_id)
    except Exception as exc:
        return {"summary": None, "available": True, "error": str(exc)}
    return {"summary": record, "available": True}


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
                    "SELECT * FROM events WHERE id > ? AND tool IS NOT NULL ORDER BY id ASC", (last_id,)
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
            "app": "flight-recorder",
            "api": "/api/sessions",
            "ui": "cd viewer && npm run build, or npm run dev (:5173 proxies /api)",
        }
