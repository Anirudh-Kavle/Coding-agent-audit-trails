"""Best-effort desktop notifications for high-risk actions.

Notifications are deliberately out-of-band: a missing desktop session, blocked
notification provider, or malformed message must never affect the agent hook.
Set FLIGHT_RECORDER_NOTIFY=0 to disable them.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def enabled() -> bool:
    return os.environ.get("FLIGHT_RECORDER_NOTIFY", "1").lower() not in {"0", "false", "no", "off"}


def _launch(command: list[str]) -> bool:
    try:
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL, "close_fds": True}
        if platform.system() == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(command, **kwargs)
        return True
    except Exception:
        return False


def notify(title: str, message: str) -> bool:
    """Launch a short desktop notification without waiting for it."""
    if not enabled():
        return False
    system = platform.system()
    if system == "Windows":
        title = f"{title}"
        text = f"{title}: {message}"[:240]
        # Use a detached native desktop popup. ``msg.exe`` can silently target
        # a different Windows session when the hook runs from an agent host.
        popup = (
            "import ctypes,sys; "
            "ctypes.windll.user32.MessageBoxW(0, sys.argv[1], sys.argv[2], 0x30)"
        )
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            subprocess.Popen(
                [sys.executable, "-c", popup, text, title[:80]],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags,
            )
            return True
        except Exception:
            return _launch(["msg.exe", "*", "/TIME:8", text])
    if system == "Darwin":
        script = f'display notification {message!r} with title {title!r}'
        return _launch(["osascript", "-e", script])
    return _launch(["notify-send", title, message])


def notify_sensitive(tool: str | None, reasons: list[str]) -> bool:
    reason = ", ".join(reasons[:2]) if reasons else "sensitive risk rule"
    return notify("Flight Recorder: sensitive action", f"{tool or 'tool'} ({reason})")
