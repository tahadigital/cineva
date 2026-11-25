"""Integration & static tests for Mavie Smart TV /tv routes, /api/tv-info, desktop specs, and CI."""
from __future__ import annotations

import ast
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

SECRET_USER = 'tv-secret-user-never-leak'
SECRET_PASS = 'tv-secret-pass-never-leak'
SECRET_M3U = 'https://iptv.example.com/get.php?username=tv-secret-user-never-leak&password=tv-secret-pass-never-leak'


class TvServerRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix='mavie-tv-route-tests-')
        cls.data_dir = Path(cls.temp.name)
        (cls.data_dir / 'config.json').write_text(
            json.dumps({
                'type': 'm3u',
                'name': 'Gizli TV Test',
                'host': 'https://iptv.example.com',
                'username': SECRET_USER,
                'password': SECRET_PASS,
                'm3uUrl': SECRET_M3U,
            }),
            encoding='utf-8',
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = int(probe.getsockname()[1])
        env = {**os.environ, 'MAVIE_DATA_DIR': str(cls.data_dir)}
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1', '--port', str(cls.port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15.0
        ready = False
        while time.monotonic() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError('Local Mavie server exited before ready in TV route tests')
            try:
                conn = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=1)
                conn.request('GET', '/api/health')
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status == 200:
                    ready = True
                    break
            except OSError:
                time.sleep(0.1)
        if not ready:
            cls.proc.terminate()
            cls.temp.cleanup()
            raise RuntimeError('Local Mavie server did not become ready in time')

    @classmethod
    def tearDownClass(cls) -> None:
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait(timeout=5)
        cls.temp.cleanup()

    def _req(self, method: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, hdrs, body
        finally:
            conn.close()

    def test_tv_root_redirects_to_trailing_slash_preserving_query(self) -> None:
        st, hdrs, _ = self._req('GET', '/tv')
        self.assertEqual(st, 302)
        self.assertEqual(hdrs.get('location'), '/tv/')
        self.assertEqual(hdrs.get('x-content-type-options'), 'nosniff')
        self.assertEqual(hdrs.get('x-frame-options'), 'DENY')

        st_q, hdrs_q, _ = self._req('GET', '/tv?mode=demo')
        self.assertEqual(st_q, 302)
        self.assertEqual(hdrs_q.get('location'), '/tv/?mode=demo')

    def test_tv_index_app_js_and_vendor_hls_served_with_security_headers(self) -> None:
        tv_src = ROOT / 'tv' / 'src'
        self.assertTrue((tv_src / 'index.html').is_file(), 'Expected tv/src/index.html to exist')
        self.assertTrue((tv_src / 'app.js').is_file(), 'Expected tv/src/app.js to exist')

        st_idx, hdrs_idx, body_idx = self._req('GET', '/tv/')
        self.assertEqual(st_idx, 200)
        self.assertIn('text/html', hdrs_idx.get('content-type', ''))
        self.assertEqual(hdrs_idx.get('x-content-type-options'), 'nosniff')
        self.assertEqual(hdrs_idx.get('x-frame-options'), 'DENY')
        self.assertIn("script-src 'self'", hdrs_idx.get('content-security-policy', ''))
        self.assertIn("object-src 'none'", hdrs_idx.get('content-security-policy', ''))
        self.assertEqual(body_idx, (tv_src / 'index.html').read_bytes())

        st_head, _, body_head = self._req('HEAD', '/tv/')
        self.assertEqual(st_head, 200)
        self.assertEqual(body_head, b'')

        st_js, hdrs_js, body_js = self._req('GET', '/tv/app.js')
        self.assertEqual(st_js, 200)
        self.assertIn('javascript', hdrs_js.get('content-type', ''))
        self.assertEqual(body_js, (tv_src / 'app.js').read_bytes())

        st_hls, hdrs_hls, body_hls = self._req('GET', '/tv/vendor/hls.min.js')
        self.assertEqual(st_hls, 200)
        self.assertIn('javascript', hdrs_hls.get('content-type', ''))
        self.assertEqual(body_hls, (ROOT / 'public' / 'vendor' / 'hls.min.js').read_bytes())

    def test_tv_path_traversal_and_missing_files_rejected_cleanly(self) -> None:
        for bad_path in (
            '/tv/../server.py',
            '/tv/../../server.py',
            '/tv/%2e%2e/server.py',
            '/tv/%2e%2e/%2e%2e/server.py',
            '/tv/..%5c..%5cserver.py',
            '/tv/vendor/../../server.py',
            '/tv/vendor/%2e%2e/%2e%2e/server.py',
            '/tv/nonexistent-file-xyz.js',
        ):
            with self.subTest(path=bad_path):
                st, hdrs, body = self._req('GET', bad_path)
                self.assertIn(st, (400, 403, 404), f'{bad_path} returned {st}')
                self.assertEqual(hdrs.get('x-content-type-options'), 'nosniff')
                self.assertEqual(hdrs.get('x-frame-options'), 'DENY')
                self.assertNotIn(b'def run_server', body)

    def test_api_tv_info_returns_clean_discovery_metadata_with_zero_secrets(self) -> None:
        st, hdrs, raw = self._req('GET', '/api/tv-info')
        self.assertEqual(st, 200)
        self.assertEqual(hdrs.get('x-content-type-options'), 'nosniff')
        self.assertEqual(hdrs.get('x-frame-options'), 'DENY')
        text = raw.decode('utf-8')
        for secret in (SECRET_USER, SECRET_PASS, SECRET_M3U, 'pairingCode'):
            self.assertNotIn(secret, text)

        data = json.loads(text)
        self.assertTrue(data['ok'])
        self.assertEqual(data['app'], 'mavie')
        self.assertEqual(data['port'], self.port)
        self.assertTrue(isinstance(data['lan_ip'], str) and len(data['lan_ip']) > 0)
        self.assertEqual(data['web_url'], f"http://{data['lan_ip']}:{self.port}/")
        self.assertEqual(data['tv_url'], f"http://{data['lan_ip']}:{self.port}/tv/")
        self.assertTrue(data['lan_sync_available'])
        self.assertIsInstance(data['lan_urls'], list)
        self.assertIsInstance(data['tv_urls'], list)

        # Untrusted Host header must still be blocked by guard()
        st_bad, _, _ = self._req('GET', '/api/tv-info', headers={'Host': 'evil.example.com:8844'})
        self.assertEqual(st_bad, 403)

    def test_tv_dir_specs_and_ci_tv_release_pipeline(self) -> None:
        self.assertEqual(server.TV_DIR, server.ROOT / 'tv' / 'src')

        win_spec = (ROOT / 'windows' / 'mavie.spec').read_text(encoding='utf-8')
        mac_spec = (ROOT / 'apple' / 'macOS' / 'mavie_server.spec').read_text(encoding='utf-8')
        ci_yml = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')

        ast.parse(win_spec, filename='windows/mavie.spec')
        ast.parse(mac_spec, filename='apple/macOS/mavie_server.spec')

        for name, spec_src in (('windows/mavie.spec', win_spec), ('apple/macOS/mavie_server.spec', mac_spec)):
            self.assertIn("os.path.join(ROOT, 'tv', 'src')", spec_src, f'Missing tv/src bundle in {name}')
            self.assertIn("os.path.join('tv', 'src')", spec_src, f'Missing tv/src target in {name}')

        for token in (
            'tv-packages:',
            'python3 tv/build_tv_packages.py',
            'dist/Mavie-Tizen.wgt',
            'dist/Mavie-webOS.ipk',
            'node --test tests/test_tv_apps.mjs',
            'name: Mavie-TV',
            'needs: [android-build-and-test, windows-desktop-package, apple-macos-and-ios, tv-packages]',
            'release-assets/Mavie-TV/Mavie-Tizen.wgt',
            'release-assets/Mavie-TV/Mavie-webOS.ipk',
        ):
            self.assertIn(token, ci_yml, f'Missing {token!r} in .github/workflows/ci.yml')


if __name__ == '__main__':
    unittest.main()
