# Flight Recorder

A local, real-time black box for Claude Code sessions. Captures every
consequential action (shell commands, file edits, network calls, account/
credential operations) at the moment it happens, binds it to the reasoning
that preceded it, and keeps everything in a local, append-only, greppable
store — so "why did the agent do that?" is answerable forever, not just
until the transcript compacts or auto-deletes.

## Status

Day 1 scaffold: real hook capture → SQLite (WAL) + JSONL mirror, a working
FastAPI viewer with a live SSE timeline + drawer, and the `fr` CLI. Reasoning
extraction (`flight_recorder/reasoning.py`) is defensive but **not yet
validated against real Claude Code transcript payloads** — that's the
first thing to check once you've captured a few live sessions. Raw hook
payloads are dumped to `~/.flight-recorder/debug/raw_payloads.jsonl` for
exactly that purpose.

## Install

```
pip install -e .
```

## Usage

```
cd your-project
fr init      # registers hooks in ./.claude/settings.json, creates the store
fr status    # check hooks + event counts
fr ui        # opens the live timeline at http://127.0.0.1:7878
fr grep <pattern>   # grep across the JSONL mirror
```

Then just use Claude Code in that project — actions stream into the
timeline live.

## Layout

- `flight_recorder/hook.py` — the hook Claude Code invokes (PreToolUse,
  PostToolUse, PreCompact, SessionStart/End, Stop). Exits 0 unconditionally.
- `flight_recorder/reasoning.py` — extracts the reasoning window preceding
  an action from the live transcript; PreCompact snapshot shield.
- `flight_recorder/risk.py` + `risk_rules.yaml` — deterministic risk tiering.
- `flight_recorder/store.py` — SQLite (WAL) + JSONL mirror, no daemon.
- `flight_recorder/viewer/` — FastAPI app + timeline/drawer UI.
- `flight_recorder/cli.py` — `fr init|status|ui|grep`.
- `bin/fr_hook_entry.py` — standalone entry point registered in
  `.claude/settings.json` (works without the package being on PATH).

## Store location

`~/.flight-recorder/` — `recorder.db`, `events/YYYY-MM-DD.jsonl`,
`snapshots/<session>/`, `debug/raw_payloads.jsonl`.

## Known gaps (honest, not hidden)

- Reasoning extraction parser is defensive-but-unverified against real
  transcript JSONL shape — see Status above.
- No incident report export, multi-session cross-search, or file diffs yet
  (stretch features S1-S4 in the spec).
