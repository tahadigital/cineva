import unittest
import m3u


class M3uAndDemoTests(unittest.TestCase):
    def test_parses_extm3u_playlist_channels_and_movies(self):
        playlist = '''#EXTM3U url-tvg="https://epg.example/guide.xml"
#EXTINF:-1 tvg-id="nasa.us" tvg-logo="https://img.example/nasa.png" group-title="Science",NASA Public TV
https://stream.example/nasa/index.m3u8
#EXTINF:-1 group-title="Open Cinema",Big Buck Bunny
https://cdn.example/bbb.mp4
'''
        parsed = m3u.parse_m3u(playlist)
        self.assertEqual(parsed['epgUrl'], 'https://epg.example/guide.xml')
        self.assertEqual(len(parsed['items']), 2)
        live, vod = parsed['items']
        self.assertEqual(live['kind'], 'live')
        self.assertEqual(live['tvg_id'], 'nasa.us')
        self.assertEqual(vod['kind'], 'vod')
        self.assertEqual(vod['extension'], 'mp4')

    def test_demo_catalog_uses_only_https_open_sources(self):
        self.assertGreaterEqual(len(m3u.DEMO_CATALOG), 4)
        for item in m3u.DEMO_CATALOG:
            self.assertTrue(item['url'].startswith('https://'))
            self.assertTrue(item['poster'].startswith('https://'))

    def test_parses_bom_quoted_commas_and_extensionless_mpegts_and_vod(self):
        long_tvg_name = 'Kanal ' + ('X' * 600)
        playlist = (
            '\ufeff#EXTM3U URL-TVG="https://epg.example/xmltv.php?token=abc&lang=tr"\n'
            '#EXTINF:-1 tvg-id="ch.news" tvg-name="News, Sports" group-title="World, News",TRT Haber HD\n'
            'http://stream.example:8080/get/u1/p1/1001?output=mpegts\n'
            f'#EXTINF:-1 tvg-name="{long_tvg_name}" group-title="Genel"\n'
            'http://stream.example:8080/u1/p1/1002\n'
            '#EXTINF:-1 group-title="Filmler",Ornek Film\n'
            'http://stream.example:8080/movie/u1/p1/5501\n'
            '#EXTINF:-1 type="movie" group-title="Arsiv",Belgesel\n'
            'http://stream.example:8080/vod/u1/p1/5502.mkv?token=fake.m3u8\n'
        )
        parsed = m3u.parse_m3u(playlist)
        self.assertEqual(parsed['epgUrl'], 'https://epg.example/xmltv.php?token=abc&lang=tr')
        self.assertEqual(len(parsed['items']), 4)

        ch1, ch2, vod1, vod2 = parsed['items']
        self.assertEqual(ch1['name'], 'TRT Haber HD')
        self.assertEqual(ch1['category_name'], 'World, News')
        self.assertEqual(ch1['kind'], 'live')
        self.assertEqual(ch1['extension'], 'ts')

        self.assertEqual(len(ch2['name']), 500)
        self.assertEqual(ch2['kind'], 'live')
        self.assertEqual(ch2['extension'], 'ts')

        self.assertEqual(vod1['kind'], 'vod')
        self.assertEqual(vod1['extension'], 'mp4')

        self.assertEqual(vod2['kind'], 'vod')
        self.assertEqual(vod2['extension'], 'mkv')

    def test_duplicate_stream_urls_with_distinct_channels_keep_distinct_ids(self):
        playlist = (
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="ch1",Kanal Bir\n'
            'https://cdn.example/shared.m3u8\n'
            '#EXTINF:-1 tvg-id="ch2",Kanal Iki\n'
            'https://cdn.example/shared.m3u8\n'
        )
        parsed = m3u.parse_m3u(playlist)
        self.assertEqual(len(parsed['items']), 2)
        self.assertNotEqual(parsed['items'][0]['id'], parsed['items'][1]['id'])
