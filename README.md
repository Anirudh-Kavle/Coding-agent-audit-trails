# Zetesis

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
extraction (`zetesis/reasoning.py`) is defensive but **not yet
validated against real Codex transcript payloads** — that's the
first thing to check once you've captured a few live sessions. Raw hook
payloads are dumped to `~/.zetesis/debug/raw_payloads.jsonl` for
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
Set `ZETESIS_NOTIFY=0` to disable alerts; notification failures never
block the agent.

## Layout

- `zetesis/hook.py` — the Codex hook invokes (PreToolUse,
  PostToolUse, PreCompact, SessionStart, Stop). Exits 0 unconditionally.
- `zetesis/reasoning.py` — extracts the reasoning window preceding
  an action from the live transcript; PreCompact snapshot shield.
- `zetesis/risk.py` + `risk_rules.yaml` — deterministic risk tiering.
- `zetesis/store.py` — SQLite (WAL) + JSONL mirror, no daemon.
- `zetesis/viewer/` — FastAPI app + timeline/drawer UI.
- `zetesis/cli.py` — `fr init|status|ui|grep|test-hook|agent|api-ui`.

## Store location

`~/.zetesis/` — `recorder.db`, `events/YYYY-MM-DD.jsonl`,
`snapshots/<session>/`, `debug/raw_payloads.jsonl`.

## Known gaps (honest, not hidden)

- Reasoning extraction parser is defensive-but-unverified against real
  transcript JSONL shape — see Status above.
- No incident report export, multi-session cross-search, or file diffs yet
  (stretch features S1-S4 in the spec).

## Complete Windows setup and runbook

The following commands assume Windows PowerShell and a fresh clone. Run them
from the repository root:

```powershell
cd "D:\OneDrive - University of Southern California\Research\Coding-agent-audit-trails\Coding-agent-audit-trails-varoon"
```

### Install dependencies

Run this once, or after changing Python dependencies or package metadata:

```powershell
python -m pip install -e .
npm install
```

The editable Python install makes the `fr` and `fr-hook` commands point at the
working copy. It does not need to be repeated for every session.

### Optional clean database reset

Stop all running Zetesis, Vite, Claude, and Codex sessions first. The following
deletes all locally recorded history, events, snapshots, and debug payloads:

```powershell
$zetesisStore = Join-Path $env:USERPROFILE ".zetesis"
$legacyStore = Join-Path $env:USERPROFILE ".flight-recorder"

if (Test-Path -LiteralPath $zetesisStore) {
    Remove-Item -LiteralPath $zetesisStore -Recurse -Force
}

if (Test-Path -LiteralPath $legacyStore) {
    Remove-Item -LiteralPath $legacyStore -Recurse -Force
}
```

### Initialize the database and hooks

```powershell
fr init
fr status
```

This creates the SQLite/JSONL store under `C:\Users\<user>\.zetesis` and
registers the project Codex hooks in `.codex\hooks.json`. Open Codex’s `/hooks`
panel once and trust the project hooks.

Claude uses the project `.claude\settings.json` hook configuration when it is
present. Do not commit API keys or local settings files.

### Start the backend viewer API

Use Terminal 1 and leave it running:

```powershell
cd "D:\OneDrive - University of Southern California\Research\Coding-agent-audit-trails\Coding-agent-audit-trails-varoon"
fr ui --port 7878 --no-browser
```

The FastAPI backend is available at `http://127.0.0.1:7878`.

If port 7878 is already occupied, inspect it with:

```powershell
Get-NetTCPConnection -LocalPort 7878 -ErrorAction SilentlyContinue
```

### Start the development frontend

Use Terminal 2:

```powershell
cd "D:\OneDrive - University of Southern California\Research\Coding-agent-audit-trails\Coding-agent-audit-trails-varoon"
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the backend on
port 7878. For a production-style static viewer, run `npm run build` and use
`fr ui` without Vite.

### Configure and run the OpenAI API agent

Create or update the project `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Use Terminal 3:

```powershell
cd "D:\OneDrive - University of Southern California\Research\Coding-agent-audit-trails\Coding-agent-audit-trails-varoon"
fr api-ui `
  --token-limit 50000 `
  --time-limit 900 `
  --daily-token-limit 100000
```

Inside `fr api-ui`:

```text
/help      show commands
/status    show recorder and budget status
/clear     clear API conversation context but keep history
/quit      exit the API session
```

The API budget can also be edited from the viewer’s token-budget control. The
terminal refreshes its displayed limits from the shared database.

### Run Claude and Codex sessions

From the project root, use a separate terminal for each session:

```powershell
claude
```

For Codex, open Codex in the project root, then open `/hooks` once and confirm
that the project hooks are active. Hook events will be written to the same
Zetesis store and appear in the viewer alongside API events.

### Verify the installation

```powershell
fr status
fr test-hook
fr test-notification
python -m pytest -q
```

Useful inspection commands:

```powershell
fr grep "calculator"
Get-ChildItem "$env:USERPROFILE\.zetesis" -Recurse
```

The viewer supports agent filters for Claude, Codex, and API sessions. Token
limit controls are currently focused on the OpenAI API agent; Claude and Codex
records remain visible and searchable.
