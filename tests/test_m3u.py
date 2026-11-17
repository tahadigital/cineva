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
