CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER,
    ended_at INTEGER,
    cwd TEXT,
    git_repo TEXT,
    source TEXT,
    title TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    ts INTEGER NOT NULL,
    phase TEXT NOT NULL,
    tool TEXT,
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
    files_touched TEXT,
    tool_use_id TEXT
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
