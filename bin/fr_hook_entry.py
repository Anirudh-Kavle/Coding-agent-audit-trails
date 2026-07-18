#!/usr/bin/env python3
"""Flight Recorder hook entry point.

Captures Claude Code lifecycle events and logs them to:
- storage/flight_recorder.jsonl (plaintext, greppable)
- storage/flight_recorder.db (SQLite state log)
"""

import json
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
STORAGE_DIR = PROJECT_ROOT / "storage"
JSONL_PATH = STORAGE_DIR / "flight_recorder.jsonl"
DB_PATH = STORAGE_DIR / "flight_recorder.db"

def ensure_storage():
    """Create storage directory if it doesn't exist."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def init_db():
    """Initialize SQLite database with schema."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            working_dir TEXT,
            git_branch TEXT,
            git_commit TEXT,
            context TEXT,
            details TEXT
        )
    """)
    db.commit()
    return db

def get_git_info():
    """Get current git branch and commit."""
    try:
        result_branch = os.popen("git rev-parse --abbrev-ref HEAD 2>/dev/null").read().strip()
        result_commit = os.popen("git rev-parse HEAD 2>/dev/null").read().strip()
        return result_branch or "unknown", result_commit or "unknown"
    except:
        return "unknown", "unknown"

def log_event(event_type):
    """Log a lifecycle event."""
    ensure_storage()

    timestamp = datetime.utcnow().isoformat() + "Z"
    working_dir = os.getcwd()
    git_branch, git_commit = get_git_info()

    event = {
        "timestamp": timestamp,
        "event_type": event_type,
        "working_dir": working_dir,
        "git_branch": git_branch,
        "git_commit": git_commit,
    }

    # Append to JSONL (greppable, fast)
    try:
        with open(JSONL_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"Warning: Failed to write JSONL: {e}", file=sys.stderr)

    # Also write to SQLite (queryable)
    try:
        db = init_db()
        db.execute(
            """INSERT INTO events
               (timestamp, event_type, working_dir, git_branch, git_commit, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, event_type, working_dir, git_branch, git_commit, json.dumps(event))
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"Warning: Failed to write SQLite: {e}", file=sys.stderr)

if __name__ == "__main__":
    # Determine event type from environment or arguments
    event_type = os.environ.get("CLAUDE_HOOK_EVENT") or "unknown"

    # Map hook names to event types
    hook_map = {
        "PreToolUse": "tool_start",
        "PostToolUse": "tool_end",
        "PreCompact": "compact_start",
        "SessionStart": "session_start",
        "SessionEnd": "session_end",
        "Stop": "session_stop",
    }

    for hook_name, event_name in hook_map.items():
        if hook_name in sys.argv or hook_name in os.environ.get("CLAUDE_HOOK_NAME", ""):
            event_type = event_name
            break

    log_event(event_type)
