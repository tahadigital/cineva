"""Tests for Cineva Control Plane, Website download portal, and Admin Dashboard API."""
from __future__ import annotations

import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cloud_admin


class CloudAdminHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cineva-cloud-tests-')
        cls.service = cloud_admin.CloudService(
            Path(cls.temp.name),
            admin_email='owner@cineva.app',
            admin_password='AdminStrongPass!2026',
            admin_gate_key='test-gate-secret-key',
        )
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), cloud_admin.make_handler(cls.service))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.temp.cleanup()

    def req(self, method: str, path: str, body: dict | None = None, *, token: str = '', raw: bool = False, headers: dict | None = None, gate: bool = True):
        req_headers = {}
        if token:
            req_headers['Authorization'] = f'Bearer {token}'
        if gate:
            req_headers['X-Admin-Gate'] = 'test-gate-secret-key'
        if headers:
            req_headers.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            req_headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=req_headers)
            resp = conn.getresponse()
            raw_bytes = resp.read()
            if raw:
                return resp.status, raw_bytes.decode('utf-8', errors='replace'), dict(resp.getheaders())
            return resp.status, (json.loads(raw_bytes.decode('utf-8')) if raw_bytes else None)
        finally:
            conn.close()

    def test_1_static_website_routes_and_download_tracking(self):
        for route, needle in (
            ('/', 'Cineva'),
            ('/privacy', 'Gizlilik Politikası'),
            ('/terms', 'Kullanım Koşulları'),
        ):
            code, html, _ = self.req('GET', route, raw=True, gate=False)
            self.assertEqual(code, 200, route)
            self.assertIn(needle, html)

        # Public homepage hides /admin links
        _, home_html, _ = self.req('GET', '/', raw=True, gate=False)
        self.assertNotIn('href="/admin"', home_html)

        # Admin routes stay hidden (404) without valid gate key/cookie
        for locked in ('/admin', '/admin/', '/admin.html', '/api/v1/admin/overview'):
            code_blocked, _, _ = self.req('GET', locked, raw=True, gate=False)
            self.assertEqual(code_blocked, 404, locked)

        # Opening secret access URL sets HttpOnly gate cookie and reveals Admin login
        code_redir, _, redir_hdrs = self.req('GET', '/admin?access=test-gate-secret-key', raw=True, gate=False)
        self.assertEqual(code_redir, 302)
        set_cookie = next((v for k, v in redir_hdrs.items() if k.lower() == 'set-cookie'), '')
        self.assertIn('cineva_admin_gate=', set_cookie)
        cookie_pair = set_cookie.split(';', 1)[0]

        code_adm, adm_html, _ = self.req('GET', '/admin', raw=True, gate=False, headers={'Cookie': cookie_pair})
        self.assertEqual(code_adm, 200)
        self.assertIn('Yönetici Girişi', adm_html)

        code, track1 = self.req('POST', '/api/v1/downloads/track', {'target': 'windows-installer'})
        self.assertEqual(code, 200)
        self.assertEqual(track1['count'], 1)

        code, cfg = self.req('GET', '/api/v1/app-config')
        self.assertEqual(code, 200)
        self.assertEqual(cfg['downloads']['windows-installer'], 1)

    def test_2_user_privilege_separation_license_devices_and_admin_mutations(self):
        # Register ordinary user
        code, reg = self.req('POST', '/api/v1/auth/register', {
            'email': 'ali@example.com', 'password': 'UserPass123!', 'displayName': 'Ali',
        })
        self.assertEqual(code, 201)
        user_token = reg['token']
        uid = reg['user']['id']
        self.assertEqual(reg['user']['role'], 'user')
        self.assertEqual(reg['user']['plan'], 'free')

        # Ordinary user CANNOT touch admin APIs
        code_forb, _ = self.req('GET', '/api/v1/admin/overview', token=user_token)
        self.assertEqual(code_forb, 403)
        code_forb2, _ = self.req('PATCH', f'/api/v1/admin/users/{uid}', {'plan': 'lifetime'}, token=user_token)
        self.assertEqual(code_forb2, 403)

        # Login as admin
        code_adm, adm_login = self.req('POST', '/api/v1/auth/login', {
            'email': 'owner@cineva.app', 'password': 'AdminStrongPass!2026',
        })
        self.assertEqual(code_adm, 200)
        admin_token = adm_login['token']

        # Admin password is PBKDF2-hashed in SQLite & never returned in API responses
        with sqlite3.connect(Path(self.temp.name) / 'cloud.sqlite3') as db:
            pw_hash = db.execute("SELECT password_hash FROM users WHERE email='ali@example.com'").fetchone()[0]
        self.assertTrue(pw_hash.startswith('pbkdf2_sha256:200000:'))
        self.assertNotIn('UserPass123', pw_hash)

        code_list, users_res = self.req('GET', '/api/v1/admin/users?q=ali', token=admin_token)
        self.assertEqual(code_list, 200)
        self.assertEqual(len(users_res['users']), 1)
        self.assertNotIn('password_hash', users_res['users'][0])
        self.assertNotIn('password', users_res['users'][0])

        # Admin creates a Pro license & user redeems it
        code_lic, lic_res = self.req('POST', '/api/v1/admin/licenses', {
            'plan': 'pro', 'durationDays': 180, 'maxDevices': 3, 'maxUses': 1, 'note': 'Promo',
        }, token=admin_token)
        self.assertEqual(code_lic, 201)
        lic_code = lic_res['license']['code']
        self.assertTrue(lic_code.startswith('CINEVA-'))

        code_red, red_res = self.req('POST', '/api/v1/licenses/redeem', {'code': lic_code}, token=user_token)
        self.assertEqual(code_red, 200)
        self.assertEqual(red_res['user']['plan'], 'pro')
        self.assertEqual(red_res['user']['maxDevices'], 3)

        # Second redeem attempt rejected
        code_dup, _ = self.req('POST', '/api/v1/licenses/redeem', {'code': lic_code}, token=user_token)
        self.assertEqual(code_dup, 400)

        # Enforce maxDevices = 3
        for idx in range(3):
            c_dev, _ = self.req('POST', '/api/v1/devices/register', {
                'deviceId': f'd{idx}', 'deviceName': f'Phone {idx}', 'platform': 'android',
            }, token=user_token)
            self.assertEqual(c_dev, 200)
        c_over, _ = self.req('POST', '/api/v1/devices/register', {
            'deviceId': 'd4', 'deviceName': 'TV', 'platform': 'windows',
        }, token=user_token)
        self.assertEqual(c_over, 400)

        # Admin suspends user -> suspended user blocked immediately
        c_susp, susp_res = self.req('PATCH', f'/api/v1/admin/users/{uid}', {
            'status': 'suspended', 'adminNote': 'Test suspend',
        }, token=admin_token)
        self.assertEqual(c_susp, 200)
        self.assertEqual(susp_res['user']['status'], 'suspended')

        c_me_blocked, _ = self.req('GET', '/api/v1/me', token=user_token)
        self.assertEqual(c_me_blocked, 403)
        c_login_blocked, _ = self.req('POST', '/api/v1/auth/login', {'email': 'ali@example.com', 'password': 'UserPass123!'})
        self.assertEqual(c_login_blocked, 403)

        # Admin upgrades to lifetime, reactivates, tests admin role invite/revoke, removes 1 device, issues reset token & sets announcement
        c_react, react_res = self.req('PATCH', f'/api/v1/admin/users/{uid}', {
            'status': 'active', 'plan': 'lifetime', 'maxDevices': 5, 'role': 'admin',
        }, token=admin_token)
        self.assertEqual(c_react, 200)
        self.assertEqual(react_res['user']['effectivePlan'], 'lifetime')
        self.assertEqual(react_res['user']['role'], 'admin')
        c_demote, demote_res = self.req('PATCH', f'/api/v1/admin/users/{uid}', {'role': 'user'}, token=admin_token)
        self.assertEqual(c_demote, 200)
        self.assertEqual(demote_res['user']['role'], 'user')

        c_rm_dev, _ = self.req('DELETE', f'/api/v1/admin/users/{uid}/devices/d0', token=admin_token)
        self.assertEqual(c_rm_dev, 200)

        c_rst, rst_res = self.req('POST', f'/api/v1/admin/users/{uid}/reset-password-token', {}, token=admin_token)
        self.assertEqual(c_rst, 200)
        c_done, _ = self.req('POST', '/api/v1/auth/reset-password', {
            'token': rst_res['resetToken'], 'newPassword': 'NewSecurePassword9!',
        })
        self.assertEqual(c_done, 200)
        c_new_log, _ = self.req('POST', '/api/v1/auth/login', {'email': 'ali@example.com', 'password': 'NewSecurePassword9!'})
        self.assertEqual(c_new_log, 200)

        c_cfg_put, cfg_updated = self.req('PUT', '/api/v1/admin/config', {
            'announcement': {'enabled': True, 'title': 'Bakım', 'message': 'v2.1 çıktı', 'severity': 'info'},
            'versions': {'windowsLatest': '2.1.0'},
        }, token=admin_token)
        self.assertEqual(c_cfg_put, 200)
        self.assertTrue(cfg_updated['announcement']['enabled'])
        self.assertEqual(cfg_updated['versions']['windowsLatest'], '2.1.0')

        # Audit log records actions
        c_aud, aud_res = self.req('GET', '/api/v1/admin/audit', token=admin_token)
        self.assertEqual(c_aud, 200)
        actions = {log['action'] for log in aud_res['logs']}
        self.assertTrue({'license.create', 'license.redeem', 'user.update', 'device.remove', 'user.reset_token', 'config.update'}.issubset(actions))

    def test_9_login_rate_limit_blocks_brute_force(self):
        statuses = [self.req('POST', '/api/v1/auth/login', {'email': 'owner@cineva.app', 'password': 'wrong'})[0] for _ in range(13)]
        self.assertEqual(statuses[:12], [403] * 12)
        self.assertEqual(statuses[12], 429)

    def test_4_desktop_server_cloud_bridge_syncs_plan_without_exposing_passwords(self):
        import importlib.util
        import os
        from unittest.mock import patch

        # First mint a license key via admin
        _, adm = self.req('POST', '/api/v1/auth/login', {'email': 'owner@cineva.app', 'password': 'AdminStrongPass!2026'})
        _, lic = self.req('POST', '/api/v1/admin/licenses', {'plan': 'pro', 'durationDays': 30, 'maxUses': 1}, token=adm['token'])

        with tempfile.TemporaryDirectory(prefix='cineva-bridge-') as tmp_srv:
            spec = importlib.util.spec_from_file_location('_cineva_cloud_bridge_srv', ROOT / 'server.py')
            srv = importlib.util.module_from_spec(spec)
            with patch.dict(os.environ, {'CINEVA_DATA_DIR': tmp_srv}):
                spec.loader.exec_module(srv)
                srv.initialize()
                cloud_base = f'http://127.0.0.1:{self.port}'
                res = srv.cloud_auth('register', {'cloudUrl': cloud_base, 'email': 'desktop@example.com', 'password': 'DeskPass123!'})
                self.assertTrue(res['connected'])
                self.assertEqual(res['user']['effectivePlan'], 'free')

                redeem_res = srv.cloud_redeem({'code': lic['license']['code']})
                self.assertEqual(redeem_res['user']['plan'], 'pro')

                # Admin suspends the desktop user -> desktop cloud_status drops invalid access cleanly
                uid = res['user']['id']
                self.req('PATCH', f'/api/v1/admin/users/{uid}', {'status': 'suspended'}, token=adm['token'])
                after_suspend = srv.cloud_status()
                self.assertIsNone(after_suspend['user'])


if __name__ == '__main__':
    unittest.main()
