CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER,
    ended_at INTEGER,
    cwd TEXT,
    git_repo TEXT,
    source TEXT,
    token_limit INTEGER,
    time_limit_s INTEGER,
    token_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_usage (
    day TEXT PRIMARY KEY,
    token_count INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    ts INTEGER NOT NULL,
    phase TEXT NOT NULL,
    tool TEXT,
    action_id TEXT,
    completed_at INTEGER,
    tool_kind TEXT,
    tool_use_id TEXT,
    turn_id TEXT,
    provider TEXT,
    model TEXT,
    notification_sent INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    usage_json TEXT,
    arguments_json TEXT,
    result_json TEXT,
    exit_ok INTEGER,
    reasoning_text TEXT,
    risk TEXT NOT NULL DEFAULT 'info',
    risk_reasons TEXT,
    capture_gap INTEGER DEFAULT 0,
    git_branch TEXT,
    git_head TEXT,
    git_dirty INTEGER,
    files_touched TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_risk ON events(risk);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    arguments_text,
    reasoning_text,
    content='events',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, arguments_text, reasoning_text)
    VALUES (new.id, new.arguments_json, new.reasoning_text);
END;
