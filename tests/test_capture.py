from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flight_recorder import hook, reasoning, store
from flight_recorder.recorder import FlightRecorder


class TemporaryStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = {
            "STORE_DIR": root,
            "DB_PATH": root / "recorder.db",
            "EVENTS_DIR": root / "events",
            "SNAPSHOTS_DIR": root / "snapshots",
            "DEBUG_LOG": root / "debug.log",
            "RAW_PAYLOADS_LOG": root / "debug" / "raw_payloads.jsonl",
        }
        self.original = {name: getattr(store, name) for name in self.paths}
        for name, value in self.paths.items():
            setattr(store, name, value)
        store.init_db()

    def tearDown(self) -> None:
        for name, value in self.original.items():
            setattr(store, name, value)
        self.temp.cleanup()


class HookCaptureTests(TemporaryStoreTestCase):
    def test_pre_and_post_are_one_complete_action(self) -> None:
        transcript = self.paths["STORE_DIR"] / "transcript.jsonl"
        entries = [
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "old", "content": "done"}
            ]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "thinking", "text": "I need to inspect the project."},
                {"type": "text", "text": "I will list the files."},
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {}}
            ]}},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        git = {"git_repo": None, "git_branch": None, "git_head": None, "git_dirty": None}

        pre = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "x" * 20000},
            "transcript_path": str(transcript),
            "cwd": self.temp.name,
        }
        post = {
            **pre,
            "hook_event_name": "PostToolUse",
            "tool_response": {"stdout": "y" * 20000},
        }
        with patch.object(hook.gitstate, "capture", return_value=git):
            hook._handle(pre)
            hook._handle(post)

        conn = store.get_conn()
        try:
            rows = conn.execute("SELECT * FROM events").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        row = dict(rows[0])
        self.assertEqual(row["action_id"], "call-1")
        self.assertEqual(row["phase"], "post")
        self.assertEqual(row["reasoning_text"], "I need to inspect the project.\nI will list the files.")
        self.assertEqual(row["capture_gap"], 0)
        self.assertGreater(len(row["arguments_json"]), 20000)
        self.assertTrue(row["result_json"].endswith("...[truncated]"))
        self.assertEqual(row["exit_ok"], 1)

    def test_missing_transcript_records_honest_capture_gap(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-gap",
            "tool_use_id": "call-gap",
            "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
        }
        git = {"git_repo": None, "git_branch": None, "git_head": None, "git_dirty": None}
        with patch.object(hook.gitstate, "capture", return_value=git):
            hook._handle(payload)
        conn = store.get_conn()
        try:
            row = dict(conn.execute("SELECT * FROM events").fetchone())
        finally:
            conn.close()
        self.assertIsNone(row["reasoning_text"])
        self.assertEqual(row["capture_gap"], 1)


class ReasoningTests(unittest.TestCase):
    def test_reasoning_stops_at_previous_tool_result(self) -> None:
        entries = [
            {"role": "assistant", "content": [{"type": "thinking", "text": "too old"}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
            {"role": "assistant", "content": [
                {"type": "reasoning_summary", "text": "visible rationale"},
                {"type": "function_call", "call_id": "fc-1", "name": "shell"},
                {"type": "text", "text": "must not be included"},
            ]},
        ]
        text, gap = reasoning.extract_reasoning_from_entries(entries, "fc-1")
        self.assertEqual(text, "visible rationale")
        self.assertFalse(gap)


class ProgrammaticRecorderTests(TemporaryStoreTestCase):
    def test_api_agent_can_record_visible_rationale_and_result(self) -> None:
        git = {"git_repo": None, "git_branch": None, "git_head": None, "git_dirty": None}
        with patch("flight_recorder.recorder.gitstate.capture", return_value=git):
            recorder = FlightRecorder("api-session", cwd=self.temp.name, source="openai-api")
            action = recorder.start_action(
                "shell", {"command": "python -m unittest"},
                reasoning_text="Run the local tests before changing code.",
            )
            action.finish({"stdout": "OK", "exit_code": 0})
        conn = store.get_conn()
        try:
            row = dict(conn.execute("SELECT * FROM events").fetchone())
        finally:
            conn.close()
        self.assertEqual(row["reasoning_text"], "Run the local tests before changing code.")
        self.assertIn('"stdout": "OK"', row["result_json"])
        self.assertEqual(row["capture_gap"], 0)


if __name__ == "__main__":
    unittest.main()
