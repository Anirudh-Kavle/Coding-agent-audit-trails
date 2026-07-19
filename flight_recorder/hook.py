"""fr-hook: the single fast entry point Claude Code invokes for every event.

Prime directive: exit 0, unconditionally. A recorder that can break the
pilot's controls is worse than no recorder. Every exception is swallowed
to the debug log; nothing here may ever propagate to the agent.
"""
from __future__ import annotations

import json
import sys
import time

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


FILE_ARG_TOOLS = {"Edit", "Write", "NotebookEdit"}


def _files_touched(tool_name: str | None, tool_input) -> str | None:
    if tool_name not in FILE_ARG_TOOLS or not isinstance(tool_input, dict):
        return None
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    return json.dumps([path]) if path else None


def _handle(payload: dict) -> None:
    hook_event_name = payload.get("hook_event_name", "Unknown")
    store.append_raw_payload(hook_event_name, payload)

    phase = PHASE_MAP.get(hook_event_name, "session")
    session_id = payload.get("session_id") or "unknown-session"
    cwd = payload.get("cwd")
    transcript_path = payload.get("transcript_path")
    tool_name = payload.get("tool_name")
    ts = _now_ms()

    git = gitstate.capture(cwd)

    conn = store.get_conn()
    try:
        store.upsert_session(conn, session_id, ts, cwd, git.get("git_repo"), payload.get("source"))

        if hook_event_name == "SessionEnd":
            store.mark_session_ended(conn, session_id, ts)

        if hook_event_name == "PreCompact":
            reasoning.snapshot_transcript(transcript_path, session_id, store.SNAPSHOTS_DIR)

        arguments_text, args_truncated = _truncate(payload.get("tool_input"))
        result_text, result_truncated = _truncate(payload.get("tool_response"))

        reasoning_text, capture_gap = (None, True)
        if phase == "pre" and tool_name:
            reasoning_text, capture_gap = reasoning.extract_reasoning(
                transcript_path, payload.get("tool_use_id")
            )

        risk_tier, risk_reasons = "info", []
        if tool_name:
            risk_tier, risk_reasons = risk.classify(tool_name, arguments_text)

        exit_ok = None
        if phase == "post":
            resp = payload.get("tool_response")
            if isinstance(resp, dict) and "error" in resp:
                exit_ok = 0
            else:
                exit_ok = 1

        event = {
            "session_id": session_id,
            "ts": ts,
            "phase": phase,
            "tool": tool_name,
            "arguments_json": arguments_text + ("...[truncated]" if args_truncated else ""),
            "result_json": result_text + ("...[truncated]" if result_truncated else ""),
            "exit_ok": exit_ok,
            "reasoning_text": reasoning_text,
            "risk": risk_tier,
            "risk_reasons": json.dumps(risk_reasons),
            "capture_gap": 1 if capture_gap else 0,
            "git_branch": git.get("git_branch"),
            "git_head": git.get("git_head"),
            "git_dirty": git.get("git_dirty"),
            "files_touched": _files_touched(tool_name, payload.get("tool_input")),
            "tool_use_id": payload.get("tool_use_id"),
        }

        pending = store.find_pending_pre_event(conn, session_id, tool_name) if phase == "post" and tool_name else None

        if pending is not None:
            store.update_event_result(conn, pending["id"], event["result_json"], event["exit_ok"])
            merged = dict(pending)
            merged["result_json"] = event["result_json"]
            merged["exit_ok"] = event["exit_ok"]

            # Self-heal: the PreToolUse capture can miss because the transcript
            # file hadn't been written past this call yet (the hook payload is
            # live in-memory dispatch; the file write lags it). By PostToolUse
            # time the tool has already run, giving the writer more real time
            # to catch up — worth one more honest attempt before giving up.
            if pending["capture_gap"]:
                healed_text, healed_gap = reasoning.extract_reasoning(
                    transcript_path, payload.get("tool_use_id")
                )
                if not healed_gap and healed_text:
                    store.update_event_reasoning(conn, pending["id"], healed_text)
                    merged["reasoning_text"] = healed_text
                    merged["capture_gap"] = 0

            current_id = pending["id"]
            store.append_jsonl(merged)
        else:
            row_id = store.insert_event(conn, event)
            event["id"] = row_id
            current_id = row_id
            store.append_jsonl(event)

        # Opportunistic heal: PostToolUse isn't guaranteed to fire at all (seen
        # in practice — a malformed command's PreToolUse never got a matching
        # PostToolUse, so the pairing self-heal above never got a chance to
        # run). Any hook firing in this session is another opportunity to
        # retry the most recent still-gapped call, bounded to a recency
        # window so one permanently-unrecoverable gap doesn't cost every
        # later hook a lookup for the rest of a long session.
        if transcript_path:
            stale = store.find_stale_gap(conn, session_id, ts)
            if stale is not None and stale["id"] != current_id:
                healed_text, healed_gap = reasoning.extract_reasoning(transcript_path, stale["tool_use_id"])
                if not healed_gap and healed_text:
                    store.update_event_reasoning(conn, stale["id"], healed_text)
                    healed_row = dict(stale)
                    healed_row["reasoning_text"] = healed_text
                    healed_row["capture_gap"] = 0
                    store.append_jsonl(healed_row)

        conn.commit()
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
