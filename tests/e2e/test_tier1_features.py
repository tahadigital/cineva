"""Tier 1: Requirement-driven single-feature opaque-box E2E tests (>=5 per feature area)."""

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
    CloudServerProcess,
    HttpClient,
    LocalMediaServerProcess,
    REPO_ROOT,
    parse_iso_dt,
)


class Tier1BrandAndHygieneTests(unittest.TestCase):
    """Feature #1 & #2: Brand `Vrelio`, zero unwanted Cineva branding, repo secret hygiene."""

    def test_local_server_health_and_vrelio_cookie_branding(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.client()
        health = c.get("/api/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(health.json, {"ok": True, "app": "vrelio"})

        root = c.get("/")
        self.assertEqual(root.status, 200)
        self.assertIn("vrelio", root.text.lower())
        self.assertNotIn("cineva", root.text.lower())
        self.assertIn("vrelio_device", c.cookies_dict())

    def test_cloud_server_health_and_vrelio_license_prefix(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        health = cloud.client().get("/api/v1/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(health.json, {"ok": True, "service": "vrelio-cloud"})

        tok = cloud.admin_login()
        lic = cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 30, "count": 1},
            headers=cloud.admin_headers(tok),
        )
        self.assertIn(lic.status, (200, 201), lic.text)
        code = (lic.json or {}).get("license", {}).get("code", "")
        self.assertRegex(code, r"^VRELIO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_website_pages_use_vrelio_branding_and_emails(self) -> None:
        for rel in ("website/index.html", "website/admin.html", "website/privacy.html", "website/terms.html"):
            path = REPO_ROOT / rel
            self.assertTrue(path.exists(), f"Missing website file: {rel}")
            content = path.read_text(encoding="utf-8")
            self.assertIn("Vrelio", content, f"{rel} should display Vrelio branding")
            self.assertNotIn("cineva", content.lower(), f"{rel} still contains Cineva branding")

        privacy = (REPO_ROOT / "website/privacy.html").read_text(encoding="utf-8")
        terms = (REPO_ROOT / "website/terms.html").read_text(encoding="utf-8")
        self.assertIn("privacy@vrelio.app", privacy)
        self.assertIn("legal@vrelio.app", terms)

    def test_repo_docs_legal_and_windows_configs_rebranded_to_vrelio(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Vrelio", readme)
        self.assertNotIn("Cineva", readme)

        for rel in ("legal/PRIVACY_POLICY.md", "legal/TERMS_OF_SERVICE.md"):
            txt = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("Vrelio", txt)
            self.assertNotIn("Cineva", txt)

        win_files = list((REPO_ROOT / "windows").glob("*"))
        self.assertTrue(win_files, "windows/ directory must contain packaging files")
        joined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in win_files if p.is_file())
        self.assertIn("Vrelio", joined)
        self.assertNotIn("Cineva", joined)

    def test_git_repo_secret_hygiene_and_android_package_vrelio(self) -> None:
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
        self.assertIn("app.vrelio.player", gradle_txt)
        self.assertNotIn("app.cineva.player", gradle_txt)


class Tier1LocalCatalogAndEpgTests(unittest.TestCase):
    """Feature #9 / Core Engine: Local Catalog, Demo, M3U, Local folder, XMLTV EPG."""

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
        with tempfile.TemporaryDirectory(prefix="vrelio_media_") as media_dir:
            mp = Path(media_dir)
            (mp / "Open.Horizon.2025.1080p.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
            (mp / "Open.Horizon.2025.1080p.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello Vrelio\n",
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
            self.assertIn("Hello Vrelio", sub.text)

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
    """Feature: Playback session creation, media proxy, ping/progress, pause, and close."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()
        self.media_dir = tempfile.TemporaryDirectory(prefix="vrelio_play_")
        self.addCleanup(self.media_dir.cleanup)
        sample_file = Path(self.media_dir.name) / "Test.Clip.2025.mp4"
        sample_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"VRELIO_VIDEO_DATA" * 16)
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
        self.assertIn(b"VRELIO_VIDEO_DATA", stream.raw)
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
    """Feature: Profiles, PBKDF2 PIN locking, and Kid Mode content filtering."""

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
        with tempfile.TemporaryDirectory(prefix="vrelio_kid_") as media_dir:
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
    """Feature: LAN Pairing & Device Authorization."""

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

    def test_pair_with_valid_code_sets_vrelio_device_cookie(self) -> None:
        code = self.srv.paired_client().get("/api/status").json["pairingCode"]
        mobile = self.srv.client()
        res = mobile.post("/api/pair", {"code": code})
        self.assertEqual(res.status, 200, res.text)
        self.assertEqual((res.json or {}).get("ok"), True)
        self.assertIn("vrelio_device", mobile.cookies_dict())

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


class Tier1EmailVerifiedRegistrationTests(unittest.TestCase):
    """Feature #3 & #5: Email-verified account registration, outbox, login block, resend."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def test_register_creates_unverified_normal_user_without_session_token(self) -> None:
        res = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "newuser@vrelio.app", "password": "StrongPassword123!", "displayName": "New User"},
        )
        self.assertEqual(res.status, 201, res.text)
        body = res.json or {}
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("verificationRequired"))
        self.assertFalse(body.get("emailVerified"))
        self.assertIsNone(body.get("token"))
        user = body.get("user", {})
        self.assertEqual(user.get("email"), "newuser@vrelio.app")
        self.assertFalse(user.get("emailVerified"))
        self.assertEqual(user.get("plan"), "normal")

    def test_register_writes_verifiable_email_to_outbox_without_response_leak(self) -> None:
        res = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "outbox@vrelio.app", "password": "StrongPassword123!", "displayName": "Outbox"},
        )
        self.assertEqual(res.status, 201, res.text)
        self.assertEqual((res.json or {}).get("deliveryMode"), "outbox")
        mail, code, token = self.cloud.find_latest_mail("outbox@vrelio.app")
        self.assertIsNotNone(mail, "Expected verification email in local outbox")
        self.assertTrue(code or token, "Outbox email must contain 6-digit code or verification token")
        if code:
            self.assertNotIn(code, res.text)
        if token:
            self.assertNotIn(token, res.text)

    def test_unverified_user_login_blocked_with_403_email_not_verified(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "unverified@vrelio.app", "password": "StrongPassword123!", "displayName": "Unver"},
        )
        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": "unverified@vrelio.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(login.status, 403, login.text)
        body = login.json or {}
        self.assertEqual(body.get("code"), "EMAIL_NOT_VERIFIED")
        self.assertTrue(body.get("verificationRequired"))

    def test_resend_verification_dispatches_fresh_outbox_email(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "resend@vrelio.app", "password": "StrongPassword123!", "displayName": "Resend"},
        )
        before_count = len(self.cloud.read_outbox())
        resend = self.cloud.client().post("/api/v1/auth/resend-verification", {"email": "resend@vrelio.app"})
        self.assertEqual(resend.status, 200, resend.text)
        self.assertTrue((resend.json or {}).get("ok"))
        self.assertGreater(len(self.cloud.read_outbox()), before_count)

    def test_verify_email_with_outbox_code_activates_account_and_unlocks_login(self) -> None:
        ver, tok, user = self.cloud.register_and_verify("verified@vrelio.app", "StrongPassword123!", "Verified")
        self.assertEqual(ver.status, 200, ver.text)
        self.assertTrue(tok)
        self.assertTrue((user or {}).get("emailVerified"))

        me = self.cloud.client().get("/api/v1/me", token=tok)
        self.assertEqual(me.status, 200, me.text)
        self.assertTrue((me.json or {}).get("user", {}).get("emailVerified"))

        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": "verified@vrelio.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(login.status, 200, login.text)
        self.assertTrue((login.json or {}).get("token"))


class Tier1PasswordResetTests(unittest.TestCase):
    """Feature #4: Self-service email-verified password reset."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)
        _, self.initial_token, _ = self.cloud.register_and_verify("reset@vrelio.app", "InitialPass123!")

    def test_forgot_password_dispatches_reset_email_to_outbox(self) -> None:
        before = len(self.cloud.read_outbox())
        resp = self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "reset@vrelio.app"})
        self.assertEqual(resp.status, 200, resp.text)
        self.assertTrue((resp.json or {}).get("ok"))
        after = self.cloud.read_outbox()
        self.assertGreater(len(after), before)
        _, code, token = self.cloud.find_latest_mail("reset@vrelio.app")
        self.assertTrue(code or token)
        if code:
            self.assertNotIn(code, resp.text)

    def test_forgot_password_unknown_email_returns_generic_200(self) -> None:
        before = len(self.cloud.read_outbox())
        resp = self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "nobody@vrelio.app"})
        self.assertEqual(resp.status, 200, resp.text)
        self.assertTrue((resp.json or {}).get("ok"))
        self.assertEqual(len(self.cloud.read_outbox()), before)

    def test_verify_reset_code_validates_outbox_code(self) -> None:
        self.assertEqual(self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "reset@vrelio.app"}).status, 200)
        _, code, token = self.cloud.find_latest_mail("reset@vrelio.app")
        payload = {"email": "reset@vrelio.app", "code": code} if code else {"token": token}
        check = self.cloud.client().post("/api/v1/auth/verify-reset-code", payload)
        self.assertEqual(check.status, 200, check.text)
        self.assertTrue((check.json or {}).get("valid"))

    def test_reset_password_updates_credentials_for_login(self) -> None:
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "reset@vrelio.app"})
        _, code, token = self.cloud.find_latest_mail("reset@vrelio.app")
        payload = {"email": "reset@vrelio.app", "code": code, "newPassword": "UpdatedPass456!"} if code else {"token": token, "newPassword": "UpdatedPass456!"}
        res = self.cloud.client().post("/api/v1/auth/reset-password", payload)
        self.assertEqual(res.status, 200, res.text)
        self.assertTrue((res.json or {}).get("ok"))

        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": "reset@vrelio.app", "password": "UpdatedPass456!"},
        )
        self.assertEqual(login.status, 200, login.text)

    def test_reset_password_invalidates_prior_session_tokens(self) -> None:
        self.assertEqual(self.cloud.client().get("/api/v1/me", token=self.initial_token).status, 200)
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "reset@vrelio.app"})
        _, code, token = self.cloud.find_latest_mail("reset@vrelio.app")
        payload = {"email": "reset@vrelio.app", "code": code, "newPassword": "UpdatedPass789!"} if code else {"token": token, "newPassword": "UpdatedPass789!"}
        self.assertEqual(self.cloud.client().post("/api/v1/auth/reset-password", payload).status, 200)
        stale_me = self.cloud.client().get("/api/v1/me", token=self.initial_token)
        self.assertEqual(stale_me.status, 401, stale_me.text)


class Tier1ThreeDayProTrialTests(unittest.TestCase):
    """Feature #6: Automatic 3-day Pro subscription trial upon email-verified signup."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def test_unverified_signup_starts_without_active_pro_trial(self) -> None:
        reg = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "trial_wait@vrelio.app", "password": "StrongPassword123!", "displayName": "Wait"},
        )
        self.assertEqual(reg.status, 201, reg.text)
        user = (reg.json or {}).get("user", {})
        self.assertEqual(user.get("plan"), "normal")
        self.assertFalse(user.get("trialActive", False))
        self.assertFalse(user.get("isPro", False))

    def test_verifying_email_automatically_activates_pro_trial(self) -> None:
        ver, tok, user = self.cloud.register_and_verify("trial_go@vrelio.app", "StrongPassword123!", "Go")
        self.assertEqual(ver.status, 200, ver.text)
        self.assertTrue((ver.json or {}).get("trialActivated"))
        self.assertEqual(user.get("effectivePlan"), "pro")
        self.assertTrue(user.get("isPro"))
        self.assertTrue(user.get("trialActive"))

    def test_pro_trial_duration_is_72_hours(self) -> None:
        _, _, user = self.cloud.register_and_verify("trial_72h@vrelio.app", "StrongPassword123!")
        started = parse_iso_dt(user["trialStartedAt"])
        ends = parse_iso_dt(user["trialEndsAt"])
        hours = (ends - started).total_seconds() / 3600.0
        self.assertGreaterEqual(hours, 71.5)
        self.assertLessEqual(hours, 72.5)
        self.assertTrue(user.get("expiresAt"))

    def test_trial_user_receives_pro_entitlements_and_5_device_limit(self) -> None:
        _, tok, user = self.cloud.register_and_verify("trial_ent@vrelio.app", "StrongPassword123!")
        self.assertEqual(user.get("maxDevices"), 5)
        feats = user.get("features", {})
        for k in ("cloudSync", "multiView", "unlimitedProfiles", "epgMatch", "advancedTracks"):
            self.assertTrue(feats.get(k), f"Expected Pro trial feature {k}=True")
        me = self.cloud.client().get("/api/v1/me", token=tok)
        self.assertEqual(me.json["user"]["maxDevices"], 5)

    def test_trial_is_single_use_and_not_regranted_on_login(self) -> None:
        _, _, user = self.cloud.register_and_verify("trial_once@vrelio.app", "StrongPassword123!")
        admin_tok = self.cloud.admin_login()
        self.cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "normal", "expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=self.cloud.admin_headers(admin_tok),
        )
        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": "trial_once@vrelio.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(login.status, 200)
        u2 = login.json["user"]
        self.assertEqual(u2.get("effectivePlan"), "normal")
        self.assertFalse(u2.get("trialActive"))


class Tier1PlanGatingAndDeviceLimitsTests(unittest.TestCase):
    """Feature #6 & #9: Normal vs Pro gating and 1-vs-5 device limits."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def _make_normal_user(self, email: str):
        _, _, user = self.cloud.register_and_verify(email, "StrongPassword123!")
        admin_tok = self.cloud.admin_login()
        self.cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "normal", "expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=self.cloud.admin_headers(admin_tok),
        )
        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": email, "password": "StrongPassword123!"},
        )
        return login.json["token"], login.json["user"]

    def test_app_config_publishes_normal_and_pro_plan_definitions(self) -> None:
        cfg = self.cloud.client().get("/api/v1/app-config")
        self.assertEqual(cfg.status, 200)
        plans = (cfg.json or {}).get("plans", {})
        self.assertEqual(plans.get("normal", {}).get("maxDevices"), 1)
        self.assertEqual(plans.get("pro", {}).get("maxDevices"), 5)
        self.assertEqual(plans.get("pro", {}).get("trialDays"), 3)

    def test_normal_user_blocked_from_cloud_sync_with_pro_required(self) -> None:
        tok, user = self._make_normal_user("norm_sync@vrelio.app")
        self.assertEqual(user["effectivePlan"], "normal")
        put_res = self.cloud.client().put(
            "/api/v1/sync",
            {"favorites": ["vod:demo_bbb"], "progress": {}, "playlists": [], "playlistItems": []},
            token=tok,
        )
        self.assertEqual(put_res.status, 403, put_res.text)
        self.assertEqual((put_res.json or {}).get("code"), "PRO_REQUIRED")
        self.assertTrue((put_res.json or {}).get("upgradeRequired"))

    def test_pro_trial_user_can_put_and_get_cloud_sync(self) -> None:
        _, tok, _ = self.cloud.register_and_verify("pro_sync@vrelio.app", "StrongPassword123!")
        payload = {"favorites": ["vod:demo_sintel"], "progress": {"vod:demo_sintel": 120}, "playlists": [], "playlistItems": []}
        put_res = self.cloud.client().put("/api/v1/sync", payload, token=tok)
        self.assertEqual(put_res.status, 200, put_res.text)
        get_res = self.cloud.client().get("/api/v1/sync", token=tok)
        self.assertEqual(get_res.status, 200, get_res.text)
        self.assertIn("vod:demo_sintel", json.dumps(get_res.json))

    def test_normal_device_limit_is_1_and_self_delete_frees_slot(self) -> None:
        tok, _ = self._make_normal_user("norm_dev@vrelio.app")
        d1 = self.cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "dev_one", "name": "Phone", "platform": "android"},
            token=tok,
        )
        self.assertEqual(d1.status, 200, d1.text)
        d2 = self.cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "dev_two", "name": "Desktop", "platform": "windows"},
            token=tok,
        )
        self.assertEqual(d2.status, 403, d2.text)
        self.assertEqual((d2.json or {}).get("code"), "DEVICE_LIMIT_REACHED")

        rm = self.cloud.client().delete("/api/v1/devices/dev_one", token=tok)
        self.assertEqual(rm.status, 200, rm.text)
        d2_retry = self.cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "dev_two", "name": "Desktop", "platform": "windows"},
            token=tok,
        )
        self.assertEqual(d2_retry.status, 200, d2_retry.text)

    def test_local_server_enforces_pro_gates_when_linked_to_normal_account(self) -> None:
        self._make_normal_user("local_norm@vrelio.app")
        srv = LocalMediaServerProcess(cloud_url=self.cloud.base_url).start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        login = c.post(
            "/api/cloud/login",
            {"email": "local_norm@vrelio.app", "password": "StrongPassword123!", "cloudUrl": self.cloud.base_url},
        )
        self.assertEqual(login.status, 200, login.text)

        sync_res = c.post("/api/cloud/sync", {})
        self.assertEqual(sync_res.status, 403, sync_res.text)
        self.assertEqual((sync_res.json or {}).get("code"), "PRO_REQUIRED")

        prof_res = c.post("/api/profiles", {"name": "Second", "pin": "1234"})
        self.assertEqual(prof_res.status, 403, prof_res.text)
        self.assertEqual((prof_res.json or {}).get("code"), "PRO_REQUIRED")


class Tier1WebsiteShowcaseAndAdminTests(unittest.TestCase):
    """Feature #11 & #7: Website 4-platform showcase, download tracking, portal modals, Admin gate."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def test_website_index_served_with_vrelio_branding(self) -> None:
        res = self.cloud.client().get("/")
        self.assertEqual(res.status, 200)
        self.assertIn("Vrelio", res.text)
        self.assertNotIn("cineva", res.text.lower())

    def test_website_showcases_all_four_platform_downloads(self) -> None:
        html = self.cloud.client().get("/").text
        for artifact in ("Vrelio-Setup.exe", "Vrelio.exe", "Vrelio-Android.apk", "Vrelio-macOS.dmg", "Vrelio-iOS.ipa"):
            self.assertIn(artifact, html, f"Website index missing download link for {artifact}")
        for label in ("Windows", "Android", "macOS", "iOS"):
            self.assertIn(label, html)

    def test_app_config_provides_4_platform_urls_and_tracks_ios_macos(self) -> None:
        cfg = self.cloud.client().get("/api/v1/app-config")
        self.assertEqual(cfg.status, 200)
        versions = (cfg.json or {}).get("versions", {})
        for key, expected in (
            ("windowsInstallerUrl", "Vrelio-Setup.exe"),
            ("windowsPortableUrl", "Vrelio.exe"),
            ("androidApkUrl", "Vrelio-Android.apk"),
            ("macosUrl", "Vrelio-macOS.dmg"),
            ("iosUrl", "Vrelio-iOS.ipa"),
        ):
            self.assertIn(expected, str(versions.get(key, "")), f"versions.{key} invalid")

        for plat in ("windows-installer", "android-apk", "macos", "ios"):
            tr = self.cloud.client().post("/api/v1/downloads/track", {"platform": plat})
            self.assertEqual(tr.status, 200, f"track failed for {plat}: {tr.text}")

        cfg2 = self.cloud.client().get("/api/v1/app-config").json
        self.assertEqual(cfg2["downloads"]["ios"], 1)
        self.assertEqual(cfg2["downloads"]["macos"], 1)

    def test_website_contains_plans_verify_reset_and_device_management_ui(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        combined = html + "\n" + portal_js
        self.assertIn("Normal", combined)
        self.assertIn("Pro", combined)
        self.assertIn("verify-email", combined)
        self.assertIn("forgot-password", combined)
        self.assertIn("reset-password", combined)
        self.assertIn("/devices/", combined)

    def test_admin_gate_protects_admin_api_and_supports_normal_pro_management(self) -> None:
        no_gate = self.cloud.client().get("/api/v1/admin/overview")
        self.assertIn(no_gate.status, (401, 403, 404))

        tok = self.cloud.admin_login()
        ov = self.cloud.client().get("/api/v1/admin/overview", headers=self.cloud.admin_headers(tok))
        self.assertEqual(ov.status, 200, ov.text)
        admin_html = (REPO_ROOT / "website/admin.html").read_text(encoding="utf-8")
        self.assertIn("VRELIO-", admin_html)
        self.assertNotIn("CINEVA-", admin_html)


class Tier1MultiPlatformPackagingAndCiTests(unittest.TestCase):
    """Feature #12–#16: Windows, Android, macOS, iOS projects/packaging & 4-platform CI."""

    def test_windows_desktop_launcher_and_installer_packaging_present(self) -> None:
        desktop_files = list((REPO_ROOT / "desktop").glob("*.py"))
        self.assertTrue(desktop_files)
        desktop_src = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in desktop_files)
        self.assertIn("Vrelio", desktop_src)
        self.assertIn("utf-8", desktop_src.lower())

        win_specs = list((REPO_ROOT / "windows").glob("*.spec"))
        win_iss = list((REPO_ROOT / "windows").glob("*.iss"))
        self.assertTrue(win_specs and win_iss, "Windows .spec and .iss files must exist")
        iss_txt = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in win_iss)
        self.assertIn("Vrelio-Setup", iss_txt)

    def test_android_project_rebranded_to_app_vrelio_player_and_manifest_fixed(self) -> None:
        gradle = (REPO_ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('applicationId = "app.vrelio.player"', gradle)

        main_manifest = (REPO_ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("Vrelio", main_manifest)
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
        self.assertIn("app.vrelio.macos", joined)
        self.assertIn("Vrelio", joined)

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
        self.assertIn("app.vrelio.ios", joined)
        self.assertTrue("AVPlayer" in joined or "AVKit" in joined, "iOS app must use native AVKit/AVPlayer")
        self.assertTrue(any("Test" in p.name for p in apple_files), "iOS XCTest suite must be present")

    def test_github_ci_workflow_covers_all_four_platforms_and_release_assets(self) -> None:
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("macos-latest", ci)
        self.assertIn("windows-latest", ci)
        self.assertIn("ubuntu-latest", ci)
        for asset in ("Vrelio-Setup.exe", "Vrelio.exe", "Vrelio-Android.apk", "Vrelio-macOS.dmg", "Vrelio-iOS.ipa"):
            self.assertIn(asset, ci, f"CI release pipeline missing {asset}")


if __name__ == "__main__":
    unittest.main()
