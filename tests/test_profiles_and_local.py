"""Tests for Stage 1 features: local media scanner/Range streaming, profiles with PIN/Kid mode, and surprise picker."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import local_media


class LocalMediaUnitTests(unittest.TestCase):
    def test_validate_rejects_system_root_and_empty(self):
        with self.assertRaises(ValueError):
            local_media.validate_local_dir('')
        with self.assertRaises(ValueError):
            local_media.validate_local_dir('/')

    def test_parse_media_filename_movie_and_episode(self):
        self.assertEqual(
            local_media.parse_media_filename('Arrival.2016.1080p.WEB-DL.x264'),
            ('Arrival', '2016', 0, 0),
        )
        self.assertEqual(
            local_media.parse_media_filename('Dark_S02E03_720p_HEVC'),
            ('Dark', '', 2, 3),
        )

    def test_scan_collects_subtitles_and_blocks_escaping_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            media = base / 'media'
            outside = base / 'outside'
            (media / 'Filmler').mkdir(parents=True)
            (media / '.hidden').mkdir()
            outside.mkdir()

            video = media / 'Filmler' / 'Cosmos.2020.1080p.mp4'
            video.write_bytes(b'0123456789abcdef')
            sub = media / 'Filmler' / 'Cosmos.2020.1080p.tr.srt'
            sub.write_text('1\n00:00:00,000 --> 00:00:01,000\nMerhaba\n', encoding='utf-8')
            (media / '.hidden' / 'secret.mp4').write_bytes(b'hidden')
            secret_out = outside / 'escape.mp4'
            secret_out.write_bytes(b'outside')
            try:
                (media / 'escape_link.mp4').symlink_to(secret_out)
            except OSError:
                pass

            scanned = local_media.scan_local_folder(str(media))
            names = [i['name'] for i in scanned['items']]
            self.assertEqual(names, ['Cosmos'])
            self.assertEqual(len(scanned['items'][0]['subtitles']), 1)
            self.assertTrue(scanned['items'][0]['subtitles'][0].endswith('.tr.srt'))


class ProfilesAndLocalHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cineva-s1-')
        cls.base = Path(cls.temp.name)
        cls.data = cls.base / 'data'
        cls.media = cls.base / 'videos'
        (cls.media / 'Aile').mkdir(parents=True)
        (cls.media / 'Yetişkin +18').mkdir(parents=True)
        cls.sample_bytes = b'CINEVA_LOCAL_STREAM_BYTES_0123456789'
        (cls.media / 'Aile' / 'Charlie.2021.mp4').write_bytes(cls.sample_bytes)
        (cls.media / 'Yetişkin +18' / 'Gece.Filmi.2024.mp4').write_bytes(b'ADULT_SAMPLE')

        cls.data.mkdir(parents=True)
        (cls.data / 'config.json').write_text(json.dumps({'name': 'Test', 'host': ''}), encoding='utf-8')
        cls.env = {**os.environ, 'AKIS_DATA_DIR': str(cls.data)}
        subprocess.run([sys.executable, '-c', 'import server; server.initialize()'], cwd=ROOT, env=cls.env, check=True, capture_output=True, timeout=15)

        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        cls.log_file = (cls.data / 'server.log').open('wb')
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1', '--port', str(cls.port)],
            cwd=ROOT, env=cls.env, stdout=cls.log_file, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                code, _, payload = cls.req('GET', '/api/health', auth=False)
                if code == 200 and payload.get('ok'):
                    break
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.05)
        else:
            raise RuntimeError('Test server failed to start')
        code, hdrs, _ = cls.req('GET', '/', auth=False, raw=True)
        assert code == 200 and 'set-cookie' in hdrs
        cls.cookie = hdrs['set-cookie'].split(';', 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.log_file.close()
        cls.temp.cleanup()

    @classmethod
    def req(cls, method, path, data=None, *, auth=True, headers=None, raw=False):
        req_headers = dict(headers or {})
        if auth and getattr(cls, 'cookie', None):
            req_headers['Cookie'] = cls.cookie
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            req_headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=15)
        try:
            conn.request(method, path, body=body, headers=req_headers)
            resp = conn.getresponse()
            raw_bytes = resp.read()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            if raw:
                return resp.status, hdrs, raw_bytes
            parsed = json.loads(raw_bytes.decode('utf-8')) if raw_bytes else None
            return resp.status, hdrs, parsed
        finally:
            conn.close()

    def test_1_local_folder_scan_range_stream_and_surprise(self):
        code, _, _ = self.req('POST', '/api/settings', {'type': 'local', 'name': 'Diskim', 'localDir': str(self.media)})
        self.assertEqual(code, 200)

        # Wait for async catalog sync to finish scanning.
        deadline = time.monotonic() + 10
        items = []
        while time.monotonic() < deadline:
            _, _, cat = self.req('GET', '/api/catalog?kind=vod')
            items = cat.get('items', [])
            if len(items) >= 2:
                break
            time.sleep(0.05)
        self.assertEqual({i['name'] for i in items}, {'Charlie', 'Gece Filmi'})
        charlie = next(i for i in items if i['name'] == 'Charlie')

        code, _, play = self.req('POST', '/api/play', {'id': charlie['id'], 'mode': 'direct', 'start': 0})
        self.assertEqual(code, 200)
        stream_url = play['url']

        # Full stream + 206 Partial Content Range check
        code_full, hdrs_full, body_full = self.req('GET', stream_url, raw=True)
        self.assertEqual(code_full, 200)
        self.assertEqual(hdrs_full.get('accept-ranges'), 'bytes')
        self.assertEqual(body_full, self.sample_bytes)

        code_part, hdrs_part, body_part = self.req('GET', stream_url, headers={'Range': 'bytes=0-5'}, raw=True)
        self.assertEqual(code_part, 206)
        self.assertEqual(hdrs_part.get('content-range'), f'bytes 0-5/{len(self.sample_bytes)}')
        self.assertEqual(body_part, self.sample_bytes[:6])

        # Surprise endpoint returns one of the available VOD items.
        code_sup, _, sup = self.req('GET', '/api/surprise')
        self.assertEqual(code_sup, 200)
        self.assertIn(sup['item']['name'], {'Charlie', 'Gece Filmi'})

        # Favorite item in default profile before switching later
        self.req('POST', '/api/favorites', {'id': charlie['id'], 'favorite': True})
        self.__class__.charlie_id = charlie['id']

    def test_2_profiles_pin_isolation_kids_filter_and_rate_limit(self):
        code, _, created = self.req('POST', '/api/profiles', {
            'name': 'Çocuklar', 'avatarColor': '#34C759', 'isKids': True, 'pin': '1234',
        })
        self.assertEqual(code, 201)
        kid_id = created['profile']['id']
        self.assertTrue(created['profile']['hasPin'])
        self.assertTrue(created['profile']['isKids'])

        # PIN must be PBKDF2-hashed (salt_hex:digest_hex) in SQLite, never stored in plaintext.
        with sqlite3.connect(self.data / 'state.sqlite3') as db:
            pin_hash = db.execute('SELECT pin_hash FROM profiles WHERE id=?', (kid_id,)).fetchone()[0]
        self.assertRegex(pin_hash, r'^[0-9a-f]{32}:[0-9a-f]{64}$')
        self.assertNotIn('1234', pin_hash)

        # Wrong PIN fails with 403.
        code_bad, _, err_bad = self.req('POST', '/api/profiles/switch', {'id': kid_id, 'pin': '9999'})
        self.assertEqual(code_bad, 403)
        self.assertIn('PIN', err_bad['error'])

        # Correct PIN switches profile cleanly & clears favorites snapshot from Adult profile.
        code_ok, _, switched = self.req('POST', '/api/profiles/switch', {'id': kid_id, 'pin': '1234'})
        self.assertEqual(code_ok, 200)
        self.assertEqual(switched['profile']['id'], kid_id)

        # Kid profile has empty favorites & filters out adult/18+ items from catalog & home.
        _, _, kid_home = self.req('GET', '/api/home')
        self.assertEqual(kid_home.get('favorites', []), [])
        _, _, kid_cat = self.req('GET', '/api/catalog?kind=vod')
        self.assertEqual([i['name'] for i in kid_cat['items']], ['Charlie'])
        kid_home_names = [i['name'] for i in kid_home.get('recent', [])]
        self.assertNotIn('Gece Filmi', kid_home_names)

        # Switching back to default restores default's favorites AND exposes adult item again.
        code_back, _, _ = self.req('POST', '/api/profiles/switch', {'id': 'default', 'pin': ''})
        self.assertEqual(code_back, 200)
        _, _, def_home = self.req('GET', '/api/home')
        self.assertEqual([i['id'] for i in def_home.get('favorites', [])], [self.__class__.charlie_id])

        # Brute-forcing PIN triggers 429 rate limit after 10 wrong attempts.
        statuses = [self.req('POST', '/api/profiles/switch', {'id': kid_id, 'pin': '0000'})[0] for _ in range(11)]
        self.assertEqual(statuses[:10], [403] * 10)
        self.assertEqual(statuses[10], 429)


if __name__ == '__main__':
    unittest.main()
