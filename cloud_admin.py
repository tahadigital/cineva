#!/usr/bin/env python3
"""Cineva Control Plane & Admin Backend.

Zero-knowledge account, subscription/plan, license key, device limit,
download counter, and remote app-config service. Intentionally NEVER stores
user IPTV credentials, M3U URLs, or watch history.
"""
from __future__ import annotations

import argparse
import base64
import collections
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import signal
import sqlite3
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBSITE = ROOT / 'website'
MAX_JSON = 512 * 1024
PLANS = ('free', 'pro', 'family', 'lifetime')
STATUSES = ('active', 'suspended')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$')


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class _DBConn(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class CloudService:
    """Thread-safe SQLite-backed control plane for accounts, licenses, devices, and admin actions."""

    def __init__(
        self,
        data_dir: Path,
        *,
        secret_key: str = '',
        admin_email: str = '',
        admin_password: str = '',
    ):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.data_dir, 0o700)
        self.db_path = self.data_dir / 'cloud.sqlite3'
        self.secret = self._load_or_create_secret(secret_key)
        self._lock = threading.Lock()
        self._rate_limits: dict[str, list[float]] = collections.defaultdict(list)
        self._init_schema()
        self.bootstrap_admin_password: str | None = self._ensure_admin(admin_email, admin_password)

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
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'active',
                    max_devices INTEGER NOT NULL DEFAULT 2,
                    expires_at TEXT DEFAULT '',
                    admin_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
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
                CREATE TABLE IF NOT EXISTS password_resets(
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
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
            """)
            defaults = {
                'announcement': json.dumps({
                    'enabled': False,
                    'title': '',
                    'message': '',
                    'severity': 'info',
                }),
                'versions': json.dumps({
                    'windowsLatest': '2.0.0',
                    'windowsMin': '2.0.0',
                    'androidLatest': '2.0.0',
                    'androidMin': '2.0.0',
                    'windowsInstallerUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Setup.exe',
                    'windowsPortableUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva.exe',
                    'androidApkUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Android.apk',
                }),
            }
            for k, v in defaults.items():
                c.execute('INSERT OR IGNORE INTO app_config VALUES(?,?)', (k, v))
            for target in ('windows-installer', 'windows-portable', 'android-apk', 'macos'):
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

    def _ensure_admin(self, admin_email: str, admin_password: str) -> str | None:
        with self.connect() as c:
            existing = c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
            if existing:
                return None
        email = (admin_email or 'admin@cineva.app').strip().lower()
        if not EMAIL_RE.fullmatch(email):
            email = 'admin@cineva.app'
        generated = None
        pwd = admin_password.strip()
        if not pwd:
            generated = secrets.token_urlsafe(14)
            pwd = generated
        pw_hash = self._hash_password(pwd)
        now = iso_now()
        with self.connect() as c:
            c.execute(
                'INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('usr_admin_' + secrets.token_hex(6), email, 'Yönetici', pw_hash, 'admin', 'lifetime', 'active', 10, '', 'Sistem yöneticisi', now, now),
            )
        return generated

    def check_rate_limit(self, bucket: str, limit: int = 12, window_s: float = 300.0) -> bool:
        now = time.monotonic()
        with self._lock:
            entries = [t for t in self._rate_limits[bucket] if t > now - window_s]
            self._rate_limits[bucket] = entries
            if len(entries) >= limit:
                return False
            entries.append(now)
            return True

    def clear_rate_limit(self, bucket: str) -> None:
        with self._lock:
            self._rate_limits.pop(bucket, None)

    def _issue_token(self, user_id: str, role: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
        payload = json.dumps({
            'sub': user_id,
            'role': role,
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
            user = self.get_user_by_id(claims['sub'])
            if not user:
                return None
            return user
        except Exception:
            return None

    @staticmethod
    def _effective_plan(plan: str, expires_at: str) -> str:
        if plan in ('free', 'lifetime') or not expires_at:
            return plan
        try:
            exp = dt.datetime.fromisoformat(expires_at)
            if exp < utc_now():
                return 'free'
        except ValueError:
            pass
        return plan

    @classmethod
    def _public_user(cls, row: sqlite3.Row, devices: list[dict] | None = None) -> dict:
        expires_at = row['expires_at'] or ''
        out = {
            'id': row['id'],
            'email': row['email'],
            'displayName': row['display_name'],
            'role': row['role'],
            'plan': row['plan'],
            'effectivePlan': cls._effective_plan(row['plan'], expires_at),
            'status': row['status'],
            'maxDevices': row['max_devices'],
            'expiresAt': expires_at,
            'adminNote': row['admin_note'] or '',
            'createdAt': row['created_at'],
            'lastSeenAt': row['last_seen_at'],
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
                devs = [dict(d) for d in c.execute('SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC', (user_id,))]
            return self._public_user(row, devs)

    def _audit(self, c: sqlite3.Connection, actor: dict, action: str, target_type: str, target_id: str, details: dict) -> None:
        c.execute(
            'INSERT INTO audit_logs(actor_id,actor_email,action,target_type,target_id,details,created_at) VALUES(?,?,?,?,?,?,?)',
            (actor['id'], actor['email'], action, target_type, target_id, json.dumps(details, ensure_ascii=False), iso_now()),
        )

    def register(self, email: str, password: str, display_name: str = '') -> dict:
        clean_email = str(email or '').strip().lower()
        if not EMAIL_RE.fullmatch(clean_email):
            raise ValueError('Geçerli bir e-posta adresi girin.')
        name = (str(display_name or '').strip() or clean_email.split('@', 1)[0])[:80]
        pw_hash = self._hash_password(password)
        uid = 'usr_' + secrets.token_hex(8)
        now = iso_now()
        try:
            with self.connect() as c:
                c.execute(
                    'INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uid, clean_email, name, pw_hash, 'user', 'free', 'active', 2, '', '', now, now),
                )
                row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        except sqlite3.IntegrityError:
            raise ValueError('Bu e-posta adresi zaten kayıtlı.')
        return {'token': self._issue_token(uid, 'user'), 'user': self._public_user(row)}

    def login(self, email: str, password: str) -> dict:
        clean_email = str(email or '').strip().lower()
        with self.connect() as c:
            row = c.execute('SELECT * FROM users WHERE email=?', (clean_email,)).fetchone()
            if not row or not self._verify_password(password, row['password_hash']):
                raise PermissionError('E-posta veya parola hatalı.')
            if row['status'] != 'active':
                raise PermissionError('Hesabınız askıya alınmış. Destek ile iletişime geçin.')
            c.execute('UPDATE users SET last_seen_at=? WHERE id=?', (iso_now(), row['id']))
            row = c.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            devs = [dict(d) for d in c.execute('SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=?', (row['id'],))]
        return {'token': self._issue_token(row['id'], row['role']), 'user': self._public_user(row, devs)}

    def register_device(self, user: dict, device_id: str, device_name: str, platform: str) -> list[dict]:
        did = str(device_id or '').strip()[:80]
        if not did:
            raise ValueError('Cihaz kimliği gerekli.')
        dname = (str(device_name or 'Cihaz').strip() or 'Cihaz')[:80]
        plat = (str(platform or 'web').strip().lower() or 'web')[:24]
        now = iso_now()
        with self.connect() as c:
            existing = c.execute('SELECT device_id FROM devices WHERE user_id=? AND device_id=?', (user['id'], did)).fetchone()
            if not existing:
                count = c.execute('SELECT COUNT(*) FROM devices WHERE user_id=?', (user['id'],)).fetchone()[0]
                if count >= user['maxDevices']:
                    raise ValueError(f"Maksimum cihaz sınırına ({user['maxDevices']}) ulaşıldı. Plan yükseltin veya eski bir cihazı kaldırın.")
            c.execute('INSERT OR REPLACE INTO devices VALUES(?,?,?,?,?)', (user['id'], did, dname, plat, now))
            c.execute('UPDATE users SET last_seen_at=? WHERE id=?', (now, user['id']))
            return [dict(d) for d in c.execute('SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=? ORDER BY last_seen_at DESC', (user['id'],))]

    def redeem_license(self, user: dict, raw_code: str) -> dict:
        code = str(raw_code or '').strip().upper()
        if not code:
            raise ValueError('Lisans anahtarı boş olamaz.')
        with self.connect() as c:
            lic = c.execute('SELECT * FROM licenses WHERE code=?', (code,)).fetchone()
            if not lic:
                raise ValueError('Lisans anahtarı bulunamadı.')
            if lic['uses_count'] >= lic['max_uses']:
                raise ValueError('Bu lisans anahtarının kullanım limiti dolmuş.')
            already = c.execute('SELECT 1 FROM license_redemptions WHERE code=? AND user_id=?', (code, user['id'])).fetchone()
            if already:
                raise ValueError('Bu lisans anahtarı bu hesapta zaten kullanıldı.')
            now_dt = utc_now()
            expires = '' if lic['plan'] == 'lifetime' or lic['duration_days'] <= 0 else (now_dt + dt.timedelta(days=lic['duration_days'])).isoformat()
            c.execute('UPDATE licenses SET uses_count=uses_count+1 WHERE code=?', (code,))
            c.execute('INSERT INTO license_redemptions VALUES(?,?,?)', (code, user['id'], now_dt.isoformat()))
            c.execute(
                'UPDATE users SET plan=?,max_devices=?,expires_at=?,last_seen_at=? WHERE id=?',
                (lic['plan'], max(user['maxDevices'], lic['max_devices']), expires, now_dt.isoformat(), user['id']),
            )
            self._audit(c, user, 'license.redeem', 'license', code, {'plan': lic['plan'], 'expiresAt': expires})
            row = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            return self._public_user(row)

    def create_reset_token(self, actor: dict, user_id: str) -> str:
        raw_token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        expires = (utc_now() + dt.timedelta(hours=1)).isoformat()
        with self.connect() as c:
            row = c.execute('SELECT id,email FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise ValueError('Kullanıcı bulunamadı.')
            c.execute('INSERT INTO password_resets VALUES(?,?,?,0)', (token_hash, user_id, expires))
            self._audit(c, actor, 'user.reset_token', 'user', user_id, {'email': row['email']})
        return raw_token

    def complete_password_reset(self, raw_token: str, new_password: str) -> None:
        token_hash = hashlib.sha256(str(raw_token or '').strip().encode('utf-8')).hexdigest()
        pw_hash = self._hash_password(new_password)
        with self.connect() as c:
            row = c.execute('SELECT * FROM password_resets WHERE token_hash=? AND used=0', (token_hash,)).fetchone()
            if not row:
                raise ValueError('Sıfırlama bağlantısı geçersiz veya kullanılmış.')
            if dt.datetime.fromisoformat(row['expires_at']) < utc_now():
                raise ValueError('Sıfırlama bağlantısının süresi dolmuş.')
            c.execute('UPDATE users SET password_hash=? WHERE id=?', (pw_hash, row['user_id']))
            c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?', (token_hash,))

    # ---------------- Admin Methods ----------------

    def admin_overview(self) -> dict:
        with self.connect() as c:
            total_users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            pro_users = c.execute("SELECT COUNT(*) FROM users WHERE plan IN ('pro','family','lifetime') AND role='user'").fetchone()[0]
            suspended = c.execute("SELECT COUNT(*) FROM users WHERE status='suspended'").fetchone()[0]
            devices = c.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
            licenses = c.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]
            redeemed = c.execute('SELECT COALESCE(SUM(uses_count),0) FROM licenses').fetchone()[0]
            downloads = {r['target']: r['count'] for r in c.execute('SELECT target,count FROM download_stats')}
        return {
            'totalUsers': total_users,
            'paidUsers': pro_users,
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
        if plan in PLANS:
            where.append('plan=?')
            args.append(plan)
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
            plan = str(patch.get('plan', old['plan'])).strip().lower()
            if plan not in PLANS:
                raise ValueError('Geçersiz plan.')
            status = str(patch.get('status', old['status'])).strip().lower()
            if status not in STATUSES:
                raise ValueError('Geçersiz hesap durumu.')
            max_devices = max(1, min(50, int(patch.get('maxDevices', old['max_devices']))))
            display_name = (str(patch.get('displayName', old['display_name'])).strip() or old['display_name'])[:80]
            admin_note = str(patch.get('adminNote', old['admin_note'] or ''))[:500]
            if 'expiresAt' in patch:
                expires_at = str(patch.get('expiresAt') or '').strip()[:64]
            elif patch.get('addDays'):
                days = int(patch['addDays'])
                base = dt.datetime.fromisoformat(old['expires_at']) if old['expires_at'] else utc_now()
                if base < utc_now():
                    base = utc_now()
                expires_at = (base + dt.timedelta(days=days)).isoformat()
            else:
                expires_at = old['expires_at'] or ''
            if plan == 'lifetime':
                expires_at = ''
            c.execute(
                'UPDATE users SET plan=?,status=?,max_devices=?,display_name=?,admin_note=?,expires_at=? WHERE id=?',
                (plan, status, max_devices, display_name, admin_note, expires_at, user_id),
            )
            self._audit(c, actor, 'user.update', 'user', user_id, {
                'old': {'plan': old['plan'], 'status': old['status'], 'maxDevices': old['max_devices']},
                'new': {'plan': plan, 'status': status, 'maxDevices': max_devices, 'expiresAt': expires_at},
            })
            updated = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            devs = [dict(d) for d in c.execute('SELECT device_id AS id,device_name AS name,platform,last_seen_at AS lastSeenAt FROM devices WHERE user_id=?', (user_id,))]
            return self._public_user(updated, devs)

    def admin_remove_device(self, actor: dict, user_id: str, device_id: str) -> None:
        with self.connect() as c:
            c.execute('DELETE FROM devices WHERE user_id=? AND device_id=?', (user_id, device_id))
            self._audit(c, actor, 'device.remove', 'device', f'{user_id}:{device_id}', {})

    def admin_create_license(self, actor: dict, plan: str = 'pro', duration_days: int = 365, max_devices: int = 5, max_uses: int = 1, note: str = '') -> dict:
        clean_plan = str(plan or 'pro').strip().lower()
        if clean_plan not in PLANS or clean_plan == 'free':
            raise ValueError('Lisans planı pro, family veya lifetime olmalıdır.')
        days = 0 if clean_plan == 'lifetime' else max(1, min(3650, int(duration_days)))
        devs = max(1, min(50, int(max_devices)))
        uses = max(1, min(10000, int(max_uses)))
        raw = secrets.token_hex(6).upper()
        code = f'CINEVA-{raw[:4]}-{raw[4:8]}-{raw[8:12]}'
        now = iso_now()
        with self.connect() as c:
            c.execute('INSERT INTO licenses VALUES(?,?,?,?,?,?,?,?,?)', (code, clean_plan, days, devs, uses, 0, str(note or '')[:200], actor['email'], now))
            self._audit(c, actor, 'license.create', 'license', code, {'plan': clean_plan, 'durationDays': days, 'maxUses': uses})
        return {'code': code, 'plan': clean_plan, 'durationDays': days, 'maxDevices': devs, 'maxUses': uses, 'usesCount': 0, 'note': note, 'createdAt': now}

    def admin_list_licenses(self) -> list[dict]:
        with self.connect() as c:
            rows = c.execute('SELECT * FROM licenses ORDER BY created_at DESC LIMIT 200').fetchall()
            return [{'code': r['code'], 'plan': r['plan'], 'durationDays': r['duration_days'], 'maxDevices': r['max_devices'], 'maxUses': r['max_uses'], 'usesCount': r['uses_count'], 'note': r['note'], 'createdBy': r['created_by'], 'createdAt': r['created_at']} for r in rows]

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
        return {'announcement': ann, 'versions': vers, 'downloads': downloads}

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
            for k in ('windowsLatest', 'windowsMin', 'androidLatest', 'androidMin', 'windowsInstallerUrl', 'windowsPortableUrl', 'androidApkUrl'):
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
        if clean not in ('windows-installer', 'windows-portable', 'android-apk', 'macos'):
            raise ValueError('Geçersiz indirme hedefi.')
        with self.connect() as c:
            c.execute('UPDATE download_stats SET count=count+1, updated_at=? WHERE target=?', (iso_now(), clean))
            cnt = c.execute('SELECT count FROM download_stats WHERE target=?', (clean,)).fetchone()[0]
        return {'target': clean, 'count': cnt}

    def admin_audit_logs(self, limit: int = 80) -> list[dict]:
        with self.connect() as c:
            rows = c.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?', (max(1, min(300, int(limit))),)).fetchall()
            return [{'id': r['id'], 'actorEmail': r['actor_email'], 'action': r['action'], 'targetType': r['target_type'], 'targetId': r['target_id'], 'details': json.loads(r['details']), 'createdAt': r['created_at']} for r in rows]


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
            self.send_header('Cache-Control', 'no-store')
            if cors_origin:
                self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS')
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict:
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_JSON:
                raise ValueError('İstek boyutu çok büyük.')
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            data = json.loads(raw.decode('utf-8'))
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
                self._json({'error': 'Hesabınız askıya alınmış.'}, 403)
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

        def _serve_static(self, rel_path: str) -> None:
            target = (WEBSITE / rel_path.lstrip('/')).resolve()
            if not target.is_relative_to(WEBSITE.resolve()) or not target.is_file():
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
            self.end_headers()
            self.wfile.write(raw)

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
                    return self._json({'ok': True, 'service': 'cineva-cloud'})
                if p in ('/api/v1/app-config', '/api/v1/downloads'):
                    return self._json(service.get_public_config())
                if p == '/api/v1/me':
                    user = self._require_user()
                    if not user:
                        return
                    return self._json({'user': service.get_user_by_id(user['id'], include_devices=True)})
                if p.startswith('/api/v1/admin/'):
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
                if p in ('/admin', '/admin/', '/admin.html'):
                    return self._serve_static('admin.html')
                if p == '/privacy':
                    return self._serve_static('privacy.html')
                if p == '/terms':
                    return self._serve_static('terms.html')
                return self._serve_static(p)
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
                    return self._json(service.track_download(body.get('target', '')))
                if p == '/api/v1/auth/register' and method == 'POST':
                    if not service.check_rate_limit('reg:' + self._client_ip(), limit=10):
                        return self._json({'error': 'Çok fazla kayıt denemesi. Lütfen bekleyin.'}, 429)
                    return self._json(service.register(body.get('email', ''), body.get('password', ''), body.get('displayName', '')), 201)
                if p == '/api/v1/auth/login' and method == 'POST':
                    bucket = 'login:' + self._client_ip()
                    if not service.check_rate_limit(bucket, limit=12):
                        return self._json({'error': 'Çok fazla hatalı giriş denemesi. 5 dakika bekleyin.'}, 429)
                    res = service.login(body.get('email', ''), body.get('password', ''))
                    service.clear_rate_limit(bucket)
                    return self._json(res)
                if p == '/api/v1/auth/reset-password' and method == 'POST':
                    service.complete_password_reset(body.get('token', ''), body.get('newPassword', ''))
                    return self._json({'ok': True})
                if p == '/api/v1/devices/register' and method == 'POST':
                    user = self._require_user()
                    if not user:
                        return
                    devs = service.register_device(user, body.get('deviceId', ''), body.get('deviceName', ''), body.get('platform', 'web'))
                    return self._json({'devices': devs})
                if p == '/api/v1/licenses/redeem' and method == 'POST':
                    user = self._require_user()
                    if not user:
                        return
                    updated = service.redeem_license(user, body.get('code', ''))
                    return self._json({'ok': True, 'user': updated})
                if p.startswith('/api/v1/admin/'):
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
            except PermissionError as err:
                self._json({'error': str(err)}, 403)
            except ValueError as err:
                self._json({'error': str(err)}, 400)
            except Exception as err:
                self._json({'error': str(err)}, 500)

    return CloudHandler


def main() -> int:
    parser = argparse.ArgumentParser(description='Cineva Bulut Hesap & Yönetim Paneli Sunucusu')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('CINEVA_CLOUD_PORT', '8899')))
    parser.add_argument('--data-dir', default=os.environ.get('CINEVA_CLOUD_DATA_DIR') or str(ROOT / 'cloud_data'))
    args = parser.parse_args()

    service = CloudService(
        Path(args.data_dir),
        secret_key=os.environ.get('CINEVA_CLOUD_SECRET', ''),
        admin_email=os.environ.get('CINEVA_ADMIN_EMAIL', ''),
        admin_password=os.environ.get('CINEVA_ADMIN_PASSWORD', ''),
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service, os.environ.get('CINEVA_CORS_ORIGIN', '')))
    server.daemon_threads = True

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f'Cineva Portal & Yönetim Paneli hazır: http://{args.host}:{args.port}/', flush=True)
    print(f'Admin Paneli: http://{args.host}:{args.port}/admin', flush=True)
    if service.bootstrap_admin_password:
        print(f'[İLK KURULUM] Yönetici E-posta: admin@cineva.app | Geçici Parola: {service.bootstrap_admin_password}', flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
