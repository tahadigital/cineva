import datetime as dt
import gzip
import io
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


class GuideTests(unittest.TestCase):
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

    def test_matches_channels_with_quality_and_region_normalization(self):
        requested = [{'channels': ['Public Sports 1', 'World News']}]
        catalog = [
            ('live:1', 'TR: Public Sports 1 HD'),
            ('live:2', 'TR: Public Sports 1 FHD'),
            ('live:3', 'US: World News 4K'),
        ]
        result = sports.match_channels(requested, catalog)
        self.assertEqual(result['Public Sports 1']['id'], 'live:2')
        self.assertEqual(result['World News']['id'], 'live:3')

    def test_returns_unconfigured_cleanly_and_caches_xmltv_snapshots(self):
        empty = sports.get_listings(DAY, lambda *a, **k: io.BytesIO(SAMPLE_XMLTV), epg_url='')
        self.assertFalse(empty['configured'])
        self.assertEqual(empty['events'], [])

        with patch.object(sports, '_cache', {}), patch.object(sports.time, 'time', return_value=1000):
            res = sports.get_listings(DAY, lambda *a, **k: io.BytesIO(SAMPLE_XMLTV), epg_url='https://epg.example/guide.xml')
            self.assertTrue(res['configured'])
            self.assertFalse(res['stale'])
            self.assertEqual(len(res['events']), 2)
        with patch.object(sports, '_cache', {('https://epg.example/guide.xml', DAY): (1000, res['events'])}), patch.object(sports.time, 'time', return_value=2000):
            def offline(*args, **kwargs):
                raise OSError
            stale = sports.get_listings(DAY, offline, epg_url='https://epg.example/guide.xml')
            self.assertTrue(stale['stale'])
