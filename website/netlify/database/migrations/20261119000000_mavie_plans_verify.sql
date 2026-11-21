-- Migration: 20261119000000_mavie_plans_verify
-- Mavie rebrand, 2-tier plans (normal/pro), 3-day Pro trial, email verification,
-- password reset codes, token_version revocation, email outbox, and 4-platform download URLs.

-- 1. Extend users table safely (existing pre-migration accounts stay email_verified = TRUE)
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ALTER COLUMN email_verified SET DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_started_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;

UPDATE users SET verified_at = created_at WHERE email_verified = TRUE AND verified_at = '';

-- 2. Normalize plans: 'free' -> 'normal' (1 device), 'family'/'lifetime' -> 'pro' (min 5 devices)
ALTER TABLE users ALTER COLUMN plan SET DEFAULT 'normal';
ALTER TABLE users ALTER COLUMN max_devices SET DEFAULT 1;

UPDATE users
SET plan = 'normal',
    max_devices = CASE WHEN role = 'admin' THEN max_devices ELSE 1 END
WHERE plan = 'free';

UPDATE users
SET plan = 'pro',
    max_devices = GREATEST(max_devices, 5)
WHERE plan IN ('family', 'lifetime');

UPDATE licenses
SET plan = 'pro'
WHERE plan IN ('family', 'lifetime');

DELETE FROM licenses WHERE plan = 'free';

-- 3. Email verifications table
CREATE TABLE IF NOT EXISTS email_verifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_verifications_user ON email_verifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_verifications_email ON email_verifications(email, created_at DESC);

-- 4. Extend existing password_resets table to support 6-digit code + email + brute-force attempts
ALTER TABLE password_resets ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';
ALTER TABLE password_resets ADD COLUMN IF NOT EXISTS code_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE password_resets ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE password_resets ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id, used);
CREATE INDEX IF NOT EXISTS idx_password_resets_email ON password_resets(email, used, created_at DESC);

-- 5. Email outbox table (verifiable local/test sink + delivery audit log)
CREATE TABLE IF NOT EXISTS email_outbox (
  id TEXT PRIMARY KEY,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  body_text TEXT NOT NULL,
  body_html TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  delivery_mode TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'stored',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_outbox_recipient ON email_outbox(recipient, created_at DESC);

-- 6. Update app_config versions with Mavie 4-platform release URLs & seed 'ios' in download_stats
INSERT INTO app_config (key, value) VALUES
  ('versions', '{"latestVersion":"2.1.0","windowsLatest":"2.1.0","windowsMin":"2.0.0","androidLatest":"2.1.0","androidMin":"2.0.0","macosLatest":"2.1.0","macosMin":"2.0.0","iosLatest":"2.1.0","iosMin":"2.0.0","windowsInstallerUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Setup.exe","windowsPortableUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie.exe","androidApkUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Android.apk","macosUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-macOS.dmg","iosUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-iOS.ipa","releaseNotes":"Mavie 2.1.0: 4 platform desteği, e-posta doğrulama ve 3 günlük Pro deneme."}')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

INSERT INTO download_stats (target, count, updated_at) VALUES
  ('windows-installer', 0, NOW()::TEXT),
  ('windows-portable', 0, NOW()::TEXT),
  ('android-apk', 0, NOW()::TEXT),
  ('macos', 0, NOW()::TEXT),
  ('ios', 0, NOW()::TEXT)
ON CONFLICT (target) DO NOTHING;
