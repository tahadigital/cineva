"""Tier 2: Boundary, corner-case, security, and error-handling E2E tests (F1-F8)."""

from __future__ import annotations

import datetime as dt
import http.client
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
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
    LocalMediaServerProcess,
    REPO_ROOT,
    requires_target,
)


try:
    _IST_TZ = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    _IST_TZ = dt.timezone(dt.timedelta(hours=3))


def _wait_sync_done(client, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get("/api/status").json or {}
        if not st.get("catalog", {}).get("syncing"):
            return st
        time.sleep(0.08)
    raise AssertionError("Sync timed out")


# =============================================================================
# F1: Setup & Sync Boundaries
# =============================================================================


class Tier2F1SetupAndSyncBoundariesTests(unittest.TestCase):
    """F1 boundaries: upstream HTTP errors, timeouts, non-destructive guard, SSRF, limits."""

    @requires_target("M1")
    def test_settings_rejects_upstream_401_403_500_with_structured_json(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            for code in (401, 403, 500):
                url = f"{mock.base_url}/err/{code}?secret=demo_secret_token"
                res = c.post("/api/settings", {"type": "m3u", "name": f"Err{code}", "m3uUrl": url})
                self.assertIn(res.status, (400, 502), f"Expected 400/502 on upstream {code}, got {res.status}: {res.text}")
                self.assertIsInstance(res.json, dict)
                self.assertTrue(res.json.get("error"), f"Missing error message for {code}")
                self.assertNotIn("demo_secret_token", res.text)

    @requires_target("M1")
    def test_settings_upstream_timeout_returns_502_cleanly(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            res = c.post(
                "/api/settings",
                {"type": "m3u", "name": "Slow", "m3uUrl": f"{mock.base_url}/err/slow?delay=50"},
                timeout=55.0,
            )
            self.assertIn(res.status, (400, 502, 504), res.text)
            self.assertIsInstance(res.json, dict)
            self.assertTrue(res.json.get("error"))
            self.assertEqual(c.get("/api/health").status, 200)

    @requires_target("M1")
    def test_non_destructive_refresh_preserves_catalog_on_html_empty_or_500(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            url = f"{mock.base_url}/m3u/plain.m3u"
            self.assertEqual(c.post("/api/settings", {"type": "m3u", "name": "Keep", "m3uUrl": url}).status, 200)
            _wait_sync_done(c)
            initial = c.get("/api/catalog?kind=live").json["items"]
            self.assertGreaterEqual(len(initial), 4)
            target_id = initial[0]["id"]
            c.post("/api/favorites", {"id": target_id, "favorite": True})

            for override in (
                (200, "text/html", b"<html><body>Sign in required</body></html>"),
                (200, "text/plain", b""),
                (500, "text/plain", b"Upstream outage"),
            ):
                mock.m3u_override = override
                self.assertEqual(c.post("/api/catalog/sync", {}).status, 202)
                st = _wait_sync_done(c)
                self.assertTrue(st["catalog"].get("error"), f"Expected error recorded for {override[0]}")
                after = c.get("/api/catalog?kind=live").json["items"]
                self.assertEqual(len(after), len(initial), f"Catalog wiped on override {override[0]}")
                self.assertIn(target_id, [i["id"] for i in c.get("/api/favorites").json["items"]])

    def test_ssrf_blocks_private_loopback_link_local_and_redirect_ssrf(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        for url in (
            "http://127.0.0.1:9999/list.m3u",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/list.m3u",
        ):
            res = c.post("/api/settings", {"type": "m3u", "m3uUrl": url, "name": "SSRF"})
            if res.status == 200:
                st = _wait_sync_done(c)
                self.assertTrue(st["catalog"]["error"], f"Private URL {url} should be blocked")
            else:
                self.assertIn(res.status, (400, 403, 502))

        with MockUpstreamServer() as mock:
            srv2 = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv2.stop)
            c2 = srv2.paired_client()
            res = c2.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/redirect/to-metadata", "name": "RedirSSRF"})
            if res.status == 200:
                st2 = _wait_sync_done(c2)
                self.assertTrue(st2["catalog"]["error"])
            else:
                self.assertIn(res.status, (400, 403, 502))
            self.assertEqual(c2.get("/api/catalog?kind=live").json["items"], [])

    def test_malformed_m3u_and_oversized_m3u_rejected_safely(self) -> None:
        for bad in (
            "",
            "not an m3u file\n###garbage",
            "#EXTM3U\n#EXTINF:-1,NoUrlChannel\n",
            "#EXTM3U\n#EXTINF:-1,BadScheme\nfile:///etc/passwd\n",
            "#EXTM3U\n#EXTINF:-1,FtpScheme\nftp://example.com/a.ts\n",
            "#EXTM3U\n#EXTINF:-1,JsScheme\njavascript:alert(1)\n",
        ):
            parsed = m3u.parse_m3u(bad)
            self.assertEqual(parsed.get("items", []), [])

        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            res = c.post("/api/settings", {"type": "m3u", "name": "Huge", "m3uUrl": f"{mock.base_url}/err/oversized.m3u"})
            if res.status == 200:
                st = _wait_sync_done(c, timeout=12.0)
                self.assertIn("büyük", st["catalog"].get("error", ""))
            else:
                self.assertIn(res.status, (400, 413, 502))

    def test_settings_forbidden_missing_creds_userinfo_and_root_dir(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        missing = c.post("/api/settings", {"type": "xtream", "host": "https://example.com", "username": "", "password": ""})
        self.assertEqual(missing.status, 400)

        userinfo = c.post("/api/settings", {"type": "m3u", "m3uUrl": "http://u:p@example.com/list.m3u"})
        self.assertEqual(userinfo.status, 400)

        root_dir = c.post("/api/settings", {"type": "local", "localDir": "/"})
        self.assertEqual(root_dir.status, 400)

        cross_origin = c.post(
            "/api/settings",
            {"type": "demo"},
            headers={"Origin": "http://evil.example"},
        )
        self.assertEqual(cross_origin.status, 403)


# =============================================================================
# F2: Catalog, Search, Detail & Multi-View Boundaries
# =============================================================================


class Tier2F2CatalogAndMultiviewBoundariesTests(unittest.TestCase):
    """F2 boundaries: invalid kind, SQL wildcards, bad IDs, corrupt EPG b64, 5th MV eviction."""

    def test_catalog_invalid_kind_sql_wildcard_injection_and_limit_bounds(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})

        self.assertEqual(c.get("/api/catalog?kind=invalid").status, 400)
        for q in ("%", "_", "' OR 1=1--"):
            r = c.get(f"/api/catalog?kind=vod&q={urllib.parse.quote(q)}")
            self.assertEqual(r.status, 200)
            self.assertEqual(r.json["total"], 0, f"Wildcard/SQL query {q!r} matched unexpectedly")

        clamped = c.get("/api/catalog?kind=vod&limit=5000&page=-3")
        self.assertEqual(clamped.status, 200)
        self.assertEqual(clamped.json["page"], 1)
        self.assertLessEqual(len(clamped.json["items"]), 100)

    def test_item_detail_invalid_id_and_missing_id_return_400(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        for bad in ("bad/id", "vod:../../etc", "vod:nonexistent"):
            r = c.get(f"/api/items/{urllib.parse.quote(bad, safe='')}")
            self.assertEqual(r.status, 400, f"Expected 400 for {bad}, got {r.status}")

    def test_epg_rejects_vod_and_series_ids_and_invalid_base64(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            _wait_sync_done(c)
            vod_id = c.get("/api/catalog?kind=vod").json["items"][0]["id"]
            ser_id = c.get("/api/catalog?kind=series").json["items"][0]["id"]
            live_items = c.get("/api/catalog?kind=live").json["items"]
            corrupt_ch = next(i for i in live_items if "Haber" in i["name"])

            self.assertEqual(c.get(f"/api/epg/{vod_id}").status, 400)
            self.assertEqual(c.get(f"/api/epg/{ser_id}").status, 400)

            epg = c.get(f"/api/epg/{corrupt_ch['id']}")
            self.assertEqual(epg.status, 200, epg.text)
            titles = [p["title"] for p in epg.json["programs"]]
            self.assertIn("%%%corrupt-not-base64%%%", titles)

    def test_multiview_invalid_slot_bounds_and_fifth_slot_eviction(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "MVB"})
            live = c.get("/api/catalog?kind=live").json["items"]
            deadline = time.monotonic() + 6.0
            while len(live) < 4 and time.monotonic() < deadline:
                time.sleep(0.08)
                live = c.get("/api/catalog?kind=live").json["items"]

            for bad_slot in (4, -1, True):
                r = c.post("/api/play", {"id": live[0]["id"], "mode": "direct", "multiview": True, "multiviewSlot": bad_slot})
                self.assertEqual(r.status, 400, f"Invalid slot {bad_slot!r} should return 400")

            sids = []
            for idx in range(5):
                p = c.post("/api/play", {"id": live[idx % len(live)]["id"], "mode": "direct", "multiview": True})
                self.assertEqual(p.status, 200)
                sids.append(p.json["sessionId"])
                time.sleep(0.02)

            self.assertEqual(c.post(f"/api/play/{sids[0]}/ping", {"position": 1}).status, 410)
            for sid in sids[1:]:
                self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 1}).status, 200)

    def test_play_series_container_rejected_and_stale_generation_409(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            _wait_sync_done(c)
            ser_id = c.get("/api/catalog?kind=series").json["items"][0]["id"]
            vod_id = c.get("/api/catalog?kind=vod").json["items"][0]["id"]

            r_ser = c.post("/api/play", {"id": ser_id, "mode": "direct"})
            self.assertEqual(r_ser.status, 400)
            self.assertIn("bölüm", r_ser.text.lower())

            p5 = c.post("/api/play", {"id": vod_id, "mode": "direct", "clientId": "c_12345678", "generation": 5})
            self.assertEqual(p5.status, 200)
            p4 = c.post("/api/play", {"id": vod_id, "mode": "direct", "clientId": "c_12345678", "generation": 4})
            self.assertEqual(p4.status, 409)
            self.assertEqual((p4.json or {}).get("code"), "superseded")
            c.delete(f"/api/play/{p5.json['sessionId']}")


# =============================================================================
# F3: Discovery & Surprise Boundaries
# =============================================================================


class Tier2F3DiscoveryBoundariesTests(unittest.TestCase):
    """F3 boundaries: stale chart expiry, corrupt JSON, remake year mismatch, empty surprise, oversized."""

    def test_discovery_stale_netflix_chart_expires_after_21_days(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        old_week = (dt.datetime.now(_IST_TZ).date() - dt.timedelta(days=30)).isoformat()
        feed = {
            "version": 3,
            "updatedAt": time.time(),
            "charts": [{"name": "Big Buck Bunny", "kind": "vod", "rank": 1, "week": old_week, "source": "netflix"}],
            "metas": [],
        }
        (srv.data_dir / "discovery-public.json").write_text(json.dumps(feed), encoding="utf-8")
        shelves = c.get("/api/home").json["discovery"]["shelves"]
        ids = {s["id"] for s in shelves}
        self.assertNotIn("turkey-vod", ids)
        self.assertNotIn("turkey-series", ids)

    def test_discovery_corrupt_json_snapshot_falls_back_cleanly(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        (srv.data_dir / "discovery-public.json").write_bytes(b"{corrupt json!!!")
        home = c.get("/api/home")
        self.assertEqual(home.status, 200)
        self.assertIn("discovery", home.json)

    def test_discovery_remake_same_title_different_year_not_merged(self) -> None:
        catalog = [
            {"id": "vod:1984", "kind": "vod", "name": "Dune", "year": "1984", "poster": "", "rating": 6.5},
            {"id": "vod:2021", "kind": "vod", "name": "Dune", "year": "2021", "poster": "", "rating": 8.0},
        ]
        feed = {
            "metas": [
                {"id": "tt1160419", "kind": "vod", "name": "Dune", "year": "2021", "genres": ["Sci-Fi"], "poster": "https://example.org/d21.jpg"}
            ],
            "charts": [],
        }
        built = discovery.build(catalog, [], feed)
        scifi = next((s for s in built["shelves"] if s["id"] == "genre-vod-Sci-Fi"), None)
        self.assertIsNotNone(scifi)
        matched_ids = [i["id"] for i in scifi["items"]]
        self.assertIn("vod:2021", matched_ids)
        self.assertNotIn("vod:1984", matched_ids)

    def test_surprise_empty_library_returns_400_structured_error(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        res = c.get("/api/surprise")
        self.assertEqual(res.status, 400)
        self.assertTrue((res.json or {}).get("error"))

    def test_discovery_oversized_response_rejected_and_incomplete_read_handled(self) -> None:
        with MockUpstreamServer() as mock:
            with self.assertRaises(ValueError):
                discovery.get(f"{mock.base_url}/err/oversized_discovery.json", timeout=5)

            with self.assertRaises((json.JSONDecodeError, ValueError)):
                discovery.get_json(f"{mock.base_url}/err/incomplete", timeout=5)


# =============================================================================
# F4: Sports Guide Boundaries
# =============================================================================


class Tier2F4SportsBoundariesTests(unittest.TestCase):
    """F4 boundaries: bad date/source, XXE/malformed XMLTV, SSRF query, >8MB XML, stale cache."""

    def test_sports_rejects_invalid_date_out_of_range_and_bad_source(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        for q in ("date=2020-01-01", "date=bad-date", "source=evil"):
            r = c.get(f"/api/sports?{q}")
            self.assertEqual(r.status, 400, f"Expected 400 for {q}, got {r.status}: {r.text}")
            self.assertTrue((r.json or {}).get("error"))

    def test_sports_rejects_xxe_doctype_and_malformed_xmltv(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            for ep in ("/err/xxe.xml", "/err/bad.xml"):
                epg = urllib.parse.quote(f"{mock.base_url}{ep}", safe="")
                r = c.get(f"/api/sports?epgUrl={epg}&source=xmltv")
                self.assertEqual(r.status, 502, r.text)
                self.assertNotIn("root:", r.text)

    @requires_target("M1")
    def test_sports_ssrf_blocks_private_epg_url_query_param(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        for url in ("http://127.0.0.1:9999/epg.xml?k=1", "http://169.254.169.254/epg.xml?k=1"):
            epg = urllib.parse.quote(url, safe="")
            r = c.get(f"/api/sports?epgUrl={epg}&source=xmltv")
            self.assertIn(r.status, (400, 502), r.text)
            self.assertNotIn("http:// veya https:// ile girin", r.text)

    def test_sports_oversized_xmltv_over_8mb_rejected(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            epg = urllib.parse.quote(f"{mock.base_url}/err/oversized.xml", safe="")
            r = c.get(f"/api/sports?epgUrl={epg}&source=xmltv")
            self.assertEqual(r.status, 502, r.text)

    def test_sports_stale_cache_served_when_upstream_subsequently_fails(self) -> None:
        with MockUpstreamServer() as mock:
            import urllib.request

            today = dt.datetime.now(_IST_TZ).date()
            epg_url = f"{mock.base_url}/guide.xml"

            def _fetch(url: str, timeout: int = 15, headers: dict | None = None):
                req = urllib.request.Request(url, headers=headers or {})
                return urllib.request.urlopen(req, timeout=timeout)

            fresh = sports.get_listings(today, _fetch, epg_url=epg_url, source_mode="xmltv")
            self.assertFalse(fresh["stale"])
            self.assertGreaterEqual(len(fresh["events"]), 1)

            # Backdate cache timestamp beyond the 15s refresh cooldown without sleeping.
            cache_key = (epg_url, today)
            with sports._lock:
                ts, evs = sports._cache[cache_key]
                sports._cache[cache_key] = (ts - 30.0, evs)

            mock.xmltv_override = (500, "text/plain", b"Upstream down")
            stale = sports.get_listings(today, _fetch, epg_url=epg_url, refresh=True, source_mode="xmltv")
            self.assertTrue(stale["stale"])
            self.assertEqual(len(stale["events"]), len(fresh["events"]))


# =============================================================================
# F5: Playback, Proxy, Progress & Playlists Boundaries
# =============================================================================


class Tier2F5PlaybackAndPlaylistBoundariesTests(unittest.TestCase):
    """F5 boundaries: proxy HTML/empty/oversized, Range 416/410, progress clamp, playlist rollback, image/sub."""

    def test_media_proxy_upstream_html_empty_and_oversized_m3u8_rejected(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            for ep in ("/err/html", "/err/empty", "/err/oversized.m3u8"):
                m3u_body = f"#EXTM3U\n#EXTINF:-1,BadStream\n{mock.base_url}{ep}\n".encode("utf-8")
                mock.m3u_override = (200, "audio/x-mpegurl", m3u_body)
                c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "Bad"})
                _wait_sync_done(c)
                item = c.get("/api/catalog?kind=live").json["items"][0]
                play = c.post("/api/play", {"id": item["id"], "mode": "direct"})
                if play.status in (500, 502):
                    # Upstream error already caught safely during pre-playback probe.
                    self.assertIsInstance(play.json, dict)
                    self.assertTrue(play.json.get("error"), f"Expected error body on {ep}: {play.text}")
                    self.assertNotIn("Sign in", play.text)
                else:
                    self.assertEqual(play.status, 200, f"Unexpected /api/play status on {ep}: {play.status} {play.text}")
                    proxied = c.get(play.json["url"])
                    self.assertIn(proxied.status, (500, 502), f"Expected 502 on {ep}, got {proxied.status}")
                    self.assertNotIn("Sign in", proxied.text)
                    c.delete(f"/api/play/{play.json['sessionId']}")
            self.assertEqual(c.get("/api/health").status, 200)

    def test_media_range_416_out_of_bounds_and_expired_session_410(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        with tempfile.TemporaryDirectory(prefix="mavie_416_") as media_dir:
            (Path(media_dir) / "Tiny.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"X" * 32)
            c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "R416"})
            deadline = time.monotonic() + 5.0
            items = []
            while time.monotonic() < deadline and not items:
                items = c.get("/api/catalog?kind=vod").json["items"]
                time.sleep(0.05)

            play = c.post("/api/play", {"id": items[0]["id"], "mode": "direct"})
            sid = play.json["sessionId"]
            url = play.json["url"]
            self.assertEqual(c.get(url, headers={"Range": "bytes=99999999-"}).status, 416)
            self.assertEqual(c.delete(f"/api/play/{sid}").status, 200)
            self.assertEqual(c.get(url).status, 410)
            self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 1}).status, 410)
            self.assertEqual(c.post(f"/api/play/{sid}/pause", {"paused": True}).status, 410)

    def test_progress_clamping_negative_overflow_and_closed_session_410(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        iid = c.get("/api/catalog").json["items"][0]["id"]

        self.assertEqual(c.post("/api/progress", {"id": iid, "position": -50, "duration": -20}).status, 200)
        p1 = c.get("/api/progress").json["items"][0]["progress"]
        self.assertEqual(p1["position"], 0)
        self.assertEqual(p1["duration"], 0)

        self.assertEqual(c.post("/api/progress", {"id": iid, "position": 5000, "duration": 1000}).status, 200)
        p2 = c.get("/api/progress").json["items"][0]["progress"]
        self.assertEqual(p2["position"], 1000)
        self.assertTrue(p2["completed"])

        stale = c.post("/api/progress", {"id": iid, "position": 10, "duration": 1000, "sessionId": "closed-sid"})
        self.assertEqual(stale.status, 410)

    def test_playlist_atomic_rollback_on_invalid_reorder_and_empty_name(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        items = c.get("/api/catalog").json["items"]
        a, b = items[0]["id"], items[1]["id"]

        self.assertEqual(c.post("/api/playlists", {"name": "  "}).status, 400)
        pid = c.post("/api/playlists", {"name": "Sabit"}).json["id"]
        c.patch(f"/api/playlists/{pid}", {"itemId": a})
        c.patch(f"/api/playlists/{pid}", {"itemId": b})

        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"name": "Yeni", "order": [a, {}]}).status, 400)
        self.assertEqual(c.patch(f"/api/playlists/{pid}", {"order": [a]}).status, 400)

        cur = next(p for p in c.get("/api/playlists").json["playlists"] if p["id"] == pid)
        self.assertEqual(cur["name"], "Sabit")
        self.assertEqual([i["id"] for i in cur["items"]], [a, b])

    def test_image_proxy_rejects_svg_html_oversized_and_private_ip(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            for ep, expected in (("/err/svg", 404), ("/err/html", 404), ("/err/oversized.png", 400)):
                qurl = urllib.parse.quote(f"{mock.base_url}{ep}", safe="")
                r = c.get(f"/api/image?url={qurl}")
                self.assertEqual(r.status, expected, f"Expected {expected} for {ep}, got {r.status}")

            priv = urllib.parse.quote("http://127.0.0.1:80/a.png", safe="")
            self.assertEqual(c.get(f"/api/image?url={priv}").status, 400)
            img_dir = srv.data_dir / "images"
            cached = list(img_dir.iterdir()) if img_dir.exists() else []
            self.assertEqual(cached, [])

    def test_sidecar_subtitle_traversal_and_non_local_mode_rejected(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        self.assertEqual(c.get("/api/subtitles/vod:1/../../etc/passwd.vtt").status, 404)
        self.assertEqual(c.get("/api/subtitles/vod:1/0.vtt").status, 403)


# =============================================================================
# F6: Auth, Profiles, Backup & Security Boundaries
# =============================================================================


class Tier2F6AuthProfilesAndSecurityBoundariesTests(unittest.TestCase):
    """F6 boundaries: unauth 401, pairing 429, PIN 403/429, Host/Origin 403, import rollback, secret logs."""

    def test_pairing_wrong_code_rate_limit_429_and_unauth_401(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        guest = srv.client()
        for path in ("/api/home", "/api/catalog", "/api/export", "/api/sports", "/media/x/y"):
            self.assertEqual(guest.get(path).status, 401, f"Expected 401 on {path}")

        statuses = []
        for i in range(15):
            r = guest.post("/api/pair", {"code": f"{i:06d}"})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(403, statuses)
        self.assertIn(429, statuses)

    def test_profile_pin_validation_wrong_pin_403_and_pin_rate_limit_429(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        self.assertEqual(c.post("/api/profiles", {"name": "BadPin", "pin": "abc"}).status, 400)
        self.assertEqual(c.post("/api/profiles", {"name": "ShortPin", "pin": "12"}).status, 400)
        self.assertEqual(c.delete("/api/profiles/default").status, 400)

        pid = c.post("/api/profiles", {"name": "Locked", "pin": "1111"}).json["profile"]["id"]
        statuses = []
        for i in range(14):
            r = c.post("/api/profiles/switch", {"id": pid, "pin": f"{2000 + i}"})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(403, statuses)
        self.assertIn(429, statuses)

    def test_cross_origin_mutations_untrusted_host_and_traversal_rejected(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        conn.request("GET", "/api/health", headers={"Host": "untrusted.example"})
        r_host = conn.getresponse()
        r_host.read()
        conn.close()
        self.assertEqual(r_host.status, 403)

        self.assertEqual(c.post("/api/demo", {}, headers={"Origin": "http://evil.example"}).status, 403)
        for path in ("/%2e%2e/server.py", "/data/config.json", "/../../etc/passwd"):
            r = c.get(path)
            self.assertIn(r.status, (400, 403, 404))

    def test_backup_import_rejects_bad_version_bad_id_and_ignores_config(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        c.post("/api/demo", {})
        good_id = c.get("/api/catalog").json["items"][0]["id"]
        c.post("/api/favorites", {"id": good_id, "favorite": True})

        self.assertEqual(c.post("/api/import", {"data": {"version": 2}}).status, 400)
        bad_ep = {
            "version": 1,
            "items": [
                {
                    "id": "episode:unsafe/id",
                    "providerId": "unsafe/id",
                    "kind": "episode",
                    "name": "Bad",
                }
            ],
        }
        self.assertEqual(c.post("/api/import", {"data": bad_ep}).status, 400)
        bad_date = {"version": 1, "favorites": [{"item_id": good_id, "created_at": "not-a-date"}]}
        self.assertEqual(c.post("/api/import", {"data": bad_date}).status, 400)

        valid_with_extra = {
            "version": 1,
            "config": {"host": "http://evil.example"},
            "devices": [{"token_hash": "abc"}],
            "favorites": [],
        }
        self.assertEqual(c.post("/api/import", {"data": valid_with_extra}).status, 200)
        self.assertEqual(c.get("/api/status").json["connection"]["type"], "demo")

    def test_credentials_never_leaked_in_export_catalog_home_or_logs(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            c = srv.paired_client()
            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            _wait_sync_done(c)
            vod_id = c.get("/api/catalog?kind=vod").json["items"][0]["id"]
            play = c.post("/api/play", {"id": vod_id, "mode": "direct"})
            c.delete(f"/api/play/{play.json['sessionId']}")

            for endpoint in ("/api/export", "/api/catalog", "/api/home", "/api/favorites", "/api/playlists"):
                self.assertNotIn("demo_pass", c.get(endpoint).text, f"Password leaked in {endpoint}")
            logs = srv.stop()
            self.assertNotIn("demo_pass", logs)
            self.assertNotIn("demo_user", logs)


# =============================================================================
# F7: Web UI Boundaries (Headless Chrome)
# =============================================================================


class Tier2F7ChromeUiBoundariesTests(unittest.TestCase):
    """F7 Chrome boundaries: pairing gate, setup inline error, empty states, sports offline, XSS."""

    def test_chrome_unpaired_remote_shows_pairing_gate_not_catalog(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        host_c.post("/api/demo", {})

        with ChromeCdpSession() as chrome:
            chrome.navigate(f"{srv.base_url}/#home")
            chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")
            # Revoke devices from host so Chrome's cookie becomes unauthorized on next API check.
            host_c.post("/api/devices/revoke", {})
            chrome.evaluate("pollStatus()")
            chrome.wait_for("Boolean(document.querySelector('.pairing-screen #pairCode'))")
            has_pairing = chrome.evaluate("Boolean(document.querySelector('#pairForm'))")
            self.assertTrue(has_pairing)
            code = host_c.get("/api/status").json["pairingCode"]
            dom_text = chrome.evaluate("document.body.innerText")
            self.assertNotIn(code, dom_text)

    def test_chrome_invalid_m3u_setup_displays_inline_error_without_crash(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        with ChromeCdpSession() as chrome:
            chrome.navigate(f"{srv.base_url}/#settings")
            chrome.wait_for("Boolean(document.querySelector('#connectionForm'))")
            chrome.evaluate(
                """
                (() => {
                  const typeEl = document.querySelector('#connectionType');
                  typeEl.value = 'm3u';
                  typeEl.dispatchEvent(new Event('change'));
                  document.querySelector('#connectionM3u').value = 'http://user:pass@example.com/bad.m3u';
                  const form = document.querySelector('#connectionForm');
                  form.noValidate = true;
                  form.dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
                })()
                """
            )
            err = chrome.wait_for("document.querySelector('#settingsError')?.textContent?.trim()")
            self.assertTrue(bool(err))
            self.assertEqual(chrome.page_errors, [])

    def test_chrome_empty_search_and_empty_favorites_render_empty_state(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        srv.paired_client().post("/api/demo", {})
        with ChromeCdpSession() as chrome:
            chrome.navigate(f"{srv.base_url}/#search?q=zzznonexistent999")
            chrome.wait_for("Boolean(document.querySelector('.empty-state'))")
            layout1 = chrome.check_layout(1440)
            self.assertFalse(layout1["overflow"])

            chrome.navigate(f"{srv.base_url}/#favorites")
            chrome.wait_for("Boolean(document.querySelector('.empty-state'))")
            layout2 = chrome.check_layout(1440)
            self.assertFalse(layout2["overflow"])
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_chrome_sports_offline_shows_retry_button(self) -> None:
        with MockUpstreamServer() as mock:
            mock.sporekrani_override = (500, "text/plain", b"Outage")
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            with ChromeCdpSession() as chrome:
                chrome.navigate(f"{srv.base_url}/#sports")
                retry_txt = chrome.wait_for("document.querySelector('.sports-status button')?.textContent?.trim()")
                self.assertIn("Tekrar dene", retry_txt)
                self.assertEqual(chrome.page_errors, [])

    def test_chrome_xss_escaping_in_channel_and_playlist_names(self) -> None:
        with MockUpstreamServer() as mock:
            xss_m3u = (
                "#EXTM3U\n"
                '#EXTINF:-1 group-title="Test",<img src=x onerror="window.__xss=1">\n'
                f"{mock.base_url}/streams/live.m3u8\n"
            ).encode("utf-8")
            mock.m3u_override = (200, "audio/x-mpegurl", xss_m3u)
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "XSS"})
            _wait_sync_done(c)
            c.post("/api/playlists", {"name": '<script>window.__xss=2</script>'})

            with ChromeCdpSession() as chrome:
                chrome.navigate(f"{srv.base_url}/#live")
                chrome.wait_for("Boolean(document.querySelector('.live-card-title'))")
                title_txt = chrome.evaluate("document.querySelector('.live-card-title').textContent")
                self.assertIn("<img src=x", title_txt)
                self.assertIsNone(chrome.evaluate("window.__xss"))

                chrome.navigate(f"{srv.base_url}/#playlists")
                chrome.wait_for("Boolean(document.querySelector('.playlist-card h3'))")
                pl_txt = chrome.evaluate("document.querySelector('.playlist-card h3').textContent")
                self.assertIn("<script>window.__xss=2</script>", pl_txt)
                self.assertIsNone(chrome.evaluate("window.__xss"))
                self.assertEqual(chrome.page_errors, [])


# =============================================================================
# F8: Packaging & Hygiene Boundaries
# =============================================================================


class Tier2F8PackagingAndHygieneBoundariesTests(unittest.TestCase):
    """F8 boundaries: removed cloud files, xcodegen plist preservation, busy port/cp1252, NSC, secrets."""

    def test_removed_cloud_endpoints_and_files_absent(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        for ep in ("/api/cloud/status", "/api/cloud/login", "/api/cloud/sync", "/api/cloud/register"):
            r = c.get(ep) if ep.endswith("status") else c.post(ep, {})
            self.assertEqual(r.status, 404)
        for rel in ("cloud_admin.py", "website/admin.html", "website/admin.js", "apple/Shared/CloudClient.swift"):
            self.assertFalse((REPO_ROOT / rel).exists(), f"Removed file still present: {rel}")

    def test_xcodegen_does_not_wipe_macos_or_ios_info_plist(self) -> None:
        yml = (REPO_ROOT / "apple/project.yml").read_text(encoding="utf-8")
        self.assertIn("GENERATE_INFOPLIST_FILE: NO", yml)
        self.assertIn("INFOPLIST_FILE: macOS/Info.plist", yml)
        self.assertIn("INFOPLIST_FILE: iOS/Info.plist", yml)
        self.assertNotIn("\n    info:\n", yml)

    def test_desktop_launcher_handles_busy_port_and_cp1252_locale(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "desktop"))
        import mavie_desktop

        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("0.0.0.0", 0))
        blocker.listen(2)
        try:
            busy_port = int(blocker.getsockname()[1])
            chosen = mavie_desktop.find_free_port(busy_port)
            self.assertNotEqual(chosen, busy_port)
        finally:
            blocker.close()

        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "PYTHONIOENCODING": "cp1252"}
        srv = LocalMediaServerProcess(override_env=env).start()
        out = srv.stop()
        self.assertNotIn("UnicodeEncodeError", out)

    def test_android_network_security_pins_https_for_public_apis(self) -> None:
        nsc_path = REPO_ROOT / "android/app/src/main/res/xml/network_security_config.xml"
        root = ET.fromstring(nsc_path.read_text(encoding="utf-8"))
        pinned_exact = set()
        pinned_subdomains = set()
        for dc in root.findall("domain-config"):
            if dc.get("cleartextTrafficPermitted") == "false":
                for dom in dc.findall("domain"):
                    if dom.text:
                        name = dom.text.strip().lower()
                        pinned_exact.add(name)
                        if dom.get("includeSubdomains") == "true":
                            pinned_subdomains.add(name)
        for req_domain in ("sporekrani.com", "v3-cinemeta.strem.io", "netflix.com", "themoviedb.org", "mavie.app"):
            covered = req_domain in pinned_exact or any(
                req_domain.endswith("." + parent) for parent in pinned_subdomains
            )
            self.assertTrue(covered, f"{req_domain} missing HTTPS-only pin in {pinned_exact}")

    def test_no_real_iptv_credentials_in_repo_or_test_files(self) -> None:
        tracked = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files"], text=True).splitlines()
        for rel in tracked:
            p = REPO_ROOT / rel
            if not p.is_file() or p.suffix.lower() in (".png", ".ico", ".icns", ".jpg", ".webp", ".woff2", ".mp4", ".ts"):
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"get\.php\?username=([^&\s\"']+)", txt):
                uname = match.group(1)
                self.assertIn(
                    uname,
                    ("demo_user", "demo", "test", "testuser", "user", "USER", "<user>", "..."),
                    f"Non-placeholder get.php username in tracked file {rel}: {uname}",
                )

        # Also inspect all files under tests/e2e/ (including newly added untracked files).
        for p in (REPO_ROOT / "tests/e2e").rglob("*.py"):
            txt = p.read_text(encoding="utf-8")
            for match in re.finditer(r"get\.php\?username=([^&\s\"']+)", txt):
                uname = match.group(1)
                self.assertIn(uname, ("demo_user", "bad_user", "test"), f"Unexpected credential in {p}: {uname}")


if __name__ == "__main__":
    unittest.main()
