import copy
import datetime as dt
import gzip
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).parent / 'fixtures/discovery.json').read_text())

    def result(self, history=None, today=dt.date(2026, 11, 6)):
        f = self.fixture
        return discovery.build(f['catalog'], f['history'] if history is None else history, f['feed'], today)

    def test_watch_history_promotes_matching_genres_and_orders_genre_shelves_by_affinity(self):
        result = self.result()
        row = next(s for s in result['shelves'] if s['id'] == 'for-you-vod')
        self.assertEqual(row['items'][0]['id'], 'vod:comedy')
        self.assertTrue(result['personalized'])
        self.assertIn('Komedi', result['topGenres'])

        # Watched genre (Comedy) must be promoted ahead of unwatched genres (Horror)
        genre_shelves = [s for s in result['shelves'] if s['id'].startswith('genre-vod-')]
        self.assertEqual(genre_shelves[0]['id'], 'genre-vod-Comedy')
        self.assertIn('öne çıkarıldı', genre_shelves[0]['subtitle'])
        self.assertEqual(genre_shelves[1]['id'], 'genre-vod-Horror')
        self.assertEqual(genre_shelves[1]['subtitle'], '')

        horror = copy.deepcopy(self.fixture['catalog'][2])
        horror['progress'] = {'position': 1000, 'duration': 1800}
        row = next(s for s in self.result([horror])['shelves'] if s['id'] == 'for-you-vod')
        self.assertNotIn('vod:horror', [i['id'] for i in row['items']])

    def test_showcase_has_both_kinds_and_excludes_future_releases(self):
        result = self.result()
        self.assertEqual({i['kind'] for i in result['showcase']}, {'vod', 'series'})
        ids = {i['id'] for i in result['showcase']}
        self.assertFalse(ids & {'vod:future', 'vod:upcoming', 'vod:remake'})

    def test_all_recommendations_are_real_local_ids_and_do_not_merge_remakes(self):
        result = self.result()
        valid = {i['id'] for i in self.fixture['catalog']}
        for shelf in result['shelves']:
            self.assertTrue({i['id'] for i in shelf['items']} <= valid)
        genres = next(s for s in result['shelves'] if s['id'] == 'genre-vod-Comedy')
        self.assertNotIn('vod:remake', [i['id'] for i in genres['items']])

    def test_netflix_turkey_top10_shelf_and_expiry(self):
        rows = self.result()['shelves']
        turkey = [s for s in rows if s['id'].startswith('turkey-')]
        self.assertEqual(len(turkey), 2)
        self.assertIn('Türkiye’de Popüler', turkey[0]['title'])
        self.assertIn('Netflix Türkiye Top 10', turkey[0]['subtitle'])
        stale = self.result(today=dt.date(2026, 12, 1))['shelves']
        self.assertFalse(any(s['id'].startswith('turkey-') for s in stale))

    def test_netflix_entries_parser_extracts_movies_and_series(self):
        payload = json.dumps({
            'data': {
                'a': {
                    'top10Video': {'title': 'Never Surrender', 'releaseYear': 2026, 'videoId': 81996126},
                    'top10': {'category': 'MOVIES', 'weeklyRank': 1, 'weekEndDate': '2026-11-15'},
                },
                'b': {
                    'top10Video': {
                        'title': 'Season 1',
                        'releaseYear': 2020,
                        'videoId': 999,
                        'parentShow': {'title': 'Ethos', 'videoId': 81205319},
                    },
                    'top10': {'category': 'TV', 'weeklyRank': 2, 'weekEndDate': '2026-11-15'},
                },
            }
        }).replace("'", "\\'")
        html = f"<script>netflix.reactContext.models.graphql = JSON.parse('{payload}');</script>"
        entries = discovery.netflix_entries(html)
        self.assertEqual(len(entries), 2)
        by_kind = {e['kind']: e for e in entries}
        self.assertEqual(by_kind['vod']['name'], 'Never Surrender')
        self.assertEqual(by_kind['vod']['netflixId'], 81996126)
        self.assertEqual(by_kind['series']['name'], 'Ethos')
        self.assertEqual(by_kind['series']['netflixId'], 81205319)

    def test_turkish_plural_genre_aliases_normalize_cleanly(self):
        self.assertEqual(discovery.genres({'genre': 'Dramalar, Komediler, Bilim Kurgu ve Fantastik'}), ('Drama', 'Comedy', 'Sci-Fi'))

    def test_empty_history_uses_honest_nonpersonalized_labels(self):
        result = self.result([])
        self.assertFalse(result['personalized'])
        self.assertTrue(any(s['title'].startswith('Keşfet:') for s in result['shelves']))

    def test_tmdb_parser_normalizes_movies_and_series_cleanly(self):
        parsed = discovery.parse_tmdb_results([
            {'id': 42, 'media_type': 'movie', 'title': 'Örnek Film', 'original_title': 'Sample Movie', 'release_date': '2026-03-01', 'genre_ids': [35]},
            {'id': 99, 'media_type': 'tv', 'name': 'Örnek Dizi', 'original_name': 'Sample Show', 'first_air_date': '2026-04-10', 'genre_ids': [18]},
        ], 'movie')
        self.assertEqual([p['kind'] for p in parsed], ['vod', 'series'])
        self.assertEqual(parsed[0]['genres'], ['Comedy'])
        self.assertEqual(parsed[1]['year'], '2026')

    def test_get_handles_case_insensitive_gzip_bad_utf8_and_transient_retries(self):
        attempts = {'count': 0}

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_args): pass
            def do_GET(self):
                attempts['count'] += 1
                if self.path == '/flaky':
                    if attempts['count'] == 1:
                        self.send_response(503)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if attempts['count'] == 2:
                        self.send_response(200)
                        self.send_header('Transfer-Encoding', 'chunked')
                        self.end_headers()
                        # Truncated chunk triggers IncompleteRead
                        self.wfile.write(b'10\r\n{"partial":')
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    body = gzip.compress(b'{"ok":true,"text":"' + b'\xff' + b'"}')
                    self.send_response(200)
                    self.send_header('Content-Encoding', 'GZIP')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == '/magic-gzip':
                    body = gzip.compress(b'{"magic":true}')
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

        srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        srv.daemon_threads = True
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with patch.object(discovery.time, 'sleep'):
                text = discovery.get(f'http://127.0.0.1:{srv.server_port}/flaky', timeout=3, retries=2)
                self.assertEqual(attempts['count'], 3)
                parsed = json.loads(text)
                self.assertTrue(parsed['ok'])
                self.assertIn('\ufffd', parsed['text'])

                magic = json.loads(discovery.get(f'http://127.0.0.1:{srv.server_port}/magic-gzip', timeout=3))
                self.assertTrue(magic['magic'])
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=2)

    def test_transient_refresh_failure_backs_off_shortly_instead_of_900s(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(discovery, '_memory', None), \
                 patch.object(discovery, '_running', False), \
                 patch.object(discovery, '_attempt', 0), \
                 patch.object(discovery, '_consecutive_failures', 0), \
                 patch.object(discovery, '_next_retry_at', 0.0), \
                 patch.object(discovery, 'get', side_effect=http.client.RemoteDisconnected('closed')):
                discovery.refresh(tmp)
                self.assertEqual(discovery._consecutive_failures, 1)
                remaining = discovery._next_retry_at - time.time()
                self.assertGreater(remaining, 0)
                self.assertLessEqual(remaining, 20.0)
                self.assertFalse(discovery._running)

    def test_build_handles_malformed_and_none_chart_weeks_without_crashing(self):
        feed = {
            'updatedAt': 1700000000,
            'metas': copy.deepcopy(self.fixture['feed']['metas']),
            'charts': [
                None,
                {'name': 'Bad1', 'kind': 'vod', 'rank': 1, 'week': None},
                {'name': 'Bad2', 'kind': 'vod', 'rank': 2, 'week': 'not-a-date'},
                *copy.deepcopy(self.fixture['feed']['charts']),
            ],
        }
        result = discovery.build(self.fixture['catalog'], [], feed, dt.date(2026, 11, 6))
        self.assertIn('shelves', result)
        self.assertTrue(len(result['shelves']) >= 1)

    def test_snapshot_isolates_multiple_directories_and_concurrent_refresh_writes(self):
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            dir_a, dir_b = Path(tmp_a), Path(tmp_b)
            (dir_a / 'discovery-public.json').write_text(json.dumps({'updatedAt': time.time(), 'metas': [{'id': 'a1'}]}), encoding='utf-8')
            (dir_b / 'discovery-public.json').write_text(json.dumps({'updatedAt': time.time(), 'metas': [{'id': 'b1'}]}), encoding='utf-8')
            snap_a = discovery.snapshot(dir_a, enabled=False)
            snap_b = discovery.snapshot(dir_b, enabled=False)
            self.assertEqual(snap_a['metas'], [{'id': 'a1'}])
            self.assertEqual(snap_b['metas'], [{'id': 'b1'}])

            sample_cm = json.dumps({'metas': [{'id': 'tt1', 'name': 'Film 1', 'year': '2026', 'genres': ['Drama']}]})
            with patch.object(discovery, 'get', return_value=sample_cm), \
                 patch.object(discovery, 'netflix_entries', return_value=[]):
                errors = []
                def worker():
                    try:
                        discovery.refresh(dir_a)
                    except BaseException as exc:
                        errors.append(exc)
                threads = [threading.Thread(target=worker) for _ in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5.0)
                self.assertEqual(errors, [])
                saved = json.loads((dir_a / 'discovery-public.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['version'], 3)

    def test_daemon_map_uses_daemon_threads_preserves_order_and_isolates_errors(self):
        seen_daemon = []

        def work(x):
            seen_daemon.append(threading.current_thread().daemon)
            if x == 2:
                raise RuntimeError('boom')
            return x * 10

        out = discovery._daemon_map(work, [1, 2, 3, 4], max_workers=2)
        self.assertEqual([ok for ok, _ in out], [True, False, True, True])
        self.assertEqual(out[0][1], 10)
        self.assertIsInstance(out[1][1], RuntimeError)
        self.assertEqual(out[2][1], 30)
        self.assertEqual(out[3][1], 40)
        self.assertTrue(all(seen_daemon))
