"""Tests for Stage 1 features: local media scanner/Range streaming, profiles with PIN/Kid mode, and surprise picker."""
from __future__ import annotations

import http.client
import http.server
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
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
        cls.temp = tempfile.TemporaryDirectory(prefix='mavie-s1-')
        cls.base = Path(cls.temp.name)
        cls.data = cls.base / 'data'
        cls.media = cls.base / 'videos'
        (cls.media / 'Aile').mkdir(parents=True)
        (cls.media / 'Yetişkin +18').mkdir(parents=True)
        cls.sample_bytes = b'MAVIE_LOCAL_STREAM_BYTES_0123456789'
        (cls.media / 'Aile' / 'Charlie.2021.mp4').write_bytes(cls.sample_bytes)
        (cls.media / 'Aile' / 'Charlie.2021.tr.srt').write_text('1\n00:00:00,000 --> 00:00:01,500\nMerhaba Mavie\n', encoding='utf-8')
        (cls.media / 'Yetişkin +18' / 'Gece.Filmi.2024.mp4').write_bytes(b'ADULT_SAMPLE')

        cls.data.mkdir(parents=True)
        (cls.data / 'config.json').write_text(json.dumps({'name': 'Test', 'host': ''}), encoding='utf-8')
        cls.env = {**os.environ, 'MAVIE_DATA_DIR': str(cls.data)}
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

    def test_3_sidecar_srt_tracks_and_play_return_200(self):
        charlie_id = self.__class__.charlie_id
        code_tr, _, tracks = self.req('GET', f'/api/tracks/{charlie_id}')
        self.assertEqual(code_tr, 200)
        ext = tracks.get('externalSubtitles', [])
        self.assertEqual(len(ext), 1)
        self.assertEqual(ext[0]['language'], 'tur')
        self.assertTrue(ext[0]['title'].endswith('.tr.srt'))

        code_play, _, play = self.req('POST', '/api/play', {'id': charlie_id, 'mode': 'direct', 'start': 0})
        self.assertEqual(code_play, 200)
        self.assertEqual(len(play.get('externalSubtitles', [])), 1)
        self.assertEqual(play['externalSubtitles'][0]['language'], 'tur')
        self.req('DELETE', f"/api/play/{play['sessionId']}")

        code_vtt, hdrs_vtt, vtt_body = self.req('GET', ext[0]['url'], raw=True)
        self.assertEqual(code_vtt, 200)
        self.assertIn('text/vtt', hdrs_vtt.get('content-type', ''))
        self.assertIn(b'WEBVTT', vtt_body)
        self.assertIn(b'Merhaba Mavie', vtt_body)

    def test_4_sports_and_multiview_four_slots_are_completely_free_without_account(self):
        import concurrent.futures

        # Sports & EPG works immediately without any account or login
        c_sp, _, _ = self.req('GET', '/api/sports')
        self.assertEqual(c_sp, 200)

        charlie_id = self.__class__.charlie_id

        def play_slot(slot_idx):
            return self.req('POST', '/api/play', {'id': charlie_id, 'mode': 'direct', 'start': 0, 'multiview': True, 'multiviewSlot': slot_idx})

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(play_slot, range(4)))

        for idx, (code, _, body) in enumerate(results):
            self.assertEqual(code, 200, f'Slot {idx} failed with {code}: {body}')

        sids = [body['sessionId'] for _, _, body in results]
        self.assertEqual(len(set(sids)), 4)

        # All 4 Multi-View sessions stay alive simultaneously.
        for idx, sid in enumerate(sids):
            c_ping, _, _ = self.req('POST', f'/api/play/{sid}/ping', {})
            self.assertEqual(c_ping, 200, f'Slot {idx} session {sid} was prematurely stopped')

        # Replacing slot 1 stops only slot 1's prior session while keeping 0, 2, 3 alive.
        c_rep, _, rep_body = self.req('POST', '/api/play', {'id': charlie_id, 'mode': 'direct', 'start': 0, 'multiview': True, 'multiviewSlot': 1})
        self.assertEqual(c_rep, 200)
        new_sid1 = rep_body['sessionId']
        self.assertNotEqual(new_sid1, sids[1])
        self.assertEqual(self.req('POST', f'/api/play/{sids[1]}/ping', {})[0], 410)
        for idx, sid in ((0, sids[0]), (1, new_sid1), (2, sids[2]), (3, sids[3])):
            self.assertEqual(self.req('POST', f'/api/play/{sid}/ping', {})[0], 200, f'Slot {idx} should stay active')

        # Starting a normal single-player session tears down all Multi-View sessions cleanly
        # and still enforces generation supersede for stale single-player requests.
        client_id = 'testclient1234'
        c_single, _, s_body = self.req('POST', '/api/play', {'id': charlie_id, 'mode': 'direct', 'start': 0, 'clientId': client_id, 'generation': 5})
        self.assertEqual(c_single, 200)
        for sid in (sids[0], new_sid1, sids[2], sids[3]):
            self.assertEqual(self.req('POST', f'/api/play/{sid}/ping', {})[0], 410)
        c_stale, _, err_stale = self.req('POST', '/api/play', {'id': charlie_id, 'mode': 'direct', 'start': 0, 'clientId': client_id, 'generation': 4})
        self.assertEqual(c_stale, 409)
        self.assertEqual(err_stale.get('code'), 'superseded')
        self.req('DELETE', f"/api/play/{s_body['sessionId']}")

    def test_5_demo_catalog_valid_urls_and_no_cloud_endpoints(self):
        import m3u
        import server

        self.assertGreaterEqual(len(m3u.DEMO_CATALOG), 4)
        for item in m3u.DEMO_CATALOG:
            for field in ('poster', 'url'):
                val = item.get(field, '')
                self.assertTrue(val.startswith('https://'), f"{item['id']} {field} must be HTTPS: {val}")
                self.assertNotIn('gtv-videos-bucket', val)
                self.assertEqual(server.safe_public_url(val), val)

        c_cloud, _, _ = self.req('GET', '/api/cloud/status')
        self.assertEqual(c_cloud, 404)


if __name__ == '__main__':
    unittest.main()
