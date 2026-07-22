"""Zetesis command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import textwrap
import threading
import webbrowser
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path

from . import limits, store

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ZETESIS_ART = r"""
⠀⠀⠀⠀⠀⠀⣠⡤⢤⣤⡴⠶⢦⣄⣀
⠀⠀⠀⠀⡠⠎⠁⠀⠀⠀⠀⢰⢶⣌⠉⠑⠂
⠀⠀⠠⠄⠁⠀⠀⠆⠀⢠⡤⠬⢬⣭⣥⣤⡈⢥⡀
⠀⠀⠏⢠⡌⠁⠀⠀⠈⠱⠆⠰⢦⣤⡤⠄⠰⠀⢥⡄
⠀⡏⠀⠛⠘⠣⠄⠘⠏⠁⠈⠱⠬⠅⠀⠈⠁⠀⢬⣧
⢀⣃⡔⠛⠋⠁⢀⣠⡜⠋⠋⠁⢠⡜⠋⠙⠙⢘⡋⢯⣷⡄
⠀⠛⠜⠃⠚⠑⠃⠀⠀⢐⣃⣼⡂⠀⠀⢠⡄⠈⣁⠺⣹⠛⠴⠶⣤⣤⣤⣠⣤⠶⠶⠴⣶⡖⢲⣧⠣⢤⣤⡄
⠀⠀⠰⢗⡒⠂⢺⣛⡋⠉⠁⢀⡀⠘⢂⡀⠀⢸⠋⣁⣀⠀⠀⢤⣀⣀⡤⣀⠀⠀⠀⠀⠀⠀⠊⠉⡠⠄⠀⠘⢣⣀
⠀⠀⠀⠀⢐⣂⢸⡗⠀⢂⡀⠀⠀⠀⠀⠀⠀⠀⠐⠀⠀⠐⠂⣉⣛⣛⡂⣀⠒⠀⠀⣤⠀⠒⠀⢂⣤⡐⠂⠀⠘⢻⡄
⠀⠀⠀⠀⠘⢓⡘⠳⢶⣆⡴⠆⠐⢆⡀⠀⠀⠀⢀⡶⠀⠀⠒⠀⠀⣉⠷⣁⠖⣀⠀⠀⣀⠖⠀⢈⣏⡁⠀⢠⡄⠀⡃
⠀⠀⠀⠀⠀⠀⢰⣾⣏⣥⣤⣆⣀⣀⣀⡀⠀⢠⡌⠀⠀⠀⠀⠀⠶⣉⠶⣉⠶⣿⠀⣀⠁⠁⢀⣬⣙⢿⣀⣀⡄⠐⣷⡀
⠀⠀⠀⠀⠀⢠⣌⠁⡀⢀⡀⠀⢀⡀⠉⢡⣄⠀⠀⠀⠀⠀⠀⠀⠶⠉⠀⠀⠀⠀⠀⠀⢀⣧⢀⡘⠛⢯⣝⡋⠀⠠⡇⢘⡃
⠀⠀⠀⠀⠀⠸⠏⡈⠡⠎⠁⠠⠌⢁⡰⠎⠉⠁⠀⠀⠀⠀⠀⠶⠀⠀⠀⠀⠀⠀⢛⡀⢶⣀⠰⠿⡀⠀⠸⠏⠀⠈⠁⠸⠷⠄
⠀⠀⠀⠀⠀⠸⠝⠟⢋⡉⠙⢛⡂⢸⡇⠀⠀⠀⠈⣁⡶⣀⠶⠉⠀⠀⠉⠀⠀⠟⠿⠛⠈⠟⠶⠉⠰⠦⠎⠉⡱⠋⠰⠜⠺⠷⠄
⠀⠀⠀⠀⠠⠜⠿⢿⡁⢀⡀⠈⠡⠌⠁⠀⠀⠀⠈⠉⠉⠈⠀⠀⠀⠀⠀⠠⠿⠛⠀⠀⠤⠀⠀⠀⠄⠀⠀⠸⡇⠀⠠⢄⡸⠼⠇
⠀⠀⠀⠀⠸⠯⠘⢯⡁⠎⠁⠀⠀⠀⠹⢆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠿⠺⣤⠀⠀⠤⠀⠐⠛⡆⠸⢿⡄⠁⠀⠀⠈⢡⡼⣧⡄
⠀⠀⠀⠀⢸⡍⠀⠈⠡⢤⡀⠀⠀⠀⠀⠈⢡⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠿⠀⠉⠀⠀⠀⠀⠉⠈⠑⢶⡜⠃⠀⠀⡀⢀⡀⡀⢹⣦⡀
⠀⠀⠀⠀⠈⢡⡄⢠⡌⢡⡄⠀⠀⠀⠀⠈⠁⠻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⣷⠀⠀⠀⠀⠀⠀⢸⣿⡗⠃⠀⠀⠈⠁⢀⡈⠉⠹⠿⡇
⠀⠀⠀⠀⠀⠀⠰⣦⢰⡎⢱⠂⠀⠀⠀⠀⠈⠀⠈⣀⠀⠀⠀⠀⠀⢀⣠⠶⠖⠛⠀⠀⠛⠀⠀⢰⣾⡟⠀⠀⠀⠀⠀⠀⢀⡈⢡⣸⣧⡀
⠀⠀⠀⠀⠀⠀⠀⠈⠳⡖⠰⡆⠀⠀⠀⠀⠀⠀⠘⠀⠐⣀⣀⠶⠒⠉⠀⠀⠋⠛⠉⠉⠓⠛⠗⠐⡷⠀⠀⠀⠀⠀⢰⡞⢃⣀⡀⠾⣶⡇
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢃⣰⠂⠀⠀⠀⠀⢀⡠⠒⠘⠀⠀⣀⣀⠖⠚⠀⠛⠉⠛⠳⠾⠻⣤⢖⡆⠀⠀⠀⠀⠀⠀⠀⠀⢀⡀⣰⠂
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣈⡩⠤⠖⠒⠚⠛⠃⣀⣀⠠⠘⠉⠉⠀⠀⠀⠀⠉⠀⠀⠀⠀⠀⢰⣶⠁⠀⠀⠀⠀⠀⠀⠘⠂⢀⡀⣰⡆
""".strip("\n").splitlines()

TOOL_HOOK_EVENTS = ["PreToolUse", "PostToolUse"]
BARE_HOOK_EVENTS = [
    "PreCompact", "PostCompact", "SessionStart", "SessionEnd", "SubagentStart",
    "SubagentStop", "UserPromptSubmit", "Stop",
]


def _hook_command() -> str:
    # Use the installed console entry point so Codex does not need access to
    # the interpreter path that happened to install the package.
    return "fr-hook"


def _settings_path(project: bool) -> Path:
    base = Path.cwd() if project else Path.home()
    return base / ".codex" / "hooks.json"


def _merge_hooks(settings: dict, command: str) -> bool:
    """Mutate hook settings without removing any existing handlers."""
    changed = False
    hooks = settings.setdefault("hooks", {})

    for event in TOOL_HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        matcher_entry = next((e for e in entries if e.get("matcher") in (".*", "*")), None)
        if matcher_entry is None:
            entries.append({"matcher": ".*", "hooks": [{"type": "command", "command": command, "timeout": 5}]})
            changed = True
            continue
        if matcher_entry.get("matcher") == "*":
            matcher_entry["matcher"] = ".*"
            changed = True
        commands = [h.get("command") for h in matcher_entry.setdefault("hooks", [])]
        if command not in commands:
            matcher_entry["hooks"].append({"type": "command", "command": command, "timeout": 5})
            changed = True

    for event in BARE_HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        if not entries:
            entries.append({"hooks": [{"type": "command", "command": command, "timeout": 5}]})
            changed = True
            continue
        target = entries[0]
        commands = [h.get("command") for h in target.setdefault("hooks", [])]
        if command not in commands:
            target["hooks"].append({"type": "command", "command": command, "timeout": 5})
            changed = True
    return changed


def _hooks_registered(settings: dict, command: str) -> bool:
    hooks = settings.get("hooks", {})
    for event in TOOL_HOOK_EVENTS + BARE_HOOK_EVENTS:
        found = any(
            handler.get("command") == command
            for entry in hooks.get(event, [])
            for handler in entry.get("hooks", [])
        )
        if not found:
            return False
    return True


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
            print(f"! {settings_path} has invalid JSON - not touching it. Merge the hook config manually.")
            return

    settings.setdefault("description", "Zetesis local audit capture")
    changed = _merge_hooks(settings, _hook_command())
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    print(f"Hooks {'registered' if changed else 'already registered'} in {settings_path}")
    print(f"Store initialized at {store.STORE_DIR}")
    print("Open /hooks in Codex once to review and trust the project hooks.")
    print("recording")


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
    if not settings_path.exists():
        print(f"Codex hooks in {settings_path}: no (file missing)")
    else:
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            registered = _hooks_registered(settings, _hook_command())
            print(f"Codex hooks in {settings_path}: {'yes' if registered else 'no'}")
        except json.JSONDecodeError:
            print(f"Codex hooks in {settings_path}: invalid JSON")


def cmd_ui(args: argparse.Namespace) -> None:
    import os
    import subprocess

    url = f"http://127.0.0.1:{args.port}"
    command = [
        sys.executable, "-m", "uvicorn", "zetesis.viewer.app:app",
        "--host", "127.0.0.1", "--port", str(args.port), "--log-level", "warning",
    ]
    process_options = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options["start_new_session"] = True

    if not args.no_browser:
        webbrowser.open(url)
    process = subprocess.Popen(command, **process_options)
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\nStopping Zetesis...", flush=True)
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def cmd_grep(args: argparse.Namespace) -> None:
    import re

    pattern = re.compile(args.pattern)
    files = sorted(store.EVENTS_DIR.glob("*.jsonl"))
    if not files:
        print("No events recorded yet.")
        return
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if pattern.search(line):
                    sys.stdout.write(f"{path.name}: {line}")


def cmd_export(args: argparse.Namespace) -> None:
    """Write the local-calendar-day's canonical event rows as a JSON array."""
    if not store.DB_PATH.exists():
        print("Not initialized. Run `fr init` first.")
        return

    today = date.today()
    day_start = int(datetime.combine(today, datetime_time.min).astimezone().timestamp() * 1000)
    next_day_start = int(datetime.combine(today + timedelta(days=1), datetime_time.min).astimezone().timestamp() * 1000)

    conn = store.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE ts >= ? AND ts < ? ORDER BY ts, id",
            (day_start, next_day_start),
        ).fetchall()
    finally:
        conn.close()

    output = args.output or Path.cwd() / f"zetesis-{today.isoformat()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([dict(row) for row in rows], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported {len(rows)} event(s) to {output}")


def cmd_test_hook(args: argparse.Namespace) -> None:
    """Feed an exact Codex PreToolUse/PostToolUse pair through the recorder."""
    from . import hook

    session_id = "manual-hook-test"
    tool_use_id = "manual-call-1"
    common = {
        "session_id": session_id,
        "turn_id": "manual-turn-1",
        "tool_use_id": tool_use_id,
        "cwd": str(Path.cwd()),
        "model": "manual-test",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
    }
    pre = {**common, "hook_event_name": "PreToolUse"}
    post = {
        **common,
        "hook_event_name": "PostToolUse",
        "tool_response": {"stdout": "manual test", "exit_code": 0},
    }
    hook._handle(pre)
    hook._handle(post)
    print("Recorded a synthetic Codex PreToolUse/PostToolUse pair.")
    print("Run `fr status` or `fr ui` to inspect it.")


def cmd_test_notification(args: argparse.Namespace) -> None:
    from .notifier import notify_sensitive

    sent = notify_sensitive("Bash", ["manual notification test"])
    print(f"Notification launch: {'ok' if sent else 'failed'}")
    print("If no popup appeared, check ZETESIS_NOTIFY and the active Windows desktop session.")


def cmd_agent(args: argparse.Namespace) -> None:
    from .agent import run_agent

    result = run_agent(
        args.task,
        root=args.root,
        model=args.model,
        max_steps=args.max_steps,
        assume_yes=args.yes,
        token_limit=args.token_limit,
        time_limit_s=args.time_limit_s,
        daily_token_limit=args.daily_token_limit,
    )
    if result:
        print(result)


def _print_zetesis_banner(width: int, color: bool) -> None:
    art_width = max(len(line) for line in ZETESIS_ART)
    if width < art_width + 4:
        return
    pad = " " * max(0, (width - art_width) // 2)
    # Single dim tone, matching the rest of the minimal palette, rather than
    # a multi-color gradient.
    dim, bold_cyan, reset = "\x1b[2m", "\x1b[1m\x1b[36m", "\x1b[0m"
    if color:
        for row in ZETESIS_ART:
            print(f"{pad}{dim}{row}{reset}")
    else:
        for row in ZETESIS_ART:
            print(f"{pad}{row}")

    title = "Z E T E S I S"
    title_pad = " " * max(0, (width - len(title)) // 2)
    if color:
        print(f"{title_pad}{bold_cyan}{title}{reset}")
    else:
        print(f"{title_pad}{title}")
    print()


_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _run_with_spinner(worker, styled, color: bool, width: int, animate: bool = True):
    """Run `worker` to completion, showing a "thinking" spinner while it's
    in flight. `worker` runs on a background daemon thread so Ctrl+C on the
    main thread can still interrupt the wait; the turn itself keeps running
    in the background but its result is discarded in that case.

    `animate` must be False whenever `worker` might block on its own input()
    call (e.g. a tool-approval prompt) — a spinner thread writing carriage
    returns would otherwise garble that prompt."""
    if not color or not animate:
        print(styled("agent is thinking…", "dim"))
        return worker()

    outcome: dict = {}

    def target() -> None:
        try:
            outcome["value"] = worker()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller below
            outcome["error"] = exc

    thread = threading.Thread(target=target, daemon=True, name="zetesis-turn-worker")
    thread.start()

    clear = "\r" + " " * min(width, 60) + "\r"
    start = time.monotonic()
    frame_index = 0
    try:
        while thread.is_alive():
            elapsed = time.monotonic() - start
            frame = _SPINNER_FRAMES[frame_index % len(_SPINNER_FRAMES)]
            sys.stdout.write(f"\r{styled(f'{frame} agent is thinking… ({elapsed:.0f}s)', 'dim')}")
            sys.stdout.flush()
            frame_index += 1
            thread.join(timeout=0.08)
    except KeyboardInterrupt:
        sys.stdout.write(clear)
        sys.stdout.flush()
        raise
    sys.stdout.write(clear)
    sys.stdout.flush()

    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def cmd_api_ui(args: argparse.Namespace) -> None:
    from .agent import ApiAgentSession

    class T:
        reset = "\x1b[0m"
        dim = "\x1b[2m"
        # Bright/bold ANSI-16 accents, matching the Codex CLI convention:
        # bold cyan frames input/borders, bright green/red are locked to
        # inserted/deleted content, assistant text inherits the terminal fg.
        cyan = "\x1b[1m\x1b[36m"
        green = "\x1b[92m"
        yellow = "\x1b[93m"
        red = "\x1b[91m"
        white = "\x1b[97m"
        bold = "\x1b[1m"

    color = sys.stdout.isatty() and not args.no_color and os.environ.get("TERM", "") != "dumb"
    if not color:
        for name in vars(T):
            if not name.startswith("_"):
                setattr(T, name, "")

    def styled(text: str, tone: str = "white") -> str:
        return f"{getattr(T, tone)}{text}{T.reset}"

    def approval(prompt: str) -> str:
        return input(f"\n{styled('permission', 'yellow')} {styled(prompt, 'white')}")

    width = min(max(shutil.get_terminal_size((88, 20)).columns, 56), 110)

    def panel(title: str, body_lines: list[str]) -> None:
        """Left-bordered panel: a titled top rule, wrapped body lines, a bottom rule.
        Borders are bold cyan, isolating each panel from the assistant text
        it contains; content lines may carry their own ANSI styling since
        padding never depends on visible width, only the border characters do."""
        inner = width - 2
        title_plain = f"─ {title} " if title else ""
        title_seg = f"─ {styled(title, 'bold')} " if title else ""
        top = styled("╭", "cyan") + styled(title_seg, "cyan") + styled("─" * max(0, inner - len(title_plain)), "cyan") + styled("╮", "cyan")
        print(top)
        for raw in body_lines:
            wrapped = textwrap.wrap(raw, inner - 2, subsequent_indent="  ") or [""]
            for chunk in wrapped:
                print(styled("│ ", "cyan") + chunk)
        print(styled("╰" + "─" * inner + "╯", "cyan"))

    def budget_lines() -> list[str]:
        if session.token_limit is None:
            token_text = f"Session tokens used: {session.token_used:,} (no session cap set)"
            donut = styled("○", "dim")
        else:
            remaining = max(0, session.token_limit - session.token_used)
            ratio = remaining / session.token_limit if session.token_limit else 0
            donut_glyph = ["○", "◔", "◑", "◕", "●"][min(4, max(0, int(ratio * 4 + 0.5)))]
            donut_tone = "green" if ratio > 0.5 else "yellow" if ratio > 0.2 else "red"
            donut = styled(donut_glyph, donut_tone)
            percent = round(ratio * 100)
            token_text = f"{remaining:,} tokens left of {session.token_limit:,} ({percent}% remaining)"
        lines = [f"{donut} {token_text}"]
        conn = store.get_conn()
        try:
            global_budget = store.get_budget(conn, "global")
            global_used = int(conn.execute("SELECT COALESCE(SUM(token_used), 0) FROM sessions").fetchone()[0] or 0)
        finally:
            conn.close()
        if global_budget and global_budget["token_limit"]:
            global_left = max(0, global_budget["token_limit"] - global_used)
            lines.append(f"Global: {global_left:,} tokens left of {global_budget['token_limit']:,} ({global_used:,} used across agents)")
        if session.time_limit_s is not None:
            lines.append(f"Time limit: {session.time_limit_s:,} seconds")
        if session.daily_token_limit is not None:
            conn = store.get_conn()
            try:
                daily_used = store.get_daily_usage(conn, limits.today())
            finally:
                conn.close()
            daily_left = max(0, session.daily_token_limit - daily_used)
            lines.append(f"Today: {daily_used:,} used · {daily_left:,} daily tokens left")
        return lines

    try:
        session = ApiAgentSession(root=args.root, model=args.model, assume_yes=args.yes,
                                  confirm=approval, token_limit=args.token_limit,
                                  time_limit_s=args.time_limit_s,
                                  daily_token_limit=args.daily_token_limit)
    except Exception as exc:
        print(styled(f"Unable to start API agent: {exc}", "red"), file=sys.stderr)
        return

    _print_zetesis_banner(width, color)
    panel(
        "API AGENT",
        [f"{styled('model', 'dim')} {session.model}",
         f"{styled('root ', 'dim')} {session.root}"],
    )
    panel("SESSION BUDGET", budget_lines())
    print(styled("Type a task, or /help for commands. Tool approvals are shown in ", "dim") + styled("yellow", "yellow") + styled(".", "dim"))

    # The browser edits the same SQLite session row. Watch it while input()
    # is blocked so a saved limit is reflected in this terminal immediately.
    def watch_budget() -> None:
        previous = (session.token_limit, session.time_limit_s, None)
        while True:
            time.sleep(0.75)
            try:
                conn = store.get_conn()
                try:
                    row = conn.execute("SELECT token_limit, time_limit_s FROM sessions WHERE id = ?",
                                       (session.recorder.session_id,)).fetchone()
                    global_row = conn.execute(
                        "SELECT token_limit FROM budget_settings WHERE scope = 'global'"
                    ).fetchone()
                finally:
                    conn.close()
                if not row:
                    continue
                current = (row["token_limit"], row["time_limit_s"], global_row["token_limit"] if global_row else None)
                if current != previous:
                    previous = current
                    session.token_limit, session.time_limit_s = current[:2]
                    print(f"\n{styled('limits updated from viewer', 'dim')}")
                    panel("SESSION BUDGET", budget_lines())
                    print(f"{styled('you', 'cyan')}{styled(' › ', 'dim')}", end="", flush=True)
            except Exception:
                # The watcher must never interrupt the interactive agent.
                pass

    threading.Thread(target=watch_budget, daemon=True, name="zetesis-budget-watch").start()
    while True:
        try:
            task = input(f"\n{styled('you', 'cyan')}{styled(' › ', 'dim')}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{styled('Goodbye.', 'dim')}")
            return
        if not task:
            continue
        if task in {"/quit", "/exit"}:
            print(styled("Goodbye.", "dim"))
            return
        if task == "/help":
            panel("COMMANDS", [
                "/help    show this help",
                "/clear   reset conversation context (history stays recorded)",
                "/status  show recorder and hook status",
                "/quit    exit the API UI",
            ])
            continue
        if task == "/clear":
            session.clear_context()
            print(styled("✓ Conversation context cleared; recorder history preserved.", "green"))
            continue
        if task == "/status":
            cmd_status(args)
            panel("SESSION BUDGET", budget_lines())
            continue
        try:
            answer = _run_with_spinner(
                lambda: session.run_turn(task, max_steps=args.max_steps),
                styled, color, width, animate=args.yes,
            )
            panel("agent", [answer] if answer else ["(no response)"])
            panel("SESSION BUDGET", budget_lines())
        except KeyboardInterrupt:
            print(styled("\nTurn interrupted (still finishing in the background; its reply will be dropped).", "yellow"))
        except Exception as exc:
            print(styled(f"\nAgent error: {exc}", "red"), file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(prog="fr", description="Zetesis CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Register hooks and create the local store")
    p_init.add_argument("--global", dest="global_", action="store_true",
                        help="Register in user config instead of this project")
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

    p_export = sub.add_parser("export", help="Write today's events to a JSON file")
    p_export.add_argument("-o", "--output", type=Path, help="Destination JSON file")
    p_export.set_defaults(func=cmd_export)

    p_test = sub.add_parser("test-hook", help="Smoke-test exact Codex hook payloads")
    p_test.set_defaults(func=cmd_test_hook)

    p_notify = sub.add_parser("test-notification", help="Test the desktop sensitive-action notification")
    p_notify.set_defaults(func=cmd_test_notification)

    p_agent = sub.add_parser("agent", help="Run the API-backed Zetesis agent")
    p_agent.add_argument("task")
    p_agent.add_argument("--root", default=".")
    p_agent.add_argument("--model", default=None)
    p_agent.add_argument("--max-steps", type=int, default=20)
    p_agent.add_argument("--yes", action="store_true", help="Auto-approve writes and commands")
    p_agent.add_argument("--token-limit", type=int, default=None)
    p_agent.add_argument("--time-limit", type=int, default=None, dest="time_limit_s", help="Session limit in seconds")
    p_agent.add_argument("--daily-token-limit", type=int, default=None)
    p_agent.set_defaults(func=cmd_agent)

    p_api = sub.add_parser("api-ui", help="Interactive API-backed coding agent")
    p_api.add_argument("--root", default=".")
    p_api.add_argument("--model", default=None)
    p_api.add_argument("--max-steps", type=int, default=20)
    p_api.add_argument("--yes", action="store_true", help="Auto-approve writes and commands")
    p_api.add_argument("--token-limit", type=int, default=None)
    p_api.add_argument("--time-limit", type=int, default=None, dest="time_limit_s", help="Session limit in seconds")
    p_api.add_argument("--daily-token-limit", type=int, default=None)
    p_api.add_argument("--no-color", action="store_true", help="Disable terminal colors")
    p_api.set_defaults(func=cmd_api_ui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
