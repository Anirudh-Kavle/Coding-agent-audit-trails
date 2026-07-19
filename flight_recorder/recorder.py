"""Provider-neutral F1/F2 API for instrumenting an API-backed coding agent."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import gitstate, notifier, risk, store, tools


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@dataclass
class ActionHandle:
    event_id: int
    action_id: str
    session_id: str
    tool: str

    def finish(self, result: Any, *, ok: bool = True) -> int:
        """Attach a tool result to this action's existing SQLite row."""
        result_text = _json(result)
        if len(result_text) > 16 * 1024:
            result_text = result_text[: 16 * 1024] + "...[truncated]"
        conn = store.get_conn()
        try:
            event_id = store.complete_event(
                conn,
                session_id=self.session_id,
                action_id=self.action_id,
                tool=self.tool,
                completed_at=_now_ms(),
                result_json=result_text,
                exit_ok=1 if ok else 0,
            )
            if event_id is None:
                raise RuntimeError(f"unmatched action {self.action_id}")
            conn.commit()
            event = store.get_event(conn, event_id)
        finally:
            conn.close()
        store.append_jsonl(event)
        return event_id


class FlightRecorder:
    """Record tool calls without coupling capture to a model provider SDK."""

    def __init__(self, session_id: str | None = None, *, cwd: str | Path | None = None,
                 source: str = "api", model: str | None = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.cwd = str(cwd or Path.cwd())
        self.source = source
        self.model = model
        store.init_db()
        ts = _now_ms()
        git = gitstate.capture(self.cwd)
        conn = store.get_conn()
        try:
            store.upsert_session(conn, self.session_id, ts, self.cwd, git.get("git_repo"), self.source)
            conn.commit()
        finally:
            conn.close()

    def start_action(self, tool: str, arguments: Any, *, reasoning_text: str | None = None,
                     action_id: str | None = None) -> ActionHandle:
        """Capture full arguments plus a genuine visible/verbatim reasoning window."""
        ts = _now_ms()
        action_id = action_id or str(uuid.uuid4())
        git = gitstate.capture(self.cwd)
        arguments_text = _json(arguments)
        tier, reasons = risk.classify(tool, arguments_text)
        notification_sent = 1 if tier == "sensitive" and notifier.notify_sensitive(tool, reasons) else 0
        why = reasoning_text.strip() if reasoning_text and reasoning_text.strip() else None
        event = {
            "session_id": self.session_id,
            "action_id": action_id,
            "ts": ts,
            "completed_at": None,
            "phase": "pre",
            "tool": tool,
            "tool_kind": tools.action_kind(tool, arguments),
            "provider": self.source,
            "model": self.model,
            "notification_sent": notification_sent,
            "arguments_json": arguments_text,
            "result_json": "",
            "exit_ok": None,
            "reasoning_text": why,
            "risk": tier,
            "risk_reasons": _json(reasons),
            "capture_gap": 0 if why else 1,
            "git_branch": git.get("git_branch"),
            "git_head": git.get("git_head"),
            "git_dirty": git.get("git_dirty"),
            "files_touched": tools.files_touched(tool, arguments),
        }
        conn = store.get_conn()
        try:
            store.upsert_session(conn, self.session_id, ts, self.cwd, git.get("git_repo"), self.source)
            event_id = store.insert_event(conn, event)
            conn.commit()
        finally:
            conn.close()
        event["id"] = event_id
        store.append_jsonl(event)
        return ActionHandle(event_id, action_id, self.session_id, tool)

    def record_session_event(self, reason: str, *, usage: dict | None = None,
                             token_count: int = 0) -> int:
        ts = _now_ms()
        event = {
            "session_id": self.session_id, "ts": ts, "phase": "session",
            "tool": "SessionLimit", "tool_kind": "other", "provider": self.source,
            "model": self.model, "arguments_json": _json({"reason": reason}),
            "result_json": "", "exit_ok": 0, "reasoning_text": reason,
            "risk": "info", "risk_reasons": "[]", "capture_gap": 0,
            "token_count": token_count, "usage_json": _json(usage or {}),
            "git_branch": None, "git_head": None, "git_dirty": None,
            "files_touched": None,
        }
        conn = store.get_conn()
        try:
            event_id = store.insert_event(conn, event)
            conn.commit()
        finally:
            conn.close()
        event["id"] = event_id
        store.append_jsonl(event)
        return event_id
