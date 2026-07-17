"""fr — the Flight Recorder CLI."""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from . import store

# Windows consoles default to cp1252, which can't encode the REC dot etc.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK_ENTRY = PROJECT_ROOT / "bin" / "fr_hook_entry.py"

TOOL_HOOK_EVENTS = ["PreToolUse", "PostToolUse"]
BARE_HOOK_EVENTS = ["PreCompact", "SessionStart", "SessionEnd", "Stop"]


def _hook_command() -> str:
    return f'"{sys.executable}" "{HOOK_ENTRY}"'


def _settings_path(project: bool) -> Path:
    if project:
        return Path.cwd() / ".claude" / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def _merge_hooks(settings: dict, command: str) -> bool:
    """Mutates settings in place. Returns True if anything changed."""
    changed = False
    hooks = settings.setdefault("hooks", {})

    for event in TOOL_HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        matcher_entry = next((e for e in entries if e.get("matcher") == "*"), None)
        if matcher_entry is None:
            entries.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
            changed = True
            continue
        cmds = [h.get("command") for h in matcher_entry.setdefault("hooks", [])]
        if command not in cmds:
            matcher_entry["hooks"].append({"type": "command", "command": command})
            changed = True

    for event in BARE_HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        if not entries:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
            continue
        target = entries[0]
        cmds = [h.get("command") for h in target.setdefault("hooks", [])]
        if command not in cmds:
            target["hooks"].append({"type": "command", "command": command})
            changed = True

    return changed


def _hooks_registered(settings: dict, command: str) -> bool:
    hooks = settings.get("hooks", {})
    for event in TOOL_HOOK_EVENTS + BARE_HOOK_EVENTS:
        for entry in hooks.get(event, []):
            for h in entry.get("hooks", []):
                if h.get("command") == command:
                    return True
    return False


def cmd_init(args: argparse.Namespace) -> None:
    store.ensure_dirs()
    store.init_db()

    settings_path = _settings_path(project=not args.global_)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"! {settings_path} has invalid JSON — not touching it. Merge the hook config manually.")
            return

    changed = _merge_hooks(settings, _hook_command())
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    if changed:
        print(f"Hooks registered in {settings_path}")
    else:
        print(f"Hooks already registered in {settings_path}")
    print(f"Store initialized at {store.STORE_DIR}")
    print("recording ●")


def cmd_status(args: argparse.Namespace) -> None:
    if not store.DB_PATH.exists():
        print("Not initialized. Run `fr init` first.")
        return

    conn = store.get_conn()
    try:
        n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        last_ts = conn.execute("SELECT MAX(ts) FROM events").fetchone()[0]
    finally:
        conn.close()

    print(f"Store: {store.STORE_DIR}")
    print(f"Sessions: {n_sessions}  Events: {n_events}")
    if last_ts:
        age_s = (time.time() * 1000 - last_ts) / 1000
        print(f"Last event: {age_s:.1f}s ago")
    else:
        print("Last event: none yet")

    settings_path = _settings_path(project=True)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        registered = _hooks_registered(settings, _hook_command())
        print(f"Hooks in {settings_path}: {'yes' if registered else 'no'}")
    else:
        print(f"Hooks in {settings_path}: no (file missing)")


def cmd_ui(args: argparse.Namespace) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run("flight_recorder.viewer.app:app", host="127.0.0.1", port=args.port, log_level="warning")


def cmd_grep(args: argparse.Namespace) -> None:
    import re

    pattern = re.compile(args.pattern)
    files = sorted(store.EVENTS_DIR.glob("*.jsonl"))
    if not files:
        print("No events recorded yet.")
        return

    for path in files:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if pattern.search(line):
                    sys.stdout.write(f"{path.name}: {line}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="fr", description="Flight Recorder CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Register hooks and create the local store")
    p_init.add_argument("--global", dest="global_", action="store_true",
                         help="Register in ~/.claude/settings.json instead of the project's .claude/settings.json")
    p_init.set_defaults(func=cmd_init)

    p_status = sub.add_parser("status", help="Show store + hook registration status")
    p_status.set_defaults(func=cmd_status)

    p_ui = sub.add_parser("ui", help="Start the viewer and open it in a browser")
    p_ui.add_argument("--port", type=int, default=7878)
    p_ui.add_argument("--no-browser", action="store_true")
    p_ui.set_defaults(func=cmd_ui)

    p_grep = sub.add_parser("grep", help="grep across the JSONL mirror")
    p_grep.add_argument("pattern")
    p_grep.set_defaults(func=cmd_grep)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
