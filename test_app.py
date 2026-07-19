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
        ("sess_a", 1100, "post", "Read", "exec"),
        ("sess_a", 1200, "post", "Bash", "sensitive"),
        ("sess_b", 2100, "post", "Edit", "write"),
    ]
    for session_id, ts, phase, tool, risk in events:
        conn.execute(
            "INSERT INTO events (session_id, ts, phase, tool, risk, risk_reasons) VALUES (?, ?, ?, ?, ?, '[]')",
            (session_id, ts, phase, tool, risk),
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


def test_root_serves_something(client):
    # dist mount when viewer/dist exists, JSON pointer otherwise — either way 200.
    assert client.get("/").status_code == 200
