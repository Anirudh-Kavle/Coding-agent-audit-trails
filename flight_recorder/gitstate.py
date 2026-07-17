"""Best-effort git context capture, bounded by a strict timeout.

Never allowed to slow the hook down meaningfully or raise — a recorder
that breaks the pilot's controls is worse than no recorder.
"""
from __future__ import annotations

import subprocess

TIMEOUT = 0.5  # seconds; generous vs the 100ms budget to survive cold Windows spawns


def _run(args: list[str], cwd: str | None) -> str | None:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def capture(cwd: str | None) -> dict:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    head = _run(["git", "rev-parse", "--short", "HEAD"], cwd)
    status = _run(["git", "status", "--porcelain"], cwd)
    repo_root = _run(["git", "rev-parse", "--show-toplevel"], cwd)

    return {
        "git_branch": branch,
        "git_head": head,
        "git_dirty": 1 if status else (0 if status is not None else None),
        "git_repo": repo_root,
    }
