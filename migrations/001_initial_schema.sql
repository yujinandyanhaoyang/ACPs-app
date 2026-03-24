CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS user_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_events_user_time
    ON user_events(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    source_event_window_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_time
    ON user_profiles(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS books (
    book_id TEXT PRIMARY KEY,
    title TEXT,
    author TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS book_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    feature_payload_json TEXT NOT NULL,
    source_label TEXT,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_book_features_book_ver
    ON book_features(book_id, feature_version, generated_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    profile_version TEXT,
    candidate_set_version_or_hash TEXT,
    candidate_provenance_json TEXT,
    book_feature_version_or_hash TEXT,
    ranking_policy_version TEXT,
    weights_or_policy_snapshot_json TEXT,
    run_timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_recommendation_runs_user_time
    ON recommendation_runs(user_id, run_timestamp DESC);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    rank_position INTEGER NOT NULL,
    book_id TEXT NOT NULL,
    score_total REAL,
    score_cf REAL,
    score_content REAL,
    score_kg REAL,
    score_diversity REAL,
    scenario_policy TEXT,
    explanation TEXT,
    explanation_evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_recommendations_run_rank
    ON recommendations(run_id, rank_position ASC);

CREATE TABLE IF NOT EXISTS agent_task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    session_id TEXT,
    sender_id TEXT,
    receiver_id TEXT,
    state_transition TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_task_logs_task_time
    ON agent_task_logs(task_id, timestamp DESC);
