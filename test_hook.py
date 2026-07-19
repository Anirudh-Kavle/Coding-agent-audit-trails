"""Gate test for the PostToolUse reasoning self-heal path (flight_recorder/hook.py).

Regression for the real race found while dogfooding: the transcript FILE can
lag behind the hook's live payload, so a PreToolUse capture can come back as
an honest gap even though the reasoning was real and would show up moments
later. By PostToolUse time more wall-clock time has passed for the writer to
catch up — this should patch the row instead of leaving a permanent gap.

Run: .venv/bin/python -m pytest test_hook.py
"""
import json
import sqlite3

import pytest

from flight_recorder import hook, store


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(store, "DEBUG_LOG", tmp_path / "debug.log")
    monkeypatch.setattr(store, "RAW_PAYLOADS_LOG", tmp_path / "debug" / "raw_payloads.jsonl")
    store.init_db()
    return tmp_path


def _write_transcript(path, entries):
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _user_prompt(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _thinking(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": text}]}}


def _tool_use(tool_use_id, name="Bash", command="echo hi"):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": name, "input": {"command": command}}
        ]},
    }


def _tool_result():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "hi"}]}}


def test_migration_adds_tool_use_id_to_a_pre_existing_db(tmp_path, monkeypatch):
    # Simulates a real install from before tool_use_id existed: the events
    # table has no such column. get_conn() must upgrade it transparently —
    # the real ~/.flight-recorder/recorder.db on this machine is exactly this
    # case, and the very next hook invocation must not crash on it.
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")

    old_schema = """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, ts INTEGER NOT NULL, phase TEXT NOT NULL, tool TEXT,
            arguments_json TEXT, result_json TEXT, exit_ok INTEGER,
            reasoning_text TEXT, risk TEXT NOT NULL DEFAULT 'info', risk_reasons TEXT,
            capture_gap INTEGER DEFAULT 0, git_branch TEXT, git_head TEXT,
            git_dirty INTEGER, files_touched TEXT
        );
    """
    store.ensure_dirs()
    raw = sqlite3.connect(store.DB_PATH)
    raw.executescript(old_schema)
    raw.commit()
    raw.close()

    conn = store.get_conn()  # must not raise
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    conn.close()
    assert "tool_use_id" in cols


def test_post_tool_use_heals_a_gap_once_the_transcript_catches_up(isolated_store, tmp_path):
    transcript_path = tmp_path / "session.jsonl"

    # At PreToolUse time, the transcript file hasn't been written past the
    # user's prompt yet — the real thinking + tool_use for THIS call haven't
    # landed on disk (the exact race observed in practice).
    _write_transcript(transcript_path, [_user_prompt("run echo hi")])

    pre_payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu_1",
    }
    hook._handle(pre_payload)

    conn = store.get_conn()
    row = conn.execute("SELECT * FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert row["capture_gap"] == 1
    assert row["reasoning_text"] is None

    # By PostToolUse time, the writer has caught up: the real thinking and
    # the matching tool_use are now on disk.
    _write_transcript(transcript_path, [
        _user_prompt("run echo hi"),
        _thinking("I'll run echo hi to check the shell works"),
        _tool_use("toolu_1"),
        _tool_result(),
    ])

    post_payload = dict(pre_payload, hook_event_name="PostToolUse", tool_response={"stdout": "hi"})
    hook._handle(post_payload)

    conn = store.get_conn()
    healed = conn.execute("SELECT * FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert healed["capture_gap"] == 0
    assert healed["reasoning_text"] == "I'll run echo hi to check the shell works"
    # Still exactly one row — the post event paired with the pre row, not a duplicate.
    conn = store.get_conn()
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert count == 1


def test_opportunistic_heal_recovers_a_gap_when_post_tool_use_never_fires(isolated_store, tmp_path):
    # Regression for the real incident: Claude Code sometimes never fires
    # PostToolUse at all (seen with a malformed command), so the pairing
    # self-heal never gets a chance to run. A later, unrelated hook event in
    # the same session should still be able to retry and heal the old gap.
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("run echo hi")])

    first_call = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu_1",
    }
    hook._handle(first_call)  # PostToolUse for this one never comes.

    conn = store.get_conn()
    row = conn.execute("SELECT * FROM events WHERE tool_use_id='toolu_1'").fetchone()
    conn.close()
    assert row["capture_gap"] == 1

    # The transcript catches up, and a second, unrelated tool call's
    # PreToolUse fires — a completely different action in the same session.
    _write_transcript(transcript_path, [
        _user_prompt("run echo hi"),
        _thinking("I'll run echo hi to check the shell works"),
        _tool_use("toolu_1"),
        _tool_result(),
        _thinking("Now let's check the date"),
        _tool_use("toolu_2", command="date"),
    ])
    second_call = dict(first_call, tool_use_id="toolu_2", tool_input={"command": "date"})
    hook._handle(second_call)

    conn = store.get_conn()
    healed = conn.execute("SELECT * FROM events WHERE tool_use_id='toolu_1'").fetchone()
    second = conn.execute("SELECT * FROM events WHERE tool_use_id='toolu_2'").fetchone()
    conn.close()
    assert healed["capture_gap"] == 0
    assert healed["reasoning_text"] == "I'll run echo hi to check the shell works"
    # The second call captures its own reasoning normally (its own thinking
    # block is already in the file by the time it fires) — the opportunistic
    # heal on top of that fixes the *older* toolu_1 row, not this one.
    assert second["capture_gap"] == 0
    assert second["reasoning_text"] == "Now let's check the date"


def test_opportunistic_heal_ignores_gaps_outside_the_recency_window(isolated_store, tmp_path):
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("run echo hi")])

    old_call = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu_old",
    }
    hook._handle(old_call)

    conn = store.get_conn()
    # Backdate it past the 5-minute recency window.
    conn.execute("UPDATE events SET ts = ts - 600000 WHERE tool_use_id='toolu_old'")
    conn.commit()
    conn.close()

    _write_transcript(transcript_path, [
        _user_prompt("run echo hi"),
        _thinking("this would heal it if it were still in the window"),
        _tool_use("toolu_old"),
        _tool_result(),
        _thinking("a later call"),
        _tool_use("toolu_new", command="date"),
    ])
    hook._handle(dict(old_call, tool_use_id="toolu_new", tool_input={"command": "date"}))

    conn = store.get_conn()
    row = conn.execute("SELECT * FROM events WHERE tool_use_id='toolu_old'").fetchone()
    conn.close()
    assert row["capture_gap"] == 1  # left alone — too old to retry


def test_post_tool_use_leaves_gap_alone_if_transcript_still_hasnt_caught_up(isolated_store, tmp_path):
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("run echo hi")])

    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu_1",
    }
    hook._handle(payload)

    # Transcript still hasn't caught up by PostToolUse time either.
    post_payload = dict(payload, hook_event_name="PostToolUse", tool_response={"stdout": "hi"})
    hook._handle(post_payload)

    conn = store.get_conn()
    row = conn.execute("SELECT * FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert row["capture_gap"] == 1
    assert row["reasoning_text"] is None
