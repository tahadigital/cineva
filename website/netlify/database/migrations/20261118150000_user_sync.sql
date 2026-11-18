-- Migration: 20261118150000_user_sync
-- Zero-Knowledge Cross-Device Library State Sync (Favorites, Watch Progress, Playlists, Track Preferences)

CREATE TABLE IF NOT EXISTS user_sync (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
