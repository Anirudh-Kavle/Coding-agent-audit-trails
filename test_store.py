import time
import sqlite3

from flight_recorder.store import (
    init_db,
    get_conn,
    insert_event,
    append_jsonl,
)

# Create database
init_db()

conn = get_conn()

event = {
    "session_id": "demo-session",
    "ts": int(time.time() * 1000),
    "phase": "pre",
    "tool": "Bash",
    "arguments_json": '{"command":"echo hello"}',
    "result_json": '{"stdout":"hello"}',
    "exit_ok": 1,
    "reasoning_text": "Testing the storage layer.",
    "risk": "exec",
    "risk_reasons": "test",
    "capture_gap": 0,
    "git_branch": "main",
    "git_head": "abc123",
    "git_dirty": 0,
    "files_touched": "[]",
}

event_id = insert_event(conn, event)
conn.commit()

append_jsonl(event)

print("Saved event:", event_id)

rows = conn.execute("SELECT * FROM events").fetchall()

for row in rows:
    print(dict(row))