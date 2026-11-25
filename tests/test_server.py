"""HTTP/state integration checks; never uses the configured IPTV account.

Run from the project directory: .venv/bin/python -m unittest discover -s tests -v
Every request goes to an isolated local server with a temporary data directory.
"""
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
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
SECRET_USER = 'test-user-never-return-this'
SECRET_PASSWORD = 'test-password-never-return-this'
FIRST = 'vod:101'
SECOND = 'vod:202'


class _DatabaseConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def _connect(path):
    return sqlite3.connect(path, factory=_DatabaseConnection)


class ServerHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mavie-api-tests-')
        cls.data = Path(cls.temp.name)
        cls.environment = {**os.environ, 'MAVIE_DATA_DIR': str(cls.data)}
        # An empty host disables all provider calls, while sentinel credentials
        # still exercise secret exclusion from HTTP responses and backups.
        cls.config = {
            'name': 'Test hesabı', 'host': '',
            'username': SECRET_USER, 'password': SECRET_PASSWORD,
        }
        (cls.data / 'config.json').write_text(json.dumps(cls.config), encoding='utf-8')
        subprocess.run(
            [sys.executable, '-c', 'import server; server.initialize()'],
            cwd=ROOT, env=cls.environment, check=True, capture_output=True, timeout=15,
        )
        with _connect(cls.data / 'state.sqlite3') as database:
            rows = [
                (FIRST, 'vod', '101', 'Işıklar İçinde (2024)', 'isiklar icinde (2024)', '', 'a', 'Türk Sineması', '2024', 8.5, 'mp4', 200, '{"duration":1000}'),
                (SECOND, 'vod', '202', 'Çığlık Şöleni (2023)', 'ciglik soleni (2023)', '', 'b', 'Gerilim', '2023', 7.2, 'mp4', 100, '{"duration":2000}'),
            ]
            database.executemany('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        cls.origin = f'http://127.0.0.1:{cls.port}'
        cls.log_file = (cls.data / 'test-server.log').open('wb')
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1', '--port', str(cls.port)],
            cwd=ROOT, env=cls.environment, stdout=cls.log_file, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if cls.process.poll() is not None:
                    raise RuntimeError('Isolated test server exited before becoming ready.')
                try:
                    code, _, payload = cls.request('GET', '/api/health', auth=False)
                    if code == 200 and payload == {'app': 'mavie', 'ok': True}:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.05)
            else:
                raise RuntimeError('Isolated test server did not start in time.')
            code, headers, _ = cls.request('GET', '/', auth=False)
            if code != 200 or 'set-cookie' not in headers:
                raise RuntimeError('Loopback bootstrap did not issue a device cookie.')
            cls.cookie = headers['set-cookie'].split(';', 1)[0]
        except BaseException:
            cls.process.terminate()
            cls.process.wait(timeout=10)
            cls.log_file.close()
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)
        cls.log_file.close()
        cls.temp.cleanup()

    @classmethod
    def request(cls, method, path, data=None, *, auth=True, headers=None):
        request_headers = {}
        if auth and getattr(cls, 'cookie', None):
            request_headers['Cookie'] = cls.cookie
        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            request_headers['Content-Type'] = 'application/json'
        if headers:
            request_headers.update(headers)
        connection = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            response_headers = {k.lower(): v for k, v in response.getheaders()}
            if response_headers.get('content-type', '').startswith('application/json'):
                payload = json.loads(raw)
            else:
                payload = raw
            return response.status, response_headers, payload
        finally:
            connection.close()

    def setUp(self):
        with _connect(self.data / 'state.sqlite3') as database:
            database.execute('PRAGMA foreign_keys=ON')
            for table in ('favorites', 'progress', 'playlists'):
                database.execute('DELETE FROM ' + table)

    def api(self, method, path, data=None, expected=200, **kwargs):
        status, headers, payload = self.request(method, path, data, **kwargs)
        self.assertEqual(status, expected, (method, path, status, payload))
        return payload

    def saved_state(self):
        payload = self.api('GET', '/api/export')
        return {key: value for key, value in payload.items() if key != 'exportedAt'}

    def make_playlist(self, name='İzlenecekler'):
        return self.api('POST', '/api/playlists', {'name': name}, expected=201)['id']

    def playlist(self, playlist_id):
        return next(p for p in self.api('GET', '/api/playlists')['playlists'] if p['id'] == playlist_id)

    def resume_episodes(self, count=9):
        rows = []
        for n in range(1, count + 1):
            extra = {'parentId': 'series:resume', 'seriesName': 'Gibi',
                     'season': 1 if n < count else 2, 'episode': n if n < count else 1}
            rows.append((f'episode:resume{n}', 'episode', f'resume{n}', f'Gibi {n}', f'gibi {n}',
                         '', '', '', '', 0, 'mp4', 0, json.dumps(extra)))
        with _connect(self.data / 'state.sqlite3') as database:
            database.executemany('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        def clean():
            with _connect(self.data / 'state.sqlite3') as database:
                database.execute("DELETE FROM progress WHERE item_id LIKE 'episode:resume%'")
                database.execute("DELETE FROM items WHERE id LIKE 'episode:resume%'")
        self.addCleanup(clean)

    def watch_resume(self, n, position=500, completed=False):
        self.api('POST', '/api/progress', {'id': f'episode:resume{n}', 'position': position,
                                         'duration': 1000, 'completed': completed})

    def test_continue_watching_has_only_the_latest_episode_even_just_started(self):
        self.resume_episodes()
        for n in (6, 7): self.watch_resume(n)
        self.watch_resume(8, position=2)
        items = self.api('GET', '/api/home')['continueWatching']
        self.assertEqual([i['id'] for i in items], ['episode:resume8'])
        self.assertEqual(items[0]['progress']['position'], 2)
        # The earlier episode records remain available in the series details.
        self.assertEqual(len(self.api('GET', '/api/progress')['items']), 3)

    def test_completed_latest_episode_offers_next_season(self):
        self.resume_episodes()
        self.watch_resume(6)
        self.watch_resume(8, completed=True)
        items = self.api('GET', '/api/home')['continueWatching']
        self.assertEqual([i['id'] for i in items], ['episode:resume9'])
        self.assertEqual(items[0]['continueReason'], 'nextEpisode')
        self.assertEqual((items[0]['season'], items[0]['episode']), (2, 1))
        self.assertIsNone(items[0]['progress'])

    def test_finished_series_does_not_resurrect_older_unfinished_episodes(self):
        self.resume_episodes()
        self.watch_resume(6)
        self.watch_resume(9, completed=True)
        self.assertEqual(self.api('GET', '/api/home')['continueWatching'], [])

    def test_rewatch_uses_latest_activity_rather_than_highest_episode_number(self):
        self.resume_episodes()
        self.watch_resume(8)
        self.watch_resume(6, position=100)
        self.assertEqual([i['id'] for i in self.api('GET', '/api/home')['continueWatching']], ['episode:resume6'])

    def test_continue_limit_applies_after_series_grouping(self):
        self.resume_episodes(count=28)
        self.api('POST', '/api/progress', {'id': FIRST, 'position': 100, 'duration': 1000})
        for n in range(1, 28): self.watch_resume(n)
        self.assertEqual([i['id'] for i in self.api('GET', '/api/home')['continueWatching']], ['episode:resume27', FIRST])

    def test_home_keeps_a_series_row_when_the_latest_additions_are_films(self):
        extra = {'plot': 'Dizi açıklaması', 'backdrop': 'https://example.com/backdrop.jpg'}
        film_rows = [(f'vod:home{i}', 'vod', f'home{i}', f'Film {i}', f'film {i}', '', '', '',
                      '2026', 6, 'mp4', 1000 + i, '{}') for i in range(25)]
        series_row = ('series:home', 'series', 'home', 'Bir Dizi', 'bir dizi', '', '', '',
                      '2024', 6, 'mp4', 1, json.dumps(extra))

        def clean():
            with _connect(self.data / 'state.sqlite3') as database:
                database.execute("DELETE FROM items WHERE id LIKE 'vod:home%' OR id='series:home'")

        self.addCleanup(clean)
        with _connect(self.data / 'state.sqlite3') as database:
            database.executemany('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', [*film_rows, series_row])
        recent = self.api('GET', '/api/home')['recent']
        self.assertEqual(sum(item['kind'] == 'vod' for item in recent), 12)
        series = [item for item in recent if item['kind'] == 'series']
        self.assertEqual([item['id'] for item in series], ['series:home'])
        self.assertEqual({key: series[0][key] for key in extra}, extra)

    def test_saved_episode_metadata_roundtrips_without_loading_series_catalog(self):
        episode = {'id': 'episode:9911', 'providerId': '9911', 'kind': 'episode', 'name': 'Yeni Dizi - S01E02',
                   'parentId': 'series:900', 'extension': 'mkv', 'durationSeconds': 1800, 'season': 1, 'episode': 2,
                   'poster': 'https://example.com/poster.jpg', 'username': 'ignored', 'password': 'ignored'}
        self.api('POST', '/api/import', {'data': {'version': 1, 'items': [episode], 'progress': [
            {'item_id': episode['id'], 'position': 123, 'duration': 1800}]}})
        home = self.api('GET', '/api/home')
        saved = next(item for item in home['continueWatching'] if item['id'] == episode['id'])
        self.assertEqual(saved['progress']['position'], 123)
        exported = self.api('GET', '/api/export')
        portable = next(item for item in exported['items'] if item['id'] == episode['id'])
        self.assertEqual(portable['parentId'], 'series:900')
        self.assertEqual(portable['poster'], episode['poster'])
        self.assertNotIn('password', portable)
        self.assertNotIn('username', portable)
        before = self.saved_state()
        self.api('POST', '/api/import', {'data': {'version': 1, 'items': [{**episode, 'id': 'episode:unsafe/value'}],
            'favorites': [{'item_id': FIRST}]}}, expected=400)
        self.assertEqual(before, self.saved_state())

    def test_unauthorized_api_does_not_expose_catalog_or_secrets(self):
        self.assertEqual(self.api('GET', '/api/health', auth=False), {'app': 'mavie', 'ok': True})
        status = self.api('GET', '/api/status', auth=False)
        self.assertEqual(status, {'authorized': False, 'pairingRequired': True})
        for route in ('/api/home', '/api/catalog', '/api/export', '/api/favorites', '/api/progress', '/api/playlists', '/media/fake/index.m3u8'):
            with self.subTest(route=route):
                payload = self.api('GET', route, auth=False, expected=401)
                self.assertNotIn('pairingCode', payload)
        self.api('POST', '/api/favorites', {'id': FIRST}, auth=False, expected=401)
        self.assertEqual(self.api('GET', '/api/favorites')['items'], [])

    def test_pairing_issues_private_cookie_and_rejects_wrong_code(self):
        status = self.api('GET', '/api/status')
        code = status['pairingCode']
        self.assertRegex(code, r'^\d{6}$')
        wrong = '000000' if code != '000000' else '000001'
        self.api('POST', '/api/pair', {'code': wrong}, auth=False, expected=403, headers={'Origin': self.origin})
        response_code, headers, payload = self.request('POST', '/api/pair', {'code': code}, auth=False, headers={'Origin': self.origin})
        self.assertEqual(response_code, 200)
        self.assertEqual(payload, {'ok': True})
        cookie = headers['set-cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertIn('Path=/', cookie)
        paired_status = self.api('GET', '/api/status', auth=False, headers={'Cookie': cookie.split(';', 1)[0]})
        self.assertTrue(paired_status['authorized'])
        with _connect(self.data / 'state.sqlite3') as database:
            hashes = [row[0] for row in database.execute('SELECT token_hash FROM devices')]
        self.assertNotIn(cookie.split(';', 1)[0].split('=', 1)[1], hashes)
        self.assertTrue(all(len(digest) == 64 for digest in hashes))

    def test_cross_origin_mutations_and_untrusted_host_are_rejected(self):
        evil = {'Origin': 'http://untrusted.example'}
        self.api('POST', '/api/favorites', {'id': FIRST}, headers=evil, expected=403)
        pid = self.make_playlist()
        self.api('PATCH', '/api/playlists/' + pid, {'name': 'Değişmemeli'}, headers=evil, expected=403)
        self.api('DELETE', '/api/playlists/' + pid, headers=evil, expected=403)
        self.assertEqual(self.playlist(pid)['name'], 'İzlenecekler')
        self.assertEqual(self.api('GET', '/api/favorites')['items'], [])
        self.api('GET', '/api/health', auth=False, headers={'Host': 'untrusted.example'}, expected=403)
        status = self.api('GET', '/api/status')
        self.api('POST', '/api/pair', {'code': status['pairingCode']}, auth=False, headers=evil, expected=403)
        self.api('POST', '/api/favorites', {'id': FIRST}, headers={'Origin': self.origin})

    def test_ipv6_loopback_host_is_valid_on_local_connection(self):
        payload = self.api('GET', '/api/health', auth=False, headers={'Host': f'[::1]:{self.port}'})
        self.assertEqual(payload, {'app': 'mavie', 'ok': True})
        self.api('GET', '/api/health', auth=False, headers={'Host': '[::1'}, expected=403)

    def test_z_demo_endpoint_populates_open_library_and_legal_notice(self):
        self.assertEqual(self.api('GET', '/api/legal')['app'], 'Mavie')
        res = self.api('POST', '/api/demo', {})
        self.assertEqual(res, {'ok': True})
        status = self.api('GET', '/api/status')
        self.assertTrue(status['configured'])
        self.assertEqual(status['connection']['type'], 'demo')
        catalog = self.api('GET', '/api/catalog?kind=vod')
        self.assertGreaterEqual(catalog['total'], 4)

    def test_unhashable_reorder_entries_return_bad_request_and_rollback(self):
        pid = self.make_playlist()
        route = '/api/playlists/' + pid
        for iid in (FIRST, SECOND):
            self.api('PATCH', route, {'itemId': iid})
        self.api('PATCH', route, {'name': 'Kaydedilmemeli', 'order': [FIRST, {}]}, expected=400)
        current = self.playlist(pid)
        self.assertEqual(current['name'], 'İzlenecekler')
        self.assertEqual([item['id'] for item in current['items']], [FIRST, SECOND])

    def test_configuration_is_not_returned_exported_or_served(self):
        self.api('POST', '/api/favorites', {'id': FIRST})
        for route in ('/api/status', '/api/home', '/api/catalog', '/api/favorites', '/api/export'):
            with self.subTest(route=route):
                raw = json.dumps(self.api('GET', route), ensure_ascii=False)
                self.assertNotIn(SECRET_USER, raw)
                self.assertNotIn(SECRET_PASSWORD, raw)
        exported = self.api('GET', '/api/export')
        self.assertNotIn('config', exported)
        self.assertNotIn('devices', exported)
        for route in ('/data/config.json', '/config.json', '/%2e%2e/server.py', '/..%2fdata/config.json', '/%2e%2e%2f%2e%2e%2fetc/passwd'):
            with self.subTest(route=route):
                self.api('GET', route, auth=False, expected=404)

    def test_favorites_and_progress_round_trip_and_clamping(self):
        self.api('POST', '/api/favorites', {'id': FIRST})
        self.api('POST', '/api/favorites', {'id': FIRST})
        favorites = self.api('GET', '/api/favorites')['items']
        self.assertEqual([item['id'] for item in favorites], [FIRST])
        self.assertTrue(favorites[0]['favorite'])
        self.api('POST', '/api/favorites', {'id': 'vod:missing'}, expected=400)
        self.api('POST', '/api/progress', {'id': FIRST, 'position': 125, 'duration': 1000})
        progress = self.api('GET', '/api/progress')['items'][0]['progress']
        self.assertEqual((progress['position'], progress['duration'], progress['completed']), (125, 1000, False))
        self.assertEqual([item['id'] for item in self.api('GET', '/api/home')['continueWatching']], [FIRST])
        self.api('POST', '/api/progress', {'id': FIRST, 'position': 5000, 'duration': 1000})
        progress = self.api('GET', '/api/progress')['items'][0]['progress']
        self.assertEqual((progress['position'], progress['duration'], progress['completed']), (1000, 1000, True))
        self.assertEqual(self.api('GET', '/api/home')['continueWatching'], [])
        self.api('POST', '/api/progress', {'id': FIRST, 'position': -50, 'duration': -20})
        progress = self.api('GET', '/api/progress')['items'][0]['progress']
        self.assertEqual((progress['position'], progress['duration']), (0, 0))
        self.api('DELETE', '/api/progress/' + FIRST)
        self.api('POST', '/api/favorites', {'id': FIRST, 'favorite': False})
        self.assertEqual(self.api('GET', '/api/progress')['items'], [])
        self.assertEqual(self.api('GET', '/api/favorites')['items'], [])

    def test_closed_playback_session_cannot_overwrite_saved_progress(self):
        self.api('POST', '/api/progress', {'id': FIRST, 'position': 25, 'duration': 100})
        before = self.api('GET', '/api/progress')['items']
        self.api('POST', '/api/progress', {
            'id': FIRST, 'position': 60, 'duration': 100, 'sessionId': 'closed-session',
        }, expected=410)
        self.assertEqual(self.api('GET', '/api/progress')['items'], before)

    def test_playlist_crud_reordering_and_failed_patch_are_atomic(self):
        self.api('POST', '/api/playlists', {'name': '  '}, expected=400)
        pid = self.make_playlist()
        route = '/api/playlists/' + pid
        for iid in (FIRST, SECOND, FIRST):
            self.api('PATCH', route, {'itemId': iid})
        self.assertEqual(self.playlist(pid)['count'], 2)
        self.api('PATCH', route, {'name': 'Hafta sonu', 'order': [SECOND, FIRST]})
        current = self.playlist(pid)
        self.assertEqual(current['name'], 'Hafta sonu')
        self.assertEqual([item['id'] for item in current['items']], [SECOND, FIRST])
        self.api('PATCH', route, {'name': 'Kaydedilmemeli', 'order': [FIRST]}, expected=400)
        current = self.playlist(pid)
        self.assertEqual(current['name'], 'Hafta sonu')
        self.assertEqual([item['id'] for item in current['items']], [SECOND, FIRST])
        self.api('PATCH', route, {'removeItemId': SECOND})
        self.assertEqual([item['id'] for item in self.playlist(pid)['items']], [FIRST])
        self.api('DELETE', route)
        self.assertEqual(self.api('GET', '/api/playlists')['playlists'], [])
        self.assertEqual(self.api('GET', '/api/export')['playlistItems'], [])

    def test_import_merges_state_ignores_config_and_invalid_import_rolls_back(self):
        self.api('POST', '/api/favorites', {'id': FIRST})
        self.api('POST', '/api/progress', {'id': FIRST, 'position': 40, 'duration': 1000})
        before = self.saved_state()
        bad = {'version': 1, 'favorites': [{'item_id': SECOND}, {}]}
        self.api('POST', '/api/import', {'data': bad}, expected=400)
        self.assertEqual(self.saved_state(), before)
        imported = {
            'version': 1,
            'favorites': [{'item_id': SECOND}],
            'progress': [{'item_id': SECOND, 'position': 3000, 'duration': 2000, 'completed': True}],
            'playlists': [{'id': 'imported-list', 'name': 'İçe aktarılanlar'}],
            'playlistItems': [
                {'playlist_id': 'imported-list', 'item_id': FIRST, 'position': 1},
                {'playlist_id': 'imported-list', 'item_id': SECOND, 'position': 0},
            ],
            'config': {'host': 'https://untrusted.example', 'username': 'overwrite', 'password': 'overwrite'},
        }
        self.api('POST', '/api/import', {'data': imported})
        self.assertEqual({item['id'] for item in self.api('GET', '/api/favorites')['items']}, {FIRST, SECOND})
        self.assertEqual([item['id'] for item in self.playlist('imported-list')['items']], [SECOND, FIRST])
        second = next(item for item in self.api('GET', '/api/progress')['items'] if item['id'] == SECOND)
        self.assertEqual(second['progress']['position'], 2000)
        self.assertTrue(second['progress']['completed'])
        # Older imported timestamps must not overwrite newer local progress.
        self.api('POST', '/api/import', {'data': {'version': 1, 'progress': [
            {'item_id': FIRST, 'position': 10, 'duration': 1000, 'completed': False, 'updated_at': '2020-01-01T00:00:00+00:00'}
        ]}})
        first = next(item for item in self.api('GET', '/api/progress')['items'] if item['id'] == FIRST)
        self.assertEqual(first['progress']['position'], 40)
        # Newer imported timestamps update progress and preserve their timestamp.
        self.api('POST', '/api/import', {'data': {'version': 1, 'progress': [
            {'item_id': FIRST, 'position': 750, 'duration': 1000, 'completed': False, 'updated_at': '2099-01-01T12:00:00+00:00'}
        ]}})
        first = next(item for item in self.api('GET', '/api/progress')['items'] if item['id'] == FIRST)
        self.assertEqual(first['progress']['position'], 750)
        self.assertEqual(first['progress']['updatedAt'], '2099-01-01T12:00:00+00:00')
        self.assertEqual(json.loads((self.data / 'config.json').read_text()), self.config)
        self.api('POST', '/api/import', {'data': {'version': 2}}, expected=400)

    def test_turkish_search_literal_wildcards_and_pagination(self):
        for query, expected in (('ISIKLAR', FIRST), ('ışıklar', FIRST), ('İÇİNDE', FIRST), ('ciglik soleni', SECOND), ('ÇIĞLIK', SECOND)):
            with self.subTest(query=query):
                result = self.api('GET', '/api/catalog?' + urlencode({'kind': 'vod', 'q': query}))
                self.assertEqual([item['id'] for item in result['items']], [expected])
        for query in ('%', '_', "' OR 1=1--"):
            result = self.api('GET', '/api/catalog?' + urlencode({'kind': 'vod', 'q': query}))
            self.assertEqual(result['total'], 0)
        result = self.api('GET', '/api/catalog?kind=vod&limit=1&page=99')
        self.assertEqual((result['total'], result['pages'], result['page']), (2, 2, 2))
        self.assertEqual([item['id'] for item in result['items']], [SECOND])
        result = self.api('GET', '/api/catalog?kind=vod&category=a')
        self.assertEqual([item['id'] for item in result['items']], [FIRST])

    def test_host_header_with_userinfo_at_or_whitespace_rejected_403(self):
        for bad_host in (
            f'evil.com@127.0.0.1:{self.port}',
            f'127.0.0.1:{self.port} @evil',
            f'127.0.0.1:{self.port}/evil',
        ):
            with self.subTest(bad_host=bad_host):
                self.api('GET', '/api/health', auth=False, headers={'Host': bad_host}, expected=403)

    def test_put_returns_json_405_with_security_headers_and_empty_play_delete_400(self):
        st, hdrs, payload = self.request('PUT', '/api/settings', {})
        self.assertEqual(st, 405)
        self.assertEqual(payload.get('error_code'), 'method_not_allowed')
        self.assertEqual(hdrs.get('x-content-type-options'), 'nosniff')
        self.assertEqual(hdrs.get('x-frame-options'), 'DENY')
        self.assertIn('POST', hdrs.get('allow', ''))

        st_del, _, payload_del = self.request('DELETE', '/api/play/')
        self.assertEqual(st_del, 400)
        self.assertEqual(payload_del.get('error_code'), 'invalid_session')

        st_img, _, _ = self.request('GET', '/api/image?url=' + urlencode({'u': 'ftp://bad.example/a.png'}).split('=', 1)[1])
        self.assertEqual(st_img, 400)

    def test_home_cache_invalidates_on_profile_switch_and_detail_extra_update(self):
        created = self.api('POST', '/api/profiles', {'name': 'CacheP2', 'isKids': False}, expected=201)['profile']
        p2_id = created['id']

        def cleanup():
            self.request('POST', '/api/profiles/switch', {'id': 'default', 'pin': ''})
            self.request('DELETE', f'/api/profiles/{p2_id}')
            with _connect(self.data / 'state.sqlite3') as database:
                database.execute("UPDATE items SET extra='{\"duration\":1000}' WHERE id=?", (FIRST,))

        self.addCleanup(cleanup)

        # Warm /api/home on default, then update items.extra directly in SQLite (simulating detail() metadata enrichment)
        h1 = self.api('GET', '/api/home')
        with _connect(self.data / 'state.sqlite3') as database:
            database.execute(
                'UPDATE items SET extra=? WHERE id=?',
                (json.dumps({'duration': 1000, 'plot': 'Güncel Özet', 'backdrop': 'https://example.com/bd.jpg'}), FIRST),
            )
        h2 = self.api('GET', '/api/home')
        rec = next(i for i in h2['recent'] if i['id'] == FIRST)
        self.assertEqual(rec.get('plot'), 'Güncel Özet')
        shelf_items = [i for s in h2.get('discovery', {}).get('shelves', []) for i in s.get('items', []) if i['id'] == FIRST]
        if shelf_items:
            self.assertEqual(shelf_items[0].get('plot'), 'Güncel Özet')
        self.assertIsNotNone(h1)

        # Profile switch invalidates _home_cache even with identical library/empty history
        self.api('POST', '/api/profiles/switch', {'id': p2_id, 'pin': ''})
        h3 = self.api('GET', '/api/home')
        self.assertIn('discovery', h3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
