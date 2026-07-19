"""Codex hook entry point for every supported lifecycle event.

Prime directive: exit 0, unconditionally. A recorder that can break the
pilot's controls is worse than no recorder. Every exception is swallowed
to the debug log; nothing here may ever propagate to the agent.
"""
from __future__ import annotations

import json
import sys
import time

from . import gitstate, notifier, reasoning, risk, store, tools

PHASE_MAP = {
    "PreToolUse": "pre",
    "PostToolUse": "post",
    "PreCompact": "compact",
    "SessionStart": "session",
    "SessionEnd": "session",
    "Stop": "session",
    "SubagentStart": "session",
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


def _provider(payload: dict) -> str:
    return "codex"


def _result_ok(response) -> int:
    if isinstance(response, dict):
        if response.get("error") or response.get("success") is False:
            return 0
        exit_code = response.get("exit_code", response.get("exitCode"))
        if isinstance(exit_code, int):
            return 1 if exit_code == 0 else 0
    return 1


def _handle(payload: dict) -> None:
    if store.is_paused():
        return

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
            tool_input = payload.get("tool_input")
            description = tool_input.get("description") if isinstance(tool_input, dict) else None
            if isinstance(description, str) and description.strip():
                reasoning_text, capture_gap = description.strip(), False
            else:
                reasoning_text, capture_gap = reasoning.extract_reasoning(
                    transcript_path, payload.get("tool_use_id")
                )

        risk_tier, risk_reasons = "info", []
        if tool_name:
            risk_tier, risk_reasons = risk.classify(tool_name, arguments_text)

        notification_sent = 0
        if phase == "pre" and risk_tier == "sensitive":
            notification_sent = 1 if notifier.notify_sensitive(tool_name, risk_reasons) else 0

        exit_ok = None
        if phase == "post":
            exit_ok = _result_ok(payload.get("tool_response"))

        event = {
            "session_id": session_id,
            "ts": ts,
            "phase": phase,
            "tool": tool_name,
            "tool_kind": tools.action_kind(tool_name, payload.get("tool_input")),
            "tool_use_id": payload.get("tool_use_id"),
            "turn_id": payload.get("turn_id"),
            "provider": _provider(payload),
            "model": payload.get("model"),
            "notification_sent": notification_sent,
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
            "files_touched": tools.files_touched(tool_name, payload.get("tool_input")),
        }

        pending = None
        if phase == "post" and tool_name:
            tool_use_id = payload.get("tool_use_id")
            if tool_use_id:
                pending = store.find_pre_event_by_tool_use_id(conn, session_id, tool_use_id)
            if pending is None and not tool_use_id:
                pending = store.find_pending_pre_event(conn, session_id, tool_name)

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
        # retry recent still-gapped calls, bounded to a recency window so a
        # long run of unrecoverable gaps doesn't cost every later hook
        # unbounded work.
        #
        # Checks several candidates, not just the newest: a batch of
        # sequential calls with nothing between them (legitimate gaps) can
        # sit in front of an older call that genuinely does have recoverable
        # reasoning — only ever checking the single most recent one lets it
        # mask an older, healable gap forever (seen in practice with three
        # sequential Reads).
        if transcript_path:
            for stale in store.find_stale_gaps(conn, session_id, ts):
                if stale["id"] == current_id:
                    continue
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
