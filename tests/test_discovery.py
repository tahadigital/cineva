import copy, datetime as dt, json, unittest
from pathlib import Path
import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).parent / 'fixtures/discovery.json').read_text())

    def result(self, history=None, today=dt.date(2026, 11, 6)):
        f = self.fixture
        return discovery.build(f['catalog'], f['history'] if history is None else history, f['feed'], today)

    def test_watch_history_promotes_matching_genres_without_using_provider_categories(self):
        result = self.result()
        row = next(s for s in result['shelves'] if s['id'] == 'for-you-vod')
        self.assertEqual(row['items'][0]['id'], 'vod:comedy')
        self.assertTrue(result['personalized'])
        horror = copy.deepcopy(self.fixture['catalog'][2])
        horror['progress'] = {'position': 1000, 'duration': 1800}
        row = next(s for s in self.result([horror])['shelves'] if s['id'] == 'for-you-vod')
        self.assertNotIn('vod:horror', [i['id'] for i in row['items']])
        comedy = next(s for s in result['shelves'] if s['id'] == 'genre-vod-Comedy')
        self.assertIn('vod:comedy', [i['id'] for i in comedy['items']])

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

    def test_trending_ranking_expires_when_stale_and_has_zero_scraped_brand_names(self):
        rows = self.result()['shelves']
        trending = [s for s in rows if s['id'].startswith('trending-')]
        self.assertEqual(len(trending), 2)
        self.assertNotIn('Netflix', trending[0]['subtitle'])
        stale = self.result(today=dt.date(2026, 12, 1))['shelves']
        self.assertFalse(any(s['id'].startswith('trending-') for s in stale))

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
