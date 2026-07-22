"""Codex hook entry point for every supported lifecycle event.

Prime directive: exit 0, unconditionally. A recorder that can break the
pilot's controls is worse than no recorder. Every exception is swallowed
to the debug log; nothing here may ever propagate to the agent.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
import time
import uuid

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


def _provider(payload: dict, override: str | None = None) -> str:
    if override in {"codex", "claude", "api"}:
        return override
    # Hook payloads do not consistently include a provider field.  The
    # command-line hook entry point supplies an explicit provider when a
    # Claude config invokes it; Codex remains the safe default.
    return str(payload.get("provider") or "codex")


def _result_ok(response) -> int:
    if isinstance(response, dict):
        if response.get("error") or response.get("success") is False:
            return 0
        exit_code = response.get("exit_code", response.get("exitCode"))
        if isinstance(exit_code, int):
            return 1 if exit_code == 0 else 0
    return 1


FILE_ARG_TOOLS = {"Edit", "Write", "NotebookEdit"}
BASH_FILE_TOUCH_VERBS = {"rm", "mv", "cp", "touch", "mkdir"}
_CHAIN_SPLIT_RE = re.compile(r"&&|\|\||;|\|")
_REDIRECT_RE = re.compile(r">>?\s*([^\s>&|;]+)")


def _bash_files_touched(command: str) -> list[str]:
    """Best-effort file paths a Bash command touches — not a real shell
    parser. Covers the common, straightforward cases (rm/mv/cp/touch/mkdir
    and output redirects) across simple &&/;/| chains; anything more exotic
    (globs, subshells, variable expansion, `find -exec`) is silently missed
    rather than guessed at — an honest gap beats a wrong guess here too."""
    paths: list[str] = []

    for match in _REDIRECT_RE.finditer(command):
        paths.append(match.group(1))

    for segment in _CHAIN_SPLIT_RE.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue  # unbalanced quotes etc. — skip this segment, not the whole command
        if not tokens:
            continue
        verb = tokens[0]
        if verb == "sudo" and len(tokens) > 1:
            verb, tokens = tokens[1], tokens[1:]
        if verb in BASH_FILE_TOUCH_VERBS:
            paths.extend(t for t in tokens[1:] if not t.startswith("-"))

    return list(dict.fromkeys(paths))


def _files_touched(tool_name: str | None, tool_input) -> str | None:
    """Claude's Edit/Write/NotebookEdit and Bash get the richer handling
    here; everything else (Codex's apply_patch, the API agent's
    write_file/read_file) falls back to tools.py's provider-neutral version
    so this doesn't regress coverage that already worked."""
    if not isinstance(tool_input, dict):
        return None
    if tool_name in FILE_ARG_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return json.dumps([path]) if path else None
    if tool_name == "Bash":
        command = tool_input.get("command")
        paths = _bash_files_touched(command) if isinstance(command, str) else []
        return json.dumps(paths) if paths else None
    return tools.files_touched(tool_name, tool_input)


def _usage_tokens(payload: dict) -> int:
    usage = payload.get("usage") or payload.get("token_usage") or {}
    if not isinstance(usage, dict):
        return 0
    for key in ("total_tokens", "total", "tokens"):
        try:
            if usage.get(key) is not None:
                return max(0, int(usage[key]))
        except (TypeError, ValueError):
            pass
    return 0


def _prompt_text(payload: dict) -> str | None:
    """Raw submitted-prompt text when a native hook payload exposes it —
    Claude/Codex lifecycle hooks don't use a consistent key for this."""
    for key in ("prompt", "user_prompt", "prompt_text", "message", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text") or value.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def _prompt_tokens(payload: dict) -> int:
    """Estimate submitted-prompt tokens when a native hook exposes text.

    Four characters is a conservative, model-agnostic proxy.
    """
    text = _prompt_text(payload)
    return max(1, (len(text) + 3) // 4) if text else 0


def _handle(payload: dict, provider: str | None = None) -> None:
    if store.is_paused():
        return

    hook_event_name = payload.get("hook_event_name", "Unknown")
    store.append_raw_payload(hook_event_name, payload)

    # PermissionRequest carries the same tool_name/tool_input as the
    # PreToolUse/PostToolUse pair for the same call, but no tool_use_id to
    # pair on and no outcome of its own (the decision isn't known yet at
    # this hook) — recording it as its own row just duplicated every
    # permission-gated action in the timeline. The real pair already
    # captures everything worth keeping.
    if hook_event_name == "PermissionRequest":
        return

    phase = PHASE_MAP.get(hook_event_name, "session")
    session_id = payload.get("session_id") or "unknown-session"
    cwd = payload.get("cwd")
    transcript_path = payload.get("transcript_path")
    tool_name = payload.get("tool_name")
    ts = _now_ms()

    git = gitstate.capture(cwd)

    conn = store.get_conn()
    try:
        provider_name = _provider(payload, provider)
        store.upsert_session(conn, session_id, ts, cwd, git.get("git_repo"), provider_name)
        store.apply_provider_budget(conn, session_id, provider_name)

        if hook_event_name == "SessionEnd":
            store.mark_session_ended(conn, session_id, ts)

        if transcript_path and store.session_needs_title(conn, session_id):
            title = reasoning.extract_session_title(transcript_path)
            if title:
                store.set_session_title(conn, session_id, title)

        # Codex has no transcript-embedded title the way Claude Code does —
        # fall back to the first submitted prompt, the same text already
        # read above for token estimation.
        if hook_event_name == "UserPromptSubmit" and store.session_needs_title(conn, session_id):
            prompt_text = _prompt_text(payload)
            if prompt_text:
                store.set_session_title(conn, session_id, store.title_from_text(prompt_text))

        # Claude Code's payloads never carry their own per-turn id (Codex's
        # sometimes do, via payload["turn_id"] below). A new prompt — or a
        # fresh/resumed session before any prompt lands — starts a new turn
        # that every tool call in between gets stamped with, so the viewer
        # can group "everything from one prompt" together.
        if hook_event_name in ("UserPromptSubmit", "SessionStart"):
            store.set_session_turn(conn, session_id, str(uuid.uuid4()))

        if hook_event_name == "PreCompact":
            reasoning.snapshot_transcript(transcript_path, session_id, store.SNAPSHOTS_DIR)

        arguments_text, args_truncated = _truncate(payload.get("tool_input"))
        tool_response = payload.get("tool_response")
        if phase == "post" and tool_response is None:
            recovered = reasoning.extract_tool_result(transcript_path, payload.get("tool_input"))
            if recovered is not None:
                tool_response = recovered
        result_text, result_truncated = _truncate(tool_response)

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
            risk_tier, risk_reasons = risk.classify(tool_name, arguments_text, result_text)

        notification_sent = 0
        if phase == "pre" and risk_tier == "sensitive":
            notification_sent = 1 if notifier.notify_sensitive(tool_name, risk_reasons) else 0

        exit_ok = None
        if phase == "post":
            exit_ok = _result_ok(tool_response)
        token_count = _usage_tokens(payload) if phase == "post" else (
            _prompt_tokens(payload) if hook_event_name == "UserPromptSubmit" else 0
        )
        usage_payload = payload.get("usage") or payload.get("token_usage") or {}
        if hook_event_name == "UserPromptSubmit" and token_count and not usage_payload:
            usage_payload = {"estimated_prompt_tokens": token_count}

        event = {
            "session_id": session_id,
            "ts": ts,
            "phase": phase,
            "tool": tool_name,
            "tool_kind": tools.action_kind(tool_name, payload.get("tool_input")),
            "tool_use_id": payload.get("tool_use_id"),
            # Codex's own payload sometimes already carries a turn_id — trust
            # that when present; otherwise fall back to the one this hook
            # mints itself on UserPromptSubmit/SessionStart (see above).
            "turn_id": payload.get("turn_id") or store.get_session_turn(conn, session_id),
            "provider": provider_name,
            "model": payload.get("model"),
            "notification_sent": notification_sent,
            "token_count": token_count,
            "usage_json": json.dumps(usage_payload),
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
        }

        pending = None
        if phase == "post" and tool_name:
            tool_use_id = payload.get("tool_use_id")
            if tool_use_id:
                pending = store.find_pre_event_by_tool_use_id(conn, session_id, tool_use_id)
            if pending is None:
                pending = store.find_pending_pre_event(conn, session_id, tool_name)

        if pending is not None:
            # risk_tier/risk_reasons above already reflect the result (this
            # is a post-phase event, so result_text was already fed into the
            # classify() call at the top) — the pending row was scored from
            # arguments alone at PreToolUse time, so patch it up to match.
            store.update_event_result(
                conn, pending["id"], event["result_json"], event["exit_ok"],
                risk_tier, event["risk_reasons"],
            )
            if token_count:
                store.update_session_usage(conn, session_id, token_count)
            merged = dict(pending)
            merged["result_json"] = event["result_json"]
            merged["exit_ok"] = event["exit_ok"]
            merged["risk"] = risk_tier
            merged["risk_reasons"] = event["risk_reasons"]

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
            if token_count:
                store.update_session_usage(conn, session_id, token_count)
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

    provider = None
    if "--provider" in sys.argv:
        try:
            provider = sys.argv[sys.argv.index("--provider") + 1].lower()
        except IndexError:
            provider = None

    try:
        _handle(payload, provider)
    except Exception as exc:
        store.log_debug(f"hook: unhandled exception: {exc!r}")

    sys.exit(0)


if __name__ == "__main__":
    main()
