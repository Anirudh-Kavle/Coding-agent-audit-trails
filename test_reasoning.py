"""Gate tests for reasoning.extract_reasoning (flight_recorder/reasoning.py).

Covers two real bugs found while dogfooding Flight Recorder on itself:

1. Stale-turn misattribution: the transcript FILE can lag behind the hook's
   in-memory payload (tool_name/tool_input/tool_use_id come from live
   dispatch; the JSONL write does not). Reading a stale tail must never
   silently attach a *previous, unrelated* turn's reasoning to the current
   action — that's worse than an honest gap, since it looks confident and
   specific while being flatly wrong.
2. Missing turn boundary: the walker only stopped at a tool_result, never at
   a fresh user prompt, so stale reasoning could bleed across a new
   instruction even when the file *was* fully caught up.

Run: .venv/bin/python -m pytest test_reasoning.py
"""
import json

from flight_recorder import reasoning


def _write(tmp_path, entries):
    path = tmp_path / "transcript.jsonl"
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return str(path)


def _user_prompt(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _tool_result():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}}


def _thinking(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": text}]}}


def _assistant_text(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _tool_use(tool_use_id, name="Bash"):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}]},
    }


def test_captures_immediate_thinking_before_matching_tool_use(tmp_path):
    path = _write(tmp_path, [
        _user_prompt("do the thing"),
        _thinking("I should run ls first"),
        _tool_use("toolu_abc"),
    ])
    text, capture_gap = reasoning.extract_reasoning(path, "toolu_abc")
    assert capture_gap is False
    assert text == "I should run ls first"


def test_capture_gap_on_batched_call_with_no_preceding_text(tmp_path):
    # Second of two parallel/sequential tool calls in the same turn: nothing
    # sits between the prior tool_result and this tool_use — a legitimate,
    # honest gap, not a bug.
    path = _write(tmp_path, [
        _user_prompt("do two things"),
        _thinking("plan"),
        _tool_use("toolu_first"),
        _tool_result(),
        _tool_use("toolu_second"),
    ])
    text, capture_gap = reasoning.extract_reasoning(path, "toolu_second")
    assert (text, capture_gap) == (None, True)


def test_stale_reasoning_not_misattributed_across_new_user_turn(tmp_path):
    # Regression for the exact bug hit in practice: an old turn's assistant
    # text must never bleed across a fresh user prompt into a new action's
    # reasoning, even when there's nothing fresh to replace it with.
    path = _write(tmp_path, [
        _assistant_text("This is the summary from a completely unrelated earlier task."),
        _user_prompt("Create scratch/hello.txt"),
        _tool_use("toolu_write"),
    ])
    text, capture_gap = reasoning.extract_reasoning(path, "toolu_write")
    assert (text, capture_gap) == (None, True)


def test_freshness_gate_rejects_a_transcript_that_hasnt_caught_up(tmp_path):
    # Simulates the real race: the hook fires with tool_use_id "toolu_new",
    # but the transcript file on disk hasn't been written past the previous
    # turn yet. Old, real, well-formed text sits at the tail — it must be
    # ignored, not returned as if it were current.
    path = _write(tmp_path, [
        _assistant_text("Old finished turn's reasoning."),
    ])
    text, capture_gap = reasoning.extract_reasoning(path, "toolu_new")
    assert (text, capture_gap) == (None, True)


def test_no_tool_use_id_falls_back_to_walking_the_tail(tmp_path):
    # PostToolUse and other non-tool phases don't pass a tool_use_id; the
    # freshness gate is skipped entirely rather than always failing closed.
    path = _write(tmp_path, [
        _user_prompt("go"),
        _thinking("reasoning without an id to check"),
        _tool_use("toolu_x"),
    ])
    text, capture_gap = reasoning.extract_reasoning(path, None)
    assert (text, capture_gap) == ("reasoning without an id to check", False)


def test_missing_transcript_path_is_an_honest_gap():
    assert reasoning.extract_reasoning(None) == (None, True)


def test_nonexistent_file_is_an_honest_gap(tmp_path):
    assert reasoning.extract_reasoning(str(tmp_path / "does_not_exist.jsonl")) == (None, True)
