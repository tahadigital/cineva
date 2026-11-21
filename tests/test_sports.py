import datetime as dt
import gzip
import io
import json
import unittest
from unittest.mock import patch

import sports

DAY = dt.date(2026, 11, 3)

SAMPLE_XMLTV = b'''<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="ch1">
    <display-name>Public Sports 1</display-name>
  </channel>
  <channel id="ch2">
    <display-name>World News</display-name>
  </channel>
  <programme start="20261103204500 +0300" stop="20261103224500 +0300" channel="ch1">
    <title>City vs United</title>
    <category>Football</category>
    <category>Champions League</category>
  </programme>
  <programme start="20261103183000 +0300" stop="20261103193000 +0300" channel="ch2">
    <title>Evening News</title>
    <category>News</category>
  </programme>
  <programme start="20261104120000 +0300" stop="20261104130000 +0300" channel="ch2">
    <title>Next Day Show</title>
    <category>News</category>
  </programme>
</tv>'''

SAMPLE_SPOREKRANI_MODERN = (
    '<html><script>window.__INITIAL_STATE__='
    + json.dumps({
        'common': {
            'eventChannels': {
                '10': {'id': 10, 'name': 'Bein Sports 1', 'active': 1},
                '11': {'id': 11, 'name': 'S Sport 1', 'active': 1},
                '12': {'id': 12, 'name': 'Yayın Yok', 'active': 1},
                '13': {'id': 13, 'name': 'Smart Spor HD', 'active': 0},
            },
            'eventRows': [
                {
                    'id': 100,
                    'sport_name': 'Programlar',
                    'league_name': 'Spor Programı',
                    'event_type_name': 'commentary',
                    'name': 'Spor Artı',
                    'date_time': '2026-11-03 18:00:00',
                    'channels': [10],
                    'featured': 0,
                },
                {
                    'id': 101,
                    'sport_name': 'Futbol',
                    'league_name': 'UEFA Şampiyonlar Ligi',
                    'event_type_name': 'match',
                    'name': 'Galatasaray - Bayern',
                    'post_fix': 'Canlı',
                    'date_time': '2026-11-03 20:45:00',
                    'channels': [10, 12],
                    'featured': 1,
                },
                {
                    'id': 102,
                    'sport_name': 'Basketbol',
                    'league_name': 'EuroLeague',
                    'event_type_name': 'match',
                    'name': 'Fenerbahçe Beko - Real Madrid',
                    'date_time': '2026-11-03 19:30:00',
                    'channels': [11, 13],
                    'featured': 0,
                },
                {
                    'id': 103,
                    'sport_name': 'Futbol',
                    'league_name': 'Süper Lig',
                    'event_type_name': 'commentary',
                    'name': 'Basın Toplantısı',
                    'date_time': '2026-11-03 15:00:00',
                    'channels': [10],
                    'featured': 0,
                },
            ],
        }
    })
    + '</script></html>'
).encode('utf-8')

SAMPLE_SPOREKRANI_LEGACY = (
    '<html><script>window.__INITIAL_STATE__='
    + json.dumps({
        'common': {
            'events': [
                {
                    'id': 201,
                    'sport_name': 'Tenis',
                    'league_name': 'ATP Finals',
                    'event_type_name': 'match',
                    'name': 'Alcaraz - Sinner',
                    'date_time': '2026-11-03 21:00:00',
                    'channels': [{'name': 'TRT Spor Star', 'active': 1}],
                    'featured': 1,
                }
            ]
        }
    })
    + '</script></html>'
).encode('utf-8')


class GuideTests(unittest.TestCase):
    def test_parses_sporekrani_modern_event_rows_and_legacy_events(self):
        modern = sports.parse_sporekrani(SAMPLE_SPOREKRANI_MODERN.decode('utf-8'), DAY)
        self.assertEqual([e['id'] for e in modern], ['102', '101'])
        self.assertEqual(modern[0]['time'], '19:30')
        self.assertEqual(modern[0]['channels'], ['S Sport 1'])
        self.assertEqual(modern[1]['title'], 'Galatasaray - Bayern · Canlı')
        self.assertEqual(modern[1]['channels'], ['Bein Sports 1'])
        self.assertTrue(modern[1]['featured'])

        legacy = sports.parse_sporekrani(SAMPLE_SPOREKRANI_LEGACY.decode('utf-8'), DAY)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]['channels'], ['TRT Spor Star'])

    def test_parses_standard_and_gzipped_xmltv_guides_by_day(self):
        parsed = sports.parse_xmltv(SAMPLE_XMLTV, DAY)
        self.assertEqual([e['title'] for e in parsed], ['Evening News', 'City vs United'])
        self.assertEqual(parsed[0]['time'], '18:30')
        self.assertEqual(parsed[1]['time'], '20:45')
        self.assertTrue(parsed[1]['featured'])
        self.assertFalse(parsed[0]['featured'])

        gz_parsed = sports.parse_xmltv(gzip.compress(SAMPLE_XMLTV), DAY)
        self.assertEqual(len(gz_parsed), 2)

    def test_rejects_dtd_entities_for_xxe_safety(self):
        unsafe = b'<?xml version="1.0"?><!DOCTYPE tv [<!ENTITY xxe "bad">]><tv></tv>'
        with self.assertRaises(RuntimeError):
            sports.parse_xmltv(unsafe, DAY)

    def test_matches_channels_with_turkish_aliases_and_quality_normalization(self):
        requested = [{'channels': ['Public Sports 1', 'S Sport 1', 'Smart Spor HD', 'TRT Spor Star']}]
        catalog = [
            ('live:1', 'TR: Public Sports 1 HD'),
            ('live:2', 'TR: Public Sports 1 FHD'),
            ('live:3', 'TR: S Sport FHD'),
            ('live:4', 'TR: Spor Smart HD'),
            ('live:5', 'TR: TRT Spor Yıldız HD'),
        ]
        result = sports.match_channels(requested, catalog)
        self.assertEqual(result['Public Sports 1']['id'], 'live:2')
        self.assertEqual(result['S Sport 1']['id'], 'live:3')
        self.assertEqual(result['Smart Spor HD']['id'], 'live:4')
        self.assertEqual(result['TRT Spor Star']['id'], 'live:5')

    def test_defaults_to_sporekrani_and_supports_xmltv_mode_with_stale_cache(self):
        with patch.object(sports, '_cache', {}), patch.object(sports.time, 'time', return_value=1000):
            auto = sports.get_listings(DAY, lambda *a, **k: io.BytesIO(SAMPLE_SPOREKRANI_MODERN), epg_url='')
            self.assertTrue(auto['configured'])
            self.assertEqual(auto['sourceType'], 'sporekrani')
            self.assertEqual(len(auto['events']), 2)

        unconfigured_xmltv = sports.get_listings(
            DAY, lambda *a, **k: io.BytesIO(SAMPLE_XMLTV), epg_url='', source_mode='xmltv'
        )
        self.assertFalse(unconfigured_xmltv['configured'])
        self.assertEqual(unconfigured_xmltv['sourceType'], 'xmltv')
        self.assertEqual(unconfigured_xmltv['events'], [])

        with patch.object(sports, '_cache', {}), patch.object(sports.time, 'time', return_value=1000):
            res = sports.get_listings(DAY, lambda *a, **k: io.BytesIO(SAMPLE_XMLTV), epg_url='https://epg.example/guide.xml')
            self.assertTrue(res['configured'])
            self.assertEqual(res['sourceType'], 'xmltv')
            self.assertFalse(res['stale'])
            self.assertEqual(len(res['events']), 2)

        with patch.object(sports, '_cache', {('https://epg.example/guide.xml', DAY): (1000, res['events'])}), patch.object(sports.time, 'time', return_value=2000):
            def offline(*args, **kwargs):
                raise OSError
            stale = sports.get_listings(DAY, offline, epg_url='https://epg.example/guide.xml')
            self.assertTrue(stale['stale'])
