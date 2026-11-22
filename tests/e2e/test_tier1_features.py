"""Tier 1: Requirement-driven single-feature opaque-box E2E tests for Mavie (F1-F8)."""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path
import plistlib
import re
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discovery
import m3u
import sports
from tests.e2e.chrome_cdp import ChromeCdpSession
from tests.e2e.mock_upstream import MockUpstreamServer
from tests.e2e.runner import (
    HttpClient,
    LocalMediaServerProcess,
    REPO_ROOT,
    requires_target,
)


try:
    _IST_TZ = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    _IST_TZ = dt.timezone(dt.timedelta(hours=3))


def _wait_sync_done(client: HttpClient, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = client.get("/api/status").json or {}
        if not last.get("catalog", {}).get("syncing"):
            return last
        time.sleep(0.08)
    raise AssertionError(f"Catalog sync did not finish within {timeout}s: {last}")


def _wait_for_items(client: HttpClient, kind: str = "vod", min_count: int = 1, timeout: float = 8.0) -> list:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get("/api/status").json or {}
        items = (client.get(f"/api/catalog?kind={kind}&limit=100").json or {}).get("items", [])
        if len(items) >= min_count and not st.get("catalog", {}).get("syncing"):
            return items
        time.sleep(0.08)
    raise AssertionError(f"Expected >= {min_count} {kind} items within {timeout}s")


# =============================================================================
# F1: Setup, M3U Plus / Xtream / Local / Demo Source Loading & Resilient Sync
# =============================================================================


class Tier1F1SetupAndSourceLoadingTests(unittest.TestCase):
    """F1: M3U Plus query URLs, redirects, gzip/BOM/commas, Xtream, local, demo."""

    @requires_target("M1")
    def test_m3u_plus_query_url_setup_and_sync(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(
                allow_mock_port=mock.port,
                mock_base_url=mock.base_url,
            ).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            m3u_url = f"{mock.base_url}/get.php?username=demo_user&password=demo_pass&type=m3u_plus&output=mpegts"
            res = c.post("/api/settings", {"type": "m3u", "name": "Test M3U Plus", "m3uUrl": m3u_url})
            self.assertEqual(res.status, 200, res.text)
            self.assertEqual((res.json or {}).get("ok"), True)

            st = _wait_sync_done(c)
            self.assertIsNone(st["catalog"].get("error"), st)
            self.assertEqual(st["connection"]["m3uUrl"], m3u_url)
            self.assertGreaterEqual(st["catalog"]["live"], 1)
            self.assertGreaterEqual(st["catalog"]["vod"], 1)

    def test_m3u_301_302_307_redirect_chain_loads(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(
                allow_mock_port=mock.port,
                mock_base_url=mock.base_url,
            ).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            res = c.post(
                "/api/settings",
                {"type": "m3u", "name": "Redirect Chain", "m3uUrl": f"{mock.base_url}/redirect/301"},
            )
            self.assertEqual(res.status, 200, res.text)
            live = _wait_for_items(c, kind="live", min_count=4)
            names = [i["name"] for i in live]
            self.assertIn("TR: BeIN Sports 1 FHD", names)

    @requires_target("M1")
    def test_m3u_gzip_utf8_bom_and_attribute_commas(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(
                allow_mock_port=mock.port,
                mock_base_url=mock.base_url,
            ).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            res = c.post(
                "/api/settings",
                {"type": "m3u", "name": "Gzip BOM", "m3uUrl": f"{mock.base_url}/m3u/gzip"},
            )
            self.assertEqual(res.status, 200, res.text)
            live = _wait_for_items(c, kind="live", min_count=3)
            haber = next((i for i in live if "Haber Kanalı" in i["name"]), None)
            self.assertIsNotNone(haber, f"Expected Haber Kanalı in {live}")
            self.assertEqual(haber["name"], "Haber Kanalı (FHD)")
            self.assertEqual(haber["categoryName"], "Haber, Dünya")
            st = c.get("/api/status").json
            self.assertIn("/guide.xml?token=epg123", st["connection"].get("epgUrl", ""))

    def test_xtream_api_setup_syncs_live_vod_series_and_account(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(
                allow_mock_port=mock.port,
                mock_base_url=mock.base_url,
            ).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            res = c.post(
                "/api/settings",
                {
                    "type": "xtream",
                    "name": "Mock Xtream",
                    "host": mock.base_url,
                    "username": "demo_user",
                    "password": "demo_pass",
                },
            )
            self.assertEqual(res.status, 200, res.text)
            st = _wait_sync_done(c)
            self.assertEqual(st["account"]["status"], "Active")
            self.assertGreaterEqual(st["catalog"]["live"], 1)
            self.assertGreaterEqual(st["catalog"]["vod"], 1)
            self.assertGreaterEqual(st["catalog"]["series"], 1)
            self.assertNotIn("demo_pass", json.dumps(st))
            self.assertNotIn("demo_pass", json.dumps(c.get("/api/export").json))

    def test_local_media_directory_scan_and_sidecar_subtitles(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        with tempfile.TemporaryDirectory(prefix="mavie_media_") as media_dir:
            mp = Path(media_dir)
            (mp / "Open.Horizon.2025.1080p.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
            (mp / "Open.Horizon.2025.1080p.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello Mavie\n",
                encoding="utf-8",
            )
            res = c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Local Movies"})
            self.assertEqual(res.status, 200, res.text)
            items = _wait_for_items(c, kind="vod", min_count=1)
            self.assertEqual(len(items), 1)
            self.assertIn("Open Horizon", items[0]["name"])
            sub = c.get(f"/api/subtitles/{items[0]['id']}/0.vtt")
            self.assertEqual(sub.status, 200)
            self.assertIn("WEBVTT", sub.text)
            self.assertIn("Hello Mavie", sub.text)

    def test_demo_catalog_populates_home_and_catalog_items(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        demo = c.post("/api/demo", {})
        self.assertEqual(demo.status, 200, demo.text)
        self.assertEqual((demo.json or {}).get("ok"), True)

        cat = c.get("/api/catalog")
        self.assertEqual(cat.status, 200)
        items = (cat.json or {}).get("items", [])
        self.assertGreaterEqual(len(items), 4)
        self.assertGreaterEqual(len((cat.json or {}).get("categories", [])), 1)

        home = c.get("/api/home")
        self.assertEqual(home.status, 200)
        self.assertIn("counts", home.json or {})


# =============================================================================
# F2: Live TV / VOD / Series Catalog, Search, Detail & 2x2 Multi-View
# =============================================================================


class Tier1F2CatalogSearchDetailMultiviewTests(unittest.TestCase):
    """F2: Turkish search folding, sort/pagination, VOD/series detail, short EPG, 2x2 multiview."""

    def test_catalog_turkish_search_folding_and_category_filter(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            self.assertEqual(
                c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"}).status,
                200,
            )
            vods = _wait_for_items(c, kind="vod", min_count=2)
            komedi_cat = next(i["categoryId"] for i in vods if "Işıklar" in i["name"])

            for query in ("ISIKLAR", "ışıklar", "İÇİNDE"):
                resp = c.get(f"/api/catalog?kind=vod&q={urllib.parse.quote(query)}")
                self.assertEqual(resp.status, 200)
                names = [i["name"] for i in resp.json["items"]]
                self.assertEqual(names, ["Işıklar İçinde"], f"Failed Turkish fold search for {query!r}")

            cat_resp = c.get(f"/api/catalog?kind=vod&category={urllib.parse.quote(komedi_cat)}")
            self.assertEqual(cat_resp.status, 200)
            self.assertEqual([i["name"] for i in cat_resp.json["items"]], ["Işıklar İçinde"])

    def test_catalog_sorting_recent_name_rating_and_pagination(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        self.assertEqual(c.post("/api/demo", {}).status, 200)

        p1 = c.get("/api/catalog?kind=vod&sort=name&limit=2&page=1").json
        p2 = c.get("/api/catalog?kind=vod&sort=name&limit=2&page=2").json
        self.assertEqual(p1["total"], 4)
        self.assertEqual(p1["pages"], 2)
        self.assertEqual(len(p1["items"]), 2)
        self.assertEqual(len(p2["items"]), 2)
        combined = [i["name"] for i in p1["items"] + p2["items"]]
        self.assertEqual(combined, sorted(combined, key=str.lower))

        by_rating = c.get("/api/catalog?kind=vod&sort=rating&limit=10").json["items"]
        ratings = [float(i["rating"]) for i in by_rating]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

    def test_vod_and_series_detail_hydrates_seasons_and_episodes(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            vods = _wait_for_items(c, kind="vod", min_count=1)
            series = _wait_for_items(c, kind="series", min_count=1)

            vod_detail = c.get(f"/api/items/{vods[0]['id']}").json
            self.assertEqual(vod_detail["info"]["plot"], "Test film açıklaması.")
            self.assertEqual(vod_detail["info"]["duration"], 5400)

            ser_detail = c.get(f"/api/items/{series[0]['id']}").json
            seasons = ser_detail["seasons"]
            self.assertEqual([s["season"] for s in seasons], [1, 2])
            self.assertEqual(len(seasons[0]["episodes"]), 2)
            self.assertTrue(seasons[0]["episodes"][0]["id"].startswith("episode:"))

    def test_live_channel_short_epg_base64_decoding(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            live = _wait_for_items(c, kind="live", min_count=1)
            ch = next(i for i in live if "BeIN Sports 1 FHD" in i["name"])

            epg = c.get(f"/api/epg/{ch['id']}")
            self.assertEqual(epg.status, 200, epg.text)
            programs = epg.json["programs"]
            self.assertEqual(len(programs), 1)
            self.assertEqual(programs[0]["title"], "Şampiyonluk Maçı")
            self.assertEqual(programs[0]["description"], "Canlı stadyum yayını.")

    def test_multiview_four_simultaneous_slots_and_slot_replace(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "MV"})
            live = _wait_for_items(c, kind="live", min_count=4)

            sids = []
            for slot in range(4):
                p = c.post("/api/play", {"id": live[slot]["id"], "mode": "direct", "multiview": True, "multiviewSlot": slot})
                self.assertEqual(p.status, 200, p.text)
                sids.append(p.json["sessionId"])
            self.assertEqual(len(set(sids)), 4)

            rep = c.post("/api/play", {"id": live[0]["id"], "mode": "direct", "multiview": True, "multiviewSlot": 1})
            self.assertEqual(rep.status, 200)
            new_sid1 = rep.json["sessionId"]
            self.assertEqual(c.post(f"/api/play/{sids[1]}/ping", {"position": 1}).status, 410)
            self.assertEqual(c.post(f"/api/play/{new_sid1}/ping", {"position": 1}).status, 200)
            for idx in (0, 2, 3):
                self.assertEqual(c.post(f"/api/play/{sids[idx]}/ping", {"position": 1}).status, 200)

    def test_single_play_takes_over_and_stops_multiview_slots(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "MV"})
            live = _wait_for_items(c, kind="live", min_count=4)

            mv_sids = []
            for slot in range(4):
                p = c.post("/api/play", {"id": live[slot]["id"], "mode": "direct", "multiview": True, "multiviewSlot": slot})
                self.assertEqual(p.status, 200)
                mv_sids.append(p.json["sessionId"])

            single = c.post("/api/play", {"id": live[0]["id"], "mode": "direct"})
            self.assertEqual(single.status, 200)
            for sid in mv_sids:
                self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 1}).status, 410)
            c.delete(f"/api/play/{single.json['sessionId']}")


# =============================================================================
# F3: Discovery, Cinemeta, Netflix Türkiye Top 10 & Surprise Pick
# =============================================================================


class Tier1F3DiscoveryAndSurpriseTests(unittest.TestCase):
    """F3: Cinemeta + Netflix TR matching, personalization, TMDB attribution, surprise."""

    def _seed_local_catalog_and_feed(self, srv: LocalMediaServerProcess, c: HttpClient, feed: dict) -> list:
        media_dir = srv.data_dir / "media_seed"
        media_dir.mkdir(exist_ok=True)
        year = dt.datetime.now(_IST_TZ).year
        (media_dir / "Komedi").mkdir(exist_ok=True)
        (media_dir / "Aksiyon").mkdir(exist_ok=True)
        (media_dir / "Komedi" / f"Isiklar.Icinde.{year}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"K" * 32)
        (media_dir / "Aksiyon" / f"Hizli.Takip.{year}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"A" * 32)
        (srv.data_dir / "discovery-public.json").write_text(json.dumps(feed), encoding="utf-8")
        c.post("/api/settings", {"type": "local", "localDir": str(media_dir), "name": "DiscSeed"})
        return _wait_for_items(c, kind="vod", min_count=2)

    def test_home_discovery_matches_cinemeta_and_netflix_tr_top10(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        today_str = dt.datetime.now(_IST_TZ).date().isoformat()
        feed = {
            "version": 3,
            "updatedAt": time.time(),
            "hasCinemeta": True,
            "hasTmdb": False,
            "chartSource": "netflix",
            "metas": [
                {"id": "tt1", "kind": "vod", "name": "Isiklar Icinde", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Comedy"], "poster": "https://example.org/p1.jpg", "released": today_str},
                {"id": "tt2", "kind": "vod", "name": "Hizli Takip", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Action"], "poster": "https://example.org/p2.jpg", "released": today_str},
            ],
            "charts": [
                {"name": "Isiklar Icinde", "kind": "vod", "rank": 1, "week": today_str, "source": "netflix", "netflixId": 81000001},
            ],
        }
        items = self._seed_local_catalog_and_feed(srv, c, feed)
        catalog_ids = {i["id"] for i in items}
        home = c.get("/api/home").json
        shelves = {s["id"]: s for s in home["discovery"]["shelves"]}
        self.assertIn("turkey-vod", shelves)
        self.assertIn("Netflix Türkiye Top 10", shelves["turkey-vod"]["subtitle"])
        self.assertIn("new-vod", shelves)
        self.assertGreaterEqual(len(home["discovery"]["showcase"]), 1)
        for shelf in home["discovery"]["shelves"]:
            for it in shelf["items"]:
                self.assertIn(it["id"], catalog_ids)

    def test_discovery_personalization_promotes_watched_genres(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        today_str = dt.datetime.now(_IST_TZ).date().isoformat()
        feed = {
            "version": 3,
            "updatedAt": time.time(),
            "hasCinemeta": True,
            "metas": [
                {"id": "tt1", "kind": "vod", "name": "Isiklar Icinde", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Comedy"], "poster": "https://example.org/p1.jpg"},
                {"id": "tt2", "kind": "vod", "name": "Hizli Takip", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Action"], "poster": "https://example.org/p2.jpg"},
            ],
            "charts": [{"name": "Isiklar Icinde", "kind": "vod", "rank": 1, "week": today_str, "source": "netflix"}],
        }
        items = self._seed_local_catalog_and_feed(srv, c, feed)
        comedy = next(i for i in items if "Isiklar" in i["name"])
        c.post("/api/progress", {"id": comedy["id"], "position": 180, "duration": 1200})
        c.post("/api/favorites", {"id": comedy["id"], "favorite": True})

        disc = c.get("/api/home").json["discovery"]
        self.assertTrue(disc["personalized"])
        self.assertIn("Komedi", disc["topGenres"])
        shelf_ids = [s["id"] for s in disc["shelves"]]
        self.assertLess(shelf_ids.index("genre-vod-Comedy"), shelf_ids.index("genre-vod-Action"))
        comedy_shelf = next(s for s in disc["shelves"] if s["id"] == "genre-vod-Comedy")
        self.assertIn("öne çıkarıldı", comedy_shelf["subtitle"])

    def test_discovery_tmdb_chart_source_and_sources_attribution(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        today_str = dt.datetime.now(_IST_TZ).date().isoformat()
        feed = {
            "version": 3,
            "updatedAt": time.time(),
            "hasTmdb": True,
            "chartSource": "tmdb",
            "metas": [{"id": "tmdb:vod:1", "kind": "vod", "name": "Isiklar Icinde", "genres": ["Comedy"], "poster": "https://example.org/p1.jpg"}],
            "charts": [{"name": "Isiklar Icinde", "kind": "vod", "rank": 1, "week": today_str, "source": "tmdb"}],
        }
        self._seed_local_catalog_and_feed(srv, c, feed)
        disc = c.get("/api/home").json["discovery"]
        source_names = [s["name"] for s in disc["sources"]]
        self.assertIn("TMDB", source_names)
        turkey = next(s for s in disc["shelves"] if s["id"] == "turkey-vod")
        self.assertIn("Haftalık trend listesi", turkey["subtitle"])

    def test_surprise_pick_excludes_continue_watching_items(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        today_str = dt.datetime.now(_IST_TZ).date().isoformat()
        feed = {
            "version": 3,
            "updatedAt": time.time(),
            "metas": [
                {"id": "tt1", "kind": "vod", "name": "Isiklar Icinde", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Comedy"], "released": today_str},
                {"id": "tt2", "kind": "vod", "name": "Hizli Takip", "year": str(dt.datetime.now(_IST_TZ).year), "genres": ["Action"], "released": today_str},
            ],
            "charts": [],
        }
        items = self._seed_local_catalog_and_feed(srv, c, feed)
        watched_item = next(i for i in items if "Isiklar" in i["name"])
        c.post("/api/progress", {"id": watched_item["id"], "position": 120, "duration": 1000})

        for _ in range(5):
            pick = c.get("/api/surprise")
            self.assertEqual(pick.status, 200)
            self.assertNotEqual(pick.json["item"]["id"], watched_item["id"])

    def test_discovery_refresh_fetches_mock_cinemeta_and_netflix(self) -> None:
        with MockUpstreamServer() as mock, tempfile.TemporaryDirectory(prefix="mavie_disc_") as tmp_dir:
            orig_cinemeta, orig_netflix, orig_get, orig_mem = (
                discovery.CINEMETA,
                discovery.NETFLIX,
                discovery.get,
                discovery._memory,
            )
            try:
                discovery.CINEMETA = f"{mock.base_url}/cinemeta"
                discovery.NETFLIX = f"{mock.base_url}/netflix/tudum/top10/turkey"
                discovery._memory = None

                def _mock_get(url: str, timeout: int = 18) -> str:
                    if url.startswith("https://www.netflix.com/tr/title/"):
                        url = f"{mock.base_url}/netflix/tr/title/" + url.rsplit("/", 1)[-1]
                    return orig_get(url, timeout=timeout)

                discovery.get = _mock_get
                discovery.refresh(tmp_dir)
            finally:
                discovery.CINEMETA = orig_cinemeta
                discovery.NETFLIX = orig_netflix
                discovery.get = orig_get
                discovery._memory = orig_mem

            out = json.loads((Path(tmp_dir) / "discovery-public.json").read_text(encoding="utf-8"))
            self.assertEqual(out["version"], 3)
            self.assertTrue(out["hasCinemeta"])
            self.assertEqual(out["chartSource"], "netflix")
            self.assertTrue(any(m["name"] == "Işıklar İçinde" for m in out["metas"]))


# =============================================================================
# F4: Sports Guide (Spor Ekranı + XMLTV EPG Query URLs & Channel Matching)
# =============================================================================


class Tier1F4SportsGuideTests(unittest.TestCase):
    """F4: Spor Ekranı mock, XMLTV query URLs, gzip XMLTV, unconfigured mode, FHD matching."""

    @requires_target("M1")
    def test_sports_xmltv_query_epg_url_and_channel_matching(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "SportM3U"})
            _wait_for_items(c, kind="live", min_count=3)

            epg_url = f"{mock.base_url}/guide.xml?token=abc&fmt=xmltv"
            resp = c.get(f"/api/sports?epgUrl={urllib.parse.quote(epg_url, safe='')}&source=xmltv")
            self.assertEqual(resp.status, 200, resp.text)
            body = resp.json
            self.assertEqual(body["sourceType"], "xmltv")
            self.assertTrue(body["hasEpg"])
            self.assertTrue(body["configured"])
            self.assertGreaterEqual(len(body["events"]), 1)
            self.assertIn("BeIN Sports 1", body["channels"])

    @requires_target("M1")
    def test_sports_gzipped_xmltv_from_configured_epg_url(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            epg_gz = f"{mock.base_url}/guide.xml.gz?token=gz1"
            res = c.post(
                "/api/settings",
                {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "epgUrl": epg_gz, "name": "GzEpg"},
            )
            self.assertEqual(res.status, 200, res.text)
            _wait_for_items(c, kind="live", min_count=2)

            sp = c.get("/api/sports?source=xmltv")
            self.assertEqual(sp.status, 200, sp.text)
            self.assertEqual(sp.json["sourceType"], "xmltv")
            self.assertTrue(any("Derbi" in e["title"] for e in sp.json["events"]))

    def test_sports_unconfigured_xmltv_mode_returns_empty_configured_false(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        resp = c.get("/api/sports?source=xmltv")
        self.assertEqual(resp.status, 200, resp.text)
        body = resp.json
        self.assertEqual(body["sourceType"], "xmltv")
        self.assertFalse(body["configured"])
        self.assertFalse(body["hasEpg"])
        self.assertEqual(body["events"], [])

    def test_sports_epg_endpoint_and_date_selection_with_mock_sporekrani_and_xmltv(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            sp_auto = c.get("/api/sports")
            self.assertEqual(sp_auto.status, 200, sp_auto.text)
            self.assertEqual(sp_auto.json["sourceType"], "sporekrani")
            self.assertTrue(any("Derbi Karşılaşması" in e["title"] for e in sp_auto.json["events"]))

            tomorrow = (dt.datetime.now(_IST_TZ).date() + dt.timedelta(days=1)).isoformat()
            epg_path = urllib.parse.quote(f"{mock.base_url}/guide.xml", safe="")
            sp_tm = c.get(f"/api/sports?date={tomorrow}&epgUrl={epg_path}&source=xmltv&refresh=1")
            self.assertEqual(sp_tm.status, 200, sp_tm.text)
            self.assertEqual(sp_tm.json["date"], tomorrow)
            titles = [e["title"] for e in sp_tm.json["events"]]
            self.assertIn("Yarınki Kupa Maçı", titles)
            self.assertNotIn("Süper Lig Derbisi", titles)

    def test_sports_channel_alias_and_fhd_priority_matching(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "Alias"})
            live = _wait_for_items(c, kind="live", min_count=4)
            fhd_id = next(i["id"] for i in live if i["name"] == "TR: BeIN Sports 1 FHD")
            yildiz_id = next(i["id"] for i in live if i["name"] == "TR: TRT Spor Yıldız HD")

            epg_path = urllib.parse.quote(f"{mock.base_url}/guide.xml", safe="")
            sp = c.get(f"/api/sports?epgUrl={epg_path}&source=xmltv")
            self.assertEqual(sp.status, 200, sp.text)
            channels = sp.json["channels"]
            self.assertEqual(channels["BeIN Sports 1"]["id"], fhd_id)
            self.assertEqual(channels["TRT Spor Star"]["id"], yildiz_id)


# =============================================================================
# F5: Favorites, Playlists, Continue Watching, Tracks, Playback & HLS Proxy
# =============================================================================


class Tier1F5PlaybackFavoritesPlaylistsTests(unittest.TestCase):
    """F5: HLS proxy rewrite, Range/CP1254 VTT, episode progression, playlist CRUD, image cache."""

    def test_hls_proxy_rewrites_master_media_playlists_and_key_uri(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "HLS"})
            live = _wait_for_items(c, kind="live", min_count=1)

            play = c.post("/api/play", {"id": live[0]["id"], "mode": "direct"})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            playlist = c.get(play.json["url"])
            self.assertEqual(playlist.status, 200, playlist.text)
            self.assertIn("application/vnd.apple.mpegurl", playlist.headers.get("content-type", ""))
            self.assertNotIn("127.0.0.1", playlist.text)

            key_m = re.search(r'URI="(/media/[^"]+)"', playlist.text)
            self.assertIsNotNone(key_m, playlist.text)
            seg_line = next(ln for ln in playlist.text.splitlines() if ln.startswith("/media/"))

            key_resp = c.get(key_m.group(1))
            self.assertEqual(key_resp.status, 200)
            self.assertEqual(key_resp.raw, b"MAVIE_AES_KEY_16")

            seg_resp = c.get(seg_line)
            self.assertEqual(seg_resp.status, 200)
            self.assertIn(b"MAVIE_TS_SEGMENT_0_", seg_resp.raw)
            c.delete(f"/api/play/{sid}")

    def test_local_playback_range_requests_and_sidecar_vtt(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        with tempfile.TemporaryDirectory(prefix="mavie_range_") as media_dir:
            mp = Path(media_dir)
            (mp / "Clip.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"MAVIE_RANGE_DATA" * 16)
            (mp / "Clip.2025.tr.srt").write_bytes(
                "1\r\n00:00:00,000 --> 00:00:02,500\r\nIşıklar ve Çığlık Şöleni\r\n".encode("cp1254")
            )
            c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "RangeTest"})
            items = _wait_for_items(c, kind="vod", min_count=1)
            iid = items[0]["id"]

            play = c.post("/api/play", {"id": iid, "mode": "direct"})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            rng = c.get(play.json["url"], headers={"Range": "bytes=0-15"})
            self.assertEqual(rng.status, 206)
            self.assertTrue(rng.headers.get("content-range", "").startswith("bytes 0-15/"))
            self.assertEqual(len(rng.raw), 16)
            c.delete(f"/api/play/{sid}")

            vtt = c.get(f"/api/subtitles/{iid}/0.vtt")
            self.assertEqual(vtt.status, 200)
            self.assertTrue(vtt.text.startswith("WEBVTT"))
            self.assertIn("Işıklar ve Çığlık Şöleni", vtt.text)

    def test_continue_watching_episode_progression_and_completion(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            series = _wait_for_items(c, kind="series", min_count=1)
            det = c.get(f"/api/items/{series[0]['id']}").json
            eps = det["seasons"][0]["episodes"]
            e1, e2 = eps[0]["id"], eps[1]["id"]

            c.post("/api/progress", {"id": e1, "position": 100, "duration": 1000})
            cw1 = c.get("/api/home").json["continueWatching"]
            self.assertEqual(cw1[0]["id"], e1)

            c.post("/api/progress", {"id": e1, "position": 960, "duration": 1000})
            cw2 = c.get("/api/home").json["continueWatching"]
            self.assertEqual(cw2[0]["id"], e2)
            self.assertEqual(cw2[0].get("continueReason"), "nextEpisode")

    def test_favorites_and_playlist_crud_reorder_and_delete(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        items = c.get("/api/catalog").json["items"]
        a, b = items[0]["id"], items[1]["id"]

        self.assertEqual(c.post("/api/favorites", {"id": a, "favorite": True}).status, 200)
        self.assertIn(a, [i["id"] for i in c.get("/api/favorites").json["items"]])

        pl = c.post("/api/playlists", {"name": "Hafta Sonu"})
        self.assertEqual(pl.status, 201)
        pid = pl.json["id"]

        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"itemId": a}).status, 200)
        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"itemId": b}).status, 200)
        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"name": "Güncel Liste", "order": [b, a]}).status, 200)

        lists = c.get("/api/playlists").json["playlists"]
        cur = next(x for x in lists if x["id"] == pid)
        self.assertEqual(cur["name"], "Güncel Liste")
        self.assertEqual([i["id"] for i in cur["items"]], [b, a])

        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"removeItemId": b}).status, 200)
        self.assertEqual(c.delete(f"/api/playlists/{pid}").status, 200)
        self.assertFalse(any(x["id"] == pid for x in c.get("/api/playlists").json["playlists"]))

    def test_track_preferences_and_playback_ping_pause_delete(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        iid = c.get("/api/catalog").json["items"][0]["id"]

        pref = c.post("/api/track-preferences", {"id": iid, "audio": "stream:1", "subtitle": "stream:2"})
        self.assertEqual(pref.status, 200)
        tr = c.get(f"/api/tracks/{iid}").json
        self.assertEqual(tr["selection"]["audio"], "stream:1")
        self.assertEqual(tr["selection"]["subtitle"], "stream:2")

        play = c.post("/api/play", {"id": iid, "mode": "direct"})
        self.assertEqual(play.status, 200)
        sid = play.json["sessionId"]
        self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 42.5}).status, 200)
        self.assertEqual(c.post(f"/api/play/{sid}/pause", {"paused": True}).status, 200)
        self.assertEqual(c.post(f"/api/play/{sid}/pause", {"paused": False}).status, 200)
        self.assertEqual(c.delete(f"/api/play/{sid}").status, 200)
        self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 45}).status, 410)

    def test_image_proxy_caches_raster_and_deduplicates(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            qurl = urllib.parse.quote(f"{mock.base_url}/posters/thumb.png", safe="")

            r1 = c.get(f"/api/image?url={qurl}")
            r2 = c.get(f"/api/image?url={qurl}")
            self.assertEqual(r1.status, 200)
            self.assertEqual(r2.status, 200)
            self.assertEqual(r1.headers.get("content-type"), "image/png")
            self.assertIn("max-age=86400", r1.headers.get("cache-control", ""))
            self.assertEqual(mock.image_hits, 1)


# =============================================================================
# F6: Profiles, PIN Security, Kid Mode, Backup Export/Import & LAN Pairing
# =============================================================================


class Tier1F6ProfilesBackupAndPairingTests(unittest.TestCase):
    """F6: LAN pairing, device revoke, profiles/PIN/kid mode, profile isolation, backup merge."""

    def test_lan_pairing_flow_cookie_and_authorized_status(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        code = host_c.get("/api/status").json["pairingCode"]
        self.assertRegex(str(code), r"^\d{6}$")

        guest = srv.client()
        self.assertEqual(guest.get("/api/status").json, {"authorized": False, "pairingRequired": True})
        self.assertEqual(guest.get("/api/catalog").status, 401)

        res = guest.post("/api/pair", {"code": code})
        self.assertEqual(res.status, 200, res.text)
        self.assertIn("mavie_device", guest.cookies_dict())
        self.assertTrue(guest.get("/api/status").json["authorized"])
        self.assertEqual(guest.get("/api/catalog").status, 200)

    def test_device_revoke_invalidates_paired_clients(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        code = host_c.get("/api/status").json["pairingCode"]
        mobile = srv.client()
        self.assertEqual(mobile.post("/api/pair", {"code": code}).status, 200)
        self.assertEqual(mobile.get("/api/catalog").status, 200)

        self.assertEqual(host_c.post("/api/devices/revoke", {}).status, 200)
        self.assertEqual(mobile.get("/api/catalog").status, 401)

    def test_profile_create_pin_switch_and_kid_filtering(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        with tempfile.TemporaryDirectory(prefix="mavie_kid_") as media_dir:
            mp = Path(media_dir)
            (mp / "Belgesel").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Belgesel" / "Aile.Belgeseli.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"FAM" * 16)
            (mp / "Korku +18" / "Korku.Gecesi.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HOR" * 16)
            c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "KidTest"})
            _wait_for_items(c, kind="vod", min_count=2)

            kid = c.post("/api/profiles", {"name": "Kid", "isKids": True, "pin": "4321", "avatarColor": "#22C55E"})
            self.assertEqual(kid.status, 201, kid.text)
            kid_id = kid.json["profile"]["id"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid_id, "pin": "4321"}).status, 200)

            cat_names = [i["name"] for i in c.get("/api/catalog").json["items"]]
            self.assertIn("Aile Belgeseli", cat_names)
            self.assertNotIn("Korku Gecesi", cat_names)

            home_names = [i["name"] for i in c.get("/api/home").json["recent"]]
            self.assertNotIn("Korku Gecesi", home_names)

    def test_profile_switching_isolates_favorites_progress_playlists_and_tracks(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        items = c.get("/api/catalog").json["items"]
        a, b = items[0]["id"], items[1]["id"]

        c.post("/api/favorites", {"id": a, "favorite": True})
        c.post("/api/progress", {"id": a, "position": 75, "duration": 600})
        pl_id = c.post("/api/playlists", {"name": "Ana Liste"}).json["id"]
        c.patch(f"/api/playlists/{pl_id}", {"itemId": a})
        c.post("/api/track-preferences", {"id": a, "audio": "stream:2"})

        p2_id = c.post("/api/profiles", {"name": "Misafir"}).json["profile"]["id"]
        c.post("/api/profiles/switch", {"id": p2_id})
        self.assertEqual(c.get("/api/favorites").json["items"], [])
        self.assertEqual(c.get("/api/progress").json["items"], [])
        self.assertEqual(c.get("/api/playlists").json["playlists"], [])
        self.assertEqual(c.get(f"/api/tracks/{a}").json["selection"]["audio"], "auto")

        c.post("/api/favorites", {"id": b, "favorite": True})
        c.post("/api/profiles/switch", {"id": "default"})
        fav_ids = [i["id"] for i in c.get("/api/favorites").json["items"]]
        self.assertEqual(fav_ids, [a])
        self.assertEqual(c.get(f"/api/tracks/{a}").json["selection"]["audio"], "stream:2")

    def test_backup_export_import_merges_episodes_playlists_and_timestamps(self) -> None:
        with MockUpstreamServer() as mock:
            srv1 = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv1.stop)
            c1 = srv1.paired_client()
            c1.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            series = _wait_for_items(c1, kind="series", min_count=1)
            ep1 = c1.get(f"/api/items/{series[0]['id']}").json["seasons"][0]["episodes"][0]["id"]

            c1.post("/api/favorites", {"id": ep1, "favorite": True})
            c1.post("/api/progress", {"id": ep1, "position": 420, "duration": 2400})
            pl = c1.post("/api/playlists", {"name": "Dizi Seçkisi"}).json["id"]
            c1.patch(f"/api/playlists/{pl}", {"itemId": ep1})
            c1.post("/api/track-preferences", {"id": ep1, "audio": "stream:1", "subtitle": "stream:3"})

            exp = c1.get("/api/export")
            self.assertEqual(exp.status, 200)
            self.assertIn("mavie-yedek.json", exp.headers.get("content-disposition", ""))

            srv2 = LocalMediaServerProcess().start()
            self.addCleanup(srv2.stop)
            c2 = srv2.paired_client()
            imp = c2.post("/api/import", {"data": exp.json})
            self.assertEqual(imp.status, 200, imp.text)
            self.assertIn(ep1, [i["id"] for i in c2.get("/api/favorites").json["items"]])
            self.assertEqual(c2.get("/api/progress").json["items"][0]["progress"]["position"], 420)
            self.assertEqual(c2.get(f"/api/tracks/{ep1}").json["selection"]["subtitle"], "stream:3")

    def test_delete_active_profile_falls_back_to_default(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        p2 = c.post("/api/profiles", {"name": "Geçici"}).json["profile"]["id"]
        c.post("/api/profiles/switch", {"id": p2})
        self.assertEqual(c.delete(f"/api/profiles/{p2}").status, 200)
        st = c.get("/api/status").json
        self.assertEqual(st["profile"]["id"], "default")
        self.assertFalse(any(p["id"] == p2 for p in c.get("/api/profiles").json["profiles"]))


# =============================================================================
# F7: Web/Desktop Liquid Glass UI, Mavie SVG Mark, Palette & Zero-Overflow
# =============================================================================


class Tier1F7ChromeLiquidGlassUiTests(unittest.TestCase):
    """F7: Headless Chrome checks for setup, home, sports, multiview, player & Liquid Glass."""

    @requires_target("M1")
    def test_chrome_setup_screen_renders_mavie_mark_palette_and_no_overflow(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        with ChromeCdpSession() as chrome:
            for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                chrome.set_viewport(w, h, mobile=mobile)
                chrome.navigate(f"{srv.base_url}/#settings")
                chrome.wait_for("Boolean(document.querySelector('#connectionForm'))")
                layout = chrome.check_layout(w)
                self.assertFalse(layout["overflow"], f"Overflow at {w}x{h}: {layout}")
                self.assertEqual(layout["clipped"], [], f"Clipped controls at {w}x{h}: {layout['clipped']}")

            marks = chrome.inspect_palette_and_marks()
            self.assertTrue(marks["topbarImgOk"])
            self.assertEqual(marks["legacyColors"], [])
            svg_low = marks["launchSvg"].lower()
            self.assertIn("#7c3aed", svg_low)
            self.assertIn("#3b82f6", svg_low)
            self.assertIn("#06b6d4", svg_low)
            self.assertIn("#22d3ee", svg_low)
            self.assertNotIn("m 42 36 l 60 80 l 78 36", svg_low)
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    @requires_target("M1")
    def test_chrome_home_demo_liquid_glass_surfaces_and_contrast(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        srv.paired_client().post("/api/demo", {})
        with ChromeCdpSession() as chrome:
            for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                chrome.set_viewport(w, h, mobile=mobile)
                chrome.navigate(f"{srv.base_url}/#home")
                chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")
                layout = chrome.check_layout(w)
                self.assertFalse(layout["overflow"], f"Home overflow at {w}x{h}: {layout}")
                self.assertEqual(layout["clipped"], [], f"Clipped home controls at {w}x{h}: {layout['clipped']}")
                self.assertEqual(layout["stripClipped"], [])

            glass = chrome.inspect_liquid_glass([".topbar", ".cinema-hero .button"])
            self.assertTrue(glass[".topbar"]["present"])
            self.assertIn("blur(", glass[".topbar"]["backdrop"].lower())
            marks = chrome.inspect_palette_and_marks()
            self.assertEqual(marks["kickerSize"], {"width": 24, "height": 24})
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    @requires_target("M1")
    def test_chrome_sports_guide_renders_dates_spotlight_and_channels(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post(
                "/api/settings",
                {
                    "type": "m3u",
                    "m3uUrl": f"{mock.base_url}/m3u/plain.m3u",
                    "epgUrl": f"{mock.base_url}/guide.xml?token=s1",
                    "name": "SportsUI",
                },
            )
            _wait_for_items(c, kind="live", min_count=3)

            with ChromeCdpSession() as chrome:
                for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                    chrome.set_viewport(w, h, mobile=mobile)
                    chrome.navigate(f"{srv.base_url}/#sports?source=xmltv")
                    chrome.wait_for("document.querySelectorAll('.sports-event').length >= 1")
                    layout = chrome.check_layout(w)
                    self.assertFalse(layout["overflow"], f"Sports overflow at {w}x{h}")
                    self.assertEqual(layout["stripClipped"], [])
                    playable = chrome.evaluate("document.querySelectorAll('.sports-channel.playable').length")
                    self.assertGreaterEqual(playable, 1)

                glass = chrome.inspect_liquid_glass([".sports-spotlight"])
                if glass[".sports-spotlight"]["present"]:
                    self.assertIn("blur(", glass[".sports-spotlight"]["backdrop"].lower())
                self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_chrome_live_and_multiview_grid_layout_desktop_mobile(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "LiveMV"})
            _wait_for_items(c, kind="live", min_count=4)

            with ChromeCdpSession() as chrome:
                for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                    chrome.set_viewport(w, h, mobile=mobile)
                    chrome.navigate(f"{srv.base_url}/#live")
                    chrome.wait_for("document.querySelectorAll('.live-card').length >= 4")
                    live_layout = chrome.check_layout(w)
                    self.assertFalse(live_layout["overflow"], f"Live overflow at {w}x{h}")
                    self.assertEqual(live_layout["clipped"], [], f"Clipped live controls at {w}x{h}")

                    chrome.navigate(f"{srv.base_url}/#multiview")
                    chrome.wait_for("document.querySelectorAll('.multiview-tile').length === 4")
                    mv_layout = chrome.check_layout(
                        w,
                        control_selectors=(".multiview-tile select", "[data-mv-mute]", "[data-mv-full]"),
                    )
                    self.assertFalse(mv_layout["overflow"], f"Multiview overflow at {w}x{h}")
                    self.assertEqual(mv_layout["clipped"], [], f"Clipped multiview controls at {w}x{h}")
                self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_chrome_player_dialog_controls_accessible_without_clipping(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        srv.paired_client().post("/api/demo", {})
        with ChromeCdpSession() as chrome:
            for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                chrome.set_viewport(w, h, mobile=mobile)
                chrome.navigate(f"{srv.base_url}/#vod")
                chrome.wait_for("document.querySelectorAll('.media-card').length >= 1")
                chrome.evaluate("document.querySelector('.media-card .poster-button').click()")
                chrome.wait_for("Boolean(document.querySelector('#detailDialog[open] [data-action=\"play\"]'))")
                chrome.evaluate("document.querySelector('#detailDialog [data-action=\"play\"]').click()")
                chrome.wait_for("Boolean(document.querySelector('#playerDialog[open]'))")

                ctl = chrome.evaluate(
                    """
                    (() => {
                      const ids = ['#closePlayer', '#togglePlay', '#toggleTracks', '#toggleModes', '#speedSelect', '#fullscreenButton'];
                      const out = {};
                      for (const id of ids) {
                        const el = document.querySelector(id);
                        const r = el.getBoundingClientRect();
                        out[id] = {w: r.width, h: r.height, left: r.left, right: r.right, innerW: window.innerWidth};
                      }
                      return out;
                    })()
                    """
                )
                for id_sel, rect in ctl.items():
                    self.assertGreater(rect["w"], 0, f"{id_sel} has 0 width at {w}x{h}")
                    self.assertGreater(rect["h"], 0, f"{id_sel} has 0 height at {w}x{h}")
                    self.assertGreaterEqual(rect["left"], -1, f"{id_sel} clipped left at {w}x{h}: {rect}")
                    self.assertLessEqual(rect["right"], w + 1, f"{id_sel} clipped right at {w}x{h}: {rect}")
                chrome.evaluate("document.querySelector('#closePlayer').click()")
                chrome.wait_for("!document.querySelector('#playerDialog')?.open")
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])


# =============================================================================
# F8: Cross-Platform Packaging, Website & Config Hygiene
# =============================================================================


class Tier1F8PackagingAndHygieneTests(unittest.TestCase):
    """F8: Website, Windows, Android, Apple packaging, git hygiene, and M2/M3 targets."""

    def test_website_pages_free_model_and_4_platform_downloads(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        for rel in ("website/index.html", "website/404.html", "website/privacy.html", "website/terms.html"):
            txt = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("Mavie", txt)
            self.assertNotIn("cineva", txt.lower())
        for artifact in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(artifact, html)
            self.assertIn(artifact, portal_js)
        for forbidden in ("accountModal", "Mavie Pro", "verify-email", "forgot-password", "/api/v1/"):
            self.assertNotIn(forbidden, html + "\n" + portal_js)
        self.assertIn("Tamamen Ücretsiz", html)

    def test_windows_spec_inno_setup_and_ico_packaging_valid(self) -> None:
        spec_path = REPO_ROOT / "windows/mavie.spec"
        iss_path = REPO_ROOT / "windows/MavieSetup.iss"
        ico_path = REPO_ROOT / "windows/mavie.ico"
        spec_txt = spec_path.read_text(encoding="utf-8")
        ast.parse(spec_txt, filename=str(spec_path))
        for tok in ("desktop", "mavie_desktop.py", "public", "legal", "mavie.ico", "imageio_ffmpeg", "tzdata", "X utf8"):
            self.assertIn(tok, spec_txt)
        for mod in ("server", "m3u", "discovery", "sports", "playback", "local_media", "zoneinfo"):
            self.assertIn(mod, spec_txt)

        iss_txt = iss_path.read_text(encoding="utf-8")
        for tok in ("OutputBaseFilename=Mavie-Setup", "SetupIconFile=mavie.ico", "x64compatible", "PrivilegesRequired=lowest"):
            self.assertIn(tok, iss_txt)

        ico_bytes = ico_path.read_bytes()
        reserved, icon_type, count = struct.unpack("<HHH", ico_bytes[:6])
        self.assertEqual((reserved, icon_type), (0, 1))
        self.assertGreaterEqual(count, 6)

    def test_android_manifest_network_security_and_gradle_valid(self) -> None:
        gradle = (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('namespace = "app.mavie.player"', gradle)
        self.assertIn('applicationId = "app.mavie.player"', gradle)
        self.assertIn("arm64-v8a", gradle)
        self.assertIn("armeabi-v7a", gradle)

        manifest = (REPO_ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("android.permission.INTERNET", manifest)
        self.assertIn("android.permission.ACCESS_NETWORK_STATE", manifest)
        self.assertIn('android:allowBackup="false"', manifest)
        self.assertIn('android:networkSecurityConfig="@xml/network_security_config"', manifest)
        self.assertNotIn("Cineva", manifest)

        nsc = ET.fromstring((REPO_ROOT / "android/app/src/main/res/xml/network_security_config.xml").read_text(encoding="utf-8"))
        base_cfg = nsc.find("base-config")
        self.assertIsNotNone(base_cfg)
        self.assertEqual(base_cfg.get("cleartextTrafficPermitted"), "true")

        mavie_xml = (REPO_ROOT / "android/app/src/main/res/drawable/mavie_mark.xml").read_text(encoding="utf-8").lower()
        for tok in ("#ff7c3aed", "#ff3b82f6", "#ff06b6d4", "#ff22d3ee"):
            self.assertIn(tok, mavie_xml)

    def test_macos_and_ios_plist_assets_and_build_script_valid(self) -> None:
        mac_plist = plistlib.loads((REPO_ROOT / "apple/macOS/Info.plist").read_bytes())
        self.assertEqual(mac_plist.get("CFBundleIdentifier"), "app.mavie.macos")
        self.assertEqual(mac_plist.get("CFBundleIconFile"), "AppIcon")
        self.assertEqual(mac_plist.get("LSMinimumSystemVersion"), "13.0")
        self.assertIs(mac_plist.get("NSAppTransportSecurity", {}).get("NSAllowsArbitraryLoads"), True)

        ios_plist = plistlib.loads((REPO_ROOT / "apple/iOS/Info.plist").read_bytes())
        self.assertEqual(ios_plist.get("CFBundleIdentifier"), "app.mavie.ios")
        self.assertIs(ios_plist.get("NSAppTransportSecurity", {}).get("NSAllowsArbitraryLoads"), True)

        appicon_dir = REPO_ROOT / "apple/macOS/Assets.xcassets/AppIcon.appiconset"
        contents = json.loads((appicon_dir / "Contents.json").read_text(encoding="utf-8"))
        for img in contents["images"]:
            p = appicon_dir / img["filename"]
            self.assertTrue(p.is_file(), f"Missing macOS icon {p}")
            raw = p.read_bytes()
            self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")

        sh_path = REPO_ROOT / "apple/macOS/build_macos.sh"
        subprocess.run(["bash", "-n", str(sh_path)], check=True)
        sh_txt = sh_path.read_text(encoding="utf-8")
        for tok in ("AppIcon.icns", "--smoke-test", "Mavie-macOS.dmg", "Mavie-macOS.zip"):
            self.assertIn(tok, sh_txt)

    def test_git_repo_secret_hygiene_and_brand_tokens(self) -> None:
        tracked = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files"], text=True).splitlines()
        forbidden = [
            f
            for f in tracked
            if re.search(r"(^android/signing/|\.jks$|\.keystore$|^data/|^cloud_data/|^\.venv/|^\.env$)", f)
        ]
        self.assertEqual(forbidden, [], f"Sensitive or local data files tracked: {forbidden}")
        for rel in ("public/cinema.css", "public/player.css", "public/sports.css", "public/styles.css"):
            txt = (REPO_ROOT / rel).read_text(encoding="utf-8").lower()
            for legacy in ("#e50914", "#ff4b45", "#ed1520"):
                self.assertNotIn(legacy, txt, f"Legacy color {legacy} in {rel}")

    @requires_target("M2")
    def test_android_r8_release_minify_and_proguard_rules(self) -> None:
        gradle = (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertRegex(gradle, r"release\s*\{[^}]*isMinifyEnabled\s*=\s*true")
        proguard = (REPO_ROOT / "android/app/proguard-rules.pro").read_text(encoding="utf-8")
        self.assertIn("org.videolan", proguard)
        self.assertGreater(len([ln for ln in proguard.splitlines() if ln.strip() and not ln.strip().startswith("#")]), 3)
        self.assertTrue("okhttp" in proguard.lower() or "app.mavie.player" in proguard)

    @requires_target("M3")
    def test_apple_liquid_glass_and_macos_target_packaging(self) -> None:
        sh_txt = (REPO_ROOT / "apple/macOS/build_macos.sh").read_text(encoding="utf-8")
        self.assertIn("-apple-macosx13.0", sh_txt)
        self.assertIn("-target ", sh_txt)
        icon_gen_path = REPO_ROOT / "apple/macOS/scripts/generate_app_icons.swift"
        icon_txt = sh_txt + ("\n" + icon_gen_path.read_text(encoding="utf-8") if icon_gen_path.is_file() else "")
        self.assertIn("#22D3EE", icon_txt.upper())

        brand_swift = (REPO_ROOT / "apple/Shared/BrandTheme.swift").read_text(encoding="utf-8")
        self.assertIn(".ultraThinMaterial", brand_swift)
        self.assertTrue("trim(" in brand_swift or "addArc(" in brand_swift)


if __name__ == "__main__":
    unittest.main()
