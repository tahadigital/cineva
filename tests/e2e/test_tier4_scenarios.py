"""Tier 4: End-to-end real-world application scenarios for free account-less Mavie."""

from __future__ import annotations

import ast
import datetime as dt
import http.client
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


def _wait_items(client, kind: str = "vod", min_count: int = 1, timeout: float = 8.0) -> list:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get("/api/status").json or {}
        items = (client.get(f"/api/catalog?kind={kind}&limit=100").json or {}).get("items", [])
        if len(items) >= min_count and not st.get("catalog", {}).get("syncing"):
            return items
        time.sleep(0.08)
    raise AssertionError(f"Expected >= {min_count} {kind} items")


class Tier4EndToEndScenariosTests(unittest.TestCase):
    """7 realistic multi-step user journeys across F1-F8."""

    @requires_target("M1")
    def test_scenario_1_fresh_m3u_plus_setup_sync_live_vod_and_hls_playback(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            m3u_url = f"{mock.base_url}/get.php?username=demo_user&password=demo_pass&type=m3u_plus&output=mpegts"
            epg_url = f"{mock.base_url}/guide.xml?token=epg123"
            self.assertEqual(
                c.post("/api/settings", {"type": "m3u", "name": "Ev IPTV", "m3uUrl": m3u_url, "epgUrl": epg_url}).status,
                200,
            )
            st = _wait_sync_done(c)
            self.assertIsNone(st["catalog"].get("error"))

            live = _wait_items(c, kind="live", min_count=4)
            vods = _wait_items(c, kind="vod", min_count=1)
            search = c.get("/api/catalog?kind=vod&q=ISIKLAR").json["items"]
            self.assertEqual([i["name"] for i in search], ["Işıklar İçinde"])

            play_live = c.post("/api/play", {"id": live[0]["id"], "mode": "direct"})
            self.assertEqual(play_live.status, 200)
            m3u8 = c.get(play_live.json["url"])
            self.assertEqual(m3u8.status, 200)
            seg_url = next(ln for ln in m3u8.text.splitlines() if ln.startswith("/media/"))
            self.assertEqual(c.get(seg_url).status, 200)
            c.delete(f"/api/play/{play_live.json['sessionId']}")

            play_vod = c.post("/api/play", {"id": vods[0]["id"], "mode": "direct"})
            self.assertEqual(play_vod.status, 200)
            c.post("/api/progress", {"id": vods[0]["id"], "position": 240, "duration": 1800, "sessionId": play_vod.json["sessionId"]})
            c.delete(f"/api/play/{play_vod.json['sessionId']}")

            # Transient upstream 500 during refresh must preserve existing library.
            mock.m3u_override = (500, "text/plain", b"Transient failure")
            self.assertEqual(c.post("/api/catalog/sync", {}).status, 202)
            st2 = _wait_sync_done(c)
            self.assertTrue(st2["catalog"].get("error"))
            self.assertEqual(len(c.get("/api/catalog?kind=live").json["items"]), len(live))
            self.assertIn("240", c.get("/api/progress").text)

    def test_scenario_2_xtream_family_household_discovery_sports_and_kid_mode(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            today_str = dt.datetime.now(_IST_TZ).date().isoformat()
            feed = {
                "version": 3,
                "updatedAt": time.time(),
                "hasCinemeta": True,
                "chartSource": "netflix",
                "metas": [
                    {"id": "tt1", "kind": "vod", "name": "Işıklar İçinde", "year": "2025", "genres": ["Comedy"], "poster": f"{mock.base_url}/posters/thumb.png", "released": today_str},
                    {"id": "tt2", "kind": "vod", "name": "Çığlık Şöleni", "year": "2024", "genres": ["Horror"], "released": today_str},
                    {"id": "tt3", "kind": "series", "name": "Gece Yolculuğu", "year": "2025", "genres": ["Drama"], "poster": f"{mock.base_url}/posters/thumb.png", "released": today_str},
                ],
                "charts": [
                    {"name": "Işıklar İçinde", "kind": "vod", "rank": 1, "week": today_str, "source": "netflix"},
                    {"name": "Gece Yolculuğu", "kind": "series", "rank": 1, "week": today_str, "source": "netflix"},
                ],
            }
            (srv.data_dir / "discovery-public.json").write_text(json.dumps(feed), encoding="utf-8")

            c.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass", "epgUrl": f"{mock.base_url}/guide.xml"})
            live = _wait_items(c, kind="live", min_count=4)
            series = _wait_items(c, kind="series", min_count=1)
            vods = _wait_items(c, kind="vod", min_count=2)

            comedy = next(i for i in vods if "Işıklar" in i["name"])
            c.post("/api/favorites", {"id": comedy["id"], "favorite": True})

            eps = c.get(f"/api/items/{series[0]['id']}").json["seasons"][0]["episodes"]
            c.post("/api/progress", {"id": eps[0]["id"], "position": 2400, "duration": 2400})
            cw = c.get("/api/home").json["continueWatching"]
            self.assertEqual(cw[0]["id"], eps[1]["id"])
            self.assertEqual(cw[0]["continueReason"], "nextEpisode")

            sp = c.get("/api/sports?source=xmltv").json
            fhd_id = next(i["id"] for i in live if i["name"] == "TR: BeIN Sports 1 FHD")
            self.assertEqual(sp["channels"]["BeIN Sports 1"]["id"], fhd_id)

            kid = c.post("/api/profiles", {"name": "Çocuk", "isKids": True, "pin": "1357"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "4040"}).status, 403)
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "1357"}).status, 200)

            kid_names = [i["name"] for i in c.get("/api/catalog?kind=vod").json["items"]]
            self.assertNotIn("Çığlık Şöleni", kid_names)
            kid_disc_names = [i["name"] for s in c.get("/api/home").json["discovery"]["shelves"] for i in s["items"]]
            self.assertNotIn("Çığlık Şöleni", kid_disc_names)

    def test_scenario_3_multi_device_lan_pairing_multiview_playlist_and_backup_migration(self) -> None:
        with MockUpstreamServer() as mock:
            srv1 = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv1.stop)
            host_c = srv1.paired_client()
            host_c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "Main"})
            live = _wait_items(host_c, kind="live", min_count=4)
            vods = _wait_items(host_c, kind="vod", min_count=1)

            code = host_c.get("/api/status").json["pairingCode"]
            tablet = srv1.client()
            self.assertEqual(tablet.post("/api/pair", {"code": code}).status, 200)

            pl_id = tablet.post("/api/playlists", {"name": "Tablet Seçkisi"}).json["id"]
            tablet.patch(f"/api/playlists/{pl_id}", {"itemId": live[0]["id"]})
            tablet.patch(f"/api/playlists/{pl_id}", {"itemId": vods[0]["id"]})
            tablet.patch(f"/api/playlists/{pl_id}", {"order": [vods[0]["id"], live[0]["id"]]})
            tablet.post("/api/favorites", {"id": vods[0]["id"], "favorite": True})
            tablet.post("/api/progress", {"id": vods[0]["id"], "position": 333, "duration": 900})
            tablet.post("/api/track-preferences", {"id": vods[0]["id"], "audio": "stream:1"})

            mv_sids = []
            for slot in range(4):
                p = tablet.post("/api/play", {"id": live[slot]["id"], "mode": "direct", "multiview": True, "multiviewSlot": slot})
                self.assertEqual(p.status, 200)
                mv_sids.append(p.json["sessionId"])
            promo = tablet.post("/api/play", {"id": live[0]["id"], "mode": "direct"})
            self.assertEqual(promo.status, 200)
            for sid in mv_sids:
                self.assertEqual(tablet.post(f"/api/play/{sid}/ping", {"position": 1}).status, 410)
            tablet.delete(f"/api/play/{promo.json['sessionId']}")

            exported = host_c.get("/api/export").json
            self.assertEqual(exported["version"], 1)

            srv2 = LocalMediaServerProcess().start()
            self.addCleanup(srv2.stop)
            c2 = srv2.paired_client()
            self.assertEqual(c2.post("/api/import", {"data": exported}).status, 200)
            pls = c2.get("/api/playlists").json["playlists"]
            self.assertEqual([i["id"] for i in pls[0]["items"]], [vods[0]["id"], live[0]["id"]])
            self.assertIn(vods[0]["id"], [i["id"] for i in c2.get("/api/favorites").json["items"]])
            self.assertEqual(c2.get("/api/progress").json["items"][0]["progress"]["position"], 333)
            self.assertEqual(c2.get(f"/api/tracks/{vods[0]['id']}").json["selection"]["audio"], "stream:1")

    def test_scenario_4_local_media_library_subtitles_resume_and_restart_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mavie_s4_media_") as media_dir, tempfile.TemporaryDirectory(prefix="mavie_s4_data_") as data_dir:
            mp = Path(media_dir)
            (mp / "Filmler").mkdir()
            (mp / "Filmler" / "Anadolu.2025.1080p.mkv").write_bytes(b"\x1a\x45\xdf\xa3" + b"MKV_BYTES" * 64)
            (mp / "Filmler" / "Anadolu.2025.1080p.tr.srt").write_bytes(
                "1\r\n00:00:01,000 --> 00:00:03,000\r\nŞanlıurfa Güneşi\r\n".encode("cp1254")
            )
            env = {"MAVIE_DATA_DIR": data_dir, "CINEVA_DATA_DIR": data_dir}

            srv1 = LocalMediaServerProcess(extra_env=env).start()
            try:
                c1 = srv1.paired_client()
                c1.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "YerelArsiv"})
                items = _wait_items(c1, kind="vod", min_count=1)
                iid = items[0]["id"]

                tracks = c1.get(f"/api/tracks/{iid}").json
                self.assertEqual(len(tracks["externalSubtitles"]), 1)
                play = c1.post("/api/play", {"id": iid, "mode": "direct"})
                self.assertEqual(play.status, 200)
                sid = play.json["sessionId"]
                self.assertEqual(c1.get(play.json["url"], headers={"Range": "bytes=0-15"}).status, 206)
                c1.post(f"/api/play/{sid}/ping", {"position": 450})
                c1.post("/api/progress", {"id": iid, "position": 450, "duration": 3600})
                c1.post(f"/api/play/{sid}/pause", {"paused": True})
                c1.delete(f"/api/play/{sid}")
            finally:
                srv1.stop()

            srv2 = LocalMediaServerProcess(extra_env=env).start()
            try:
                c2 = srv2.paired_client()
                cw = c2.get("/api/home").json["continueWatching"]
                self.assertEqual(cw[0]["id"], iid)
                self.assertEqual(cw[0]["progress"]["position"], 450)
                vtt = c2.get(f"/api/subtitles/{iid}/0.vtt")
                self.assertEqual(vtt.status, 200)
                self.assertIn("Şanlıurfa Güneşi", vtt.text)
            finally:
                srv2.stop()

    @requires_target("M1")
    def test_scenario_5_headless_chrome_full_visual_liquid_glass_journey(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            with ChromeCdpSession() as chrome:
                # 1. Setup screen
                chrome.navigate(f"{srv.base_url}/#settings")
                chrome.wait_for("Boolean(document.querySelector('#connectionForm'))")

                # 2. Activate Demo & inspect Home Liquid Glass on desktop & mobile
                srv.paired_client().post("/api/demo", {})
                for w, h, mobile in ((1440, 900, False), (390, 844, True)):
                    chrome.set_viewport(w, h, mobile=mobile)
                    chrome.navigate(f"{srv.base_url}/#home")
                    chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")
                    layout = chrome.check_layout(w)
                    self.assertFalse(layout["overflow"], f"Home overflow at {w}x{h}")
                    self.assertEqual(layout["clipped"], [])

                glass = chrome.inspect_liquid_glass([".topbar", ".cinema-hero .button"])
                self.assertIn("blur(", glass[".topbar"]["backdrop"].lower())
                marks = chrome.inspect_palette_and_marks()
                self.assertEqual(marks["kickerSize"], {"width": 24, "height": 24})
                self.assertEqual(marks["legacyColors"], [])

                # 3. Sports Guide + Detail + Player
                chrome.set_viewport(1440, 900, mobile=False)
                chrome.navigate(f"{srv.base_url}/#sports")
                chrome.wait_for("document.querySelectorAll('.sports-event').length >= 1")
                chrome.navigate(f"{srv.base_url}/#vod")
                chrome.wait_for("document.querySelectorAll('.media-card').length >= 1")
                chrome.evaluate("document.querySelector('.media-card .poster-button').click()")
                chrome.wait_for("Boolean(document.querySelector('#detailDialog[open] [data-action=\"play\"]'))")
                chrome.evaluate("document.querySelector('#detailDialog [data-action=\"play\"]').click()")
                chrome.wait_for("Boolean(document.querySelector('#playerDialog[open]'))")
                chrome.evaluate("document.querySelector('#closePlayer').click()")

                # 4. Profiles dialog
                chrome.evaluate("document.querySelector('#profileAvatarBtn').click()")
                chrome.wait_for("Boolean(document.querySelector('#createProfileForm'))")
                self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_scenario_6_cross_platform_packaging_website_and_windows_locale_stability(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        ci_yml = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for asset in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(asset, html)
            self.assertIn(asset, portal_js)
            self.assertIn(asset, ci_yml)

        ast.parse((REPO_ROOT / "windows/mavie.spec").read_text(encoding="utf-8"))
        self.assertIn("Mavie-Setup", (REPO_ROOT / "windows/MavieSetup.iss").read_text(encoding="utf-8"))
        ico_magic = struct.unpack("<HHH", (REPO_ROOT / "windows/mavie.ico").read_bytes()[:6])
        self.assertEqual(ico_magic[:2], (0, 1))
        self.assertIn('applicationId = "app.mavie.player"', (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8"))
        self.assertEqual(plistlib.loads((REPO_ROOT / "apple/macOS/Info.plist").read_bytes()).get("CFBundleIdentifier"), "app.mavie.macos")

        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "PYTHONIOENCODING": "cp1252"}
        srv = LocalMediaServerProcess(override_env=env).start()
        try:
            time.sleep(1.5)
            self.assertIsNone(srv.proc.poll())
            self.assertEqual(srv.client().get("/api/health").json, {"ok": True, "app": "mavie"})
            self.assertTrue((srv.data_dir / "server.pid").exists())
        finally:
            out = srv.stop()
        self.assertNotIn("UnicodeEncodeError", out)

    def test_scenario_7_security_audit_ssrf_xxe_xss_rate_limit_and_secret_hygiene(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess().start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            # SSRF private IPs blocked on default server
            for url in ("http://127.0.0.1:9999/a.m3u", "http://169.254.169.254/latest/meta-data/"):
                r = c.post("/api/settings", {"type": "m3u", "m3uUrl": url})
                if r.status == 200:
                    st = _wait_sync_done(c)
                    self.assertTrue(st["catalog"]["error"])
                else:
                    self.assertIn(r.status, (400, 403))

            # Path traversal & Host/Origin guards
            self.assertIn(c.get("/%2e%2e/server.py").status, (400, 403, 404))
            self.assertEqual(c.post("/api/demo", {}, headers={"Origin": "http://evil.example"}).status, 403)
            conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
            conn.request("GET", "/api/health", headers={"Host": "evil.example"})
            hr = conn.getresponse()
            hr.read()
            conn.close()
            self.assertEqual(hr.status, 403)

            # Pairing brute-force rate limit 429
            guest = srv.client()
            pair_statuses = []
            for i in range(15):
                resp = guest.post("/api/pair", {"code": f"{i:06d}"})
                pair_statuses.append(resp.status)
                if resp.status == 429:
                    break
            self.assertIn(429, pair_statuses)

            # XXE & SVG rejection on mock-enabled server
            srv2 = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv2.stop)
            c2 = srv2.paired_client()
            xxe_epg = urllib.parse.quote(f"{mock.base_url}/err/xxe.xml", safe="")
            r_xxe = c2.get(f"/api/sports?epgUrl={xxe_epg}&source=xmltv")
            self.assertEqual(r_xxe.status, 502)
            self.assertNotIn("root:", r_xxe.text)
            svg_img = urllib.parse.quote(f"{mock.base_url}/err/svg", safe="")
            self.assertEqual(c2.get(f"/api/image?url={svg_img}").status, 404)

        # Repo-scoped git & test hygiene check (strictly inside Cineva)
        tracked = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files"], text=True).splitlines()
        for f in tracked:
            self.assertFalse(
                bool(re.search(r"(^android/signing/|\.jks$|\.keystore$|^data/|^cloud_data/|^\.venv/|^\.env$)", f)),
                f"Tracked sensitive/local path: {f}",
            )


if __name__ == "__main__":
    unittest.main()
