<div align="center">

<a name="top"></a>

# ✈️ Flight Recorder

### A local, real-time black box for your coding agent: what it did, and *why*

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-38BDF8?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

[![tests](https://img.shields.io/badge/tests-102%20passing-2ea44f)](#development)
[![last commit](https://img.shields.io/github/last-commit/Anirudh-Kavle/Coding-agent-audit-trails)](https://github.com/Anirudh-Kavle/Coding-agent-audit-trails/commits)
[![stars](https://img.shields.io/github/stars/Anirudh-Kavle/Coding-agent-audit-trails?style=flat)](https://github.com/Anirudh-Kavle/Coding-agent-audit-trails/stargazers)
[![local-first](https://img.shields.io/badge/local--first-airplane%20mode-0b0e11)](#privacy)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey.svg)](#license)

[![works with](https://img.shields.io/badge/works%20with-Codex%20%C2%B7%20OpenAI%20API%20%C2%B7%20Claude%20Code-6f42c1)](#usage)

<img src="docs/demo.gif" alt="Flight Recorder timeline: actions stream in live, risk-colored, reasoning one click away" width="820"/>

**[Install](#install)** • **[Usage](#usage)** • **[How it works](#how-it-works)** • **[Risk tiers](#risk-tiers)** • **[The viewer](#the-viewer)** • **[Development](#development)** • **[Roadmap](#roadmap)**

</div>

---

> Your agent's **actions** survive in git and shell history. Its **reasoning**
> does not. The transcript that held the "why" is compacted mid-session and
> auto-deleted after 30 days. Flight Recorder is the black box that keeps it.

**Flight Recorder** captures every consequential action your coding agent takes
(shell commands, file edits, network calls, credential and account operations)
at the moment it happens, binds each action to the reasoning that produced it,
and preserves everything in a local, append-only, greppable store with a live
timeline. It records **Codex, the OpenAI API, and Claude Code**, and it works
best with API-driven agents like Codex, which run headless and autonomous
exactly where a durable audit trail matters most. **The one-sentence demo:**
ask *"why did the agent add this environment variable?"* three weeks later,
click the action, and read the exact reasoning that produced it.

> [!TIP]
> Flight Recorder shines with API-driven agents. Codex and the OpenAI API run
> autonomously in CI, cron, and headless jobs, the settings where no human sees
> what the agent did and a black box matters most.

## Why

Ask yourself:

- Has an agent ever changed a config or created a resource you couldn't later explain?
- Do you run agents headless, in CI, or on cron, where nobody is watching?
- Have you lost the reasoning behind a change because the transcript compacted or expired?
- Do you need an audit trail of what an agent did, not just the chat log, for review or compliance?

**If yes to any of these, Flight Recorder is for you.** Agent actions have real
side effects, and the actions are often recoverable, but the *reasoning* lives
only in the transcript, which vanishes under context pressure and after 30
days. Everyone else records *what happened*; Flight Recorder durably records
*why*, and "why" is exactly what transcript deletion destroys.

> [!NOTE]
> **Best for:** developers running Codex, the OpenAI API, or Claude Code,
> locally or in CI, who want a durable, private record of what the agent did
> and why. It works best with API-driven agents (Codex and the OpenAI API),
> which often run headless and autonomous, exactly where nobody is watching.
>
> **Not for:** cloud observability, or blocking and policy enforcement (it
> records, it does not gate).

## How Flight Recorder compares

| Tool | What it is | What Flight Recorder does instead |
|------|------------|-----------------------------------|
| Post-hoc transcript summarizers | Distill an expired chat log into markdown | We capture at action time via hooks, so nothing is lost to expiry |
| Cloud agent observability | Enterprise dashboards, OTel pipelines | We stay local-first and zero-config, so your audit trail never leaves your disk |
| LLM call recorders | Record or replay calls for framework agents (LangChain, etc.) | We record Codex, the OpenAI API, and Claude Code natively, with no code changes |
| DIY hook loggers | Append tool names to a file | We capture what, why, git state, and risk, with a live viewer |

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## Install

**1. the recorder and CLI** (Python 3.11+):

```
pip install -e .
```

**2. build the viewer** (Node 18+):

```
cd viewer
npm install
npm run build
```

That produces `viewer/dist`, which `fr ui` serves. (For UI development, use
`npm run dev` instead. It runs on `:5173` and proxies `/api` to the backend.)

## Usage

```
cd your-project
fr init      # wires Flight Recorder into your agent, creates the store
fr status    # recorder installed? events flowing? last event age
fr ui        # opens the live timeline at http://127.0.0.1:7878
fr grep rm   # grep across the plaintext JSONL mirror
```

Then just run your agent in that project. Actions stream into the timeline
live. `fr init --global` registers the recorder for every project at once.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## How it works

A single hook runs on every tool-call and lifecycle event, writes directly to
SQLite in WAL mode, and **exits 0 no matter what**, because a recorder that can
break the pilot's controls is worse than no recorder. **There is no daemon:**
the hook is the only writer, the viewer is a pure reader, so "forgot to start
the service" can't cause silent data loss, and install is one command.

```mermaid
flowchart TD
    CC["Coding agent session<br/>Codex · OpenAI API · Claude Code"]
    CC -->|"tool-call + lifecycle events"| HOOK

    subgraph REC["fr-hook: exits 0 always · &lt;150ms budget"]
      direction LR
      HOOK["parse<br/>event JSON"] --> GIT["git state<br/>branch · HEAD · dirty"]
      GIT --> REASON["reasoning window<br/>from transcript tail"]
      REASON --> RISK["risk tier<br/>deterministic"]
    end

    RISK --> STORE
    subgraph STORE["~/.flight-recorder"]
      direction LR
      DB[("recorder.db<br/>SQLite · WAL · FTS5")]
      JSONL["events/*.jsonl<br/>greppable mirror"]
      SNAP["snapshots/<br/>pre-compact transcripts"]
    end

    STORE --> VIEWER["fr-viewer<br/>FastAPI · :7878"]
    VIEWER -->|"REST + live SSE"| SPA["React timeline + drawer"]
```

The reasoning window is read from the tail of the live transcript at capture
time. When the model didn't narrate a step, the event is stored with an honest
`capture_gap` flag rather than fabricated text. **We never invent a "why."**
The pre-compaction hook snapshots the whole transcript before the agent
compacts it, so the reasoning survives even when the context does not.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## Risk tiers

Every action is auto-tagged by a deterministic, table-driven classifier, with
no LLM in the hot path. Rules live in one editable [`risk_rules.yaml`](flight_recorder/risk_rules.yaml).

| Tier | Color | Triggers |
|------|--------|----------|
| `info` | ⚪ gray | `Read`, `Glob`, `Grep`, `LS` |
| `write` | 🔵 blue | `Edit`, `Write`, `NotebookEdit` |
| `exec` | 🟠 amber | `Bash` (default) |
| `network` | 🟣 purple | `WebFetch`, `WebSearch`, `curl`/`wget`/`ssh`/`scp` in a shell command |
| `sensitive` | 🔴 red | secrets/tokens, `rm -rf`, `sudo`, permissive `chmod`, `.env`, `DROP TABLE`, `git push --force`, account creation, keychain access |

Patterns are matched against a tool's **arguments and its result**, so a secret
that only appears in output still gets flagged. Search tools (`Grep`/`Glob`/
`WebSearch`) are exempt from argument matching, since searching *for* the word
`sudo` isn't running it.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## The viewer

<div align="center">
<img src="docs/timeline.png" alt="Live timeline, newest at top, risk-colored rows" width="820"/>
<br/><br/>
<img src="docs/drawer-why.png" alt="Detail drawer, WHY tab: the captured reasoning behind an action" width="820"/>
</div>

One vertical stream, newest at top, risk color as the primary channel. Every
row's first line of reasoning shows inline (`↳ why: …`); click any action for
the full drawer: **WHAT** (syntax-highlighted arguments), **WHY** (the captured
reasoning, verbatim), **CONTEXT** (git branch, HEAD, dirty flag), and
**RESULT** (output, exit status). Search takes qualifier chips
(`tool:bash risk:sensitive file:deploy session:brainstorm`) over a SQLite FTS5
index. Keyboard-native: `j`/`k` to move, `Enter` to open, `/` to search.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## Project structure

```
flight_recorder/            # the recorder (Python, stdlib + sqlite3)
├── hook.py                 # the event capture entry point; exits 0 unconditionally
├── reasoning.py            # reasoning-window extraction + pre-compaction snapshot shield
├── risk.py + risk_rules.yaml   # deterministic, table-driven risk tiering
├── gitstate.py             # best-effort git context, timeout-bounded
├── store.py                # SQLite (WAL) + JSONL mirror, no daemon
├── schema.sql              # events + sessions + FTS5
├── cli.py                  # fr init | status | ui | grep
└── viewer/app.py           # FastAPI: REST + live SSE, serves the SPA
bin/fr_hook_entry.py        # standalone capture entry point
viewer/src/                 # the timeline UI (React 19 · TS · Vite · Tailwind 4)
├── components/             # Timeline, DetailDrawer, EventRow, SessionSidebar, …
├── hooks/                  # useEventStream (SSE), useKeyboardNav
└── lib/                    # api, dataSource, search, format (+ tests)
test_*.py                   # 60 backend gate tests
```

## Store layout

Everything lives under `~/.flight-recorder/`, all local, all yours:

```
recorder.db                 # SQLite, WAL mode, FTS5 search index
events/YYYY-MM-DD.jsonl     # append-only plaintext mirror, cat / grep / jq it
snapshots/<session>/        # transcripts copied before compaction
debug/raw_payloads.jsonl    # every raw event payload, for parser inspection
```

## Privacy

Zero remote servers, zero external auth, zero cloud tracking. The recorder
makes no network calls, ever. The entire suite passes the airplane-mode test,
so your audit trail never leaves your disk. This is a headline feature, not an
afterthought.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## Development

**Backend:**

```
pip install -e ".[dev]"
python -m pytest            # 60 gate tests, deterministic, < 1s
```

**Frontend:**

```
cd viewer
npm install
npm run dev                 # :5173, proxies /api to :7878
npm test                    # 42 tests (vitest)
npm run build               # produces viewer/dist, served by `fr ui`
```

To try changes end to end: `fr init` in any project, run your agent, and watch
`fr ui`. New contributions ship with tests in the same commit; see
[CLAUDE.md](CLAUDE.md) for the working standard.

## Roadmap

- **Incident report export:** select a time range and get one markdown report
  of what happened, in order, with reasoning excerpts.
- **Multi-session view:** all recorded sessions in one list, cross-session search.
- **File-diff snapshots:** before/after content for edits, beyond what
  `tool_input` provides.
- **Sensitive-action desktop notification:** a ping the moment a
  `sensitive`-tier action fires.
- **More agent adapters:** beyond Codex, the OpenAI API, and Claude Code.
- **Packaged viewer:** ship `viewer/dist` inside the wheel so `pip install` is
  the only step.

<div align="right"><kbd><a href="#top">↑ back to top ↑</a></kbd></div>

## License

MIT, see [`LICENSE`](LICENSE).

---

<div align="center"><sub>Built with Claude Code. The first session in the demo database is the session that built it.</sub></div>
