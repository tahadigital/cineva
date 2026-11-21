#!/usr/bin/env python3
"""Mavie Control Plane & Admin Backend.

Zero-knowledge account, email verification, 2-tier plan (Normal / Pro + 3-day trial),
license key, device limit, download counter, and remote app-config service.
Intentionally NEVER stores user IPTV credentials, M3U URLs, or watch history.
"""
from __future__ import annotations

import argparse
import base64
import collections
import contextlib
import datetime as dt
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import signal
import smtplib
import sqlite3
import ssl
import threading
import time
import urllib.parse
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBSITE = ROOT / 'website'
MAX_JSON = 512 * 1024
PLANS = ('normal', 'pro')
LEGACY_PLAN_MAP = {
    'free': 'normal',
    'normal': 'normal',
    'pro': 'pro',
    'family': 'pro',
    'lifetime': 'pro',
}
STATUSES = ('active', 'suspended')
ROLES = ('user', 'admin')
DOWNLOAD_TARGETS = ('windows-installer', 'windows-portable', 'android-apk', 'macos', 'ios')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$')
TRIAL_DURATION_HOURS = 72
VERIFY_TTL_HOURS = 24
RESET_TTL_MINUTES = 30
MAX_CODE_ATTEMPTS = 5

DEFAULT_VERSIONS = {
    'latestVersion': '2.1.0',
    'windowsLatest': '2.1.0',
    'windowsMin': '2.0.0',
    'androidLatest': '2.1.0',
    'androidMin': '2.0.0',
    'macosLatest': '2.1.0',
    'macosMin': '2.0.0',
    'iosLatest': '2.1.0',
    'iosMin': '2.0.0',
    'windowsInstallerUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Setup.exe',
    'windowsPortableUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Mavie.exe',
    'androidApkUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Android.apk',
    'macosUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Mavie-macOS.dmg',
    'iosUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Mavie-iOS.ipa',
    'releaseNotes': 'Mavie 2.1.0: 4 platform desteği, e-posta doğrulama ve 3 günlük Pro deneme.',
}

PLAN_CATALOG = {
    'normal': {
        'maxDevices': 1,
        'features': ['demo_m3u_local', 'single_profile', 'single_device'],
    },
    'pro': {
        'maxDevices': 5,
        'trialDays': 3,
        'features': ['cloud_sync', 'multi_view', 'unlimited_profiles_pin', 'epg_match', 'advanced_tracks', 'five_devices'],
    },
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _parse_iso(value: str) -> dt.datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except ValueError:
        return None


def _env_first(*names: str, default: str = '') -> str:
    for name in names:
        val = os.environ.get(name, '').strip()
        if val:
            return val
    return default


def _strip_header_crlf(value: str) -> str:
    return re.sub(r'[\r\n\x00]+', ' ', str(value or '')).strip()


def normalize_plan(plan: str) -> str:
    clean = str(plan or '').strip().lower()
    if clean in LEGACY_PLAN_MAP:
        return LEGACY_PLAN_MAP[clean]
    return 'normal'


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = '', extra: dict | None = None):
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.code = code
        self.extra = dict(extra or {})


class _DBConn(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class CloudService:
    """Thread-safe SQLite-backed control plane for accounts, verification, plans, licenses, devices, and admin actions."""

    def __init__(
        self,
        data_dir: Path,
        *,
        secret_key: str = '',
        admin_email: str = '',
        admin_password: str = '',
        admin_gate_key: str = '',
        email_mode: str = '',
        outbox_file: Path | str | None = None,
        smtp_host: str = '',
        smtp_port: int = 0,
        smtp_user: str = '',
        smtp_pass: str = '',
        smtp_from: str = '',
        smtp_tls: str = '',
    ):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.data_dir, 0o700)
        self.db_path = self.data_dir / 'cloud.sqlite3'
        self.secret = self._load_or_create_secret(secret_key)
        self.admin_gate_key = self._load_gate_key(admin_gate_key)
        self._email_mode_override = str(email_mode or '').strip().lower()
        self._outbox_file_override = Path(outbox_file).resolve() if outbox_file else None
        self._smtp_host_override = str(smtp_host or '').strip()
        self._smtp_port_override = int(smtp_port or 0)
        self._smtp_user_override = str(smtp_user or '').strip()
        self._smtp_pass_override = str(smtp_pass or '')
        self._smtp_from_override = str(smtp_from or '').strip()
        self._smtp_tls_override = str(smtp_tls or '').strip().lower()
        self._lock = threading.Lock()
        self._rate_limits: dict[str, list[float]] = collections.defaultdict(list)
        self._init_schema()
        self.bootstrap_admin_password: str | None = self._ensure_admin(admin_email, admin_password)

    def _load_gate_key(self, explicit: str) -> str:
        clean = explicit.strip()
        if clean and clean != '__auto__':
            return clean
        if clean != '__auto__':
            return ''
        gate_file = self.data_dir / 'admin_gate.key'
        if gate_file.exists():
            raw = gate_file.read_text(encoding='utf-8').strip()
            if raw:
                return raw
        generated = secrets.token_urlsafe(18)
        fd = os.open(gate_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(generated)
        return generated

    def sign_gate_cookie(self, ttl_seconds: int = 12 * 3600) -> str:
        exp = str(int(time.time()) + ttl_seconds)
        sig = hmac.new(self.secret, ('gate:' + exp).encode('ascii'), hashlib.sha256).hexdigest()
        return f'{exp}.{sig}'

    def verify_gate_cookie(self, value: str) -> bool:
        if not value or '.' not in value:
            return False
        try:
            exp_s, sig_hex = value.strip().split('.', 1)
            if int(exp_s) < int(time.time()):
                return False
            expected = hmac.new(self.secret, ('gate:' + exp_s).encode('ascii'), hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig_hex, expected)
        except (ValueError, TypeError):
            return False

    def _load_or_create_secret(self, explicit: str) -> bytes:
        clean = explicit.strip()
        if clean:
            return clean.encode('utf-8')
        secret_file = self.data_dir / 'cloud_secret.key'
        if secret_file.exists():
            raw = secret_file.read_text(encoding='utf-8').strip()
            if raw:
                return raw.encode('utf-8')
        generated = secrets.token_hex(32)
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(generated)
        return generated.encode('utf-8')

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False, factory=_DBConn)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=30000')
        return c

    def _init_schema(self) -> None:
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    plan TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'active',
                    max_devices INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT DEFAULT '',
                    admin_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    verified_at TEXT NOT NULL DEFAULT '',
                    trial_used INTEGER NOT NULL DEFAULT 0,
                    trial_started_at TEXT NOT NULL DEFAULT '',
                    trial_ends_at TEXT NOT NULL DEFAULT '',
                    token_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);
                CREATE TABLE IF NOT EXISTS devices(
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, device_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS licenses(
                    code TEXT PRIMARY KEY,
                    plan TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    max_devices INTEGER NOT NULL DEFAULT 5,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses_count INTEGER NOT NULL DEFAULT 0,
                    note TEXT DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS license_redemptions(
                    code TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    redeemed_at TEXT NOT NULL,
                    PRIMARY KEY(code, user_id),
                    FOREIGN KEY(code) REFERENCES licenses(code) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS email_verifications(
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_email_verifications_user ON email_verifications(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_email_verifications_email ON email_verifications(email, used, created_at DESC);
                CREATE TABLE IF NOT EXISTS password_resets(
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    code_hash TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS email_outbox(
                    id TEXT PRIMARY KEY,
                    recipient TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    token TEXT NOT NULL DEFAULT '',
                    delivery_mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'stored',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_email_outbox_recipient ON email_outbox(recipient, created_at DESC);
                CREATE TABLE IF NOT EXISTS app_config(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS download_stats(
                    target TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_logs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id TEXT NOT NULL,
                    actor_email TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_sync(
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # Idempotent ALTER TABLE migrations for pre-existing databases
            user_cols = {r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()}
            user_alter_stmts = {
                'email_verified': 'ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1',
                'verified_at': "ALTER TABLE users ADD COLUMN verified_at TEXT NOT NULL DEFAULT ''",
                'trial_used': 'ALTER TABLE users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0',
                'trial_started_at': "ALTER TABLE users ADD COLUMN trial_started_at TEXT NOT NULL DEFAULT ''",
                'trial_ends_at': "ALTER TABLE users ADD COLUMN trial_ends_at TEXT NOT NULL DEFAULT ''",
                'token_version': 'ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1',
            }
            for col, stmt in user_alter_stmts.items():
                if col not in user_cols:
                    c.execute(stmt)
            c.execute("UPDATE users SET verified_at=created_at WHERE email_verified=1 AND verified_at=''")

            # Normalize legacy 4-tier plans to 2-tier ('normal' vs 'pro')
            c.execute("UPDATE users SET plan='normal', max_devices=CASE WHEN role='admin' THEN max_devices ELSE 1 END WHERE plan='free'")
            c.execute("UPDATE users SET plan='pro', max_devices=MAX(max_devices, 5) WHERE plan IN ('family','lifetime')")
            c.execute("UPDATE licenses SET plan='pro' WHERE plan IN ('family','lifetime')")
            c.execute("DELETE FROM licenses WHERE plan='free'")

            reset_cols = {r['name'] for r in c.execute('PRAGMA table_info(password_resets)').fetchall()}
            reset_alter_stmts = {
                'email': "ALTER TABLE password_resets ADD COLUMN email TEXT NOT NULL DEFAULT ''",
                'code_hash': "ALTER TABLE password_resets ADD COLUMN code_hash TEXT NOT NULL DEFAULT ''",
                'attempts': 'ALTER TABLE password_resets ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0',
                'created_at': "ALTER TABLE password_resets ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
            }
            for col, stmt in reset_alter_stmts.items():
                if col not in reset_cols:
                    c.execute(stmt)
            c.execute('CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id, used)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_password_resets_email ON password_resets(email, used, created_at DESC)')

            defaults = {
                'announcement': json.dumps({
                    'enabled': False,
                    'title': '',
                    'message': '',
                    'severity': 'info',
                }),
                'versions': json.dumps(DEFAULT_VERSIONS, ensure_ascii=False),
            }
            for k, v in defaults.items():
                c.execute('INSERT OR IGNORE INTO app_config VALUES(?,?)', (k, v))

            # Upgrade legacy Cineva-* version URLs & backfill new 4-platform keys
            vers_row = c.execute("SELECT value FROM app_config WHERE key='versions'").fetchone()
            if vers_row:
                try:
                    cur_vers = json.loads(vers_row['value'])
                except Exception:
                    cur_vers = {}
                if isinstance(cur_vers, dict):
                    changed = False
                    for k, default_val in DEFAULT_VERSIONS.items():
                        existing_val = cur_vers.get(k)
                        if not existing_val:
                            cur_vers[k] = default_val
                            changed = True
                        elif isinstance(existing_val, str):
                            legacy_pat = r'(?:Cineva|' + 'Vrel' + r'io)(?=[-. ])'
                            updated_val = re.sub(legacy_pat, 'Mavie', existing_val)
                            if updated_val != existing_val:
                                cur_vers[k] = updated_val
                                changed = True
                    if changed:
                        c.execute("UPDATE app_config SET value=? WHERE key='versions'", (json.dumps(cur_vers, ensure_ascii=False),))

            for target in DOWNLOAD_TARGETS:
                c.execute('INSERT OR IGNORE INTO download_stats VALUES(?,0,?)', (target, iso_now()))

    @staticmethod
    def _hash_password(password: str) -> str:
        raw = str(password or '')
        if len(raw) < 8 or len(raw) > 200:
            raise ValueError('Parola 8 ile 200 karakter arasında olmalıdır.')
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', raw.encode('utf-8'), salt, 200_000)
        return f'pbkdf2_sha256:200000:{salt.hex()}:{digest.hex()}'

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            scheme, iters_s, salt_hex, digest_hex = stored.split(':', 3)
            if scheme != 'pbkdf2_sha256':
                return False
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac('sha256', str(password or '').encode('utf-8'), salt, int(iters_s))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _hash_code(purpose: str, user_id: str, code: str) -> str:
        clean = str(code or '').strip()
        return hashlib.sha256(f'{purpose}:{user_id}:{clean}'.encode('utf-8')).hexdigest()

    @staticmethod
    def _hash_token(purpose: str, raw_token: str) -> str:
        clean = str(raw_token or '').strip()
        return hashlib.sha256(f'{purpose}_token:{clean}'.encode('utf-8')).hexdigest()

    @staticmethod
    def _legacy_hash_token(raw_token: str) -> str:
        clean = str(raw_token or '').strip()
        return hashlib.sha256(clean.encode('utf-8')).hexdigest()

    def _ensure_admin(self, admin_email: str, admin_password: str) -> str | None:
        with self.connect() as c:
            existing = c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
            if existing:
                return None
        email = (admin_email or 'admin@mavie.app').strip().lower()
        if not EMAIL_RE.fullmatch(email):
            email = 'admin@mavie.app'
        generated = None
        pwd = admin_password.strip()
        if not pwd:
            generated = secrets.token_urlsafe(14)
            pwd = generated
        pw_hash = self._hash_password(pwd)
        now = iso_now()
        with self.connect() as c:
            c.execute(
                """INSERT OR IGNORE INTO users(
                       id, email, display_name, password_hash, role, plan, status,
                       max_devices, expires_at, admin_note, created_at, last_seen_at,
                       email_verified, verified_at, trial_used, trial_started_at, trial_ends_at, token_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    'usr_admin_' + secrets.token_hex(6), email, 'Yönetici', pw_hash,
                    'admin', 'pro', 'active', 10, '', 'Sistem yöneticisi', now, now,
                    1, now, 1, '', '', 1,
                ),
            )
        return generated

    def check_rate_limit(self, bucket: str, limit: int = 12, window_s: float = 300.0) -> bool:
        now = time.monotonic()
        with self._lock:
            cutoff = now - window_s
            entries = [t for t in self._rate_limits.get(bucket, ()) if t > cutoff]
            if len(entries) >= limit:
                self._rate_limits[bucket] = entries
                return False
            entries.append(now)
            self._rate_limits[bucket] = entries
            if len(self._rate_limits) > 256:
                stale = [k for k, v in self._rate_limits.items() if not v or v[-1] <= cutoff]
                for k in stale:
                    if k != bucket:
                        self._rate_limits.pop(k, None)
            return True

    def is_rate_limited(self, bucket: str, limit: int = 12, window_s: float = 300.0) -> bool:
        now = time.monotonic()
        with self._lock:
            cutoff = now - window_s
            entries = [t for t in self._rate_limits.get(bucket, ()) if t > cutoff]
            if entries:
                self._rate_limits[bucket] = entries
            else:
                self._rate_limits.pop(bucket, None)
            return len(entries) >= limit

    def record_rate_limit(self, bucket: str, window_s: float = 300.0) -> None:
        now = time.monotonic()
        with self._lock:
            cutoff = now - window_s
            entries = [t for t in self._rate_limits.get(bucket, ()) if t > cutoff]
            entries.append(now)
            self._rate_limits[bucket] = entries

    def clear_rate_limit(self, bucket: str) -> None:
        with self._lock:
            self._rate_limits.pop(bucket, None)

    def _issue_token(self, user_id: str, role: str, token_version: int = 1, ttl_seconds: int = 7 * 24 * 3600) -> str:
        payload = json.dumps({
            'sub': user_id,
            'role': role,
            'tv': int(token_version or 1),
            'exp': int(time.time()) + ttl_seconds,
            'jti': secrets.token_hex(8),
        }, separators=(',', ':')).encode('utf-8')
        body = base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')
        sig = hmac.new(self.secret, body.encode('ascii'), hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).decode('ascii').rstrip('=')
        return f'{body}.{sig_b64}'

    def verify_token(self, token: str) -> dict | None:
        if not token or '.' not in token:
            return None
        try:
            body, sig_b64 = token.strip().split('.', 1)
            padded_sig = sig_b64 + '=' * (-len(sig_b64) % 4)
            expected = hmac.new(self.secret, body.encode('ascii'), hashlib.sha256).digest()
            if not hmac.compare_digest(base64.urlsafe_b64decode(padded_sig), expected):
                return None
            padded_body = body + '=' * (-len(body) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded_body).decode('utf-8'))
            if int(claims.get('exp', 0)) < int(time.time()):
                return None
            with self.connect() as c:
                row = c.execute('SELECT * FROM users WHERE id=?', (claims['sub'],)).fetchone()
                if not row:
                    return None
                claim_tv = int(claims.get('tv', claims.get('ver', 1)))
                if claim_tv != int(row['token_version']):
                    return None
                return self._public_user(row)
        except Exception:
            return None

    @staticmethod
    def _effective_plan(plan: str, expires_at: str) -> str:
        norm = normalize_plan(plan)
        if norm != 'pro':
            return 'normal'
        if not expires_at:
            return 'pro'
        exp = _parse_iso(expires_at)
        if exp is not None and exp < utc_now():
            return 'normal'
        return 'pro'

    @classmethod
    def _public_user(cls, row: sqlite3.Row, devices: list[dict] | None = None) -> dict:
        expires_at = row['expires_at'] or ''
        raw_plan = normalize_plan(row['plan'])
        eff_plan = cls._effective_plan(raw_plan, expires_at)
        is_pro = eff_plan == 'pro'
        email_verified = bool(row['email_verified'])
        trial_used = bool(row['trial_used'])
        trial_started_at = row['trial_started_at'] or ''
        trial_ends_at = row['trial_ends_at'] or ''
        trial_end_dt = _parse_iso(trial_ends_at)
        trial_active = bool(
            is_pro
            and trial_ends_at
            and expires_at == trial_ends_at
            and trial_end_dt is not None
            and trial_end_dt > utc_now()
        )
        if row['role'] == 'admin':
            eff_max_devices = max(1, int(row['max_devices'] or 10))
        elif not is_pro:
            eff_max_devices = 1
        else:
            eff_max_devices = max(1, int(row['max_devices'] or 5))

        out = {
            'id': row['id'],
            'email': row['email'],
            'displayName': row['display_name'],
            'role': row['role'],
            'emailVerified': email_verified,
            'verifiedAt': row['verified_at'] or '',
            'plan': raw_plan,
            'effectivePlan': eff_plan,
            'isPro': is_pro,
            'trialActive': trial_active,
            'trialUsed': trial_used,
            'trialStartedAt': trial_started_at,
            'trialEndsAt': trial_ends_at,
            'status': row['status'],
            'maxDevices': eff_max_devices,
            'expiresAt': expires_at,
            'adminNote': row['admin_note'] or '',
            'createdAt': row['created_at'],
            'lastSeenAt': row['last_seen_at'],
            'features': {
                'cloudSync': is_pro,
                'multiView': is_pro,
                'unlimitedProfiles': is_pro,
                'epgMatch': is_pro,
                'advancedTracks': is_pro,
                'maxDevices': eff_max_devices,
            },
        }
        if devices is not None:
            out['devices'] = devices
        return out

    def get_user_by_id(self, user_id: str, include_devices: bool = False) -> dict | None:
        with self.connect() as c:
            row = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                return None
            devs = None
            if include_devices:
                devs = [
                    dict(d)
                    for d in c.execute(
                        'SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC',
                        (user_id,),
                    )
                ]
            return self._public_user(row, devs)

    def _outbox_file_path(self) -> Path:
        if self._outbox_file_override is not None:
            return self._outbox_file_override
        env_path = _env_first('MAVIE_EMAIL_OUTBOX_FILE', 'CINEVA_EMAIL_OUTBOX_FILE')
        if env_path:
            return Path(env_path).resolve()
        return self.data_dir / 'email_outbox.json'

    def _email_config(self) -> dict:
        mode = self._email_mode_override or _env_first('MAVIE_EMAIL_MODE', 'CINEVA_EMAIL_MODE', 'EMAIL_MODE', default='auto').lower()
        host = self._smtp_host_override or _env_first('MAVIE_SMTP_HOST', 'CINEVA_SMTP_HOST', 'SMTP_HOST')
        port_raw = str(self._smtp_port_override or _env_first('MAVIE_SMTP_PORT', 'CINEVA_SMTP_PORT', 'SMTP_PORT', default='587'))
        try:
            port = int(port_raw)
        except ValueError:
            port = 587
        user = self._smtp_user_override or _env_first('MAVIE_SMTP_USER', 'CINEVA_SMTP_USER', 'SMTP_USER')
        password = self._smtp_pass_override or _env_first('MAVIE_SMTP_PASS', 'CINEVA_SMTP_PASS', 'SMTP_PASS')
        sender = _strip_header_crlf(
            self._smtp_from_override or _env_first('MAVIE_SMTP_FROM', 'CINEVA_SMTP_FROM', 'SMTP_FROM', default='Mavie <noreply@mavie.app>')
        )
        tls = self._smtp_tls_override or _env_first('MAVIE_SMTP_TLS', 'SMTP_TLS', default=('ssl' if port == 465 else 'starttls')).lower()
        effective_mode = 'outbox' if (mode == 'outbox' or (mode != 'smtp' and not host)) else 'smtp'
        if mode == 'smtp' and not host:
            effective_mode = 'smtp'
        return {
            'mode': effective_mode,
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'sender': sender,
            'tls': tls,
        }

    def _append_outbox_file(self, entry: dict) -> None:
        out_path = self._outbox_file_path()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            existing = []
            if out_path.exists():
                with contextlib.suppress(Exception):
                    parsed = json.loads(out_path.read_text(encoding='utf-8'))
                    if isinstance(parsed, list):
                        existing = parsed
            existing.append(entry)
            tmp_path = out_path.with_name(f'.{out_path.name}.{secrets.token_hex(4)}.tmp')
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, out_path)
            with contextlib.suppress(OSError):
                os.chmod(out_path, 0o600)

    def _deliver_email(self, *, kind: str, recipient: str, display_name: str, code: str, token: str) -> str:
        clean_recipient = _strip_header_crlf(recipient).lower()
        clean_name = _strip_header_crlf(display_name) or 'Kullanıcı'
        if kind == 'verify_email':
            subject = _strip_header_crlf('Mavie — E-posta Adresinizi Doğrulayın')
            body_text = (
                f'Merhaba {clean_name},\n\n'
                f'Mavie hesabınızı doğrulamak için 6 haneli kodunuz: {code}\n'
                f'Doğrulama belirteci: {token}\n\n'
                'Bu kod 24 saat geçerlidir. Doğrulama tamamlandığında 3 günlük ücretsiz Pro denemeniz otomatik başlar.\n'
            )
        else:
            subject = _strip_header_crlf('Mavie — Parola Sıfırlama Kodu')
            body_text = (
                f'Merhaba {clean_name},\n\n'
                f'Mavie hesabınız için parola sıfırlama kodunuz: {code}\n'
                f'Sıfırlama belirteci: {token}\n\n'
                'Bu kod 30 dakika geçerlidir. Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz.\n'
            )

        cfg = self._email_config()
        msg_id = 'mail_' + secrets.token_hex(8)
        now = iso_now()

        if cfg['mode'] == 'smtp':
            if not cfg['host']:
                raise ApiError(500, 'SMTP sunucusu yapılandırılmamış.', 'SMTP_NOT_CONFIGURED')
            msg = EmailMessage()
            msg['From'] = cfg['sender']
            msg['To'] = clean_recipient
            msg['Subject'] = subject
            msg.set_content(body_text)
            try:
                if cfg['tls'] == 'ssl':
                    with smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=15, context=ssl.create_default_context()) as client:
                        if cfg['user'] and cfg['password']:
                            client.login(cfg['user'], cfg['password'])
                        client.send_message(msg)
                else:
                    with smtplib.SMTP(cfg['host'], cfg['port'], timeout=15) as client:
                        if cfg['tls'] != 'none':
                            client.ehlo()
                            client.starttls(context=ssl.create_default_context())
                            client.ehlo()
                        if cfg['user'] and cfg['password']:
                            client.login(cfg['user'], cfg['password'])
                        client.send_message(msg)
                with self.connect() as c:
                    c.execute(
                        'INSERT INTO email_outbox(id,recipient,kind,subject,body_text,code,token,delivery_mode,status,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (msg_id, clean_recipient, kind, subject, body_text, '', '', 'smtp', 'sent', '', now),
                    )
                return 'smtp'
            except Exception as exc:
                with self.connect() as c:
                    c.execute(
                        'INSERT INTO email_outbox(id,recipient,kind,subject,body_text,code,token,delivery_mode,status,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (msg_id, clean_recipient, kind, subject, body_text, '', '', 'smtp', 'failed', str(exc)[:300], now),
                    )
                raise ApiError(502, 'E-posta gönderilemedi. Lütfen daha sonra tekrar deneyin.', 'EMAIL_DELIVERY_FAILED')

        with self.connect() as c:
            c.execute(
                'INSERT INTO email_outbox(id,recipient,kind,subject,body_text,code,token,delivery_mode,status,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (msg_id, clean_recipient, kind, subject, body_text, code, token, 'outbox', 'stored', '', now),
            )
        self._append_outbox_file({
            'id': msg_id,
            'recipient': clean_recipient,
            'kind': kind,
            'subject': subject,
            'bodyText': body_text,
            'code': code,
            'token': token,
            'deliveryMode': 'outbox',
            'createdAt': now,
        })
        return 'outbox'

    def get_sync_state(self, user_id: str) -> dict:
        with self.connect() as c:
            row = c.execute('SELECT state_json, updated_at FROM user_sync WHERE user_id=?', (user_id,)).fetchone()
            if not row:
                return {'state': None, 'updatedAt': ''}
            try:
                state = json.loads(row['state_json'])
            except Exception:
                state = None
            return {'state': state, 'updatedAt': row['updated_at']}

    def put_sync_state(self, user_id: str, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError('Eşitleme verisi geçerli bir JSON nesnesi olmalıdır.')
        source = raw['state'] if isinstance(raw.get('state'), dict) else raw
        clean = {
            'version': int(source.get('version') or 1),
            'exportedAt': str(source.get('exportedAt') or iso_now())[:64],
            'items': list(source.get('items') or [])[:2000] if isinstance(source.get('items'), list) else [],
            'favorites': list(source.get('favorites') or [])[:2000] if isinstance(source.get('favorites'), list) else [],
            'progress': list(source.get('progress') or [])[:2000] if isinstance(source.get('progress'), list) else [],
            'playlists': list(source.get('playlists') or [])[:200] if isinstance(source.get('playlists'), list) else [],
            'playlistItems': list(source.get('playlistItems') or [])[:5000] if isinstance(source.get('playlistItems'), list) else [],
            'trackPreferences': list(source.get('trackPreferences') or [])[:2000] if isinstance(source.get('trackPreferences'), list) else [],
            'nativeTrackPreferences': list(source.get('nativeTrackPreferences') or [])[:2000] if isinstance(source.get('nativeTrackPreferences'), list) else [],
        }
        now = iso_now()
        with self.connect() as c:
            c.execute(
                'INSERT OR REPLACE INTO user_sync(user_id, state_json, updated_at) VALUES(?,?,?)',
                (user_id, json.dumps(clean, ensure_ascii=False), now),
            )
            c.execute('UPDATE users SET last_seen_at=? WHERE id=?', (now, user_id))
        return {'ok': True, 'state': clean, 'updatedAt': now}

    def _audit(self, c: sqlite3.Connection, actor: dict, action: str, target_type: str, target_id: str, details: dict) -> None:
        c.execute(
            'INSERT INTO audit_logs(actor_id,actor_email,action,target_type,target_id,details,created_at) VALUES(?,?,?,?,?,?,?)',
            (actor['id'], actor['email'], action, target_type, target_id, json.dumps(details, ensure_ascii=False), iso_now()),
        )

    def register(self, email: str, password: str, display_name: str = '') -> dict:
        clean_email = str(email or '').strip().lower()
        if not EMAIL_RE.fullmatch(clean_email):
            raise ValueError('Geçerli bir e-posta adresi girin.')
        name = (_strip_header_crlf(display_name) or clean_email.split('@', 1)[0])[:80]
        pw_hash = self._hash_password(password)
        now_dt = utc_now()
        now = now_dt.isoformat()
        expires = (now_dt + dt.timedelta(hours=VERIFY_TTL_HOURS)).isoformat()
        code = f'{secrets.randbelow(1_000_000):06d}'
        token = secrets.token_urlsafe(24)

        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT * FROM users WHERE email=?', (clean_email,)).fetchone()
            if existing:
                if int(existing['email_verified']) == 1:
                    raise ApiError(400, 'Bu e-posta adresi zaten kayıtlı.', 'EMAIL_ALREADY_EXISTS')
                uid = existing['id']
                c.execute(
                    'UPDATE users SET display_name=?, password_hash=?, last_seen_at=? WHERE id=?',
                    (name, pw_hash, now, uid),
                )
                c.execute('UPDATE email_verifications SET used=1 WHERE user_id=? AND used=0', (uid,))
            else:
                uid = 'usr_' + secrets.token_hex(8)
                c.execute(
                    """INSERT INTO users(
                           id, email, display_name, password_hash, role, plan, status,
                           max_devices, expires_at, admin_note, created_at, last_seen_at,
                           email_verified, verified_at, trial_used, trial_started_at, trial_ends_at, token_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uid, clean_email, name, pw_hash, 'user', 'normal', 'active',
                        1, '', '', now, now,
                        0, '', 0, '', '', 1,
                    ),
                )
            ver_id = 'ver_' + secrets.token_hex(8)
            c.execute(
                'INSERT INTO email_verifications(id,user_id,email,code_hash,token_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,?,0,0,?)',
                (
                    ver_id,
                    uid,
                    clean_email,
                    self._hash_code('verify_email', uid, code),
                    self._hash_token('verify_email', token),
                    expires,
                    now,
                ),
            )
            row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        delivery_mode = self._deliver_email(
            kind='verify_email',
            recipient=clean_email,
            display_name=row['display_name'],
            code=code,
            token=token,
        )
        return {
            'ok': True,
            'verificationRequired': True,
            'emailVerified': False,
            'deliveryMode': delivery_mode,
            'user': self._public_user(row),
        }

    def verify_email(self, *, email: str = '', code: str = '', token: str = '') -> dict:
        clean_email = str(email or '').strip().lower()
        clean_code = str(code or '').strip()
        clean_token = str(token or '').strip()
        if not clean_token and (not EMAIL_RE.fullmatch(clean_email) or not clean_code):
            raise ApiError(400, 'Doğrulama kodu veya belirteci gerekli.', 'INVALID_VERIFICATION_INPUT')

        err_to_raise: ApiError | None = None
        trial_activated = False
        user_row = None

        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if clean_token:
                thash = self._hash_token('verify_email', clean_token)
                rec = c.execute('SELECT * FROM email_verifications WHERE token_hash=? AND used=0', (thash,)).fetchone()
                matched = bool(rec and hmac.compare_digest(rec['token_hash'], thash))
            else:
                rec = c.execute(
                    'SELECT * FROM email_verifications WHERE email=? AND used=0 ORDER BY created_at DESC LIMIT 1',
                    (clean_email,),
                ).fetchone()
                if rec:
                    chash = self._hash_code('verify_email', rec['user_id'], clean_code)
                    matched = hmac.compare_digest(rec['code_hash'], chash)
                else:
                    matched = False

            if not rec:
                err_to_raise = ApiError(400, 'Doğrulama kodu geçersiz veya kullanılmış.', 'INVALID_VERIFICATION_CODE')
            else:
                exp = _parse_iso(rec['expires_at'])
                if exp is not None and exp < utc_now():
                    c.execute('UPDATE email_verifications SET used=1 WHERE id=?', (rec['id'],))
                    err_to_raise = ApiError(400, 'Doğrulama kodunun süresi dolmuş.', 'VERIFICATION_EXPIRED')
                elif int(rec['attempts']) >= MAX_CODE_ATTEMPTS:
                    c.execute('UPDATE email_verifications SET used=1 WHERE id=?', (rec['id'],))
                    err_to_raise = ApiError(400, 'Çok fazla hatalı deneme. Yeni doğrulama kodu isteyin.', 'VERIFICATION_LOCKED')
                elif not matched:
                    new_attempts = int(rec['attempts']) + 1
                    burn = 1 if new_attempts >= MAX_CODE_ATTEMPTS else 0
                    c.execute(
                        'UPDATE email_verifications SET attempts=?, used=CASE WHEN ?=1 THEN 1 ELSE used END WHERE id=?',
                        (new_attempts, burn, rec['id']),
                    )
                    msg = (
                        'Çok fazla hatalı deneme. Yeni doğrulama kodu isteyin.'
                        if burn
                        else 'Doğrulama kodu hatalı.'
                    )
                    err_to_raise = ApiError(400, msg, 'VERIFICATION_LOCKED' if burn else 'INVALID_VERIFICATION_CODE')
                else:
                    cur = c.execute('UPDATE email_verifications SET used=1 WHERE id=? AND used=0', (rec['id'],))
                    if cur.rowcount != 1:
                        err_to_raise = ApiError(400, 'Doğrulama kodu geçersiz veya kullanılmış.', 'INVALID_VERIFICATION_CODE')
                    else:
                        c.execute('UPDATE email_verifications SET used=1 WHERE user_id=? AND used=0', (rec['user_id'],))
                        u = c.execute('SELECT * FROM users WHERE id=?', (rec['user_id'],)).fetchone()
                        if not u:
                            err_to_raise = ApiError(400, 'Kullanıcı bulunamadı.', 'USER_NOT_FOUND')
                        elif u['status'] != 'active':
                            err_to_raise = ApiError(403, 'Hesabınız askıya alınmış. Destek ile iletişime geçin.', 'ACCOUNT_SUSPENDED')
                        else:
                            now_dt = utc_now()
                            now = now_dt.isoformat()
                            verified_at = u['verified_at'] or now
                            if int(u['trial_used']) == 0 and normalize_plan(u['plan']) == 'normal':
                                trial_ends = (now_dt + dt.timedelta(hours=TRIAL_DURATION_HOURS)).isoformat()
                                c.execute(
                                    """UPDATE users
                                       SET email_verified=1, verified_at=?, plan='pro', max_devices=5,
                                           trial_used=1, trial_started_at=?, trial_ends_at=?, expires_at=?, last_seen_at=?
                                       WHERE id=?""",
                                    (verified_at, now, trial_ends, trial_ends, now, u['id']),
                                )
                                trial_activated = True
                            else:
                                c.execute(
                                    'UPDATE users SET email_verified=1, verified_at=?, last_seen_at=? WHERE id=?',
                                    (verified_at, now, u['id']),
                                )
                            user_row = c.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone()

        if err_to_raise is not None:
            raise err_to_raise

        token_out = self._issue_token(user_row['id'], user_row['role'], int(user_row['token_version']))
        return {
            'ok': True,
            'token': token_out,
            'trialActivated': trial_activated,
            'user': self._public_user(user_row),
        }

    def resend_verification(self, email: str) -> dict:
        clean_email = str(email or '').strip().lower()
        if not EMAIL_RE.fullmatch(clean_email):
            raise ValueError('Geçerli bir e-posta adresi girin.')
        cfg_mode = self._email_config()['mode']
        now_dt = utc_now()
        now = now_dt.isoformat()
        expires = (now_dt + dt.timedelta(hours=VERIFY_TTL_HOURS)).isoformat()
        code = f'{secrets.randbelow(1_000_000):06d}'
        token = secrets.token_urlsafe(24)

        target_row = None
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM users WHERE email=?', (clean_email,)).fetchone()
            if row:
                if int(row['email_verified']) == 1:
                    raise ApiError(400, 'E-posta adresi zaten doğrulanmış.', 'ALREADY_VERIFIED')
                if row['status'] == 'active':
                    c.execute('UPDATE email_verifications SET used=1 WHERE user_id=? AND used=0', (row['id'],))
                    c.execute(
                        'INSERT INTO email_verifications(id,user_id,email,code_hash,token_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,?,0,0,?)',
                        (
                            'ver_' + secrets.token_hex(8),
                            row['id'],
                            clean_email,
                            self._hash_code('verify_email', row['id'], code),
                            self._hash_token('verify_email', token),
                            expires,
                            now,
                        ),
                    )
                    target_row = row

        if target_row is not None:
            delivery_mode = self._deliver_email(
                kind='verify_email',
                recipient=clean_email,
                display_name=target_row['display_name'],
                code=code,
                token=token,
            )
        else:
            delivery_mode = cfg_mode
        return {'ok': True, 'deliveryMode': delivery_mode}

    def login(self, email: str, password: str) -> dict:
        clean_email = str(email or '').strip().lower()
        with self.connect() as c:
            row = c.execute('SELECT * FROM users WHERE email=?', (clean_email,)).fetchone()
            if not row or not self._verify_password(password, row['password_hash']):
                raise ApiError(401, 'E-posta veya parola hatalı.', 'INVALID_CREDENTIALS')
            if row['status'] != 'active':
                raise ApiError(403, 'Hesabınız askıya alınmış. Destek ile iletişime geçin.', 'ACCOUNT_SUSPENDED')
            if int(row['email_verified']) != 1:
                raise ApiError(
                    403,
                    'E-posta doğrulaması gerekli.',
                    'EMAIL_NOT_VERIFIED',
                    {'verificationRequired': True, 'email': row['email']},
                )
            c.execute('UPDATE users SET last_seen_at=? WHERE id=?', (iso_now(), row['id']))
            row = c.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            devs = [
                dict(d)
                for d in c.execute(
                    'SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC',
                    (row['id'],),
                )
            ]
        return {
            'ok': True,
            'token': self._issue_token(row['id'], row['role'], int(row['token_version'])),
            'user': self._public_user(row, devs),
        }

    def forgot_password(self, email: str) -> dict:
        clean_email = str(email or '').strip().lower()
        if not EMAIL_RE.fullmatch(clean_email):
            raise ValueError('Geçerli bir e-posta adresi girin.')
        cfg_mode = self._email_config()['mode']
        now_dt = utc_now()
        now = now_dt.isoformat()
        expires = (now_dt + dt.timedelta(minutes=RESET_TTL_MINUTES)).isoformat()
        code = f'{secrets.randbelow(1_000_000):06d}'
        token = secrets.token_urlsafe(24)

        target_row = None
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM users WHERE email=?', (clean_email,)).fetchone()
            if row and row['status'] == 'active' and int(row['email_verified']) == 1:
                c.execute('UPDATE password_resets SET used=1 WHERE user_id=? AND used=0', (row['id'],))
                c.execute(
                    'INSERT INTO password_resets(token_hash,user_id,email,code_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,0,0,?)',
                    (
                        self._hash_token('password_reset', token),
                        row['id'],
                        clean_email,
                        self._hash_code('password_reset', row['id'], code),
                        expires,
                        now,
                    ),
                )
                target_row = row

        if target_row is not None:
            delivery_mode = self._deliver_email(
                kind='password_reset',
                recipient=clean_email,
                display_name=target_row['display_name'],
                code=code,
                token=token,
            )
        else:
            delivery_mode = cfg_mode
        return {
            'ok': True,
            'deliveryMode': delivery_mode,
            'message': 'Eğer hesap kayıtlıysa şifre sıfırlama kodu gönderildi.',
        }

    def verify_reset_code(self, *, email: str = '', code: str = '', token: str = '') -> dict:
        clean_email = str(email or '').strip().lower()
        clean_code = str(code or '').strip()
        clean_token = str(token or '').strip()
        if not clean_token and (not EMAIL_RE.fullmatch(clean_email) or not clean_code):
            raise ApiError(400, 'Sıfırlama kodu veya belirteci gerekli.', 'INVALID_RESET_INPUT')

        err_to_raise: ApiError | None = None
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rec, matched = self._find_reset_record(c, clean_email=clean_email, clean_code=clean_code, clean_token=clean_token)
            if not rec:
                err_to_raise = ApiError(400, 'Sıfırlama kodu geçersiz veya kullanılmış.', 'INVALID_RESET_CODE')
            else:
                exp = _parse_iso(rec['expires_at'])
                if exp is not None and exp < utc_now():
                    c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?', (rec['token_hash'],))
                    err_to_raise = ApiError(400, 'Sıfırlama kodunun süresi dolmuş.', 'RESET_EXPIRED')
                elif int(rec['attempts']) >= MAX_CODE_ATTEMPTS:
                    c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?', (rec['token_hash'],))
                    err_to_raise = ApiError(400, 'Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.', 'RESET_LOCKED')
                elif not matched:
                    new_attempts = int(rec['attempts']) + 1
                    burn = 1 if new_attempts >= MAX_CODE_ATTEMPTS else 0
                    c.execute(
                        'UPDATE password_resets SET attempts=?, used=CASE WHEN ?=1 THEN 1 ELSE used END WHERE token_hash=?',
                        (new_attempts, burn, rec['token_hash']),
                    )
                    err_to_raise = ApiError(
                        400,
                        'Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.' if burn else 'Sıfırlama kodu hatalı.',
                        'RESET_LOCKED' if burn else 'INVALID_RESET_CODE',
                    )
        if err_to_raise is not None:
            raise err_to_raise
        return {'ok': True, 'valid': True}

    def _find_reset_record(self, c: sqlite3.Connection, *, clean_email: str, clean_code: str, clean_token: str):
        if clean_token:
            thash = self._hash_token('password_reset', clean_token)
            legacy_hash = self._legacy_hash_token(clean_token)
            rec = c.execute(
                'SELECT * FROM password_resets WHERE (token_hash=? OR token_hash=?) AND used=0',
                (thash, legacy_hash),
            ).fetchone()
            matched = bool(
                rec and (
                    hmac.compare_digest(rec['token_hash'], thash)
                    or hmac.compare_digest(rec['token_hash'], legacy_hash)
                )
            )
            return rec, matched

        rec = c.execute(
            'SELECT * FROM password_resets WHERE email=? AND used=0 ORDER BY created_at DESC LIMIT 1',
            (clean_email,),
        ).fetchone()
        if not rec:
            rec = c.execute(
                """SELECT pr.* FROM password_resets pr
                   JOIN users u ON u.id = pr.user_id
                   WHERE u.email=? AND pr.used=0
                   ORDER BY pr.created_at DESC LIMIT 1""",
                (clean_email,),
            ).fetchone()
        if not rec or not rec['code_hash']:
            return rec, False
        expected_code = self._hash_code('password_reset', rec['user_id'], clean_code)
        return rec, hmac.compare_digest(rec['code_hash'], expected_code)

    def register_device(self, user: dict, device_id: str, device_name: str, platform: str) -> list[dict]:
        did = str(device_id or '').strip()[:80]
        if not did:
            raise ValueError('Cihaz kimliği gerekli.')
        dname = (str(device_name or 'Cihaz').strip() or 'Cihaz')[:80]
        plat = (str(platform or 'web').strip().lower() or 'web')[:24]
        now = iso_now()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            u_row = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            if not u_row:
                raise ApiError(401, 'Oturum açmanız gerekiyor.')
            pub = self._public_user(u_row)
            max_devs = pub['maxDevices']
            existing = c.execute('SELECT device_id FROM devices WHERE user_id=? AND device_id=?', (user['id'], did)).fetchone()
            count = c.execute('SELECT COUNT(*) FROM devices WHERE user_id=?', (user['id'],)).fetchone()[0]
            if (not existing and count >= max_devs) or (existing and count > max_devs):
                raise ApiError(
                    403,
                    f"Maksimum cihaz sınırına ({max_devs}) ulaşıldı. Plan yükseltin veya eski bir cihazı kaldırın.",
                    'DEVICE_LIMIT_REACHED',
                    {'maxDevices': max_devs, 'upgradeRequired': not pub['isPro']},
                )
            c.execute('INSERT OR REPLACE INTO devices VALUES(?,?,?,?,?)', (user['id'], did, dname, plat, now))
            c.execute('UPDATE users SET last_seen_at=? WHERE id=?', (now, user['id']))
            return [
                dict(d)
                for d in c.execute(
                    'SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC',
                    (user['id'],),
                )
            ]

    def remove_user_device(self, user_id: str, device_id: str) -> list[dict]:
        did = str(device_id or '').strip()
        if not did:
            raise ValueError('Cihaz kimliği gerekli.')
        with self.connect() as c:
            cur = c.execute('DELETE FROM devices WHERE user_id=? AND device_id=?', (user_id, did))
            if cur.rowcount == 0:
                raise ApiError(404, 'Cihaz bulunamadı.', 'DEVICE_NOT_FOUND')
            return [
                dict(d)
                for d in c.execute(
                    'SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC',
                    (user_id,),
                )
            ]

    def redeem_license(self, user: dict, raw_code: str) -> dict:
        code = str(raw_code or '').strip().upper()
        if not code:
            raise ValueError('Lisans anahtarı boş olamaz.')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            lic = c.execute('SELECT * FROM licenses WHERE code=?', (code,)).fetchone()
            if not lic:
                raise ValueError('Lisans anahtarı bulunamadı.')
            if lic['uses_count'] >= lic['max_uses']:
                raise ValueError('Bu lisans anahtarının kullanım limiti dolmuş.')
            already = c.execute('SELECT 1 FROM license_redemptions WHERE code=? AND user_id=?', (code, user['id'])).fetchone()
            if already:
                raise ValueError('Bu lisans anahtarı bu hesapta zaten kullanıldı.')
            u_row = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            if not u_row:
                raise ApiError(401, 'Oturum açmanız gerekiyor.')

            now_dt = utc_now()
            lic_plan = normalize_plan(lic['plan'])
            if lic['plan'] == 'lifetime' or int(lic['duration_days']) <= 0:
                expires = ''
            else:
                expires = (now_dt + dt.timedelta(days=int(lic['duration_days']))).isoformat()

            cur_pub = self._public_user(u_row)
            if cur_pub['effectivePlan'] == 'normal' or cur_pub['trialActive']:
                new_max_devices = max(1, int(lic['max_devices']))
            else:
                new_max_devices = max(cur_pub['maxDevices'], int(lic['max_devices']))

            c.execute('UPDATE licenses SET uses_count=uses_count+1 WHERE code=?', (code,))
            c.execute('INSERT INTO license_redemptions VALUES(?,?,?)', (code, user['id'], now_dt.isoformat()))
            c.execute(
                'UPDATE users SET plan=?,max_devices=?,expires_at=?,last_seen_at=? WHERE id=?',
                (lic_plan, new_max_devices, expires, now_dt.isoformat(), user['id']),
            )
            self._audit(c, user, 'license.redeem', 'license', code, {'plan': lic_plan, 'expiresAt': expires})
            row = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            return self._public_user(row)

    def create_reset_token(self, actor: dict, user_id: str) -> str:
        raw_token = secrets.token_urlsafe(24)
        token_hash = self._hash_token('password_reset', raw_token)
        now_dt = utc_now()
        expires = (now_dt + dt.timedelta(hours=1)).isoformat()
        with self.connect() as c:
            row = c.execute('SELECT id,email FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise ValueError('Kullanıcı bulunamadı.')
            c.execute(
                'INSERT INTO password_resets(token_hash,user_id,email,code_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,0,0,?)',
                (token_hash, user_id, row['email'], '', expires, now_dt.isoformat()),
            )
            self._audit(c, actor, 'user.reset_token', 'user', user_id, {'email': row['email']})
        return raw_token

    def complete_password_reset(self, raw_token: str = '', new_password: str = '', *, email: str = '', code: str = '') -> None:
        pw_hash = self._hash_password(new_password)
        clean_token = str(raw_token or '').strip()
        clean_email = str(email or '').strip().lower()
        clean_code = str(code or '').strip()
        if not clean_token and (not EMAIL_RE.fullmatch(clean_email) or not clean_code):
            raise ApiError(400, 'Sıfırlama bağlantısı veya kodu gerekli.', 'INVALID_RESET_INPUT')

        err_to_raise: ApiError | None = None
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rec, matched = self._find_reset_record(c, clean_email=clean_email, clean_code=clean_code, clean_token=clean_token)
            if not rec:
                err_to_raise = ApiError(400, 'Sıfırlama bağlantısı geçersiz veya kullanılmış.', 'INVALID_RESET_CODE')
            else:
                exp = _parse_iso(rec['expires_at'])
                if exp is not None and exp < utc_now():
                    c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?', (rec['token_hash'],))
                    err_to_raise = ApiError(400, 'Sıfırlama bağlantısının süresi dolmuş.', 'RESET_EXPIRED')
                elif int(rec['attempts']) >= MAX_CODE_ATTEMPTS:
                    c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?', (rec['token_hash'],))
                    err_to_raise = ApiError(400, 'Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.', 'RESET_LOCKED')
                elif not matched:
                    new_attempts = int(rec['attempts']) + 1
                    burn = 1 if new_attempts >= MAX_CODE_ATTEMPTS else 0
                    c.execute(
                        'UPDATE password_resets SET attempts=?, used=CASE WHEN ?=1 THEN 1 ELSE used END WHERE token_hash=?',
                        (new_attempts, burn, rec['token_hash']),
                    )
                    err_to_raise = ApiError(
                        400,
                        'Çok fazla hatalı deneme. Yeni bir sıfırlama kodu isteyin.' if burn else 'Sıfırlama kodu hatalı.',
                        'RESET_LOCKED' if burn else 'INVALID_RESET_CODE',
                    )
                else:
                    cur = c.execute('UPDATE password_resets SET used=1 WHERE token_hash=? AND used=0', (rec['token_hash'],))
                    if cur.rowcount != 1:
                        err_to_raise = ApiError(400, 'Sıfırlama bağlantısı geçersiz veya kullanılmış.', 'INVALID_RESET_CODE')
                    else:
                        c.execute('UPDATE password_resets SET used=1 WHERE user_id=? AND used=0', (rec['user_id'],))
                        c.execute(
                            'UPDATE users SET password_hash=?, token_version=token_version+1, last_seen_at=? WHERE id=?',
                            (pw_hash, iso_now(), rec['user_id']),
                        )
                        u = c.execute('SELECT id, email FROM users WHERE id=?', (rec['user_id'],)).fetchone()
                        if u:
                            self._audit(c, {'id': u['id'], 'email': u['email']}, 'user.password_reset', 'user', u['id'], {})
        if err_to_raise is not None:
            raise err_to_raise

    # ---------------- Admin Methods ----------------

    def admin_overview(self) -> dict:
        now = iso_now()
        with self.connect() as c:
            total_users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            pro_users = c.execute(
                "SELECT COUNT(*) FROM users WHERE plan IN ('pro','family','lifetime') AND role='user' AND (expires_at='' OR expires_at > ?)",
                (now,),
            ).fetchone()[0]
            trial_users = c.execute(
                "SELECT COUNT(*) FROM users WHERE plan='pro' AND role='user' AND trial_ends_at!='' AND expires_at=trial_ends_at AND trial_ends_at > ?",
                (now,),
            ).fetchone()[0]
            verified_users = c.execute("SELECT COUNT(*) FROM users WHERE email_verified=1").fetchone()[0]
            suspended = c.execute("SELECT COUNT(*) FROM users WHERE status='suspended'").fetchone()[0]
            devices = c.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
            licenses = c.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]
            redeemed = c.execute('SELECT COALESCE(SUM(uses_count),0) FROM licenses').fetchone()[0]
            downloads = {r['target']: r['count'] for r in c.execute('SELECT target,count FROM download_stats')}
        return {
            'totalUsers': total_users,
            'paidUsers': pro_users,
            'trialUsers': trial_users,
            'verifiedUsers': verified_users,
            'suspendedUsers': suspended,
            'activeDevices': devices,
            'licensesCreated': licenses,
            'licensesRedeemed': redeemed,
            'downloads': downloads,
        }

    def admin_list_users(self, query: str = '', plan: str = '', status: str = '', limit: int = 100) -> list[dict]:
        where, args = ['1=1'], []
        q = str(query or '').strip().lower()
        if q:
            where.append('(LOWER(email) LIKE ? OR LOWER(display_name) LIKE ? OR id=?)')
            args.extend([f'%{q}%', f'%{q}%', q])
        clean_plan = str(plan or '').strip().lower()
        if clean_plan in LEGACY_PLAN_MAP:
            where.append('plan=?')
            args.append(normalize_plan(clean_plan))
        if status in STATUSES:
            where.append('status=?')
            args.append(status)
        with self.connect() as c:
            rows = c.execute(
                f"SELECT * FROM users WHERE {' AND '.join(where)} ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, created_at DESC LIMIT ?",
                (*args, max(1, min(200, int(limit)))),
            ).fetchall()
            out = []
            for r in rows:
                dc = c.execute('SELECT COUNT(*) FROM devices WHERE user_id=?', (r['id'],)).fetchone()[0]
                u = self._public_user(r)
                u['deviceCount'] = dc
                out.append(u)
            return out

    def admin_update_user(self, actor: dict, user_id: str, patch: dict) -> dict:
        with self.connect() as c:
            old = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not old:
                raise ValueError('Kullanıcı bulunamadı.')
            if old['id'] == actor['id'] and patch.get('status') == 'suspended':
                raise ValueError('Kendi yönetici hesabınızı askıya alamazsınız.')
            raw_plan = str(patch.get('plan', old['plan'])).strip().lower()
            if raw_plan not in LEGACY_PLAN_MAP:
                raise ValueError('Geçersiz plan.')
            plan = normalize_plan(raw_plan)
            status = str(patch.get('status', old['status'])).strip().lower()
            if status not in STATUSES:
                raise ValueError('Geçersiz hesap durumu.')
            role = str(patch.get('role', old['role'])).strip().lower()
            if role not in ROLES:
                raise ValueError('Geçersiz rol.')
            if old['id'] == actor['id'] and role != 'admin':
                raise ValueError('Kendi yönetici rolünüzü kaldıramazsınız.')

            if 'maxDevices' in patch:
                max_devices = max(1, min(50, int(patch['maxDevices'])))
            elif plan == 'normal' and normalize_plan(old['plan']) != 'normal':
                max_devices = 1
            elif plan == 'pro' and normalize_plan(old['plan']) != 'pro':
                max_devices = max(5, int(old['max_devices']))
            else:
                max_devices = max(1, min(50, int(old['max_devices'])))

            display_name = (str(patch.get('displayName', old['display_name'])).strip() or old['display_name'])[:80]
            admin_note = str(patch.get('adminNote', old['admin_note'] or ''))[:500]
            if 'expiresAt' in patch:
                expires_at = str(patch.get('expiresAt') or '').strip()[:64]
            elif patch.get('addDays'):
                days = int(patch['addDays'])
                base = _parse_iso(old['expires_at']) or utc_now()
                if base < utc_now():
                    base = utc_now()
                expires_at = (base + dt.timedelta(days=days)).isoformat()
            else:
                expires_at = old['expires_at'] or ''
            if raw_plan == 'lifetime':
                expires_at = ''

            email_verified = int(bool(patch['emailVerified'])) if 'emailVerified' in patch else int(old['email_verified'])
            verified_at = old['verified_at'] or (iso_now() if email_verified else '')
            bump_tv = 1 if (status == 'suspended' and old['status'] != 'suspended') or (role != old['role']) else 0

            c.execute(
                """UPDATE users
                   SET plan=?,status=?,role=?,max_devices=?,display_name=?,admin_note=?,expires_at=?,
                       email_verified=?,verified_at=?,token_version=token_version+?
                   WHERE id=?""",
                (plan, status, role, max_devices, display_name, admin_note, expires_at, email_verified, verified_at, bump_tv, user_id),
            )
            self._audit(c, actor, 'user.update', 'user', user_id, {
                'old': {'plan': old['plan'], 'status': old['status'], 'role': old['role'], 'maxDevices': old['max_devices']},
                'new': {'plan': plan, 'status': status, 'role': role, 'maxDevices': max_devices, 'expiresAt': expires_at},
            })
            updated = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            devs = [
                dict(d)
                for d in c.execute(
                    'SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC',
                    (user_id,),
                )
            ]
            return self._public_user(updated, devs)

    def admin_remove_device(self, actor: dict, user_id: str, device_id: str) -> None:
        with self.connect() as c:
            c.execute('DELETE FROM devices WHERE user_id=? AND device_id=?', (user_id, device_id))
            self._audit(c, actor, 'device.remove', 'device', f'{user_id}:{device_id}', {})

    def admin_create_license(self, actor: dict, plan: str = 'pro', duration_days: int = 365, max_devices: int = 5, max_uses: int = 1, note: str = '') -> dict:
        raw_plan = str(plan or 'pro').strip().lower()
        if raw_plan not in LEGACY_PLAN_MAP or normalize_plan(raw_plan) == 'normal':
            raise ValueError('Lisans planı pro olmalıdır.')
        clean_plan = 'pro'
        days = 0 if (raw_plan == 'lifetime' or int(duration_days) <= 0) else max(1, min(3650, int(duration_days)))
        devs = max(1, min(50, int(max_devices)))
        uses = max(1, min(10000, int(max_uses)))
        raw = secrets.token_hex(6).upper()
        code = f'MAVIE-{raw[:4]}-{raw[4:8]}-{raw[8:12]}'
        now = iso_now()
        with self.connect() as c:
            c.execute('INSERT INTO licenses VALUES(?,?,?,?,?,?,?,?,?)', (code, clean_plan, days, devs, uses, 0, str(note or '')[:200], actor['email'], now))
            self._audit(c, actor, 'license.create', 'license', code, {'plan': clean_plan, 'durationDays': days, 'maxUses': uses})
        return {'code': code, 'plan': clean_plan, 'durationDays': days, 'maxDevices': devs, 'maxUses': uses, 'usesCount': 0, 'note': note, 'createdAt': now}

    def admin_list_licenses(self) -> list[dict]:
        with self.connect() as c:
            rows = c.execute('SELECT * FROM licenses ORDER BY created_at DESC LIMIT 200').fetchall()
            return [
                {
                    'code': r['code'],
                    'plan': normalize_plan(r['plan']),
                    'durationDays': r['duration_days'],
                    'maxDevices': r['max_devices'],
                    'maxUses': r['max_uses'],
                    'usesCount': r['uses_count'],
                    'note': r['note'],
                    'createdBy': r['created_by'],
                    'createdAt': r['created_at'],
                }
                for r in rows
            ]

    def admin_delete_license(self, actor: dict, code: str) -> None:
        clean = str(code or '').strip().upper()
        with self.connect() as c:
            c.execute('DELETE FROM licenses WHERE code=?', (clean,))
            self._audit(c, actor, 'license.delete', 'license', clean, {})

    def get_public_config(self) -> dict:
        with self.connect() as c:
            ann = json.loads(c.execute("SELECT value FROM app_config WHERE key='announcement'").fetchone()[0])
            vers = json.loads(c.execute("SELECT value FROM app_config WHERE key='versions'").fetchone()[0])
            downloads = {r['target']: r['count'] for r in c.execute('SELECT target,count FROM download_stats')}
        merged_vers = dict(DEFAULT_VERSIONS)
        if isinstance(vers, dict):
            merged_vers.update(vers)
        return {
            'announcement': ann,
            'versions': merged_vers,
            'downloads': downloads,
            'plans': PLAN_CATALOG,
        }

    def update_config(self, actor: dict, payload: dict) -> dict:
        current = self.get_public_config()
        ann = current['announcement']
        vers = current['versions']
        if 'announcement' in payload and isinstance(payload['announcement'], dict):
            a = payload['announcement']
            ann = {
                'enabled': bool(a.get('enabled', ann['enabled'])),
                'title': str(a.get('title', ann['title']))[:120],
                'message': str(a.get('message', ann['message']))[:500],
                'severity': a.get('severity') if a.get('severity') in ('info', 'warning', 'critical') else 'info',
            }
        if 'versions' in payload and isinstance(payload['versions'], dict):
            v = payload['versions']
            allowed_keys = (
                'latestVersion',
                'windowsLatest', 'windowsMin',
                'androidLatest', 'androidMin',
                'macosLatest', 'macosMin',
                'iosLatest', 'iosMin',
                'windowsInstallerUrl', 'windowsPortableUrl', 'androidApkUrl', 'macosUrl', 'iosUrl',
                'releaseNotes',
            )
            for k in allowed_keys:
                if k in v and isinstance(v[k], str):
                    val = v[k].strip()[:500]
                    if 'Url' in k and val and not re.match(r'^https?://|^/', val):
                        raise ValueError('İndirme bağlantısı geçerli bir adres olmalıdır.')
                    vers[k] = val
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO app_config VALUES('announcement',?)", (json.dumps(ann, ensure_ascii=False),))
            c.execute("INSERT OR REPLACE INTO app_config VALUES('versions',?)", (json.dumps(vers, ensure_ascii=False),))
            self._audit(c, actor, 'config.update', 'app_config', 'global', {'announcementEnabled': ann['enabled']})
        return self.get_public_config()

    def track_download(self, target: str) -> dict:
        clean = str(target or '').strip().lower()
        if clean not in DOWNLOAD_TARGETS:
            raise ValueError('Geçersiz indirme hedefi.')
        with self.connect() as c:
            c.execute('UPDATE download_stats SET count=count+1, updated_at=? WHERE target=?', (iso_now(), clean))
            cnt = c.execute('SELECT count FROM download_stats WHERE target=?', (clean,)).fetchone()[0]
        return {'target': clean, 'count': cnt}

    def admin_audit_logs(self, limit: int = 80) -> list[dict]:
        with self.connect() as c:
            rows = c.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?', (max(1, min(300, int(limit))),)).fetchall()
            return [
                {
                    'id': r['id'],
                    'actorEmail': r['actor_email'],
                    'action': r['action'],
                    'targetType': r['target_type'],
                    'targetId': r['target_id'],
                    'details': json.loads(r['details']),
                    'createdAt': r['created_at'],
                }
                for r in rows
            ]


def make_handler(service: CloudService, cors_origin: str = ''):
    class CloudHandler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def _client_ip(self) -> str:
            return self.client_address[0]

        def _json(self, payload, status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cache-Control', 'no-store')
            if cors_origin:
                self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS')
            self.end_headers()
            self.wfile.write(raw)

        def _send_api_error(self, err: ApiError) -> None:
            payload = {'error': err.message}
            if err.code:
                payload['code'] = err.code
            if err.extra:
                payload.update(err.extra)
            self._json(payload, err.status)

        def _read_json(self) -> dict:
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except (TypeError, ValueError):
                raise ValueError('Geçersiz Content-Length başlığı.')
            if length > MAX_JSON:
                raise ValueError('İstek boyutu çok büyük.')
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError('JSON gövdesi okunamadı.')
            if not isinstance(data, dict):
                raise ValueError('JSON nesnesi bekleniyor.')
            return data

        def _bearer_user(self) -> dict | None:
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                return None
            return service.verify_token(auth[7:].strip())

        def _require_user(self) -> dict | None:
            u = self._bearer_user()
            if not u:
                self._json({'error': 'Oturum açmanız gerekiyor.'}, 401)
                return None
            if u['status'] != 'active':
                self._json({'error': 'Hesabınız askıya alınmış.', 'code': 'ACCOUNT_SUSPENDED'}, 403)
                return None
            if not u.get('emailVerified'):
                self._json(
                    {
                        'error': 'E-posta doğrulaması gerekli.',
                        'code': 'EMAIL_NOT_VERIFIED',
                        'verificationRequired': True,
                        'email': u['email'],
                    },
                    403,
                )
                return None
            return u

        def _require_admin(self) -> dict | None:
            u = self._require_user()
            if not u:
                return None
            if u['role'] != 'admin':
                self._json({'error': 'Bu işlem için yönetici yetkisi gerekli.'}, 403)
                return None
            return u

        def _serve_static(self, rel_path: str, extra_headers: dict | None = None) -> None:
            website_root = WEBSITE.resolve()
            clean_rel = rel_path.lstrip('/').replace('\\', '/')
            parts = [p for p in clean_rel.split('/') if p]
            blocked_names = {'netlify.toml', 'package.json', 'package-lock.json'}
            if (
                not parts
                or any(p.startswith('.') or p in ('..', 'netlify', 'node_modules') for p in parts)
                or parts[-1].lower() in blocked_names
            ):
                self._json({'error': 'Sayfa bulunamadı.'}, 404)
                return
            target = (WEBSITE / clean_rel).resolve()
            if not target.is_relative_to(website_root) or not target.is_file():
                self._json({'error': 'Sayfa bulunamadı.'}, 404)
                return
            if target.name.lower() == 'admin.html' and not self._has_admin_gate():
                self._json({'error': 'Sayfa bulunamadı.'}, 404)
                return
            raw = target.read_bytes()
            ctype = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            if ctype.startswith('text/'):
                ctype += '; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
            self.send_header(
                'Content-Security-Policy',
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
            for k, v in (extra_headers or {}).items():
                self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(raw)

        def _has_admin_gate(self) -> bool:
            if not service.admin_gate_key:
                return True
            hdr = self.headers.get('X-Admin-Gate', '').strip()
            if hdr and hmac.compare_digest(hdr, service.admin_gate_key):
                return True
            try:
                cookies = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
                for cookie_name in ('mavie_admin_gate', 'cineva_admin_gate'):
                    gate = cookies.get(cookie_name)
                    if gate and service.verify_gate_cookie(gate.value):
                        return True
            except http.cookies.CookieError:
                pass
            return False

        def do_OPTIONS(self):
            self.send_response(204)
            if cors_origin:
                self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS')
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            p = urllib.parse.unquote(u.path)
            q = urllib.parse.parse_qs(u.query)
            try:
                if p == '/api/v1/health':
                    return self._json({'ok': True, 'service': 'mavie-cloud'})
                if p in ('/api/v1/app-config', '/api/v1/downloads'):
                    return self._json(service.get_public_config())
                if p == '/api/v1/me':
                    user = self._require_user()
                    if not user:
                        return
                    return self._json({'user': service.get_user_by_id(user['id'], include_devices=True)})
                if p == '/api/v1/sync':
                    user = self._require_user()
                    if not user:
                        return
                    if user['effectivePlan'] != 'pro':
                        return self._json(
                            {'error': 'Bu özellik Pro plan gerektirir.', 'code': 'PRO_REQUIRED', 'upgradeRequired': True},
                            403,
                        )
                    return self._json(service.get_sync_state(user['id']))
                if p.startswith('/api/v1/admin/'):
                    if not self._has_admin_gate():
                        return self._json({'error': 'Sayfa bulunamadı.'}, 404)
                    admin = self._require_admin()
                    if not admin:
                        return
                    if p == '/api/v1/admin/overview':
                        return self._json(service.admin_overview())
                    if p == '/api/v1/admin/users':
                        return self._json({'users': service.admin_list_users(q.get('q', [''])[0], q.get('plan', [''])[0], q.get('status', [''])[0])})
                    if p.startswith('/api/v1/admin/users/'):
                        uid = p[len('/api/v1/admin/users/'):]
                        found = service.get_user_by_id(uid, include_devices=True)
                        if not found:
                            return self._json({'error': 'Kullanıcı bulunamadı.'}, 404)
                        return self._json({'user': found})
                    if p == '/api/v1/admin/licenses':
                        return self._json({'licenses': service.admin_list_licenses()})
                    if p == '/api/v1/admin/config':
                        return self._json(service.get_public_config())
                    if p == '/api/v1/admin/audit':
                        return self._json({'logs': service.admin_audit_logs()})
                    return self._json({'error': 'Bilinmeyen yönetim uç noktası.'}, 404)

                # Static website routes
                if p in ('/', '/index.html'):
                    return self._serve_static('index.html')
                if p.lower() in ('/admin', '/admin/', '/admin.html'):
                    if service.admin_gate_key:
                        access = q.get('access', [''])[0].strip()
                        if access and hmac.compare_digest(access, service.admin_gate_key):
                            cookie_val = service.sign_gate_cookie()
                            self.send_response(302)
                            self.send_header('Location', '/admin')
                            self.send_header('Set-Cookie', f'mavie_admin_gate={cookie_val}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200')
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('X-Robots-Tag', 'noindex, nofollow')
                            self.send_header('Content-Length', '0')
                            self.end_headers()
                            return
                        if not self._has_admin_gate():
                            return self._json({'error': 'Sayfa bulunamadı.'}, 404)
                    return self._serve_static('admin.html', {'X-Robots-Tag': 'noindex, nofollow', 'Cache-Control': 'no-store'})
                if p == '/privacy':
                    return self._serve_static('privacy.html')
                if p == '/terms':
                    return self._serve_static('terms.html')
                return self._serve_static(p)
            except ApiError as err:
                self._send_api_error(err)
            except Exception as err:
                self._json({'error': str(err)}, 400 if isinstance(err, ValueError) else 500)

        def do_POST(self):
            self._handle_mutation('POST')

        def do_PATCH(self):
            self._handle_mutation('PATCH')

        def do_PUT(self):
            self._handle_mutation('PUT')

        def do_DELETE(self):
            self._handle_mutation('DELETE')

        def _handle_mutation(self, method: str) -> None:
            p = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            try:
                body = self._read_json() if method in ('POST', 'PATCH', 'PUT') else {}
                if p == '/api/v1/downloads/track' and method == 'POST':
                    return self._json(service.track_download(body.get('target') or body.get('platform', '')))
                if p == '/api/v1/auth/register' and method == 'POST':
                    if not service.check_rate_limit('reg:' + self._client_ip(), limit=10):
                        return self._json({'error': 'Çok fazla kayıt denemesi. Lütfen bekleyin.'}, 429)
                    return self._json(service.register(body.get('email', ''), body.get('password', ''), body.get('displayName', '')), 201)
                if p == '/api/v1/auth/verify-email' and method == 'POST':
                    if not service.check_rate_limit('verify:' + self._client_ip(), limit=15):
                        return self._json({'error': 'Çok fazla doğrulama denemesi. Lütfen bekleyin.'}, 429)
                    return self._json(
                        service.verify_email(
                            email=body.get('email', ''),
                            code=body.get('code', ''),
                            token=body.get('token', ''),
                        )
                    )
                if p == '/api/v1/auth/resend-verification' and method == 'POST':
                    clean_em = str(body.get('email', '')).strip().lower()
                    if not service.check_rate_limit('resend:' + self._client_ip(), limit=6) or (
                        clean_em and not service.check_rate_limit('resend_email:' + clean_em, limit=3)
                    ):
                        return self._json({'error': 'Çok fazla kod isteği. Lütfen daha sonra tekrar deneyin.'}, 429)
                    return self._json(service.resend_verification(clean_em))
                if p == '/api/v1/auth/login' and method == 'POST':
                    ip = self._client_ip()
                    clean_em = str(body.get('email', '')).strip().lower()
                    ip_bucket = 'login_ip:' + ip
                    acct_bucket = f'login:{ip}:{clean_em}' if clean_em else ip_bucket
                    if service.is_rate_limited(ip_bucket, limit=30) or service.is_rate_limited(acct_bucket, limit=12):
                        return self._json({'error': 'Çok fazla hatalı giriş denemesi. 5 dakika bekleyin.'}, 429)
                    try:
                        res = service.login(body.get('email', ''), body.get('password', ''))
                    except ApiError:
                        service.record_rate_limit(ip_bucket)
                        if acct_bucket != ip_bucket:
                            service.record_rate_limit(acct_bucket)
                        raise
                    if acct_bucket != ip_bucket:
                        service.clear_rate_limit(acct_bucket)
                    return self._json(res)
                if p == '/api/v1/auth/forgot-password' and method == 'POST':
                    clean_em = str(body.get('email', '')).strip().lower()
                    if not service.check_rate_limit('forgot:' + self._client_ip(), limit=6) or (
                        clean_em and not service.check_rate_limit('forgot_email:' + clean_em, limit=3)
                    ):
                        return self._json({'error': 'Çok fazla sıfırlama isteği. Lütfen bekleyin.'}, 429)
                    return self._json(service.forgot_password(clean_em))
                if p == '/api/v1/auth/verify-reset-code' and method == 'POST':
                    if not service.check_rate_limit('reset:' + self._client_ip(), limit=12):
                        return self._json({'error': 'Çok fazla deneme. Lütfen bekleyin.'}, 429)
                    return self._json(
                        service.verify_reset_code(
                            email=body.get('email', ''),
                            code=body.get('code', ''),
                            token=body.get('token', ''),
                        )
                    )
                if p == '/api/v1/auth/reset-password' and method == 'POST':
                    if not service.check_rate_limit('reset:' + self._client_ip(), limit=12):
                        return self._json({'error': 'Çok fazla deneme. Lütfen bekleyin.'}, 429)
                    service.complete_password_reset(
                        body.get('token', ''),
                        body.get('newPassword', ''),
                        email=body.get('email', ''),
                        code=body.get('code', ''),
                    )
                    return self._json({'ok': True})
                if p == '/api/v1/devices/register' and method == 'POST':
                    user = self._require_user()
                    if not user:
                        return
                    devs = service.register_device(user, body.get('deviceId', ''), body.get('deviceName', ''), body.get('platform', 'web'))
                    return self._json({'devices': devs})
                if p.startswith('/api/v1/devices/') and method == 'DELETE':
                    user = self._require_user()
                    if not user:
                        return
                    did = p[len('/api/v1/devices/'):].strip()
                    devs = service.remove_user_device(user['id'], did)
                    return self._json({'ok': True, 'devices': devs})
                if p == '/api/v1/sync' and method in ('PUT', 'POST'):
                    user = self._require_user()
                    if not user:
                        return
                    if user['effectivePlan'] != 'pro':
                        return self._json(
                            {'error': 'Bu özellik Pro plan gerektirir.', 'code': 'PRO_REQUIRED', 'upgradeRequired': True},
                            403,
                        )
                    return self._json(service.put_sync_state(user['id'], body))
                if p == '/api/v1/licenses/redeem' and method == 'POST':
                    user = self._require_user()
                    if not user:
                        return
                    updated = service.redeem_license(user, body.get('code', ''))
                    return self._json({'ok': True, 'user': updated})
                if p.startswith('/api/v1/admin/'):
                    if not self._has_admin_gate():
                        return self._json({'error': 'Sayfa bulunamadı.'}, 404)
                    admin = self._require_admin()
                    if not admin:
                        return
                    if p.startswith('/api/v1/admin/users/') and p.endswith('/reset-password-token') and method == 'POST':
                        uid = p[len('/api/v1/admin/users/'):-len('/reset-password-token')]
                        return self._json({'resetToken': service.create_reset_token(admin, uid)})
                    if '/devices/' in p and p.startswith('/api/v1/admin/users/') and method == 'DELETE':
                        tail = p[len('/api/v1/admin/users/'):]
                        uid, did = tail.split('/devices/', 1)
                        service.admin_remove_device(admin, uid, did)
                        return self._json({'ok': True})
                    if p.startswith('/api/v1/admin/users/') and method == 'PATCH':
                        uid = p[len('/api/v1/admin/users/'):]
                        return self._json({'user': service.admin_update_user(admin, uid, body)})
                    if p == '/api/v1/admin/licenses' and method == 'POST':
                        lic = service.admin_create_license(
                            admin, body.get('plan', 'pro'), body.get('durationDays', 365),
                            body.get('maxDevices', 5), body.get('maxUses', 1), body.get('note', ''),
                        )
                        return self._json({'license': lic}, 201)
                    if p.startswith('/api/v1/admin/licenses/') and method == 'DELETE':
                        service.admin_delete_license(admin, p[len('/api/v1/admin/licenses/'):])
                        return self._json({'ok': True})
                    if p == '/api/v1/admin/config' and method in ('PUT', 'PATCH'):
                        return self._json(service.update_config(admin, body))
                return self._json({'error': 'Uç nokta bulunamadı.'}, 404)
            except ApiError as err:
                self._send_api_error(err)
            except PermissionError as err:
                self._json({'error': str(err)}, 403)
            except ValueError as err:
                self._json({'error': str(err)}, 400)
            except Exception as err:
                self._json({'error': str(err)}, 500)

    return CloudHandler


def main() -> int:
    parser = argparse.ArgumentParser(description='Mavie Bulut Hesap & Yönetim Paneli Sunucusu')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(_env_first('MAVIE_CLOUD_PORT', 'CINEVA_CLOUD_PORT', default='8899')))
    parser.add_argument('--data-dir', default=_env_first('MAVIE_CLOUD_DATA_DIR', 'CINEVA_CLOUD_DATA_DIR') or str(ROOT / 'cloud_data'))
    args = parser.parse_args()

    admin_email = _env_first('MAVIE_ADMIN_EMAIL', 'CINEVA_ADMIN_EMAIL', default='admin@mavie.app')
    service = CloudService(
        Path(args.data_dir),
        secret_key=_env_first('MAVIE_CLOUD_SECRET', 'CINEVA_CLOUD_SECRET'),
        admin_email=admin_email,
        admin_password=_env_first('MAVIE_ADMIN_PASSWORD', 'CINEVA_ADMIN_PASSWORD'),
        admin_gate_key=_env_first('MAVIE_ADMIN_GATE_KEY', 'CINEVA_ADMIN_GATE_KEY', default='__auto__'),
    )
    cors_origin = _env_first('MAVIE_CORS_ORIGIN', 'CINEVA_CORS_ORIGIN')
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service, cors_origin))
    server.daemon_threads = True

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f'Mavie Portal hazır: http://{args.host}:{args.port}/', flush=True)
    if service.admin_gate_key:
        print(f'Gizli Yönetim Paneli Bağlantısı: http://{args.host}:{args.port}/admin?access={service.admin_gate_key}', flush=True)
    else:
        print(f'Admin Paneli: http://{args.host}:{args.port}/admin', flush=True)
    if service.bootstrap_admin_password:
        print(f'[İLK KURULUM] Yönetici E-posta: {admin_email} | Geçici Parola: {service.bootstrap_admin_password}', flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
