# Flight Recorder

## Quickstart — run everything from a fresh clone

Prerequisites: Python 3.11+, Node 18+, git.

```bash
# 1. Python package + `fr` CLI
pip install -e ".[dev]"

# 2. Build the web viewer (fr ui serves viewer/dist)
cd viewer && npm install && npm run build && cd ..

# 3. Register hooks + create the local store at ~/.flight-recorder
fr init            # Codex hooks -> ./.codex/hooks.json
fr test-hook       # optional: record a synthetic event to confirm capture

# 4. Open the live timeline
fr ui              # http://127.0.0.1:7878
```

Recording Claude Code sessions: create `.claude/settings.json` in the project
(it is gitignored — per-machine config) with `fr-hook --provider claude` as a
command hook for each event you want captured:

```json
{
  "hooks": {
    "PreToolUse":  [{"matcher": ".*", "hooks": [{"type": "command", "command": "fr-hook --provider claude", "timeout": 5}]}],
    "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "fr-hook --provider claude", "timeout": 5}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "fr-hook --provider claude", "timeout": 5}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "fr-hook --provider claude", "timeout": 5}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "fr-hook --provider claude", "timeout": 5}]}]
  }
}
```

Optional — the API-backed agent (needs `OPENAI_API_KEY` in the env or `.env`):

```bash
fr api-ui --token-limit 50000 --time-limit 600
```

Viewer feature tour: sessions grouped by project (repo/folder) in the sidebar
with folder sub-groups for multiple checkouts; deterministic per-scope stat
line (actions / commands / edits / failed / sensitive); full-database search
with qualifiers (`tool:` `risk:` `file:` `session:` `exit:` `provider:`
`after:` `before:`); per-session token/time budgets editable from the top bar;
recording pause/resume.

---

Codex support: run `fr init` to register project hooks in `.codex/hooks.json`.
Codex `PreToolUse`/`PostToolUse` events preserve the exact raw `tool_name` and
store a normalized `tool_kind`: `bash`, `edit`, `write`, `read`, `webfetch`,
`mcp`, or `other`. Codex's `tool_use_id` pairs each pre-action with its exact
post-action result, even when identical tools run concurrently. Open `/hooks`
in Codex once to review and trust the project hook commands.

Coverage note: Codex hooks observe shell/unified-exec (`Bash`), `apply_patch`,
MCP, and other local function tools. Hosted tools such as `WebSearch` do not
use the local hook path and therefore remain outside this recorder's coverage.

A local, real-time black box for Codex sessions. Captures every
consequential action (shell commands, file edits, network calls, account/
credential operations) at the moment it happens, binds it to the reasoning
that preceded it, and keeps everything in a local, append-only, greppable
store — so "why did the agent do that?" is answerable forever, not just
until the transcript compacts or auto-deletes.

## Status

Day 1 scaffold: real hook capture → SQLite (WAL) + JSONL mirror, a working
FastAPI viewer with a live SSE timeline + drawer, and the `fr` CLI. Reasoning
extraction (`flight_recorder/reasoning.py`) is defensive but **not yet
validated against real Codex transcript payloads** — that's the
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
fr init      # registers hooks in ./.codex/hooks.json, creates the store
fr status    # check hooks + event counts
fr ui        # opens the live timeline at http://127.0.0.1:7878
fr grep <pattern>   # grep across the JSONL mirror
fr api-ui    # interactive API-backed agent with reasoning summaries
```

Then just use Codex in that project — actions stream into the
timeline live.

Set `OPENAI_API_KEY` and run `fr api-ui` for the separate API-backed agent.
It records into the same store and requests API reasoning summaries. Use
`/clear` to reset conversation context, `/status` to inspect the store, and
`/quit` to exit. These are summaries, not private chain-of-thought.

Session guardrails are available with `--token-limit N`, `--time-limit SECONDS`,
and `--daily-token-limit N`. When a limit is reached, no new API request is
made and a `SessionLimit` event records the reason in the black box.

Sensitive-risk events trigger a best-effort desktop alert before execution.
Set `FLIGHT_RECORDER_NOTIFY=0` to disable alerts; notification failures never
block the agent.

## Layout

- `flight_recorder/hook.py` — the Codex hook invokes (PreToolUse,
  PostToolUse, PreCompact, SessionStart, Stop). Exits 0 unconditionally.
- `flight_recorder/reasoning.py` — extracts the reasoning window preceding
  an action from the live transcript; PreCompact snapshot shield.
- `flight_recorder/risk.py` + `risk_rules.yaml` — deterministic risk tiering.
- `flight_recorder/store.py` — SQLite (WAL) + JSONL mirror, no daemon.
- `flight_recorder/viewer/` — FastAPI app + timeline/drawer UI.
- `flight_recorder/cli.py` — `fr init|status|ui|grep|test-hook|agent|api-ui`.

## Store location

`~/.flight-recorder/` — `recorder.db`, `events/YYYY-MM-DD.jsonl`,
`snapshots/<session>/`, `debug/raw_payloads.jsonl`.

## Known gaps (honest, not hidden)

- Reasoning extraction parser is defensive-but-unverified against real
  transcript JSONL shape — see Status above.
- No incident report export, multi-session cross-search, or file diffs yet
  (stretch features S1-S4 in the spec).
