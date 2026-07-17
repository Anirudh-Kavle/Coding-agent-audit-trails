"""Standalone entry point registered in .claude/settings.json.

Exists so the hook command works via a plain interpreter + script path
(no dependency on the package being installed or on PATH — Claude Code
invokes this as a bare shell command from an arbitrary cwd).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flight_recorder.hook import main  # noqa: E402

if __name__ == "__main__":
    main()
