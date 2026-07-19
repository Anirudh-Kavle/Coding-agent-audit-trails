FLIGHT RECORDER — Summary

What it is: Local, real-time black box for Codex sessions. Logs every
consequential action (shell commands, file edits, network calls, credential
ops) with the reasoning behind it, in a local, append-only, greppable store.

Status: Day 1 scaffold. Hook capture -> SQLite (WAL) + JSONL mirror, FastAPI
viewer with live SSE timeline, and `fr` CLI all working. Reasoning extraction
is defensive but not yet validated against real transcripts.

Install:
  pip install -e .

Usage:
  fr init    - register hooks + create store
  fr status  - check hooks + event counts
  fr ui      - live timeline at http://127.0.0.1:7878
  fr grep    - grep across JSONL mirror

Key files:
  hook.py       - Codex hook entry (Pre/PostToolUse, PreCompact, etc.)
  reasoning.py  - extracts reasoning preceding an action
  risk.py       - deterministic risk tiering
  store.py      - SQLite (WAL) + JSONL mirror
  viewer/       - FastAPI timeline UI
  cli.py        - fr commands

Store location: ~/.flight-recorder/ (recorder.db, events/, snapshots/, debug/)

Known gaps:
  - Reasoning parser unverified against real transcript shape
  - No incident export, cross-session search, or file diffs yet
