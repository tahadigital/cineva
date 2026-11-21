"""Dedicated M1 security, email verification, password reset, trial, and Normal/Pro plan gating tests."""
from __future__ import annotations

import datetime as dt
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cloud_admin


class _BaseCloudHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mavie-m1-tests-')
        self.data_dir = Path(self.temp.name)
        self.service = cloud_admin.CloudService(
            self.data_dir,
            admin_email='admin@mavie.app',
            admin_password='AdminStrongPass!2026',
            admin_gate_key='m1-gate-key',
        )
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), cloud_admin.make_handler(self.service))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.temp.cleanup()

    def req(self, method: str, path: str, body: dict | None = None, *, token: str = ''):
        headers = {'X-Admin-Gate': 'm1-gate-key'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, (json.loads(raw.decode('utf-8')) if raw else None)
        finally:
            conn.close()

    def outbox_entries(self, email: str = '', kind: str = '') -> list[dict]:
        p = self.data_dir / 'email_outbox.json'
        if not p.exists():
            return []
        entries = json.loads(p.read_text(encoding='utf-8'))
        return [
            e for e in entries
            if (not email or e['recipient'] == email.lower())
            and (not kind or e['kind'] == kind)
        ]


class EmailVerificationAndPlansTests(_BaseCloudHarness):
    def test_1_unverified_registration_outbox_and_no_secret_leak(self):
        code, reg = self.req('POST', '/api/v1/auth/register', {
            'email': 'alice@example.com',
            'password': 'AlicePassword123!',
            'displayName': 'Alice',
        })
        self.assertEqual(code, 201)
        self.assertTrue(reg['ok'])
        self.assertTrue(reg['verificationRequired'])
        self.assertFalse(reg['emailVerified'])
        self.assertEqual(reg['deliveryMode'], 'outbox')
        self.assertNotIn('token', reg)
        self.assertNotIn('code', reg)
        self.assertEqual(reg['user']['plan'], 'normal')
        self.assertEqual(reg['user']['effectivePlan'], 'normal')
        self.assertFalse(reg['user']['isPro'])
        self.assertEqual(reg['user']['maxDevices'], 1)
        self.assertFalse(reg['user']['features']['cloudSync'])

        entries = self.outbox_entries('alice@example.com', 'verify_email')
        self.assertEqual(len(entries), 1)
        mail = entries[0]
        self.assertEqual(len(mail['code']), 6)
        self.assertTrue(mail['code'].isdigit())
        self.assertTrue(len(mail['token']) >= 20)

        # Verify plaintext code & token are NOT stored in email_verifications table
        with sqlite3.connect(self.data_dir / 'cloud.sqlite3') as db:
            row = db.execute(
                'SELECT code_hash, token_hash FROM email_verifications WHERE email=?',
                ('alice@example.com',),
            ).fetchone()
            outbox_row = db.execute(
                'SELECT delivery_mode, status, code, token FROM email_outbox WHERE recipient=?',
                ('alice@example.com',),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[0], mail['code'])
        self.assertNotEqual(row[1], mail['token'])
        self.assertNotIn(mail['code'], row[0])
        self.assertEqual(outbox_row, ('outbox', 'stored', mail['code'], mail['token']))

    def test_2_unverified_account_blocked_across_login_and_verified_endpoints(self):
        _, reg = self.req('POST', '/api/v1/auth/register', {
            'email': 'bob@example.com',
            'password': 'BobPassword123!',
        })
        uid = reg['user']['id']

        c_login, login_res = self.req('POST', '/api/v1/auth/login', {
            'email': 'bob@example.com',
            'password': 'BobPassword123!',
        })
        self.assertEqual(c_login, 403)
        self.assertEqual(login_res['code'], 'EMAIL_NOT_VERIFIED')
        self.assertTrue(login_res['verificationRequired'])

        # Even with a signed token matching uid/tv, unverified accounts must be blocked on verified-only routes
        forged_tok = self.service._issue_token(uid, 'user', 1)
        for method, path, payload in (
            ('GET', '/api/v1/me', None),
            ('GET', '/api/v1/sync', None),
            ('PUT', '/api/v1/sync', {'state': {'version': 1}}),
            ('POST', '/api/v1/devices/register', {'deviceId': 'd1', 'deviceName': 'PC', 'platform': 'windows'}),
            ('DELETE', '/api/v1/devices/d1', None),
            ('POST', '/api/v1/licenses/redeem', {'code': 'MAVIE-0000-0000-0000'}),
        ):
            status, body = self.req(method, path, payload, token=forged_tok)
            self.assertEqual(status, 403, f'{method} {path} returned {status}: {body}')
            self.assertEqual(body.get('code'), 'EMAIL_NOT_VERIFIED')

    def test_3_unverified_reregistration_overwrites_without_squatting_or_trial(self):
        c1, _ = self.req('POST', '/api/v1/auth/register', {
            'email': 'squat@example.com',
            'password': 'OldPassword123!',
            'displayName': 'Squatter',
        })
        self.assertEqual(c1, 201)
        first_code = self.outbox_entries('squat@example.com', 'verify_email')[-1]['code']

        # Legitimate owner re-registers same unverified email with new password & displayName
        c2, reg2 = self.req('POST', '/api/v1/auth/register', {
            'email': 'squat@example.com',
            'password': 'RealOwnerPass123!',
            'displayName': 'Real Owner',
        })
        self.assertEqual(c2, 201)
        self.assertEqual(reg2['user']['displayName'], 'Real Owner')
        self.assertFalse(reg2['user']['trialUsed'])

        # Old code must now be invalidated
        c_old, _ = self.req('POST', '/api/v1/auth/verify-email', {
            'email': 'squat@example.com',
            'code': first_code,
        })
        self.assertEqual(c_old, 400)

        # Fresh code verifies and accepts new password (not squatter's password)
        second_code = self.outbox_entries('squat@example.com', 'verify_email')[-1]['code']
        c_ok, ver_res = self.req('POST', '/api/v1/auth/verify-email', {
            'email': 'squat@example.com',
            'code': second_code,
        })
        self.assertEqual(c_ok, 200)
        self.assertTrue(ver_res['trialActivated'])

        c_bad_pw, _ = self.req('POST', '/api/v1/auth/login', {
            'email': 'squat@example.com',
            'password': 'OldPassword123!',
        })
        self.assertEqual(c_bad_pw, 401)

        c_good_pw, _ = self.req('POST', '/api/v1/auth/login', {
            'email': 'squat@example.com',
            'password': 'RealOwnerPass123!',
        })
        self.assertEqual(c_good_pw, 200)

        # Re-registering an already verified email must be rejected
        c_dup, dup_res = self.req('POST', '/api/v1/auth/register', {
            'email': 'squat@example.com',
            'password': 'AnotherPass123!',
        })
        self.assertEqual(c_dup, 400)
        self.assertEqual(dup_res.get('code'), 'EMAIL_ALREADY_EXISTS')

    def test_4_verification_lockout_expiry_single_use_and_resend(self):
        self.req('POST', '/api/v1/auth/register', {
            'email': 'lock@example.com',
            'password': 'LockPass123!',
        })
        mail1 = self.outbox_entries('lock@example.com', 'verify_email')[-1]

        # 5 wrong attempts burn the verification code
        for i in range(5):
            st, body = self.req('POST', '/api/v1/auth/verify-email', {
                'email': 'lock@example.com',
                'code': f'99999{i}',
            })
            self.assertEqual(st, 400)

        # 6th attempt even with real code must fail because record is locked/used
        st_burned, burned_body = self.req('POST', '/api/v1/auth/verify-email', {
            'email': 'lock@example.com',
            'code': mail1['code'],
        })
        self.assertEqual(st_burned, 400)

        # Unknown email resend returns 200 (non-enumerating)
        st_unk, unk_res = self.req('POST', '/api/v1/auth/resend-verification', {'email': 'nobody@example.com'})
        self.assertEqual(st_unk, 200)
        self.assertTrue(unk_res['ok'])

        # Resend issues fresh working token/code
        st_res, _ = self.req('POST', '/api/v1/auth/resend-verification', {'email': 'lock@example.com'})
        self.assertEqual(st_res, 200)
        mail2 = self.outbox_entries('lock@example.com', 'verify_email')[-1]
        self.assertNotEqual(mail2['token'], mail1['token'])

        # Simulate expired verification record first, verify rejection, then resend & verify via token
        past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        with sqlite3.connect(self.data_dir / 'cloud.sqlite3') as db:
            db.execute("UPDATE email_verifications SET expires_at=? WHERE email='lock@example.com' AND used=0", (past,))
        st_exp, exp_res = self.req('POST', '/api/v1/auth/verify-email', {'token': mail2['token']})
        self.assertEqual(st_exp, 400)
        self.assertEqual(exp_res.get('code'), 'VERIFICATION_EXPIRED')

        st_res2, _ = self.req('POST', '/api/v1/auth/resend-verification', {'email': 'lock@example.com'})
        self.assertEqual(st_res2, 200)
        mail3 = self.outbox_entries('lock@example.com', 'verify_email')[-1]

        st_ok, ok_res = self.req('POST', '/api/v1/auth/verify-email', {'token': mail3['token']})
        self.assertEqual(st_ok, 200)
        self.assertTrue(ok_res['user']['emailVerified'])

        # Token/code cannot be reused after verification
        st_reuse, _ = self.req('POST', '/api/v1/auth/verify-email', {'token': mail3['token']})
        self.assertEqual(st_reuse, 400)

        # Resending to already-verified email returns 400 (clear rate limit first)
        self.service.clear_rate_limit('resend:127.0.0.1')
        self.service.clear_rate_limit('resend_email:lock@example.com')
        st_alr, alr_res = self.req('POST', '/api/v1/auth/resend-verification', {'email': 'lock@example.com'})
        self.assertEqual(st_alr, 400)
        self.assertEqual(alr_res.get('code'), 'ALREADY_VERIFIED')

    def test_5_three_day_trial_gating_expiry_downgrade_device_trim_and_idor(self):
        # Register & verify user A -> receives 72h Pro trial
        self.req('POST', '/api/v1/auth/register', {'email': 'trial@example.com', 'password': 'TrialPass123!'})
        mail_a = self.outbox_entries('trial@example.com', 'verify_email')[-1]
        c_v, v_res = self.req('POST', '/api/v1/auth/verify-email', {
            'email': 'trial@example.com',
            'code': mail_a['code'],
        })
        self.assertEqual(c_v, 200)
        self.assertTrue(v_res['trialActivated'])
        user_a = v_res['user']
        tok_a = v_res['token']
        self.assertEqual(user_a['effectivePlan'], 'pro')
        self.assertTrue(user_a['isPro'])
        self.assertTrue(user_a['trialActive'])
        self.assertTrue(user_a['trialUsed'])
        self.assertEqual(user_a['maxDevices'], 5)
        self.assertTrue(user_a['features']['cloudSync'])
        delta = dt.datetime.fromisoformat(user_a['trialEndsAt']) - dt.datetime.fromisoformat(user_a['trialStartedAt'])
        self.assertAlmostEqual(delta.total_seconds(), 72 * 3600, delta=5)

        # Active trial allows cloud sync and 3 devices
        c_sync_put, _ = self.req('PUT', '/api/v1/sync', {
            'state': {'version': 1, 'favorites': [{'itemId': 'movie:42'}]},
        }, token=tok_a)
        self.assertEqual(c_sync_put, 200)
        for idx in range(3):
            c_dev, _ = self.req('POST', '/api/v1/devices/register', {
                'deviceId': f'dev-{idx}', 'deviceName': f'Device {idx}', 'platform': 'android',
            }, token=tok_a)
            self.assertEqual(c_dev, 200)

        # Register & verify user B to test IDOR isolation on DELETE /devices/<id>
        self.req('POST', '/api/v1/auth/register', {'email': 'other@example.com', 'password': 'OtherPass123!'})
        mail_b = self.outbox_entries('other@example.com', 'verify_email')[-1]
        _, v_b = self.req('POST', '/api/v1/auth/verify-email', {'email': 'other@example.com', 'code': mail_b['code']})
        tok_b = v_b['token']
        self.req('POST', '/api/v1/devices/register', {
            'deviceId': 'b-device-1', 'deviceName': 'Other Phone', 'platform': 'ios',
        }, token=tok_b)

        # Expire user A's trial in SQLite -> auto-downgrades to normal (maxDevices=1), preserves sync & devices
        expired_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat()
        with sqlite3.connect(self.data_dir / 'cloud.sqlite3') as db:
            db.execute(
                "UPDATE users SET trial_ends_at=?, expires_at=? WHERE email='trial@example.com'",
                (expired_iso, expired_iso),
            )

        c_me, me_res = self.req('GET', '/api/v1/me', token=tok_a)
        self.assertEqual(c_me, 200)
        self.assertEqual(me_res['user']['effectivePlan'], 'normal')
        self.assertFalse(me_res['user']['isPro'])
        self.assertFalse(me_res['user']['trialActive'])
        self.assertEqual(me_res['user']['maxDevices'], 1)
        self.assertFalse(me_res['user']['features']['cloudSync'])
        self.assertEqual(len(me_res['user']['devices']), 3)

        # Sync is blocked for Normal plan with 403 PRO_REQUIRED
        c_sg, sg_res = self.req('GET', '/api/v1/sync', token=tok_a)
        self.assertEqual(c_sg, 403)
        self.assertEqual(sg_res.get('code'), 'PRO_REQUIRED')
        self.assertTrue(sg_res.get('upgradeRequired'))

        c_sp, sp_res = self.req('PUT', '/api/v1/sync', {'state': {'version': 1}}, token=tok_a)
        self.assertEqual(c_sp, 403)
        self.assertEqual(sp_res.get('code'), 'PRO_REQUIRED')

        # Registering a new device OR re-authing >1 device when downgraded is blocked (403 DEVICE_LIMIT_REACHED)
        c_dnew, dnew_res = self.req('POST', '/api/v1/devices/register', {
            'deviceId': 'dev-new', 'deviceName': 'New PC', 'platform': 'windows',
        }, token=tok_a)
        self.assertEqual(c_dnew, 403)
        self.assertEqual(dnew_res.get('code'), 'DEVICE_LIMIT_REACHED')
        self.assertTrue(dnew_res.get('upgradeRequired'))

        c_dre, dre_res = self.req('POST', '/api/v1/devices/register', {
            'deviceId': 'dev-0', 'deviceName': 'Device 0', 'platform': 'android',
        }, token=tok_a)
        self.assertEqual(c_dre, 403)
        self.assertEqual(dre_res.get('code'), 'DEVICE_LIMIT_REACHED')

        # IDOR check: user A attempting to delete user B's device returns 404 and leaves user B's device intact
        c_idor, _ = self.req('DELETE', '/api/v1/devices/b-device-1', token=tok_a)
        self.assertEqual(c_idor, 404)
        _, b_me = self.req('GET', '/api/v1/me', token=tok_b)
        self.assertEqual(len(b_me['user']['devices']), 1)

        # User A trims 2 of their own 3 devices -> remaining 1 device can re-auth
        self.req('DELETE', '/api/v1/devices/dev-1', token=tok_a)
        c_del2, del2_res = self.req('DELETE', '/api/v1/devices/dev-2', token=tok_a)
        self.assertEqual(c_del2, 200)
        self.assertEqual(len(del2_res['devices']), 1)
        c_dre_ok, _ = self.req('POST', '/api/v1/devices/register', {
            'deviceId': 'dev-0', 'deviceName': 'Device 0', 'platform': 'android',
        }, token=tok_a)
        self.assertEqual(c_dre_ok, 200)

        # Admin mints a MAVIE-* Pro license -> user A redeems -> Pro & preserved sync data restored
        _, adm_login = self.req('POST', '/api/v1/auth/login', {
            'email': 'admin@mavie.app', 'password': 'AdminStrongPass!2026',
        })
        _, lic_res = self.req('POST', '/api/v1/admin/licenses', {
            'plan': 'pro', 'durationDays': 365, 'maxDevices': 5, 'maxUses': 1,
        }, token=adm_login['token'])
        self.assertTrue(lic_res['license']['code'].startswith('MAVIE-'))

        c_red, red_res = self.req('POST', '/api/v1/licenses/redeem', {'code': lic_res['license']['code']}, token=tok_a)
        self.assertEqual(c_red, 200)
        self.assertEqual(red_res['user']['effectivePlan'], 'pro')
        self.assertFalse(red_res['user']['trialActive'])

        c_sync_restored, sync_data = self.req('GET', '/api/v1/sync', token=tok_a)
        self.assertEqual(c_sync_restored, 200)
        self.assertEqual(sync_data['state']['favorites'][0]['itemId'], 'movie:42')

    def test_6_self_service_password_reset_lockout_and_token_version_revocation(self):
        self.req('POST', '/api/v1/auth/register', {'email': 'reset@example.com', 'password': 'OldPassword123!'})
        mail_v = self.outbox_entries('reset@example.com', 'verify_email')[-1]
        _, ver = self.req('POST', '/api/v1/auth/verify-email', {'email': 'reset@example.com', 'code': mail_v['code']})
        pre_reset_token = ver['token']

        # Unknown email returns 200 without writing outbox
        c_unk, unk_res = self.req('POST', '/api/v1/auth/forgot-password', {'email': 'unknown@example.com'})
        self.assertEqual(c_unk, 200)
        self.assertTrue(unk_res['ok'])
        self.assertEqual(self.outbox_entries('unknown@example.com', 'password_reset'), [])

        # Known verified email writes password_reset outbox
        c_fg, fg_res = self.req('POST', '/api/v1/auth/forgot-password', {'email': 'reset@example.com'})
        self.assertEqual(c_fg, 200)
        self.assertEqual(fg_res['deliveryMode'], 'outbox')
        self.assertNotIn('code', fg_res)
        self.assertNotIn('token', fg_res)
        mail_r1 = self.outbox_entries('reset@example.com', 'password_reset')[-1]

        # 5 wrong verify-reset-code attempts lock out the code
        for i in range(5):
            c_bad, _ = self.req('POST', '/api/v1/auth/verify-reset-code', {
                'email': 'reset@example.com', 'code': f'11111{i}',
            })
            self.assertEqual(c_bad, 400)
        c_locked, _ = self.req('POST', '/api/v1/auth/verify-reset-code', {
            'email': 'reset@example.com', 'code': mail_r1['code'],
        })
        self.assertEqual(c_locked, 400)

        # Request fresh reset code
        c_fg2, _ = self.req('POST', '/api/v1/auth/forgot-password', {'email': 'reset@example.com'})
        self.assertEqual(c_fg2, 200)
        mail_r2 = self.outbox_entries('reset@example.com', 'password_reset')[-1]

        # Valid verify-reset-code returns 200 without consuming code
        c_vrc, vrc_res = self.req('POST', '/api/v1/auth/verify-reset-code', {
            'email': 'reset@example.com', 'code': mail_r2['code'],
        })
        self.assertEqual(c_vrc, 200)
        self.assertTrue(vrc_res['valid'])

        # Weak password fails BEFORE consuming the reset code
        c_weak, _ = self.req('POST', '/api/v1/auth/reset-password', {
            'email': 'reset@example.com', 'code': mail_r2['code'], 'newPassword': 'short',
        })
        self.assertEqual(c_weak, 400)

        # Complete reset with strong password
        c_rst, rst_res = self.req('POST', '/api/v1/auth/reset-password', {
            'email': 'reset@example.com', 'code': mail_r2['code'], 'newPassword': 'BrandNewPassword!2026',
        })
        self.assertEqual(c_rst, 200)
        self.assertTrue(rst_res['ok'])

        # Pre-reset session token is immediately invalidated by token_version bump
        c_old_me, _ = self.req('GET', '/api/v1/me', token=pre_reset_token)
        self.assertEqual(c_old_me, 401)

        # Old password fails (401), new password succeeds (200), trial is NOT re-granted
        c_old_pw, _ = self.req('POST', '/api/v1/auth/login', {
            'email': 'reset@example.com', 'password': 'OldPassword123!',
        })
        self.assertEqual(c_old_pw, 401)

        c_new_pw, new_login = self.req('POST', '/api/v1/auth/login', {
            'email': 'reset@example.com', 'password': 'BrandNewPassword!2026',
        })
        self.assertEqual(c_new_pw, 200)
        self.assertTrue(new_login['user']['trialUsed'])

        # Reusing consumed reset code/token fails
        c_reuse, _ = self.req('POST', '/api/v1/auth/reset-password', {
            'token': mail_r2['token'], 'newPassword': 'YetAnotherPassword!99',
        })
        self.assertEqual(c_reuse, 400)

    def test_7_smtp_delivery_mode_and_crlf_sanitization(self):
        sent_messages = []
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False
        fake_client.send_message.side_effect = lambda msg: sent_messages.append(msg)

        env_patch = {
            'MAVIE_EMAIL_MODE': 'smtp',
            'MAVIE_SMTP_HOST': 'smtp.example.test',
            'MAVIE_SMTP_PORT': '587',
            'MAVIE_SMTP_USER': 'mailer@mavie.app',
            'MAVIE_SMTP_PASS': 'smtp-secret',
            'MAVIE_SMTP_FROM': 'Mavie <noreply@mavie.app>',
        }
        with patch.dict(os.environ, env_patch), patch('smtplib.SMTP', return_value=fake_client) as smtp_cls:
            c_reg, reg_res = self.req('POST', '/api/v1/auth/register', {
                'email': 'smtpuser@example.com',
                'password': 'SmtpPassword123!',
                'displayName': "User\r\nBcc: evil@attacker.test",
            })
        self.assertEqual(c_reg, 201)
        self.assertEqual(reg_res['deliveryMode'], 'smtp')
        smtp_cls.assert_called_once_with('smtp.example.test', 587, timeout=15)
        fake_client.starttls.assert_called_once()
        fake_client.login.assert_called_once_with('mailer@mavie.app', 'smtp-secret')
        self.assertEqual(len(sent_messages), 1)
        sent_msg = sent_messages[0]
        self.assertEqual(sent_msg['To'], 'smtpuser@example.com')
        self.assertNotIn('\r', sent_msg['Subject'])
        self.assertNotIn('\n', sent_msg['Subject'])
        self.assertNotIn('\r\nBcc:', sent_msg.get_content())

        # Outbox JSON should not receive secrets in smtp mode, and SQLite outbox omits code/token
        self.assertEqual(self.outbox_entries('smtpuser@example.com'), [])
        with sqlite3.connect(self.data_dir / 'cloud.sqlite3') as db:
            r = db.execute(
                'SELECT delivery_mode, status, code, token FROM email_outbox WHERE recipient=?',
                ('smtpuser@example.com',),
            ).fetchone()
        self.assertEqual(r, ('smtp', 'sent', '', ''))

    def test_8_legacy_sqlite_migration_preserves_existing_users_and_normalizes_plans(self):
        with tempfile.TemporaryDirectory(prefix='mavie-legacy-db-') as tmp:
            legacy_dir = Path(tmp)
            db_path = legacy_dir / 'cloud.sqlite3'
            with sqlite3.connect(db_path) as db:
                db.executescript("""
                    CREATE TABLE users(
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
                    CREATE TABLE licenses(
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
                    CREATE TABLE password_resets(
                        token_hash TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        used INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE app_config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE download_stats(target TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
                """)
                pw = cloud_admin.CloudService._hash_password('LegacyPass123!')
                now = '2026-11-01T10:00:00+00:00'
                db.execute(
                    "INSERT INTO users VALUES('u_free','free@example.com','Free User',?,'user','free','active',2,'','',?,?)",
                    (pw, now, now),
                )
                db.execute(
                    "INSERT INTO users VALUES('u_fam','fam@example.com','Family User',?,'user','family','active',5,'','',?,?)",
                    (pw, now, now),
                )
                db.execute(
                    "INSERT INTO users VALUES('u_life','life@example.com','Life User',?,'user','lifetime','active',5,'','',?,?)",
                    (pw, now, now),
                )
                db.execute(
                    "INSERT INTO licenses VALUES('CINEVA-1111-2222-3333','lifetime',0,5,1,0,'','admin',?)",
                    (now,),
                )
                legacy_reset_token = 'legacy-reset-token-abc'
                legacy_reset_hash = cloud_admin.CloudService._legacy_hash_token(legacy_reset_token)
                future_exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
                db.execute(
                    "INSERT INTO password_resets VALUES(?,?,?,0)",
                    (legacy_reset_hash, 'u_free', future_exp),
                )
                db.execute(
                    "INSERT INTO app_config VALUES('versions', ?)",
                    (json.dumps({
                        'windowsLatest': '2.0.0',
                        'windowsInstallerUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Setup.exe',
                        'windowsPortableUrl': 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva.exe',
                    }),),
                )

            migrated = cloud_admin.CloudService(legacy_dir, admin_email='admin@mavie.app', admin_password='AdminStrongPass!2026')
            u_free = migrated.get_user_by_id('u_free')
            u_fam = migrated.get_user_by_id('u_fam')
            u_life = migrated.get_user_by_id('u_life')
            self.assertTrue(u_free['emailVerified'])
            self.assertEqual(u_free['plan'], 'normal')
            self.assertEqual(u_free['maxDevices'], 1)
            self.assertTrue(u_fam['emailVerified'])
            self.assertEqual(u_fam['plan'], 'pro')
            self.assertEqual(u_fam['effectivePlan'], 'pro')
            self.assertEqual(u_fam['maxDevices'], 5)
            self.assertTrue(u_life['emailVerified'])
            self.assertEqual(u_life['plan'], 'pro')
            self.assertEqual(u_life['effectivePlan'], 'pro')
            self.assertEqual(u_life['maxDevices'], 5)

            cfg = migrated.get_public_config()
            self.assertIn('Mavie-Setup.exe', cfg['versions']['windowsInstallerUrl'])
            self.assertTrue(cfg['versions']['windowsPortableUrl'].endswith('/Mavie.exe'))
            self.assertNotIn('Cineva', cfg['versions']['windowsPortableUrl'])
            self.assertIn('Mavie-macOS.dmg', cfg['versions']['macosUrl'])
            self.assertIn('Mavie-iOS.ipa', cfg['versions']['iosUrl'])
            self.assertIn('ios', cfg['downloads'])

            # Active legacy password_resets row (sha256(token)) migrates and completes reset cleanly
            migrated.complete_password_reset(raw_token=legacy_reset_token, new_password='NewLegacyPassword!1')
            with self.assertRaises(cloud_admin.ApiError):
                migrated.login('free@example.com', 'LegacyPass123!')
            ok_login = migrated.login('free@example.com', 'NewLegacyPassword!1')
            self.assertEqual(ok_login['user']['id'], 'u_free')

    def test_9_admin_gate_case_insensitive_and_login_rate_limit_isolation(self):
        # Case-insensitive or normalized paths to admin.html must NOT bypass the admin gate
        for path in ('/Admin.html', '/ADMIN.HTML', '/ADMIN', '/./admin.html'):
            conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
            try:
                conn.request('GET', path)
                resp = conn.getresponse()
                resp.read()
                self.assertEqual(resp.status, 404, f'{path} bypassed admin gate')
            finally:
                conn.close()

        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('GET', '/Admin.html', headers={'X-Admin-Gate': 'm1-gate-key'})
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 200)
        finally:
            conn.close()

        # Register & verify attacker and victim accounts
        for em in ('victim@example.com', 'attacker@example.com'):
            c_reg, _ = self.req('POST', '/api/v1/auth/register', {'email': em, 'password': 'StrongPassword123!'})
            self.assertEqual(c_reg, 201)
            mail = self.outbox_entries(em, 'verify_email')[-1]
            c_ver, _ = self.req('POST', '/api/v1/auth/verify-email', {'email': em, 'code': mail['code']})
            self.assertEqual(c_ver, 200)

        # 11 wrong guesses on victim, then valid login on attacker must NOT reset victim's bucket
        for _ in range(11):
            c_bad, _ = self.req('POST', '/api/v1/auth/login', {'email': 'victim@example.com', 'password': 'wrong'})
            self.assertEqual(c_bad, 401)
        c_att, _ = self.req('POST', '/api/v1/auth/login', {'email': 'attacker@example.com', 'password': 'StrongPassword123!'})
        self.assertEqual(c_att, 200)
        c_12th, _ = self.req('POST', '/api/v1/auth/login', {'email': 'victim@example.com', 'password': 'wrong'})
        self.assertEqual(c_12th, 401)
        c_13th, _ = self.req('POST', '/api/v1/auth/login', {'email': 'victim@example.com', 'password': 'wrong'})
        self.assertEqual(c_13th, 429)


if __name__ == '__main__':
    unittest.main()
