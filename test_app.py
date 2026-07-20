"""Gate tests for the viewer API (flight_recorder/viewer/app.py).

Runs against a temp SQLite DB by monkeypatching store.DB_PATH — the app's
_conn() reads it at call time, so no real ~/.flight-recorder data is touched.
Run: .venv/bin/python -m pytest test_app.py
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flight_recorder import store
from flight_recorder.viewer.app import app

SCHEMA = Path("flight_recorder/schema.sql").read_text()


def _seed(conn):
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO sessions (id, started_at, cwd, source) VALUES ('sess_a', 1000, '/tmp/a', 'startup')"
    )
    conn.execute(
        "INSERT INTO sessions (id, started_at, ended_at, cwd, source) VALUES ('sess_b', 2000, 3000, '/tmp/b', 'resume')"
    )
    events = [
        ("sess_a", 1100, "post", "Read", "read", 1, "exec"),
        ("sess_a", 1200, "post", "Bash", "bash", 0, "sensitive"),
        ("sess_b", 2100, "post", "Edit", "edit", 1, "write"),
    ]
    for session_id, ts, phase, tool, tool_kind, exit_ok, risk in events:
        conn.execute(
            "INSERT INTO events (session_id, ts, phase, tool, tool_kind, exit_ok, risk, risk_reasons)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '[]')",
            (session_id, ts, phase, tool, tool_kind, exit_ok, risk),
        )
    conn.commit()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    monkeypatch.setattr(store, "DB_PATH", db_path)
    import sqlite3

    conn = sqlite3.connect(db_path)
    _seed(conn)
    conn.close()
    return TestClient(app)


def test_all_returns_events_across_sessions(client):
    events = client.get("/api/sessions/all/events").json()
    assert {e["session_id"] for e in events} == {"sess_a", "sess_b"}
    assert [e["ts"] for e in events] == sorted([e["ts"] for e in events], reverse=True)


def test_specific_session_still_filters(client):
    events = client.get("/api/sessions/sess_a/events").json()
    assert len(events) == 2
    assert all(e["session_id"] == "sess_a" for e in events)


def test_risk_filter_combines_with_all(client):
    events = client.get("/api/sessions/all/events", params={"risk": "sensitive"}).json()
    assert len(events) == 1
    assert events[0]["tool"] == "Bash"


def test_risk_reasons_deserialized_to_list(client):
    events = client.get("/api/sessions/all/events").json()
    assert all(isinstance(e["risk_reasons"], list) for e in events)


def test_missing_event_returns_null(client):
    res = client.get("/api/events/99999")
    assert res.status_code == 200
    assert res.json() is None


def test_sessions_include_deterministic_stat_counts(client):
    sessions = {s["id"]: s for s in client.get("/api/sessions").json()}
    a = sessions["sess_a"]
    assert a["action_count"] == 2
    assert a["bash_count"] == 1
    assert a["failed_count"] == 1
    assert a["sensitive_count"] == 1
    assert a["edit_count"] == 0
    b = sessions["sess_b"]
    assert b["action_count"] == 1
    assert b["edit_count"] == 1
    assert b["failed_count"] == 0


def test_sessions_derive_project_from_repo_or_cwd(client):
    sessions = {s["id"]: s for s in client.get("/api/sessions").json()}
    # No git_repo seeded → falls back to cwd; display name is the basename.
    assert sessions["sess_a"]["project_key"] == "/tmp/a"
    assert sessions["sess_a"]["project"] == "a"
    assert sessions["sess_b"]["project"] == "b"


def test_root_serves_something(client):
    # dist mount when viewer/dist exists, JSON pointer otherwise — either way 200.
    assert client.get("/").status_code == 200
