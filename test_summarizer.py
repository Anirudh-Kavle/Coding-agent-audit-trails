"""Tests for the grounded local-LLM session summarizer.

Uses an injected fake model — the real GGUF never loads here. What's under
test is everything around the model: deterministic packaging, citation
validation, thinking-tag stripping, and caching in sessions.summary.
"""
import json

import pytest

from flight_recorder import store, summarizer


@pytest.fixture()
def seeded_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "recorder.db")
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(store, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(store, "DEBUG_LOG", tmp_path / "debug.log")
    monkeypatch.setattr(store, "RAW_PAYLOADS_LOG", tmp_path / "debug" / "raw_payloads.jsonl")
    store.init_db()
    conn = store.get_conn()
    conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', 1000)")
    for ts, tool, args, exit_ok, risk, reasoning in [
        (1100, "Bash", '{"command": "pytest -q"}', 0, "exec", "run the tests first"),
        (1200, "Edit", '{"file_path": "app.py"}', 1, "write", "fix the failing assertion"),
        (1300, "Bash", '{"command": "pytest -q"}', 1, "exec", None),
    ]:
        conn.execute(
            "INSERT INTO events (session_id, ts, phase, tool, arguments_json, exit_ok, risk, reasoning_text)"
            " VALUES ('s1', ?, 'pre', ?, ?, ?, ?, ?)",
            (ts, tool, args, exit_ok, risk, reasoning),
        )
    conn.commit()
    conn.close()
    return tmp_path


class FakeLlm:
    def __init__(self, text):
        self.text = text
        self.messages = None

    def create_chat_completion(self, messages, **kwargs):
        self.messages = messages
        return {"choices": [{"message": {"content": self.text}}]}


def test_package_session_renders_numbered_lines(seeded_store):
    conn = store.get_conn()
    try:
        packed, ids = summarizer.package_session(conn, "s1")
    finally:
        conn.close()
    assert len(ids) == 3
    assert "command=pytest -q" in packed
    assert "FAILED" in packed  # the exit_ok=0 run is marked
    assert "why: run the tests first" in packed


def test_package_session_empty_session(seeded_store):
    conn = store.get_conn()
    try:
        packed, ids = summarizer.package_session(conn, "nope")
    finally:
        conn.close()
    assert packed == "" and ids == set()


def test_summarize_strips_invalid_citations_and_caches(seeded_store):
    fake = FakeLlm("Ran tests [event 1], fixed app.py [event 2], hallucinated [event 999].")
    record = summarizer.summarize_session("s1", llm=fake)
    assert "[event 1]" in record["text"]
    assert "999" not in record["text"]  # invented citation removed
    # model only ever saw the packaged records
    assert "pytest -q" in fake.messages[1]["content"]
    # cached in sessions.summary
    conn = store.get_conn()
    try:
        cached = summarizer.load_cached_summary(conn, "s1")
    finally:
        conn.close()
    assert cached["text"] == record["text"]


def test_summarize_dedupes_repeated_citation_of_the_same_event(seeded_store):
    # Regression: a summary that leans on one record for every sentence used
    # to cite it every time — [event 1] four sentences running — which reads
    # as noise, not rigor. Only the first mention should keep the citation.
    fake = FakeLlm(
        "The agent attempted to install dependencies [event 1] and ran the "
        "tests, which failed [event 1]. The agent reached the daily API "
        "token limit [event 1], resulting in a failure to proceed. The "
        "agent changed the code to handle the token limit issue [event 1]."
    )
    record = summarizer.summarize_session("s1", llm=fake)
    assert record["text"].count("[event 1]") == 1
    # the prose itself must survive — only the repeated markers are dropped
    assert "resulting in a failure to proceed." in record["text"]
    assert "  " not in record["text"]  # no double-space left behind
    assert " ." not in record["text"] and " ," not in record["text"]


def test_summarize_keeps_distinct_citations_separate(seeded_store):
    fake = FakeLlm("Ran tests [event 1] then fixed the bug [event 2].")
    record = summarizer.summarize_session("s1", llm=fake)
    assert "[event 1]" in record["text"]
    assert "[event 2]" in record["text"]


def test_summarize_strips_thinking_tags(seeded_store):
    fake = FakeLlm("<think>secret chain of thought</think>Tests were run [event 1].")
    record = summarizer.summarize_session("s1", llm=fake)
    assert "secret" not in record["text"]
    assert record["text"].startswith("Tests were run")


def test_summarize_empty_session_returns_none(seeded_store):
    assert summarizer.summarize_session("nope", llm=FakeLlm("x")) is None


def test_packaging_truncates_but_keeps_head_and_tail(seeded_store):
    conn = store.get_conn()
    try:
        for i in range(200):
            conn.execute(
                "INSERT INTO events (session_id, ts, phase, tool, arguments_json, risk)"
                " VALUES ('s1', ?, 'pre', 'Read', ?, 'info')",
                (2000 + i, json.dumps({"file_path": f"src/module_{i}.py"})),
            )
        conn.commit()
        packed, _ = summarizer.package_session(conn, "s1")
    finally:
        conn.close()
    assert len(packed) <= summarizer.MAX_PACKED_CHARS + 100
    assert "events omitted" in packed
    assert "pytest -q" in packed  # chronological head survives
    assert "module_199" in packed  # tail survives