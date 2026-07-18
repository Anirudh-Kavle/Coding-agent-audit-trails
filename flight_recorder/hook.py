"""fr-hook: the single fast entry point Claude Code invokes for every event.

Prime directive: exit 0, unconditionally. A recorder that can break the
pilot's controls is worse than no recorder. Every exception is swallowed
to the debug log; nothing here may ever propagate to the agent.
"""
from __future__ import annotations

import json
import sys
import time
import uuid

from . import gitstate, reasoning, risk, store

PHASE_MAP = {
    "PreToolUse": "pre",
    "PostToolUse": "post",
    "PreCompact": "compact",
    "SessionStart": "session",
    "SessionEnd": "session",
    "Stop": "session",
    "SubagentStop": "session",
    "UserPromptSubmit": "session",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _truncate(obj, max_len: int = 16 * 1024) -> tuple[str, bool]:
    text = json.dumps(obj, ensure_ascii=False, default=str) if obj is not None else ""
    if len(text) > max_len:
        return text[:max_len], True
    return text, False


def _serialize(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str) if obj is not None else ""


def _handle(payload: dict) -> None:
    hook_event_name = payload.get("hook_event_name", "Unknown")
    store.append_raw_payload(hook_event_name, payload)

    phase = PHASE_MAP.get(hook_event_name, "session")
    session_id = payload.get("session_id") or "unknown-session"
    cwd = payload.get("cwd")
    transcript_path = payload.get("transcript_path")
    tool_name = payload.get("tool_name")
    action_id = payload.get("tool_use_id") or payload.get("tool_call_id") or payload.get("call_id")
    ts = _now_ms()

    git = gitstate.capture(cwd)

    conn = store.get_conn()
    try:
        store.upsert_session(conn, session_id, ts, cwd, git.get("git_repo"), payload.get("source"))

        if hook_event_name == "SessionEnd":
            store.mark_session_ended(conn, session_id, ts)

        if hook_event_name == "PreCompact":
            reasoning.snapshot_transcript(transcript_path, session_id, store.SNAPSHOTS_DIR)

        arguments_text = _serialize(payload.get("tool_input"))
        result_text, result_truncated = _truncate(payload.get("tool_response"))

        reasoning_text, capture_gap = (None, True)
        if phase == "pre" and tool_name:
            explicit_reasoning = payload.get("reasoning_text") or payload.get("reasoning")
            if isinstance(explicit_reasoning, str) and explicit_reasoning.strip():
                reasoning_text = explicit_reasoning.strip()[-reasoning.MAX_REASONING_LEN:]
                capture_gap = False
            else:
                reasoning_text, capture_gap = reasoning.extract_reasoning(transcript_path, action_id)

        risk_tier, risk_reasons = "info", []
        if tool_name:
            risk_tier, risk_reasons = risk.classify(tool_name, arguments_text)

        exit_ok = None
        if phase == "post":
            resp = payload.get("tool_response")
            if isinstance(resp, dict) and (
                "error" in resp or resp.get("is_error") is True or resp.get("success") is False
            ):
                exit_ok = 0
            else:
                exit_ok = 1

        if phase == "post" and tool_name:
            row_id = store.complete_event(
                conn,
                session_id=session_id,
                action_id=action_id,
                tool=tool_name,
                completed_at=ts,
                result_json=result_text + ("...[truncated]" if result_truncated else ""),
                exit_ok=exit_ok if exit_ok is not None else 1,
            )
            if row_id is not None:
                conn.commit()
                store.append_jsonl(store.get_event(conn, row_id))
                return

        event = {
            "session_id": session_id,
            "action_id": action_id or (str(uuid.uuid4()) if phase == "pre" and tool_name else None),
            "ts": ts,
            "completed_at": ts if phase == "post" else None,
            "phase": phase,
            "tool": tool_name,
            "arguments_json": arguments_text,
            "result_json": result_text + ("...[truncated]" if result_truncated else ""),
            "exit_ok": exit_ok,
            "reasoning_text": reasoning_text,
            "risk": risk_tier,
            "risk_reasons": json.dumps(risk_reasons),
            "capture_gap": 1 if capture_gap else 0,
            "git_branch": git.get("git_branch"),
            "git_head": git.get("git_head"),
            "git_dirty": git.get("git_dirty"),
            "files_touched": None,
        }

        row_id = store.insert_event(conn, event)
        conn.commit()
        event["id"] = row_id
        store.append_jsonl(event)
    finally:
        conn.close()


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        store.log_debug(f"hook: failed to parse stdin JSON: {exc!r}")
        sys.exit(0)

    try:
        _handle(payload)
    except Exception as exc:
        store.log_debug(f"hook: unhandled exception: {exc!r}")

    sys.exit(0)


if __name__ == "__main__":
    main()
