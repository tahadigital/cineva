"""Tier 3: Cross-feature pairwise & multi-component integration E2E tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import time
import unittest
import urllib.parse
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


class Tier3CrossFeatureCombinationsTests(unittest.TestCase):
    """12 pairwise / multi-feature combinations across F1-F8."""

    @requires_target("M1")
    def test_m3u_plus_query_url_with_epg_query_url_drives_sports_matching(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            m3u_url = f"{mock.base_url}/get.php?username=demo_user&password=demo_pass&type=m3u_plus&output=mpegts"
            epg_url = f"{mock.base_url}/guide.xml?token=epg123&fmt=xml"
            res = c.post("/api/settings", {"type": "m3u", "name": "ComboM3U", "m3uUrl": m3u_url, "epgUrl": epg_url})
            self.assertEqual(res.status, 200, res.text)
            _wait_items(c, kind="live", min_count=3)

            sp = c.get("/api/sports?source=xmltv")
            self.assertEqual(sp.status, 200, sp.text)
            self.assertEqual(sp.json["sourceType"], "xmltv")
            self.assertTrue(sp.json["channels"], f"Expected matched channels in {sp.json}")
            self.assertIn("BeIN Sports 1", sp.json["channels"])

    @requires_target("M1")
    def test_redirected_gzipped_m3u_to_hls_proxy_and_multiview_playback(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()

            res = c.post("/api/settings", {"type": "m3u", "name": "RedirGz", "m3uUrl": f"{mock.base_url}/redirect/m3u-gzip"})
            self.assertEqual(res.status, 200, res.text)
            live = _wait_items(c, kind="live", min_count=4)
            vods = _wait_items(c, kind="vod", min_count=1)

            mv_sids = []
            for slot in range(4):
                p = c.post("/api/play", {"id": live[slot]["id"], "mode": "direct", "multiview": True, "multiviewSlot": slot})
                self.assertEqual(p.status, 200, p.text)
                mv_sids.append(p.json["sessionId"])
                if slot == 0:
                    m3u8 = c.get(p.json["url"])
                    self.assertEqual(m3u8.status, 200)
                    seg_url = next(ln for ln in m3u8.text.splitlines() if ln.startswith("/media/"))
                    self.assertEqual(c.get(seg_url).status, 200)

            single = c.post("/api/play", {"id": vods[0]["id"], "mode": "direct"})
            self.assertEqual(single.status, 200)
            for sid in mv_sids:
                self.assertEqual(c.post(f"/api/play/{sid}/ping", {"position": 1}).status, 410)
            c.delete(f"/api/play/{single.json['sessionId']}")

    def test_profile_switch_pin_isolates_favorites_playlists_and_continue_watching(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        with tempfile.TemporaryDirectory(prefix="mavie_t3_iso_") as media_dir:
            mp = Path(media_dir)
            (mp / "Belgesel").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Belgesel" / "Doga.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"D" * 32)
            (mp / "Korku +18" / "Korku.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"K" * 32)
            c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Iso"})
            items = _wait_items(c, kind="vod", min_count=2)
            safe_item = next(i for i in items if "Doga" in i["name"])
            horror_item = next(i for i in items if "Korku" in i["name"])

            c.post("/api/favorites", {"id": horror_item["id"], "favorite": True})
            c.post("/api/progress", {"id": horror_item["id"], "position": 120, "duration": 600})
            pl_id = c.post("/api/playlists", {"name": "Yetişkin Listesi"}).json["id"]
            c.patch(f"/api/playlists/{pl_id}", {"itemId": horror_item["id"]})

            kid = c.post("/api/profiles", {"name": "KidSafe", "isKids": True, "pin": "2468"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "2468"}).status, 200)
            self.assertEqual(c.get("/api/favorites").json["items"], [])
            self.assertEqual(c.get("/api/playlists").json["playlists"], [])
            self.assertEqual(c.get("/api/home").json["continueWatching"], [])
            self.assertNotIn(horror_item["name"], [i["name"] for i in c.get("/api/catalog").json["items"]])

            c.post("/api/favorites", {"id": safe_item["id"], "favorite": True})
            self.assertEqual(c.post("/api/profiles/switch", {"id": "default"}).status, 200)
            fav_ids = [i["id"] for i in c.get("/api/favorites").json["items"]]
            self.assertEqual(fav_ids, [horror_item["id"]])
            self.assertEqual(len(c.get("/api/playlists").json["playlists"]), 1)

    def test_kid_profile_isolates_discovery_shelves_and_surprise_from_horror(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()
        year = dt.datetime.now(_IST_TZ).year
        today_str = dt.datetime.now(_IST_TZ).date().isoformat()
        with tempfile.TemporaryDirectory(prefix="mavie_t3_disc_") as media_dir:
            mp = Path(media_dir)
            (mp / "Komedi").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Komedi" / f"Neseli.Gun.{year}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"C" * 32)
            (mp / "Korku +18" / f"Korku.Evi.{year}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"H" * 32)
            feed = {
                "version": 3,
                "updatedAt": time.time(),
                "metas": [
                    {"id": "tt1", "kind": "vod", "name": "Neseli Gun", "year": str(year), "genres": ["Comedy"], "released": today_str},
                    {"id": "tt2", "kind": "vod", "name": "Korku Evi", "year": str(year), "genres": ["Horror"], "released": today_str},
                ],
                "charts": [],
            }
            (srv.data_dir / "discovery-public.json").write_text(json.dumps(feed), encoding="utf-8")
            c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "KidDisc"})
            _wait_items(c, kind="vod", min_count=2)

            adult_shelves = [s["id"] for s in c.get("/api/home").json["discovery"]["shelves"]]
            self.assertIn("genre-vod-Horror", adult_shelves)

            kid_id = c.post("/api/profiles", {"name": "Minik", "isKids": True}).json["profile"]["id"]
            c.post("/api/profiles/switch", {"id": kid_id})
            kid_home = c.get("/api/home").json
            kid_shelf_names = [i["name"] for s in kid_home["discovery"]["shelves"] for i in s["items"]]
            self.assertNotIn("Korku Evi", kid_shelf_names)
            for _ in range(5):
                pick = c.get("/api/surprise").json["item"]
                self.assertNotIn("Korku", pick["name"])

    @requires_target("M1")
    def test_lan_pairing_settings_non_destructive_refresh_and_playback(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            host_c = srv.paired_client()
            host_c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "PairND"})
            live = _wait_items(host_c, kind="live", min_count=4)

            code = host_c.get("/api/status").json["pairingCode"]
            mobile = srv.client()
            self.assertEqual(mobile.post("/api/pair", {"code": code}).status, 200)
            self.assertEqual(
                mobile.post("/api/settings", {"type": "demo"}, headers={"Origin": "http://evil.example"}).status,
                403,
            )

            mock.m3u_override = (500, "text/plain", b"Outage")
            self.assertEqual(mobile.post("/api/catalog/sync", {}).status, 202)
            st = _wait_sync_done(mobile)
            self.assertTrue(st["catalog"].get("error"))
            self.assertGreaterEqual(len(mobile.get("/api/catalog?kind=live").json["items"]), 4)

            play = mobile.post("/api/play", {"id": live[0]["id"], "mode": "direct"})
            self.assertEqual(play.status, 200)
            self.assertEqual(mobile.get(play.json["url"]).status, 200)
            mobile.delete(f"/api/play/{play.json['sessionId']}")

            host_c.post("/api/devices/revoke", {})
            self.assertEqual(mobile.get("/api/catalog").status, 401)

    def test_xtream_series_episodes_progress_export_to_clean_server_import(self) -> None:
        with MockUpstreamServer() as mock:
            srv1 = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv1.stop)
            c1 = srv1.paired_client()
            c1.post("/api/settings", {"type": "xtream", "host": mock.base_url, "username": "demo_user", "password": "demo_pass"})
            ser = _wait_items(c1, kind="series", min_count=1)[0]
            eps = c1.get(f"/api/items/{ser['id']}").json["seasons"][0]["episodes"]
            e1, e2 = eps[0]["id"], eps[1]["id"]

            c1.post("/api/progress", {"id": e1, "position": 2400, "duration": 2400, "completed": True})
            c1.post("/api/progress", {"id": e2, "position": 120, "duration": 2500})
            c1.post("/api/track-preferences", {"id": e2, "audio": "stream:1", "subtitle": "stream:2"})
            exported = c1.get("/api/export").json

            srv2 = LocalMediaServerProcess().start()
            self.addCleanup(srv2.stop)
            c2 = srv2.paired_client()
            self.assertEqual(c2.post("/api/import", {"data": exported}).status, 200)
            cw = c2.get("/api/home").json["continueWatching"]
            self.assertTrue(any(i["id"] == e2 for i in cw))
            self.assertEqual(c2.get(f"/api/tracks/{e2}").json["selection"]["subtitle"], "stream:2")

    def test_local_media_scan_subtitles_discovery_and_xmltv_sports_restart_persistence(self) -> None:
        with MockUpstreamServer() as mock, tempfile.TemporaryDirectory(prefix="mavie_t3_media_") as media_dir, tempfile.TemporaryDirectory(prefix="mavie_t3_data_") as data_dir:
            mp = Path(media_dir)
            (mp / "Spor").mkdir()
            (mp / "Spor" / "BeIN.Sports.1.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"S" * 32)
            (mp / "Spor" / "BeIN.Sports.1.2025.tr.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nMaç Başlıyor\n", encoding="utf-8")
            (Path(data_dir) / "discovery-public.json").write_text(
                json.dumps({"version": 3, "updatedAt": time.time(), "metas": [], "charts": []}),
                encoding="utf-8",
            )
            env = {"MAVIE_DATA_DIR": data_dir, "CINEVA_DATA_DIR": data_dir}

            srv1 = LocalMediaServerProcess(extra_env=env, allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            try:
                c1 = srv1.paired_client()
                c1.post("/api/settings", {"type": "local", "localDir": media_dir, "epgUrl": f"{mock.base_url}/guide.xml", "name": "PersistAll"})
                items = _wait_items(c1, kind="vod", min_count=1)
                iid = items[0]["id"]
                c1.post("/api/progress", {"id": iid, "position": 95, "duration": 400})
                c1.post("/api/favorites", {"id": iid, "favorite": True})
            finally:
                srv1.stop()

            srv2 = LocalMediaServerProcess(extra_env=env, allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            try:
                c2 = srv2.paired_client()
                self.assertIn("95", c2.get("/api/progress").text)
                self.assertIn("Maç Başlıyor", c2.get(f"/api/subtitles/{iid}/0.vtt").text)
                self.assertIn("discovery", c2.get("/api/home").json)
                sp = c2.get("/api/sports?source=xmltv")
                self.assertEqual(sp.status, 200)
                self.assertGreaterEqual(len(sp.json["events"]), 1)
            finally:
                srv2.stop()

    @requires_target("M1")
    def test_chrome_setup_demo_to_home_detail_and_player_flow(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        with ChromeCdpSession() as chrome:
            chrome.navigate(f"{srv.base_url}/")
            chrome.wait_for("Boolean(document.querySelector('.setup-intro [data-action=\"demo\"]'))")
            chrome.evaluate("document.querySelector('[data-action=\"demo\"]').click()")
            chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")
            glass = chrome.inspect_liquid_glass([".topbar"])
            self.assertIn("blur(", glass[".topbar"]["backdrop"].lower())

            chrome.evaluate("document.querySelector('.media-card .poster-button').click()")
            chrome.wait_for("Boolean(document.querySelector('#detailDialog[open] [data-action=\"play\"]'))")
            chrome.evaluate("document.querySelector('#detailDialog [data-action=\"play\"]').click()")
            chrome.wait_for("Boolean(document.querySelector('#playerDialog[open]'))")
            layout = chrome.check_layout(1440, control_selectors=("#closePlayer", "#togglePlay"))
            self.assertFalse(layout["overflow"])
            self.assertEqual(layout["clipped"], [])
            chrome.evaluate("document.querySelector('#closePlayer').click()")
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    @requires_target("M1")
    def test_chrome_sports_page_clicks_matched_channel_to_open_player(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post(
                "/api/settings",
                {
                    "type": "m3u",
                    "m3uUrl": f"{mock.base_url}/m3u/plain.m3u",
                    "epgUrl": f"{mock.base_url}/guide.xml?token=sp9",
                    "name": "ChromeSports",
                },
            )
            _wait_items(c, kind="live", min_count=3)

            with ChromeCdpSession() as chrome:
                chrome.navigate(f"{srv.base_url}/#sports?source=xmltv")
                chrome.wait_for("Boolean(document.querySelector('.sports-channel.playable'))")
                chrome.evaluate("document.querySelector('.sports-channel.playable').click()")
                chrome.wait_for("Boolean(document.querySelector('#playerDialog[open]'))")
                title = chrome.evaluate("document.querySelector('#playerTitle').textContent")
                self.assertTrue(bool(title))
                chrome.evaluate("document.querySelector('#closePlayer').click()")
                self.assertEqual(chrome.page_errors, [])

    def test_chrome_multiview_slot_selection_and_single_mute_toggle(self) -> None:
        with MockUpstreamServer() as mock:
            srv = LocalMediaServerProcess(allow_mock_port=mock.port, mock_base_url=mock.base_url).start()
            self.addCleanup(srv.stop)
            c = srv.paired_client()
            c.post("/api/settings", {"type": "m3u", "m3uUrl": f"{mock.base_url}/m3u/plain.m3u", "name": "ChromeMV"})
            _wait_items(c, kind="live", min_count=4)

            with ChromeCdpSession() as chrome:
                chrome.navigate(f"{srv.base_url}/#multiview")
                chrome.wait_for("document.querySelectorAll('.multiview-tile video').length === 4")
                chrome.evaluate("document.querySelector('[data-mv-mute=\"1\"]').click()")
                self.assertEqual(chrome.evaluate("document.querySelector('[data-mv-mute=\"1\"]').getAttribute('aria-pressed')"), "true")
                self.assertEqual(chrome.evaluate("document.querySelector('#mvVideo1').muted"), False)

                chrome.evaluate("document.querySelector('[data-mv-mute=\"2\"]').click()")
                self.assertEqual(chrome.evaluate("document.querySelector('[data-mv-mute=\"1\"]').getAttribute('aria-pressed')"), "false")
                self.assertEqual(chrome.evaluate("document.querySelector('#mvVideo1').muted"), True)
                self.assertEqual(chrome.evaluate("document.querySelector('[data-mv-mute=\"2\"]').getAttribute('aria-pressed')"), "true")
                self.assertEqual(chrome.evaluate("document.querySelector('#mvVideo2').muted"), False)
                self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_chrome_lan_pairing_and_profile_pin_dialog_interaction(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        host_c.post("/api/demo", {})

        with ChromeCdpSession() as chrome:
            chrome.navigate(f"{srv.base_url}/#home")
            chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")
            host_c.post("/api/devices/revoke", {})
            chrome.evaluate("pollStatus()")
            chrome.wait_for("Boolean(document.querySelector('#pairCode'))")

            code = host_c.get("/api/status").json["pairingCode"]
            chrome.evaluate(
                f"""
                (() => {{
                  document.querySelector('#pairCode').value = {json.dumps(code)};
                  document.querySelector('#pairForm').dispatchEvent(new Event('submit', {{cancelable: true, bubbles: true}}));
                }})()
                """
            )
            chrome.wait_for("Boolean(document.querySelector('.cinema-hero'))")

            chrome.evaluate("document.querySelector('#profileAvatarBtn').click()")
            chrome.wait_for("Boolean(document.querySelector('#createProfileForm'))")
            chrome.evaluate(
                """
                (() => {
                  document.querySelector('#newProfileName').value = 'ChromeKid';
                  document.querySelector('#newProfilePin').value = '2468';
                  document.querySelector('#newProfileKids').checked = true;
                  document.querySelector('#createProfileForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
                })()
                """
            )
            chrome.wait_for("Boolean(document.querySelector('[data-pick-profile][data-has-pin=\"1\"]'))")
            chrome.evaluate("document.querySelector('[data-pick-profile][data-has-pin=\"1\"]').click()")
            chrome.wait_for("!document.querySelector('#pinPromptBox').hidden")
            chrome.evaluate(
                """
                (() => {
                  document.querySelector('#switchPinInput').value = '2468';
                  document.querySelector('#confirmPinBtn').click();
                })()
                """
            )
            chrome.wait_for("document.querySelector('#profileInitial')?.textContent === 'C'")
            self.assertEqual(chrome.console_errors + chrome.page_errors, [])

    def test_website_assets_match_ci_and_windows_macos_bundles_reference_server(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        ci_yml = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        spec_txt = (REPO_ROOT / "windows/mavie.spec").read_text(encoding="utf-8")
        mac_sh = (REPO_ROOT / "apple/macOS/build_macos.sh").read_text(encoding="utf-8")
        mac_spec_path = REPO_ROOT / "apple/macOS/mavie_server.spec"
        mac_bundle_src = mac_sh + ("\n" + mac_spec_path.read_text(encoding="utf-8") if mac_spec_path.is_file() else "")

        for asset in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(asset, html)
            self.assertIn(asset, portal_js)
            self.assertIn(asset, ci_yml)
        for mod in ("server", "m3u", "sports", "discovery", "playback"):
            self.assertIn(mod, spec_txt)
        for rel in ("server.py", "m3u", "sports", "discovery", "playback", "public"):
            self.assertIn(rel, mac_bundle_src)


if __name__ == "__main__":
    unittest.main()
