"""OpenAI Responses API coding-agent loop, instrumented by Flight Recorder."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from .recorder import FlightRecorder

DEFAULT_MODEL = "gpt-5.6"
MAX_TOOL_OUTPUT = 32 * 1024

SYSTEM_INSTRUCTIONS = """You are a careful local coding agent.
Work only inside the provided project root. Inspect files before changing them.
For every tool call, provide a short, specific `reason` that explains the visible
rationale for that action. Never put secrets or hidden chain-of-thought in `reason`.
Prefer small changes and run relevant tests after editing. If a tool is denied or
fails, adapt safely instead of repeatedly issuing the same call.
"""


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding the current shell."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


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


def run_agent(task: str, *, root: str | Path = ".", model: str | None = None,
              max_steps: int = 20, assume_yes: bool = False, client: Any = None,
              executor: ToolExecutor | None = None) -> str:
    """Run one task until the model returns text or the step budget is exhausted."""
    if not task.strip():
        raise ValueError("task cannot be empty")
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    root_path = Path(root).resolve()
    _load_env_file(root_path / ".env")
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is missing; run `pip install -e .`") from exc
        client = OpenAI()

    model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    executor = executor or ToolExecutor(root_path, assume_yes=assume_yes)
    recorder = FlightRecorder(cwd=root_path, source="openai-api")
    inputs: list[Any] = [{"role": "user", "content": task}]

    for _ in range(max_steps):
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_INSTRUCTIONS + f"\nThe project root is: {root_path}",
            tools=TOOLS,
            input=inputs,
        )
        inputs.extend(response.output)
        calls = _function_calls(response)
        if not calls:
            return response.output_text or ""

        for call in calls:
            try:
                raw_arguments = json.loads(call.arguments)
                if not isinstance(raw_arguments, dict):
                    raise ValueError("tool arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                result, ok = {"error": f"invalid tool arguments: {exc}"}, False
                action = recorder.start_action(
                    call.name,
                    {"_raw_arguments": call.arguments},
                    action_id=call.call_id,
                )
                action.finish(result, ok=ok)
                inputs.append({"type": "function_call_output", "call_id": call.call_id,
                               "output": json.dumps(result)})
                continue

            reason = raw_arguments.pop("reason", None)
            action = recorder.start_action(
                call.name,
                raw_arguments,
                reasoning_text=reason if isinstance(reason, str) else None,
                action_id=call.call_id,
            )
            try:
                result, ok = executor.execute(call.name, raw_arguments)
            except Exception as exc:
                result, ok = {"error": f"{type(exc).__name__}: {exc}"}, False
            action.finish(result, ok=ok)
            inputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })

    raise RuntimeError(f"agent exceeded the {max_steps}-step limit")
