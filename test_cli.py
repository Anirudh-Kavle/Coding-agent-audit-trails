"""CLI export checks."""
import argparse
import json
import time

from zetesis import cli, store


def test_export_writes_only_todays_events(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(store, "RAW_PAYLOADS_LOG", tmp_path / "debug" / "raw_payloads.jsonl")
    monkeypatch.setattr(store, "DEBUG_LOG", tmp_path / "debug.log")
    monkeypatch.setattr(store, "PAUSE_FLAG", tmp_path / "paused")
    store.init_db()

    now = int(time.time() * 1000)
    conn = store.get_conn()
    try:
        conn.execute("INSERT INTO events (session_id, ts, phase, tool) VALUES (?, ?, ?, ?)", ("today", now, "pre", "Read"))
        conn.execute("INSERT INTO events (session_id, ts, phase, tool) VALUES (?, ?, ?, ?)", ("old", now - 86_400_000, "pre", "Bash"))
        conn.commit()
    finally:
        conn.close()

    output = tmp_path / "today.json"
    cli.cmd_export(argparse.Namespace(output=output))

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert [event["session_id"] for event in exported] == ["today"]
