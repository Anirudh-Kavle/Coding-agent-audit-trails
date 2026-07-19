# Flight Recorder Store Service

SQLite + JSONL append-only event storage for Flight Recorder.

## Setup

```bash
pip install -r requirements.txt
```

## Schema

- `recorder.db` - SQLite database with events and sessions
- `events/YYYY-MM-DD.jsonl` - Greppable JSONL mirror of events

See `schema.sql` for full DDL.
