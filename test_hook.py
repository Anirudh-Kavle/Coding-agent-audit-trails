"""Gate test for the PostToolUse reasoning self-heal path (zetesis/hook.py).

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

from zetesis import hook, store


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(store, "DEBUG_LOG", tmp_path / "debug.log")
    monkeypatch.setattr(store, "RAW_PAYLOADS_LOG", tmp_path / "debug" / "raw_payloads.jsonl")
    # Without this, a real paused recorder on the dev machine makes every
    # hook call here a silent no-op and all assertions fail confusingly.
    monkeypatch.setattr(store, "PAUSE_FLAG", tmp_path / "paused")
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


def test_bash_files_touched_covers_rm_mv_cp_touch_mkdir():
    # Regression: file: search used to be blind to Bash entirely — only
    # Edit/Write/NotebookEdit ever populated files_touched, so `rm`/`mv`/`cp`
    # never showed up no matter what you searched for.
    assert hook._bash_files_touched("rm file.txt") == ["file.txt"]
    assert hook._bash_files_touched("rm -rf node_modules") == ["node_modules"]
    assert hook._bash_files_touched("mv a.txt b.txt") == ["a.txt", "b.txt"]
    assert hook._bash_files_touched("cp -r src dst") == ["src", "dst"]
    assert hook._bash_files_touched("touch new.py") == ["new.py"]
    assert hook._bash_files_touched("mkdir -p some/nested/dir") == ["some/nested/dir"]


def test_bash_files_touched_covers_redirects():
    assert hook._bash_files_touched("echo hi > out.txt") == ["out.txt"]
    assert hook._bash_files_touched("echo hi >> out.txt") == ["out.txt"]


def test_bash_files_touched_ignores_flags():
    assert hook._bash_files_touched("rm -rf --no-preserve-root /tmp/x") == ["/tmp/x"]


def test_bash_files_touched_handles_chained_commands():
    assert hook._bash_files_touched("cd /tmp && rm file.txt") == ["file.txt"]
    assert hook._bash_files_touched("rm a.txt; rm b.txt") == ["a.txt", "b.txt"]


def test_bash_files_touched_strips_leading_sudo():
    assert hook._bash_files_touched("sudo rm -rf /var/log/app.log") == ["/var/log/app.log"]


def test_bash_files_touched_respects_quoted_paths():
    assert hook._bash_files_touched("rm 'my file.txt'") == ["my file.txt"]


def test_bash_files_touched_deduplicates():
    assert hook._bash_files_touched("rm a.txt a.txt") == ["a.txt"]


def test_bash_files_touched_ignores_non_file_commands():
    assert hook._bash_files_touched("ls -la") == []
    assert hook._bash_files_touched("cat file1 | grep foo") == []
    assert hook._bash_files_touched('git commit -m "fix: something"') == []


def test_bash_files_touched_survives_unbalanced_quotes():
    # Best-effort, not a real shell parser — malformed input must not crash
    # the hook, just skip that segment.
    assert hook._bash_files_touched("rm 'unterminated") == []


def test_files_touched_populated_end_to_end_for_a_bash_command(isolated_store, tmp_path):
    hook._handle({
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf node_modules"},
        "tool_use_id": "toolu_1",
    })
    conn = store.get_conn()
    row = conn.execute("SELECT files_touched FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert json.loads(row["files_touched"]) == ["node_modules"]


def test_permission_request_does_not_duplicate_the_paired_event(isolated_store, tmp_path):
    # Regression: Claude Code fires PreToolUse, PermissionRequest, and
    # PostToolUse for the same call — PermissionRequest carries the same
    # tool_name/tool_input but no tool_use_id and no outcome of its own.
    # Recording it as its own row duplicated every permission-gated action
    # in the timeline (seen live while dogfooding).
    common = {
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "npm run build"},
    }
    hook._handle({**common, "hook_event_name": "PreToolUse", "tool_use_id": "toolu_1"})
    hook._handle({**common, "hook_event_name": "PermissionRequest"})
    hook._handle({
        **common, "hook_event_name": "PostToolUse", "tool_use_id": "toolu_1",
        "tool_response": {"exit_code": 0},
    })

    conn = store.get_conn()
    rows = conn.execute("SELECT phase, exit_ok FROM events WHERE tool='Bash'").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["phase"] == "pre"
    assert rows[0]["exit_ok"] == 1


def test_codex_session_gets_a_title_from_the_first_prompt(isolated_store, tmp_path):
    # Regression: only Claude Code writes an "ai-title" transcript entry, so
    # extract_session_title() always came back empty for Codex/API sessions
    # and the sidebar fell back to showing the raw session id. Codex's
    # UserPromptSubmit carries the prompt text itself — use that instead.
    hook._handle({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess-codex",
        "cwd": str(tmp_path),
        "prompt": "fix the login bug\nsecond line should be ignored",
    })
    conn = store.get_conn()
    row = conn.execute("SELECT title FROM sessions WHERE id = 'sess-codex'").fetchone()
    conn.close()
    assert row["title"] == "fix the login bug"


def test_existing_claude_title_is_not_overwritten_by_the_prompt_fallback(isolated_store, tmp_path):
    hook._handle({
        "hook_event_name": "SessionStart",
        "session_id": "sess-claude",
        "cwd": str(tmp_path),
    })
    conn = store.get_conn()
    store.set_session_title(conn, "sess-claude", "Claude's own title")
    conn.commit()
    conn.close()

    hook._handle({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess-claude",
        "cwd": str(tmp_path),
        "prompt": "this should never appear as the title",
    })
    conn = store.get_conn()
    row = conn.execute("SELECT title FROM sessions WHERE id = 'sess-claude'").fetchone()
    conn.close()
    assert row["title"] == "Claude's own title"


def test_migration_adds_tool_use_id_to_a_pre_existing_db(tmp_path, monkeypatch):
    # Simulates a real install from before tool_use_id existed: the events
    # table has no such column. get_conn() must upgrade it transparently —
    # the real ~/.zetesis/recorder.db on this machine is exactly this
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


def test_risk_is_reclassified_once_the_result_reveals_a_secret(isolated_store, tmp_path):
    # The PreToolUse row is scored from arguments alone ("cat config.py"
    # looks clean) — the tool hasn't run yet, so there's no result to scan.
    # By PostToolUse time the actual output is known, and if IT contains
    # something like a hardcoded secret, the stored row must be upgraded,
    # not left at whatever the clean-looking request implied.
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("cat the config")])

    pre_payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Bash",
        "tool_input": {"command": "cat config.py"},
        "tool_use_id": "toolu_1",
    }
    hook._handle(pre_payload)

    conn = store.get_conn()
    row = conn.execute("SELECT * FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert row["risk"] == "exec"
    assert row["risk_reasons"] == "[]"

    post_payload = dict(
        pre_payload,
        hook_event_name="PostToolUse",
        tool_response={"stdout": 'API_KEY = "sk-abc123"'},
    )
    hook._handle(post_payload)

    conn = store.get_conn()
    healed = conn.execute("SELECT * FROM events WHERE tool='Bash'").fetchone()
    conn.close()
    assert healed["risk"] == "sensitive"
    assert "secret-like keyword" in healed["risk_reasons"]
    # Still exactly one row — healed in place, not duplicated.
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


def test_opportunistic_heal_reaches_past_a_newer_unhealable_gap(isolated_store, tmp_path):
    # Regression for the real incident: three sequential calls where the
    # OLDEST has real, recoverable reasoning but the two newer ones are
    # legitimate permanent gaps (nothing preceded them). Only ever checking
    # the single most recent stale row lets those newer gaps mask the older,
    # healable one forever — this must reach past them.
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("read three files")])

    base_payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
        "tool_name": "Read",
    }
    for tool_use_id in ("toolu_a", "toolu_b", "toolu_c"):
        hook._handle(dict(base_payload, tool_input={"file_path": tool_use_id}, tool_use_id=tool_use_id))

    conn = store.get_conn()
    rows = {r["tool_use_id"]: r["capture_gap"] for r in conn.execute("SELECT * FROM events")}
    conn.close()
    assert rows == {"toolu_a": 1, "toolu_b": 1, "toolu_c": 1}

    # Transcript catches up: real thinking before the FIRST call only; the
    # second and third really do have nothing between them (legitimate gaps).
    _write_transcript(transcript_path, [
        _user_prompt("read three files"),
        _thinking("I'll read all three files"),
        _tool_use("toolu_a", name="Read"),
        _tool_result(),
        _tool_use("toolu_b", name="Read"),
        _tool_result(),
        _tool_use("toolu_c", name="Read"),
        _tool_result(),
        _thinking("a later, unrelated action"),
        _tool_use("toolu_d", name="Bash", command="date"),
    ])
    hook._handle(dict(base_payload, tool_name="Bash", tool_input={"command": "date"}, tool_use_id="toolu_d"))

    conn = store.get_conn()
    rows = {r["tool_use_id"]: (r["capture_gap"], r["reasoning_text"]) for r in conn.execute("SELECT * FROM events")}
    conn.close()
    assert rows["toolu_a"] == (0, "I'll read all three files")
    assert rows["toolu_b"] == (1, None)
    assert rows["toolu_c"] == (1, None)


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
    # Backdate it past the 30-minute recency window.
    conn.execute("UPDATE events SET ts = ts - 2400000 WHERE tool_use_id='toolu_old'")
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


def test_session_title_captured_from_transcript_ai_title(isolated_store, tmp_path):
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [
        _user_prompt("brainstorm art contest ideas"),
        {"type": "ai-title", "sessionId": "sess1", "aiTitle": "Brainstorm art contest project ideas"},
    ])

    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
    }
    hook._handle(payload)

    conn = store.get_conn()
    row = conn.execute("SELECT title FROM sessions WHERE id='sess1'").fetchone()
    conn.close()
    assert row["title"] == "Brainstorm art contest project ideas"


def test_session_title_stays_once_set_even_if_transcript_title_later_differs(isolated_store, tmp_path):
    # The title is generated once by Claude Code and doesn't change — once
    # captured, later hook calls in the same session must not overwrite it
    # (also means they can skip re-scanning the transcript for it at all).
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [
        {"type": "ai-title", "sessionId": "sess1", "aiTitle": "Original title"},
    ])
    hook._handle({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
    })

    _write_transcript(transcript_path, [
        {"type": "ai-title", "sessionId": "sess1", "aiTitle": "A different title"},
    ])
    hook._handle({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
    })

    conn = store.get_conn()
    row = conn.execute("SELECT title FROM sessions WHERE id='sess1'").fetchone()
    conn.close()
    assert row["title"] == "Original title"


def test_session_title_absent_when_transcript_has_none_yet(isolated_store, tmp_path):
    transcript_path = tmp_path / "session.jsonl"
    _write_transcript(transcript_path, [_user_prompt("hello")])
    hook._handle({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess1",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript_path),
    })

    conn = store.get_conn()
    row = conn.execute("SELECT title FROM sessions WHERE id='sess1'").fetchone()
    conn.close()
    assert row["title"] is None


def test_migration_adds_title_to_a_pre_existing_sessions_table(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")

    old_schema = """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, started_at INTEGER, ended_at INTEGER,
            cwd TEXT, git_repo TEXT, source TEXT
        );
    """
    store.ensure_dirs()
    raw = sqlite3.connect(store.DB_PATH)
    raw.executescript(old_schema)
    raw.commit()
    raw.close()

    conn = store.get_conn()  # must not raise
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    conn.close()
    assert "title" in cols


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
