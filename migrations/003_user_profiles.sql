-- Phase 1 vector-profile fields for the upgraded architecture.
-- Backward compatible with the legacy `user_profiles` table from 001_initial_schema.sql.

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    profile_vector TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.2,
    event_count INTEGER NOT NULL DEFAULT 0,
    cold_start INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

ALTER TABLE user_profiles ADD COLUMN profile_vector TEXT;
ALTER TABLE user_profiles ADD COLUMN confidence REAL NOT NULL DEFAULT 0.2;
ALTER TABLE user_profiles ADD COLUMN event_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_profiles ADD COLUMN cold_start INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_profiles ADD COLUMN updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE INDEX IF NOT EXISTS idx_user_profiles_updated_at
    ON user_profiles(updated_at DESC);
