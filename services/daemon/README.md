# Flight Recorder Daemon (fr-hook)

Real-time event capture via Claude Code lifecycle hooks.

## Responsibilities

- Parse hook JSON from stdin
- Extract reasoning from transcript
- Classify risk tier
- Write events to SQLite + JSONL (WAL mode)
- Exit 0 unconditionally (never blocks Claude)

## Performance Budget

- p95 < 150ms per invocation
- No blocking I/O
- Timeout all subprocess calls (100ms)
