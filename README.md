# Flight Recorder

A local, real-time black box for coding-agent sessions. It captures each
consequential tool action, binds it to the assistant context that preceded it,
and preserves the evidence in SQLite plus an append-only JSONL mirror.

## F1/F2 status

F1 action capture and F2 reasoning capture are implemented and tested:

- Pre-action arguments and the post-action result are paired into one SQLite
  row. Provider tool-call IDs are preferred; older hook payloads use the newest
  unmatched action from the same session and tool.
- Full tool arguments are retained. Large results are truncated at 16KB with an
  explicit marker.
- The reasoning parser tails at most 64KB of a live JSONL transcript, captures
  assistant text/thinking before the current tool call, stops at the previous
  tool result, and stores at most 8KB.
- If the transcript is absent or unreadable, the action is still recorded with
  `reasoning_text=NULL` and `capture_gap=1`.
- A provider-neutral Python API is ready for an OpenAI-powered agent. The
  recorder never reads or stores the model API key.

Raw hook payloads are also mirrored to
`~/.flight-recorder/debug/raw_payloads.jsonl` so the parser can be checked
against the exact coding-agent version used in the demo.

## Install

```text
pip install -e .
```

## Claude Code hook usage

```text
cd your-project
fr init
fr status
fr ui
fr grep <pattern>
```

`fr init` merges the recorder hooks into the project's
`.claude/settings.json`; it does not replace existing hooks.

## API-backed coding agent

Wrap every tool execution with the provider-neutral recorder. Supply only a
genuine visible rationale or transcript excerpt; do not manufacture hidden
chain-of-thought.

```python
from flight_recorder.recorder import FlightRecorder

recorder = FlightRecorder(source="openai-api")
action = recorder.start_action(
    "shell",
    {"command": "python -m unittest"},
    reasoning_text="Run the local tests before editing code.",
)

try:
    result = run_tool()  # your agent's tool implementation
except Exception as exc:
    action.finish({"error": str(exc)}, ok=False)
    raise
else:
    action.finish(result, ok=True)
```

The later OpenAI tool loop can use the Responses API for model/tool calls and
this wrapper around each local tool. Audit content remains local.

## Test

```text
python -m unittest discover -v
```

## Layout

- `flight_recorder/hook.py` - hook ingestion and pre/post action pairing
- `flight_recorder/reasoning.py` - transcript tail parsing for F2
- `flight_recorder/recorder.py` - provider-neutral API-agent instrumentation
- `flight_recorder/store.py` - SQLite WAL store and JSONL mirror
- `flight_recorder/schema.sql` - local schema and FTS index
- `flight_recorder/viewer/` - FastAPI timeline viewer
- `flight_recorder/cli.py` - `fr init|status|ui|grep`

## Local data

The default store is `~/.flight-recorder/`:

- `recorder.db`
- `events/YYYY-MM-DD.jsonl`
- `snapshots/<session>/`
- `debug/raw_payloads.jsonl`

## Known gaps

- Representative Claude-style and function-call transcript records are tested,
  but F2 must still be checked against real payloads from the exact agent build
  used for the hackathon.
- The OpenAI model/tool execution loop is intentionally the next slice; F1/F2 do
  not need an API key to develop or test.
- Incident reports, cross-session search polish, and file snapshot diffs are
  stretch features.
