"""Normalize provider-specific tool names without losing the raw name."""
from __future__ import annotations

import json
import re


READ_NAMES = re.compile(r"(^|__)(read|view|list|find|glob|grep|search)(_|$)", re.IGNORECASE)
WEB_NAMES = re.compile(r"(web[_-]?(fetch|search)|browser|http|url)", re.IGNORECASE)


def action_kind(tool_name: str | None, tool_input=None) -> str | None:
    """Return a stable UI/search category while preserving ``tool_name``.

    Codex reports shell and unified-exec calls as ``Bash`` and file patches as
    ``apply_patch``. MCP names remain provider-specific, so they are grouped as
    MCP unless their name clearly identifies a web/browser operation.
    """
    if not tool_name:
        return None

    lower = tool_name.lower()
    if lower in {"bash", "run_command"}:
        return "bash"
    if lower == "apply_patch":
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        has_add = "*** Add File:" in command
        has_other = "*** Update File:" in command or "*** Delete File:" in command
        return "write" if has_add and not has_other else "edit"
    if lower in {"edit", "notebookedit"}:
        return "edit"
    if lower in {"write", "write_file"}:
        return "write"
    if lower in {"read", "read_file", "list_files", "glob", "grep", "ls"}:
        return "read"
    if lower in {"webfetch", "websearch"} or WEB_NAMES.search(tool_name):
        return "webfetch"
    if lower.startswith("mcp__"):
        return "mcp"
    if READ_NAMES.search(tool_name):
        return "read"
    return "other"


def files_touched(tool_name: str | None, tool_input) -> str | None:
    if not isinstance(tool_input, dict):
        return None

    if tool_name in {"Edit", "Write", "NotebookEdit", "write_file", "read_file"}:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")
        return json.dumps([path]) if path else None

    if tool_name == "apply_patch":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        paths = re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", command, re.MULTILINE)
        return json.dumps(list(dict.fromkeys(paths))) if paths else None

    return None
