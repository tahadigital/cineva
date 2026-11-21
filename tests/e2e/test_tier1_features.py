"""Tier 1: Requirement-driven single-feature opaque-box E2E tests for free account-less Mavie."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

import m3u
import sports
from tests.e2e.runner import (
    LocalMediaServerProcess,
    REPO_ROOT,
)


class Tier1BrandAndHygieneTests(unittest.TestCase):
    """Brand `Mavie`, zero account/admin/Pro artifacts, repo secret hygiene."""

    def test_local_server_health_and_mavie_cookie_branding(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.client()
        health = c.get("/api/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(health.json, {"ok": True, "app": "mavie"})

        root = c.get("/")
        self.assertEqual(root.status, 200)
        self.assertIn("mavie", root.text.lower())
        self.assertNotIn("cineva", root.text.lower())
        self.assertIn("mavie_device", c.cookies_dict())

    def test_website_pages_are_free_no_account_and_mavie_branded(self) -> None:
        for rel in ("website/index.html", "website/404.html", "website/privacy.html", "website/terms.html"):
            path = REPO_ROOT / rel
            self.assertTrue(path.exists(), f"Missing website file: {rel}")
            content = path.read_text(encoding="utf-8")
            self.assertIn("Mavie", content, f"{rel} should display Mavie branding")
            self.assertNotIn("cineva", content.lower(), f"{rel} still contains Cineva branding")

        self.assertFalse((REPO_ROOT / "website/admin.html").exists())
        self.assertFalse((REPO_ROOT / "cloud_admin.py").exists())
        privacy = (REPO_ROOT / "website/privacy.html").read_text(encoding="utf-8")
        terms = (REPO_ROOT / "website/terms.html").read_text(encoding="utf-8")
        self.assertIn("privacy@mavie.app", privacy)
        self.assertIn("legal@mavie.app", terms)

    def test_repo_docs_legal_and_windows_configs_rebranded_to_mavie(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Mavie", readme)
        self.assertNotIn("Cineva", readme)

        for rel in ("legal/PRIVACY_POLICY.md", "legal/TERMS_OF_SERVICE.md"):
            txt = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("Mavie", txt)
            self.assertNotIn("Cineva", txt)

        win_files = list((REPO_ROOT / "windows").glob("*"))
        self.assertTrue(win_files, "windows/ directory must contain packaging files")
        joined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in win_files if p.is_file())
        self.assertIn("Mavie", joined)
        self.assertNotIn("Cineva", joined)

    def test_git_repo_secret_hygiene_and_android_package_mavie(self) -> None:
        tracked = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "ls-files"],
            text=True,
        ).splitlines()
        forbidden = [
            f for f in tracked
            if re.search(r"(^android/signing/|\.jks$|\.keystore$|^data/|^cloud_data/|^\.venv/|^\.env$)", f)
        ]
        self.assertEqual(forbidden, [], f"Sensitive or local data files must not be tracked: {forbidden}")

        gradle_txt = (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn("app.mavie.player", gradle_txt)
        self.assertNotIn("app.cineva.player", gradle_txt)


class Tier1LocalCatalogAndEpgTests(unittest.TestCase):
    """Local Catalog, Demo, M3U, Local folder, XMLTV EPG — all 100% free."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()

    def test_demo_catalog_populates_home_and_catalog_items(self) -> None:
        demo = self.c.post("/api/demo", {})
        self.assertEqual(demo.status, 200, demo.text)
        self.assertEqual((demo.json or {}).get("ok"), True)

        cat = self.c.get("/api/catalog")
        self.assertEqual(cat.status, 200)
        items = (cat.json or {}).get("items", [])
        self.assertGreaterEqual(len(items), 4)
        self.assertGreaterEqual(len((cat.json or {}).get("categories", [])), 1)

        home = self.c.get("/api/home")
        self.assertEqual(home.status, 200)
        self.assertIn("counts", home.json or {})

    def test_item_detail_and_surprise_recommendation_endpoints(self) -> None:
        self.assertEqual(self.c.post("/api/demo", {}).status, 200)
        items = self.c.get("/api/catalog").json["items"]
        first_id = items[0]["id"]

        detail = self.c.get(f"/api/items/{first_id}")
        self.assertEqual(detail.status, 200)
        detail_item = (detail.json or {}).get("item") or detail.json or {}
        self.assertEqual(detail_item.get("id"), first_id)

        surprise = self.c.get("/api/surprise")
        self.assertEqual(surprise.status, 200)
        self.assertTrue((surprise.json or {}).get("id") or (surprise.json or {}).get("item"))

    def test_local_media_directory_scan_and_sidecar_subtitles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mavie_media_") as media_dir:
            mp = Path(media_dir)
            (mp / "Open.Horizon.2025.1080p.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
            (mp / "Open.Horizon.2025.1080p.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello Mavie\n",
                encoding="utf-8",
            )
            res = self.c.post(
                "/api/settings",
                {"type": "local", "localDir": media_dir, "name": "Local Movies"},
            )
            self.assertEqual(res.status, 200, res.text)
            deadline = time.monotonic() + 3.0
            items = []
            while time.monotonic() < deadline:
                items = (self.c.get("/api/catalog").json or {}).get("items", [])
                if items:
                    break
                time.sleep(0.1)
            self.assertEqual(len(items), 1)
            self.assertIn("Open Horizon", items[0]["name"])
            sub = self.c.get(f"/api/subtitles/{items[0]['id']}/0.vtt")
            self.assertEqual(sub.status, 200)
            self.assertIn("WEBVTT", sub.text)
            self.assertIn("Hello Mavie", sub.text)

    def test_m3u_parse_and_catalog_import_exposes_live_channels(self) -> None:
        playlist = (
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="trtspor.tr" group-title="Spor",TRT Spor HD\n'
            'https://example.org/streams/trtspor.m3u8\n'
            '#EXTINF:-1 group-title="Belgesel",Open Science TV\n'
            'https://example.org/streams/science.m3u8\n'
        )
        parsed = m3u.parse_m3u(playlist)
        self.assertEqual(len(parsed["items"]), 2)
        self.assertEqual(parsed["items"][0]["name"], "TRT Spor HD")
        self.assertEqual(parsed["items"][0]["kind"], "live")

        self.assertEqual(self.c.post("/api/demo", {}).status, 200)
        items = self.c.get("/api/catalog").json["items"]
        target_id = items[0]["id"]
        self.assertEqual(self.c.post("/api/favorites", {"id": target_id, "favorite": True}).status, 200)
        exported = self.c.get("/api/export").json
        self.assertIn(target_id, json.dumps(exported.get("favorites", [])))

        self.assertEqual(self.c.post("/api/favorites", {"id": target_id, "favorite": False}).status, 200)
        imp = self.c.post("/api/import", {"data": exported})
        self.assertEqual(imp.status, 200, imp.text)
        favs = self.c.get("/api/favorites").json
        self.assertIn(target_id, json.dumps(favs))

    def test_sports_epg_endpoint_and_xmltv_channel_matching(self) -> None:
        resp = self.c.get("/api/sports")
        self.assertEqual(resp.status, 200)
        body = resp.json or {}
        for key in ("date", "timezone", "events", "channels"):
            self.assertIn(key, body)

        today_date = datetime.now(timezone.utc).date()
        today = today_date.strftime("%Y%m%d")
        xmltv = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<tv>"
            '<channel id="trtspor.tr"><display-name>TRT Spor</display-name></channel>'
            f'<programme start="{today}180000 +0000" stop="{today}200000 +0000" channel="trtspor.tr">'
            "<title>Super Lig Live Match</title>"
            "<category>Sports</category>"
            "</programme>"
            "</tv>"
        )
        events = sports.parse_xmltv(xmltv, today_date)
        self.assertEqual(len(events), 1)
        matched = sports.match_channels(events, [("live:trtspor", "TRT Spor HD")])
        self.assertIn("live:trtspor", json.dumps(matched))


class Tier1PlaybackLifecycleTests(unittest.TestCase):
    """Playback session creation, media proxy, ping/progress, pause, and close."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()
        self.media_dir = tempfile.TemporaryDirectory(prefix="mavie_play_")
        self.addCleanup(self.media_dir.cleanup)
        sample_file = Path(self.media_dir.name) / "Test.Clip.2025.mp4"
        sample_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"MAVIE_VIDEO_DATA" * 16)
        self.assertEqual(
            self.c.post("/api/settings", {"type": "local", "localDir": self.media_dir.name, "name": "PlayTest"}).status,
            200,
        )
        for _ in range(30):
            items = (self.c.get("/api/catalog").json or {}).get("items", [])
            if items:
                self.item_id = items[0]["id"]
                break
            time.sleep(0.1)
        else:
            self.fail("Local sample item was not indexed in time")

    def test_play_creates_session_with_url_and_track_metadata(self) -> None:
        play = self.c.post("/api/play", {"id": self.item_id})
        self.assertEqual(play.status, 200, play.text)
        data = play.json or {}
        self.assertTrue(data.get("sessionId"))
        self.assertTrue(str(data.get("url", "")).startswith("/media/"))
        self.assertIn("tracks", data)
        self.assertIn("selection", data)
        self.c.delete(f"/api/play/{data['sessionId']}")

    def test_media_proxy_streams_local_video_bytes(self) -> None:
        play = self.c.post("/api/play", {"id": self.item_id})
        self.assertEqual(play.status, 200)
        url = play.json["url"]
        sid = play.json["sessionId"]
        stream = self.c.get(url)
        self.assertIn(stream.status, (200, 206))
        self.assertIn(b"MAVIE_VIDEO_DATA", stream.raw)
        self.c.delete(f"/api/play/{sid}")

    def test_play_ping_persists_watch_progress(self) -> None:
        play = self.c.post("/api/play", {"id": self.item_id})
        sid = play.json["sessionId"]
        ping = self.c.post(f"/api/play/{sid}/ping", {"position": 42.5})
        self.assertEqual(ping.status, 200)
        self.assertEqual((ping.json or {}).get("ok"), True)

        saved = self.c.post("/api/progress", {"id": self.item_id, "position": 42.5, "duration": 600})
        self.assertEqual(saved.status, 200, saved.text)
        prog = self.c.get("/api/progress")
        self.assertEqual(prog.status, 200)
        self.assertIn("42.5", prog.text)
        self.c.delete(f"/api/play/{sid}")

    def test_play_pause_endpoint_toggles_cleanly(self) -> None:
        play = self.c.post("/api/play", {"id": self.item_id})
        sid = play.json["sessionId"]
        paused = self.c.post(f"/api/play/{sid}/pause", {"paused": True})
        self.assertEqual(paused.status, 200)
        self.assertEqual((paused.json or {}).get("ok"), True)
        resumed = self.c.post(f"/api/play/{sid}/pause", {"paused": False})
        self.assertEqual(resumed.status, 200)
        self.c.delete(f"/api/play/{sid}")

    def test_play_delete_terminates_session_cleanly(self) -> None:
        play = self.c.post("/api/play", {"id": self.item_id})
        sid = play.json["sessionId"]
        closed = self.c.delete(f"/api/play/{sid}")
        self.assertEqual(closed.status, 200)
        self.assertEqual((closed.json or {}).get("ok"), True)
        after = self.c.post(f"/api/play/{sid}/ping", {"position": 5})
        self.assertIn(after.status, (404, 410))


class Tier1ProfilesPinKidModeTests(unittest.TestCase):
    """Unlimited Profiles, PBKDF2 PIN locking, and Kid Mode content filtering — 100% free."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()

    def test_default_profile_listed_and_active(self) -> None:
        res = self.c.get("/api/profiles")
        self.assertEqual(res.status, 200)
        body = res.json or {}
        self.assertEqual(body.get("activeProfileId"), "default")
        self.assertGreaterEqual(len(body.get("profiles", [])), 1)

    def test_create_custom_profile_with_pin_and_kid_flag(self) -> None:
        res = self.c.post(
            "/api/profiles",
            {"name": "Cocuk", "isKids": True, "pin": "4321", "avatarColor": "#22C55E"},
        )
        self.assertIn(res.status, (200, 201), res.text)
        prof = (res.json or {}).get("profile", {})
        self.assertEqual(prof.get("name"), "Cocuk")
        self.assertTrue(prof.get("isKids"))
        self.assertTrue(prof.get("hasPin"))
        self.assertEqual(prof.get("avatarColor"), "#22C55E")

    def test_switch_profile_with_valid_pin_updates_active_status(self) -> None:
        prof = self.c.post("/api/profiles", {"name": "Aile", "pin": "9876"}).json["profile"]
        sw = self.c.post("/api/profiles/switch", {"id": prof["id"], "pin": "9876"})
        self.assertEqual(sw.status, 200, sw.text)
        status = self.c.get("/api/status").json
        self.assertEqual(status["profile"]["id"], prof["id"])

    def test_kid_mode_filters_adult_and_horror_catalog_items(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mavie_kid_") as media_dir:
            mp = Path(media_dir)
            (mp / "Belgesel").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Belgesel" / "Aile.Belgeseli.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"FAM" * 16)
            (mp / "Korku +18" / "Korku.Gecesi.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HOR" * 16)
            self.assertEqual(self.c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "KidTest"}).status, 200)
            for _ in range(40):
                st = self.c.get("/api/status").json or {}
                items = (self.c.get("/api/catalog").json or {}).get("items", [])
                if len(items) >= 2 and not st.get("catalog", {}).get("syncing"):
                    break
                time.sleep(0.1)

            kid = self.c.post("/api/profiles", {"name": "Kid", "isKids": True}).json["profile"]
            self.assertEqual(self.c.post("/api/profiles/switch", {"id": kid["id"]}).status, 200)
            cat = self.c.get("/api/catalog").json
            names = [i["name"] for i in cat.get("items", [])]
            self.assertIn("Aile Belgeseli", names)
            self.assertNotIn("Korku Gecesi", names)

    def test_delete_non_default_profile_succeeds(self) -> None:
        prof = self.c.post("/api/profiles", {"name": "TempProfile"}).json["profile"]
        deleted = self.c.delete(f"/api/profiles/{prof['id']}")
        self.assertEqual(deleted.status, 200)
        profiles = self.c.get("/api/profiles").json["profiles"]
        self.assertFalse(any(p["id"] == prof["id"] for p in profiles))


class Tier1LanPairingTests(unittest.TestCase):
    """LAN Pairing & Device Authorization."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)

    def test_unpaired_client_blocked_with_pairing_required_status(self) -> None:
        guest = self.srv.client()
        st = guest.get("/api/status")
        self.assertEqual(st.status, 200)
        self.assertEqual(st.json, {"authorized": False, "pairingRequired": True})
        cat = guest.get("/api/catalog")
        self.assertEqual(cat.status, 401)

    def test_authorized_status_exposes_pairing_code_and_lan_urls(self) -> None:
        host_client = self.srv.paired_client()
        st = host_client.get("/api/status")
        self.assertEqual(st.status, 200)
        self.assertTrue(st.json.get("authorized"))
        self.assertRegex(str(st.json.get("pairingCode", "")), r"^\d{6}$")
        self.assertTrue(st.json.get("network", {}).get("localUrl"))

    def test_pair_with_valid_code_sets_mavie_device_cookie(self) -> None:
        code = self.srv.paired_client().get("/api/status").json["pairingCode"]
        mobile = self.srv.client()
        res = mobile.post("/api/pair", {"code": code})
        self.assertEqual(res.status, 200, res.text)
        self.assertEqual((res.json or {}).get("ok"), True)
        self.assertIn("mavie_device", mobile.cookies_dict())

    def test_paired_cookie_grants_catalog_and_profile_access(self) -> None:
        code = self.srv.paired_client().get("/api/status").json["pairingCode"]
        mobile = self.srv.client()
        self.assertEqual(mobile.post("/api/pair", {"code": code}).status, 200)
        self.assertTrue(mobile.get("/api/status").json.get("authorized"))
        self.assertEqual(mobile.get("/api/catalog").status, 200)
        self.assertEqual(mobile.get("/api/profiles").status, 200)

    def test_revoke_devices_invalidates_paired_sessions(self) -> None:
        host_client = self.srv.paired_client()
        code = host_client.get("/api/status").json["pairingCode"]
        mobile = self.srv.client()
        self.assertEqual(mobile.post("/api/pair", {"code": code}).status, 200)
        self.assertEqual(mobile.get("/api/catalog").status, 200)

        rev = host_client.post("/api/devices/revoke", {})
        self.assertEqual(rev.status, 200, rev.text)
        self.assertEqual(mobile.get("/api/catalog").status, 401)


class Tier1WebsiteShowcaseAndFreeModelTests(unittest.TestCase):
    """Website 4-platform showcase, direct downloads, and zero account/admin/Pro UI."""

    def test_website_showcases_all_four_platform_downloads(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        for artifact in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(artifact, html, f"Website index missing download link for {artifact}")
            self.assertIn(artifact, portal_js, f"portal.js missing direct URL for {artifact}")
        for label in ("Windows", "Android", "macOS", "iOS"):
            self.assertIn(label, html)

    def test_website_has_no_account_modals_plans_or_admin_files(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        combined = html + "\n" + portal_js
        for forbidden in ("accountModal", "Mavie Pro", "verify-email", "forgot-password", "reset-password", "/api/v1/"):
            self.assertNotIn(forbidden, combined)
        self.assertIn("Tamamen Ücretsiz", html)


class Tier1MultiPlatformPackagingAndCiTests(unittest.TestCase):
    """Windows, Android, macOS, iOS projects/packaging & 4-platform CI."""

    def test_windows_desktop_launcher_and_installer_packaging_present(self) -> None:
        desktop_files = list((REPO_ROOT / "desktop").glob("*.py"))
        self.assertTrue(desktop_files)
        desktop_src = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in desktop_files)
        self.assertIn("Mavie", desktop_src)
        self.assertIn("utf-8", desktop_src.lower())

        win_specs = list((REPO_ROOT / "windows").glob("*.spec"))
        win_iss = list((REPO_ROOT / "windows").glob("*.iss"))
        self.assertTrue(win_specs and win_iss, "Windows .spec and .iss files must exist")
        iss_txt = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in win_iss)
        self.assertIn("Mavie-Setup", iss_txt)

    def test_android_project_rebranded_to_app_mavie_player_and_manifest_fixed(self) -> None:
        gradle = (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('applicationId = "app.mavie.player"', gradle)

        main_manifest = (REPO_ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("Mavie", main_manifest)
        self.assertNotIn("Cineva", main_manifest)

        test_manifest = (REPO_ROOT / "android/app/src/androidTest/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertNotIn("com.akis", test_manifest)

    def test_macos_native_app_and_dmg_packaging_present(self) -> None:
        apple_texts = []
        for folder in ("macos", "apple", "native"):
            d = REPO_ROOT / folder
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix in (".swift", ".plist", ".yml", ".yaml", ".sh", ".pbxproj", ".md"):
                        apple_texts.append(p.read_text(encoding="utf-8", errors="ignore"))
        joined = "\n".join(apple_texts)
        self.assertIn("app.mavie.macos", joined)
        self.assertIn("Mavie", joined)

    def test_ios_native_app_and_xctest_packaging_present(self) -> None:
        apple_files = []
        for folder in ("ios", "apple"):
            d = REPO_ROOT / folder
            if d.exists():
                apple_files.extend([p for p in d.rglob("*") if p.is_file()])
        self.assertTrue(apple_files, "iOS/Apple native project directory must exist")
        joined = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in apple_files
            if p.suffix in (".swift", ".plist", ".yml", ".yaml", ".sh", ".pbxproj")
        )
        self.assertIn("app.mavie.ios", joined)
        self.assertTrue("AVPlayer" in joined or "AVKit" in joined, "iOS app must use native AVKit/AVPlayer")
        self.assertTrue(any("Test" in p.name for p in apple_files), "iOS XCTest suite must be present")

    def test_github_ci_workflow_covers_all_four_platforms_and_release_assets(self) -> None:
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("macos-latest", ci)
        self.assertIn("windows-latest", ci)
        self.assertIn("ubuntu-latest", ci)
        for asset in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(asset, ci, f"CI release pipeline missing {asset}")


if __name__ == "__main__":
    unittest.main()
