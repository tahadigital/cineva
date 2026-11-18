CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  plan TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'active',
  max_devices INTEGER NOT NULL DEFAULT 2,
  expires_at TEXT NOT NULL DEFAULT '',
  admin_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);

CREATE TABLE IF NOT EXISTS devices (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_id TEXT NOT NULL,
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (user_id, device_id)
);

CREATE TABLE IF NOT EXISTS licenses (
  code TEXT PRIMARY KEY,
  plan TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  max_devices INTEGER NOT NULL DEFAULT 5,
  max_uses INTEGER NOT NULL DEFAULT 1,
  uses_count INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS license_redemptions (
  code TEXT NOT NULL REFERENCES licenses(code) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  redeemed_at TEXT NOT NULL,
  PRIMARY KEY (code, user_id)
);

CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download_stats (
  target TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  actor_id TEXT NOT NULL,
  actor_email TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  details TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limits (
  bucket TEXT NOT NULL,
  ts BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_bucket_ts ON rate_limits(bucket, ts);

INSERT INTO app_config (key, value) VALUES
  ('announcement', '{"enabled":false,"title":"","message":"","severity":"info"}'),
  ('versions', '{"windowsLatest":"2.0.1","windowsMin":"2.0.0","androidLatest":"2.0.1","androidMin":"2.0.0","windowsInstallerUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Setup.exe","windowsPortableUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Cineva.exe","androidApkUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Android.apk"}')
ON CONFLICT (key) DO NOTHING;

INSERT INTO download_stats (target, count, updated_at) VALUES
  ('windows-installer', 0, NOW()::TEXT),
  ('windows-portable', 0, NOW()::TEXT),
  ('android-apk', 0, NOW()::TEXT),
  ('macos', 0, NOW()::TEXT)
ON CONFLICT (target) DO NOTHING;
