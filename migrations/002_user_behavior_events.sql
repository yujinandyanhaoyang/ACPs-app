CREATE TABLE IF NOT EXISTS user_behavior_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    book_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    weight REAL NOT NULL,
    rating SMALLINT,
    duration_sec INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_user_behavior_events_user_time
    ON user_behavior_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_behavior_events_book
    ON user_behavior_events(book_id);
