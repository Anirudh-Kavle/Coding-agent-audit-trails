# Zetesis

> *An agent's actions survive in your shell history and your git log. Its
> reasoning doesn't: the transcript that explains* why *gets compacted
> mid-session and deleted the moment it ends.*

Zetesis is a local, real-time black box for AI coding-agent sessions. It
captures every consequential action (shell commands, file edits, network
calls, account/credential operations) at the moment it happens, binds it to
the reasoning that preceded it, and keeps everything in a local,
append-only, greppable store. So "why did the agent do that?" stays
answerable forever, not just until the transcript compacts or auto-deletes.

It works with three kinds of session, side by side in the same store:

1. **The bundled API agent** (`fr api-ui`) is a small terminal coding agent
   built directly on the OpenAI Responses API. It's the primary,
   most-integrated workflow: every tool call is captured in-process (no
   subprocess, no hook), and reasoning is never guessed at, since each call
   carries a required, model-written reason plus the API's own reasoning
   summary.
2. **Codex CLI**, via its native hook system.
3. **Claude Code**, via its native hook system.

All three write into the same SQLite store and show up together (or
filtered by agent) in the viewer UI.

## Prerequisites

- Python 3.11+
- Node 18+
- git

## Install and build

One-time setup (repeat only after changing dependencies):

```bash
# Python package + `fr` / `fr-hook` CLI entry points
pip install -e ".[dev]"

# Build the web viewer (fr ui serves the static build from viewer/dist)
cd viewer && npm install && npm run build && cd ..
```

Windows PowerShell: `python -m pip install -e ".[dev]"` (the `[dev]` extra
pulls in `pytest`, needed for the test suite).

## Running the API agent (primary workflow)

**Built with Codex (GPT-5.6 mode):** the Responses API agent loop itself -
in-process tool capture with no subprocess or hook, `gpt-5.6` set as the
default model - came out of Codex session `019f7392-7c8a-7d93-8ea5-40d514c51d92`.

**1. Add your API key**, either exported or dropped in a `.env` /
`.env.local` file in the project root:

```bash
export OPENAI_API_KEY=sk-...
```

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

**2. Launch the terminal UI:**

```bash
fr init                                          # one-time: creates the local store
fr api-ui --token-limit 50000 --time-limit 600
```

Model defaults to `gpt-5.6`; override with `--model` or the `OPENAI_MODEL`
env var. Inside the session:

- `/help`: list commands
- `/clear`: reset conversation context (recorded history is untouched)
- `/status`: recorder + hook status and the current token budget
- `/quit` / `/exit`: leave

For a single non-interactive task instead of a REPL: `fr agent "<task>"`
(same flags).

### Guardrails

**Built with Codex (GPT-5.6 mode):** the `risk_rules.yaml` table-driven
risk classifier and the live-editable budget limits were designed in the
same Codex session, with Codex reasoning through the `info`/`write`/`exec`/
`network`/`sensitive` tiering scheme before implementing it.

Two independent safety layers, both always on:

- **Budget limits**: `--token-limit N`, `--time-limit SECONDS`,
  `--daily-token-limit N`. When a limit is reached, no new API request is
  made and a `SessionLimit` event records the reason in the store instead.
  Limits can also be edited live from the viewer's top bar while the
  terminal session is running; the agent picks up the change within a
  second.
- **Risk tiering**: every action (from any of the three providers) is
  auto-classified into `info` / `write` / `exec` / `network` / `sensitive`
  by a deterministic, table-driven rule set (`zetesis/risk_rules.yaml`, no
  LLM in the hot path). A `sensitive`-tier action triggers a best-effort
  desktop alert *before* it runs. Set `ZETESIS_NOTIFY=0` to disable alerts;
  a notification failure never blocks the agent.

## Running Codex CLI

**Built with Codex (GPT-5.6 mode):** since this integration observes Codex's
own hook events, it doubled as a dogfooding target — the `tool_kind`
normalization and `tool_use_id` pairing logic were written and verified
against Codex's real hook payloads in session `019f7392-7c8a-7d93-8ea5-40d514c51d92`.

```bash
cd your-project
fr init            # registers hooks in ./.codex/hooks.json (--global for ~/.codex/hooks.json)
fr status          # check hooks + event counts
```

Then just use Codex in that project. Codex's `PreToolUse`/`PostToolUse`
events preserve the exact raw `tool_name` and store a normalized
`tool_kind` (`bash`, `edit`, `write`, `read`, `webfetch`, `mcp`, `other`);
`tool_use_id` pairs each pre-action with its exact post-action result, even
when identical tools run concurrently. Open `/hooks` in Codex once to
review and trust the project hook commands.

Coverage note: Codex hooks observe shell/unified-exec (`Bash`),
`apply_patch`, MCP, and other local function tools. Hosted tools such as
`WebSearch` don't use the local hook path and stay outside this recorder's
coverage.

## Running Claude Code

**Built with Codex (GPT-5.6 mode):** the `.claude/settings.json` hook wiring
and the `PermissionRequest`-vs-`PreToolUse` dedup decision came from Codex
session `019f7392-7c8a-7d93-8ea5-40d514c51d92`, adapting the Codex hook
integration's design to Claude Code's event model.

Create `.claude/settings.json` in the project (gitignored, per-machine
config), registering `fr-hook --provider claude` as a command hook for each
event you want captured:

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

Then just use Claude Code in that project. Actions stream into the timeline
live. Don't add a `PermissionRequest` hook here: it fires alongside
`PreToolUse`/`PostToolUse` for the same call with no way to pair it, so
Zetesis ignores it rather than recording a duplicate row.

## Launching the web viewer

**Built with Codex (GPT-5.6 mode):** the FastAPI app and its REST/SSE
endpoints, serving the built React bundle with no separate daemon process,
were implemented in Codex session `019f7392-7c8a-7d93-8ea5-40d514c51d92`.

```bash
fr ui                    # builds nothing itself, serves the viewer/dist from "Install and build" first
fr ui --port 7878 --no-browser
```

Opens the live timeline at `http://127.0.0.1:7878`, backed by the same
FastAPI process that also serves the REST/SSE API. Everything (SQLite DB,
JSONL mirror, debug logs) lives under `~/.zetesis/`; there's no separate
daemon to run.

**Frontend dev mode** (hot reload, for working on the viewer itself):

```bash
cd viewer
npm run dev              # http://localhost:5173, proxies /api to :7878; run `fr ui` alongside it
# or, with no backend running at all:
VITE_USE_MOCK=true npm run dev   # generated demo data, no store required
```

## Verify the installation

```bash
fr status              # store path, session/event counts, hook registration
fr test-hook            # record a synthetic Pre/PostToolUse pair
fr test-notification    # test the desktop sensitive-action alert
python -m pytest -q     # backend test suite
cd viewer && npm test   # frontend test suite
```

To inspect the store directly: `fr grep "<pattern>"` greps the JSONL
mirror, or list the raw files with `ls ~/.zetesis` (PowerShell:
`Get-ChildItem "$env:USERPROFILE\.zetesis" -Recurse`).

## CLI reference

```
fr init  [--global]           register hooks (project by default) + create the store
fr status                     store path, session/event counts, hook registration status
fr ui    [--port] [--no-browser]   start the viewer and open it in a browser
fr grep <pattern>             grep across the JSONL mirror
fr export [-o <path>]         write today's canonical events to a JSON file
fr agent <task> [...]         one-shot API-backed agent run
fr api-ui [...]               interactive API-backed agent (see above)
fr test-hook                  record a synthetic Pre/PostToolUse pair to confirm capture
fr test-notification          test the desktop sensitive-action alert
```

## Viewer feature tour

**Built with Codex (GPT-5.6 mode):** the React UI shown below — search
qualifiers, live timeline, per-session budget controls — was built and
iterated on in Codex session `019f7392-7c8a-7d93-8ea5-40d514c51d92`.

Sessions grouped by project (repo/folder) in the sidebar, with folder
sub-groups for multiple checkouts; deterministic per-scope stat line
(actions / commands / edits / failed / sensitive); full-database search with
qualifiers (`tool:` `risk:` `file:` `session:` `exit:` `provider:` `after:`
`before:`); per-session token/time budgets editable from the top bar;
recording pause/resume. Agent filters cover Claude, Codex, and API
sessions; the budget controls currently focus on the API agent, though
Claude and Codex records stay fully visible and searchable alongside it.

## Layout

**Built with Codex (GPT-5.6 mode):** most of the module scaffold below,
including the SQLite (WAL) + JSONL mirror in `store.py`, was laid out in
Codex session `019f7392-7c8a-7d93-8ea5-40d514c51d92`.

- `zetesis/hook.py`: the hook entry point every provider calls
  (`PreToolUse`, `PostToolUse`, `PreCompact`, `SessionStart`, `Stop`, ...).
  Exits 0 unconditionally; a recorder that can break the agent's controls
  is worse than no recorder.
- `zetesis/reasoning.py`: extracts the reasoning window preceding an
  action from the live transcript; PreCompact snapshot shield.
- `zetesis/risk.py` + `risk_rules.yaml`: deterministic risk tiering.
- `zetesis/agent.py` + `recorder.py`: the OpenAI Responses API agent loop
  behind `fr agent` / `fr api-ui`, and its in-process capture API.
- `zetesis/store.py`: SQLite (WAL) + JSONL mirror, no daemon.
- `zetesis/viewer/`: FastAPI app serving the API + the built React UI.
- `zetesis/cli.py`: the `fr` command group.

## Store location

`~/.zetesis/`: `recorder.db`, `events/YYYY-MM-DD.jsonl`,
`snapshots/<session>/`, `debug/raw_payloads.jsonl`.

To wipe all locally recorded history, events, snapshots, and debug payloads
(stop any running Zetesis/Vite/Claude/Codex sessions first):

```bash
rm -rf ~/.zetesis ~/.flight-recorder   # the second path only matters if you used this before the rename
```

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.zetesis" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:USERPROFILE\.flight-recorder" -ErrorAction SilentlyContinue
```

## Known gaps (honest, not hidden)

- Reasoning extraction (`zetesis/reasoning.py`) is defensive but not
  exhaustively validated against every real transcript shape across
  providers. Raw hook payloads are always dumped to
  `~/.zetesis/debug/raw_payloads.jsonl` for exactly that kind of debugging.
- No incident report export, multi-session cross-search, or file diffs yet.

---

Codex session: `019f7392-7c8a-7d93-8ea5-40d514c51d92`

This project thread contains most of the core Zetesis implementation:
hook-based event capture, SQLite/JSONL storage, Claude/Codex/API recording,
the FastAPI viewer, token-budget controls, and the React UI.
