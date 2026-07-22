"""OpenAI Responses API coding-agent loop, instrumented by Zetesis."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from . import limits, store
from .recorder import ZetesisRecorder

DEFAULT_MODEL = "gpt-5.6"
MAX_TOOL_OUTPUT = 32 * 1024
MAX_API_RESPONSE_TOKENS = 1024
# Keep prompt history conservative because the tool schemas and response
# budget also count toward the provider's per-minute token limit.
MAX_INPUT_CHARS = 12 * 1024

SYSTEM_INSTRUCTIONS = """You are a careful local coding agent.
Work only inside the provided project root. Inspect files before changing them.
For every tool call, provide a short, specific `reason` that explains the visible
rationale for that action. Never put secrets or hidden chain-of-thought in `reason`.
Prefer small changes and run relevant tests after editing. If a tool is denied or
fails, adapt safely instead of repeatedly issuing the same call.
"""


def _load_env_file(path: Path) -> bool:
    """Load simple KEY=VALUE entries without overriding the current shell."""
    if not path.is_file():
        return False
    loaded = False
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if line.lower().startswith("set "):
            line = line[4:].strip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
        loaded = loaded or key in {"OPENAI_API_KEY", "OPENAI_MODEL"}
    return loaded


def _load_project_env(root_path: Path) -> list[Path]:
    candidates = [root_path / ".env", Path.cwd() / ".env", root_path / ".env.local"]
    loaded: list[Path] = []
    for candidate in dict.fromkeys(candidates):
        if _load_env_file(candidate):
            loaded.append(candidate)
    return loaded


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


REASON_PROPERTY = {
    "type": "string",
    "description": "Short visible rationale for why this action is needed; never hidden chain-of-thought.",
}

TOOLS = [
    {
        "type": "function",
        "name": "list_files",
        "description": "List project files under a directory before deciding what to inspect.",
        "parameters": _schema(
            {
                "path": {"type": "string", "description": "Directory relative to the project root."},
                "reason": REASON_PROPERTY,
            },
            ["path", "reason"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Read a UTF-8 text file inside the project root.",
        "parameters": _schema(
            {
                "path": {"type": "string", "description": "File path relative to the project root."},
                "reason": REASON_PROPERTY,
            },
            ["path", "reason"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Create or completely replace one UTF-8 text file inside the project root.",
        "parameters": _schema(
            {
                "path": {"type": "string", "description": "File path relative to the project root."},
                "content": {"type": "string", "description": "Complete replacement file contents."},
                "reason": REASON_PROPERTY,
            },
            ["path", "content", "reason"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "run_command",
        "description": "Run a shell command in the project root and return its output and exit code.",
        "parameters": _schema(
            {
                "command": {"type": "string", "description": "Shell command to execute."},
                "reason": REASON_PROPERTY,
            },
            ["command", "reason"],
        ),
        "strict": True,
    },
]


class ToolExecutor:
    def __init__(self, root: str | Path, *, assume_yes: bool = False,
                 confirm: Callable[[str], str] = input) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"project root is not a directory: {self.root}")
        self.assume_yes = assume_yes
        self.confirm = confirm

    def _path(self, value: str) -> Path:
        candidate = (self.root / value).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes the project root") from exc
        return candidate

    def _approved(self, prompt: str) -> bool:
        if self.assume_yes:
            return True
        return self.confirm(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}

    def execute(self, name: str, arguments: dict) -> tuple[dict, bool]:
        if name == "list_files":
            directory = self._path(arguments["path"])
            if not directory.is_dir():
                raise ValueError(f"not a directory: {arguments['path']}")
            ignored = {".git", ".venv", "venv", "node_modules", "__pycache__"}
            files = []
            for path in directory.rglob("*"):
                if any(part in ignored for part in path.relative_to(self.root).parts):
                    continue
                if path.is_file():
                    files.append(path.relative_to(self.root).as_posix())
                if len(files) >= 500:
                    break
            return {"files": sorted(files), "truncated": len(files) >= 500}, True

        if name == "read_file":
            path = self._path(arguments["path"])
            text = path.read_text(encoding="utf-8")
            truncated = len(text) > MAX_TOOL_OUTPUT
            return {
                "path": path.relative_to(self.root).as_posix(),
                "content": text[:MAX_TOOL_OUTPUT],
                "truncated": truncated,
            }, True

        if name == "write_file":
            path = self._path(arguments["path"])
            relative = path.relative_to(self.root).as_posix()
            if not self._approved(f"Allow agent to write {relative}?"):
                return {"error": "write denied by user", "path": relative}, False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(arguments["content"], encoding="utf-8")
            return {"path": relative, "bytes_written": len(arguments["content"].encode("utf-8"))}, True

        if name == "run_command":
            command = arguments["command"]
            if not self._approved(f"Allow agent to run: {command}"):
                return {"error": "command denied by user", "command": command}, False
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.root,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                result = {
                    "command": command,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout[:MAX_TOOL_OUTPUT],
                    "stderr": completed.stderr[:MAX_TOOL_OUTPUT],
                    "truncated": len(completed.stdout) > MAX_TOOL_OUTPUT or len(completed.stderr) > MAX_TOOL_OUTPUT,
                }
                return result, completed.returncode == 0
            except subprocess.TimeoutExpired as exc:
                return {"error": "command timed out after 60 seconds", "command": command,
                        "stdout": str(exc.stdout or "")[:MAX_TOOL_OUTPUT],
                        "stderr": str(exc.stderr or "")[:MAX_TOOL_OUTPUT]}, False

        raise ValueError(f"unknown tool: {name}")


def _function_calls(response: Any) -> list[Any]:
    return [item for item in response.output if item.type == "function_call"]


def _reasoning_summary(response: Any) -> str | None:
    """Extract only the API-provided reasoning summary, never hidden CoT."""
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "reasoning":
            continue
        for summary in getattr(item, "summary", []) or []:
            text = getattr(summary, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts) or None


class ApiAgentSession:
    """Interactive, stateful API agent sharing one conversation and recorder session."""

    def __init__(self, *, root: str | Path = ".", model: str | None = None,
                 assume_yes: bool = False, client: Any = None,
                 confirm: Callable[[str], str] = input,
                 token_limit: int | None = None, time_limit_s: int | None = None,
                 daily_token_limit: int | None = None) -> None:
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise ValueError(f"project root is not a directory: {root_path}")
        env_files = _load_project_env(root_path)
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                searched = ", ".join(str(path) for path in env_files) or str(root_path / ".env")
                raise RuntimeError(f"OPENAI_API_KEY is not set (checked {searched})")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("OpenAI SDK is missing; run `pip install -e .`") from exc
            client = OpenAI()
        self.root = root_path
        self.model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
        self.client = client
        self.executor = ToolExecutor(root_path, assume_yes=assume_yes, confirm=confirm)
        self.recorder = ZetesisRecorder(cwd=root_path, source="openai-api", model=self.model)
        self.started_monotonic = time.monotonic()
        # A new API chat inherits the API scope configured in the viewer when
        # the CLI did not provide an explicit override.
        conn = store.get_conn()
        try:
            api_budget = store.get_budget(conn, "openai-api")
            global_budget = store.get_budget(conn, "global")
        finally:
            conn.close()
        inherited = api_budget or global_budget
        self.token_limit = token_limit if token_limit is not None else (inherited["token_limit"] if inherited else None)
        self.time_limit_s = time_limit_s if time_limit_s is not None else (inherited["time_limit_s"] if inherited else None)
        self.daily_token_limit = daily_token_limit
        self.global_token_limit = None
        self.provider_token_limit = None
        self.token_used = 0
        conn = store.get_conn()
        try:
            conn.execute("UPDATE sessions SET token_limit = ?, time_limit_s = ? WHERE id = ?",
                         (self.token_limit, self.time_limit_s, self.recorder.session_id))
            conn.commit()
        finally:
            conn.close()
        self.inputs: list[Any] = []

    def _sync_limits(self) -> None:
        """Pick up budget edits made in the browser between turns."""
        conn = store.get_conn()
        try:
            row = conn.execute("SELECT token_limit, time_limit_s, token_used FROM sessions WHERE id = ?",
                               (self.recorder.session_id,)).fetchone()
        finally:
            conn.close()
        if row:
            self.token_limit = row["token_limit"]
            self.time_limit_s = row["time_limit_s"]
            self.token_used = max(self.token_used, int(row["token_used"] or 0))
        conn = store.get_conn()
        try:
            global_budget = store.get_budget(conn, "global")
            provider_budget = store.get_budget(conn, "openai-api")
            self.global_token_limit = global_budget["token_limit"] if global_budget else None
            self.provider_token_limit = provider_budget["token_limit"] if provider_budget else None
        finally:
            conn.close()

    def _limit_reason(self) -> str | None:
        self._sync_limits()
        if self.token_limit is not None and self.token_used >= self.token_limit:
            return f"Session token limit reached ({self.token_used}/{self.token_limit})."
        conn = store.get_conn()
        try:
            global_used = int(conn.execute("SELECT COALESCE(SUM(token_used), 0) FROM sessions").fetchone()[0] or 0)
            provider_used = int(conn.execute(
                "SELECT COALESCE(SUM(token_used), 0) FROM sessions WHERE source = 'openai-api'"
            ).fetchone()[0] or 0)
        finally:
            conn.close()
        if self.global_token_limit is not None and global_used >= self.global_token_limit:
            return f"Global token limit reached ({global_used}/{self.global_token_limit})."
        if self.provider_token_limit is not None and provider_used >= self.provider_token_limit:
            return f"OpenAI API token limit reached ({provider_used}/{self.provider_token_limit})."
        elapsed = limits.elapsed_seconds(self.started_monotonic)
        if self.time_limit_s is not None and elapsed >= self.time_limit_s:
            return f"Session time limit reached ({elapsed}s/{self.time_limit_s}s)."
        if self.daily_token_limit is not None:
            conn = store.get_conn()
            try:
                daily = store.get_daily_usage(conn, limits.today())
            finally:
                conn.close()
            if daily >= self.daily_token_limit:
                return f"Daily API token limit reached ({daily}/{self.daily_token_limit})."
        return None

    def _record_usage(self, response) -> int:
        count = limits.usage_tokens(getattr(response, "usage", None))
        self.token_used += count
        conn = store.get_conn()
        try:
            store.update_session_usage(conn, self.recorder.session_id, count)
            store.add_daily_usage(conn, limits.today(), count, int(time.time() * 1000))
            conn.commit()
        finally:
            conn.close()
        return count

    def _trim_context(self) -> None:
        """Keep requests below common TPM limits without using another model."""
        encoded = json.dumps(self.inputs, ensure_ascii=False, default=str)
        if len(encoded) <= MAX_INPUT_CHARS:
            return
        # Only discard complete earlier user turns. Never slice through a
        # function_call/function_call_output pair.
        user_indexes = [i for i, item in enumerate(self.inputs)
                        if isinstance(item, dict) and item.get("role") == "user"]
        if len(user_indexes) > 1:
            self.inputs = self.inputs[user_indexes[-1]:]

    def run_turn(self, task: str, *, max_steps: int = 20) -> str:
        if not task.strip():
            raise ValueError("task cannot be empty")
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")

        conn = store.get_conn()
        try:
            if store.session_needs_title(conn, self.recorder.session_id):
                store.set_session_title(conn, self.recorder.session_id, store.title_from_text(task))
                conn.commit()
        finally:
            conn.close()
        self._trim_context()
        self.inputs.append({"role": "user", "content": task})
        # One turn_id per submitted task — every tool call this turn makes,
        # across every step below, shares it, so the viewer can group
        # "everything from this one prompt" together.
        turn_id = str(uuid.uuid4())

        for _ in range(max_steps):
            reason = self._limit_reason()
            if reason:
                self.recorder.record_session_event(reason)
                return reason
            try:
                response = self.client.responses.create(
                    model=self.model,
                    instructions=SYSTEM_INSTRUCTIONS + f"\nThe project root is: {self.root}",
                    tools=TOOLS,
                    input=self.inputs,
                    reasoning={"summary": "auto"},
                    max_output_tokens=MAX_API_RESPONSE_TOKENS,
                )
            except Exception as exc:
                text = str(exc)
                if "No tool call found" in text or "function call output" in text:
                    raise RuntimeError("Conversation context was invalid; use /clear and retry the task.") from exc
                if "429" in text or "rate_limit" in text or "tokens per min" in text:
                    raise RuntimeError("OpenAI rate limit reached. Wait briefly, lower the task scope, or start a new /clear context.") from exc
                raise
            self.inputs.extend(response.output)
            token_count = self._record_usage(response)
            limit_reason = self._limit_reason()
            if limit_reason:
                self.recorder.record_session_event(limit_reason, usage={"response_usage": str(getattr(response, "usage", ""))}, token_count=token_count)
                return limit_reason
            response_summary = _reasoning_summary(response)
            calls = _function_calls(response)
            if not calls:
                answer = response.output_text or ""
                self.recorder.record_api_turn(
                    task, answer, turn_id=turn_id,
                    reasoning_text=response_summary, token_count=token_count,
                    usage={"response_usage": str(getattr(response, "usage", ""))},
                )
                return answer

            for call in calls:
                try:
                    raw_arguments = json.loads(call.arguments)
                    if not isinstance(raw_arguments, dict):
                        raise ValueError("tool arguments must be a JSON object")
                except (json.JSONDecodeError, ValueError) as exc:
                    result, ok = {"error": f"invalid tool arguments: {exc}"}, False
                    action = self.recorder.start_action(
                        call.name, {"_raw_arguments": call.arguments},
                        reasoning_text=response_summary, action_id=call.call_id, turn_id=turn_id,
                    )
                    action.finish(result, ok=ok)
                    self.inputs.append({"type": "function_call_output", "call_id": call.call_id,
                                       "output": json.dumps(result)})
                    continue

                reason = raw_arguments.pop("reason", None)
                action = self.recorder.start_action(
                    call.name, raw_arguments,
                    reasoning_text=(reason if isinstance(reason, str) else None) or response_summary,
                    action_id=call.call_id, turn_id=turn_id,
                )
                try:
                    result, ok = self.executor.execute(call.name, raw_arguments)
                except Exception as exc:
                    result, ok = {"error": f"{type(exc).__name__}: {exc}"}, False
                action.finish(result, ok=ok)
                self.inputs.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                })

        raise RuntimeError(f"agent exceeded the {max_steps}-step limit")

    def clear_context(self) -> None:
        self.inputs.clear()


def run_agent(task: str, *, root: str | Path = ".", model: str | None = None,
              max_steps: int = 20, assume_yes: bool = False, client: Any = None,
              executor: ToolExecutor | None = None, token_limit: int | None = None,
              time_limit_s: int | None = None, daily_token_limit: int | None = None) -> str:
    """Run one task until the model returns text or the step budget is exhausted."""
    # Keep the original injectable executor/client API for tests and callers.
    if executor is not None:
        session = ApiAgentSession(root=root, model=model, assume_yes=assume_yes, client=client,
                                  token_limit=token_limit, time_limit_s=time_limit_s,
                                  daily_token_limit=daily_token_limit)
        session.executor = executor
    else:
        session = ApiAgentSession(root=root, model=model, assume_yes=assume_yes, client=client,
                                  token_limit=token_limit, time_limit_s=time_limit_s,
                                  daily_token_limit=daily_token_limit)
    return session.run_turn(task, max_steps=max_steps)
