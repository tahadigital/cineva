import copy
import datetime as dt
import json
import unittest
from pathlib import Path

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
