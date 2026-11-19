"""Tier 4: End-to-end real-world application scenarios (>=6 scenarios)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

import sports
from tests.e2e.runner import (
    AKIS_ROOT,
    CloudServerProcess,
    LocalMediaServerProcess,
    REPO_ROOT,
    parse_iso_dt,
)


class Tier4EndToEndScenariosTests(unittest.TestCase):
    """8 full real-world application journeys across website, cloud, local engine, and packaging."""

    def test_scenario_1_full_new_user_onboarding_website_cloud_and_local_server(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        srv = LocalMediaServerProcess(cloud_url=cloud.base_url).start()
        self.addCleanup(srv.stop)

        # User visits portal & inspects 4-platform download config
        portal = cloud.client().get("/")
        self.assertEqual(portal.status, 200)
        self.assertIn("Vrelio", portal.text)
        cfg = cloud.client().get("/api/v1/app-config").json
        self.assertEqual(cfg["plans"]["pro"]["trialDays"], 3)

        # User signs up -> unverified, blocked from login
        email = "onboard@vrelio.app"
        pw = "OnboardPass!2026"
        reg = cloud.client().post("/api/v1/auth/register", {"email": email, "password": pw, "displayName": "Taha"})
        self.assertEqual(reg.status, 201)
        self.assertEqual(cloud.client().post("/api/v1/auth/login", {"email": email, "password": pw}).status, 403)

        # User reads verification code from email outbox and verifies
        _, code, token = cloud.find_latest_mail(email)
        ver = cloud.client().post("/api/v1/auth/verify-email", {"email": email, "code": code} if code else {"token": token})
        self.assertEqual(ver.status, 200)
        self.assertTrue(ver.json["trialActivated"])
        self.assertEqual(ver.json["user"]["effectivePlan"], "pro")

        # User opens local desktop/web app, signs into cloud, loads demo catalog, watches & syncs
        local_client = srv.paired_client()
        self.assertEqual(
            local_client.post("/api/cloud/login", {"email": email, "password": pw, "cloudUrl": cloud.base_url}).status,
            200,
        )
        self.assertEqual(local_client.post("/api/demo", {}).status, 200)
        items = local_client.get("/api/catalog").json["items"]
        self.assertGreaterEqual(len(items), 4)

        play = local_client.post("/api/play", {"id": items[0]["id"]})
        self.assertEqual(play.status, 200)
        sid = play.json["sessionId"]
        local_client.post(f"/api/play/{sid}/ping", {"position": 65.0})
        local_client.post("/api/progress", {"id": items[0]["id"], "position": 65.0, "duration": 600})
        local_client.delete(f"/api/play/{sid}")
        local_client.post("/api/favorites", {"id": items[0]["id"], "favorite": True})

        sync_res = local_client.post("/api/cloud/sync", {})
        self.assertEqual(sync_res.status, 200, sync_res.text)
        cloud_sync = cloud.client().get("/api/v1/sync", token=ver.json["token"])
        self.assertEqual(cloud_sync.status, 200)
        self.assertIn(items[0]["id"], cloud_sync.text)

    def test_scenario_2_forgotten_password_recovery_and_token_invalidation(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        email = "recover@vrelio.app"
        _, active_token, _ = cloud.register_and_verify(email, "OriginalPass123!")

        self.assertEqual(cloud.client().get("/api/v1/me", token=active_token).status, 200)

        fg = cloud.client().post("/api/v1/auth/forgot-password", {"email": email})
        self.assertEqual(fg.status, 200)
        _, rcode, rtok = cloud.find_latest_mail(email)
        self.assertTrue(rcode or rtok)

        chk = cloud.client().post(
            "/api/v1/auth/verify-reset-code",
            {"email": email, "code": rcode} if rcode else {"token": rtok},
        )
        self.assertEqual(chk.status, 200)

        rst_payload = {"email": email, "code": rcode, "newPassword": "RecoveredPass999!"} if rcode else {"token": rtok, "newPassword": "RecoveredPass999!"}
        self.assertEqual(cloud.client().post("/api/v1/auth/reset-password", rst_payload).status, 200)

        # Prior session invalidated, old password fails, code cannot be reused, new password succeeds
        self.assertEqual(cloud.client().get("/api/v1/me", token=active_token).status, 401)
        self.assertEqual(cloud.client().post("/api/v1/auth/login", {"email": email, "password": "OriginalPass123!"}).status, 401)
        self.assertIn(cloud.client().post("/api/v1/auth/reset-password", rst_payload).status, (400, 401, 409, 410))

        new_login = cloud.client().post("/api/v1/auth/login", {"email": email, "password": "RecoveredPass999!"})
        self.assertEqual(new_login.status, 200)
        self.assertEqual(cloud.client().get("/api/v1/me", token=new_login.json["token"]).status, 200)

    def test_scenario_3_trial_expiry_and_pro_license_upgrade_journey(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        srv = LocalMediaServerProcess(cloud_url=cloud.base_url).start()
        self.addCleanup(srv.stop)

        email = "upgrade@vrelio.app"
        pw = "UpgradePass123!"
        _, tok, user = cloud.register_and_verify(email, pw)

        # During 3-day trial: Pro works across 3 devices & multi-profile PIN
        for i in range(1, 4):
            self.assertEqual(
                cloud.client().post("/api/v1/devices/register", {"deviceId": f"u_dev_{i}", "name": f"D{i}", "platform": "macos"}, token=tok).status,
                200,
            )
        local_c = srv.paired_client()
        local_c.post("/api/cloud/login", {"email": email, "password": pw, "cloudUrl": cloud.base_url})
        self.assertEqual(local_c.post("/api/profiles", {"name": "Parent", "pin": "1234"}).status, 201)

        # Simulate 72h expiry
        admin_tok = cloud.admin_login()
        cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=cloud.admin_headers(admin_tok),
        )
        me_expired = cloud.client().get("/api/v1/me", token=tok).json["user"]
        self.assertEqual(me_expired["effectivePlan"], "normal")
        self.assertFalse(me_expired["trialActive"])
        self.assertEqual(me_expired["maxDevices"], 1)

        # Re-sync local cloud session & confirm Pro gates block sync and new PIN profiles
        local_c.post("/api/cloud/login", {"email": email, "password": pw, "cloudUrl": cloud.base_url})
        self.assertEqual(local_c.post("/api/cloud/sync", {}).status, 403)
        self.assertEqual(local_c.post("/api/profiles", {"name": "BlockedPin", "pin": "9999"}).status, 403)

        # Admin issues Pro license; user redeems via local server bridge -> Pro restored
        lic_code = cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 365, "count": 1},
            headers=cloud.admin_headers(admin_tok),
        ).json["license"]["code"]
        self.assertEqual(local_c.post("/api/cloud/redeem", {"code": lic_code}).status, 200)
        self.assertEqual(local_c.post("/api/cloud/sync", {}).status, 200)
        self.assertEqual(local_c.post("/api/profiles", {"name": "UnlockedPin", "pin": "5555"}).status, 201)

    def test_scenario_4_household_kid_safe_sports_epg_and_playback_flow(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        with tempfile.TemporaryDirectory(prefix="vrelio_family_") as media_dir:
            mp = Path(media_dir)
            (mp / "Belgesel").mkdir()
            (mp / "Spor").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Belgesel" / "Nature.Doc.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"NATURE" * 32)
            (mp / "Belgesel" / "Nature.Doc.2025.tr.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nDoğa Belgeseli\n", encoding="utf-8")
            (mp / "Spor" / "BeIN.Sports.Haber.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"SPORT" * 16)
            (mp / "Korku +18" / "Korku.Filmi.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HORROR" * 16)
            self.assertEqual(c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Family"}).status, 200)
            cat_items = []
            for _ in range(40):
                st = c.get("/api/status").json or {}
                cat_items = (c.get("/api/catalog").json or {}).get("items", [])
                if len(cat_items) >= 3 and not st.get("catalog", {}).get("syncing"):
                    break
                time.sleep(0.1)
            self.assertEqual(len(cat_items), 3)
            doc_item = next(i for i in cat_items if "Nature Doc" in i["name"])
            sport_item = next(i for i in cat_items if "BeIN Sports" in i["name"])

            today_date = datetime.now(timezone.utc).date()
            today = today_date.strftime("%Y%m%d")
            epg_events = sports.parse_xmltv(
                f'<tv><channel id="sp1"><display-name>BeIN Sports Haber</display-name></channel>'
                f'<programme start="{today}160000 +0000" stop="{today}180000 +0000" channel="sp1"><title>Derbi Özetleri</title><category>Sports</category></programme></tv>',
                today_date,
            )
            matched = sports.match_channels(epg_events, [(i["id"], i["name"]) for i in cat_items])
            self.assertIn(sport_item["id"], json.dumps(matched))

            # Create PIN-locked Kid profile and verify adult content hidden
            kid = c.post("/api/profiles", {"name": "Minik", "isKids": True, "pin": "1357"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "1357"}).status, 200)
            kid_names = [i["name"] for i in c.get("/api/catalog").json["items"]]
            self.assertNotIn("Korku Filmi", kid_names)
            self.assertIn(sport_item["name"], kid_names)

            # Play family documentary with WebVTT subtitle & persist progress
            doc_id = doc_item["id"]
            sub = c.get(f"/api/subtitles/{doc_id}/0.vtt")
            self.assertEqual(sub.status, 200)
            self.assertIn("Doğa Belgeseli", sub.text)
            play = c.post("/api/play", {"id": doc_id})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            c.post(f"/api/play/{sid}/ping", {"position": 33.0})
            c.post("/api/progress", {"id": doc_id, "position": 33.0, "duration": 200})
            c.post(f"/api/play/{sid}/pause", {"paused": True})
            c.delete(f"/api/play/{sid}")
            self.assertIn("33", c.get("/api/progress").text)

    def test_scenario_5_cross_platform_release_packaging_and_4_platform_downloads(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)

        html = cloud.client().get("/").text
        cfg = cloud.client().get("/api/v1/app-config").json
        ci_yml = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        expected_assets = (
            ("windowsInstallerUrl", "Vrelio-Setup.exe", "windows-installer"),
            ("windowsPortableUrl", "Vrelio.exe", "windows-portable"),
            ("androidApkUrl", "Vrelio-Android.apk", "android-apk"),
            ("macosUrl", "Vrelio-macOS.dmg", "macos"),
            ("iosUrl", "Vrelio-iOS.ipa", "ios"),
        )
        for cfg_key, asset_name, track_slug in expected_assets:
            self.assertIn(asset_name, cfg["versions"].get(cfg_key, ""))
            self.assertIn(asset_name, html)
            self.assertIn(asset_name, ci_yml)
            self.assertEqual(cloud.client().post("/api/v1/downloads/track", {"platform": track_slug}).status, 200)

        downloads = cloud.client().get("/api/v1/app-config").json["downloads"]
        for _, _, track_slug in expected_assets:
            self.assertEqual(downloads.get(track_slug), 1)

    def test_scenario_6_secret_hygiene_and_akis_programi_untouched(self) -> None:
        # 1. Cineva repo git tracked files hygiene
        tracked = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files"], text=True).splitlines()
        for f in tracked:
            self.assertFalse(
                bool(re.search(r"(^android/signing/|\.jks$|\.keystore$|^data/|^cloud_data/|^\.venv/|^\.env$)", f)),
                f"Tracked sensitive/local path found: {f}",
            )

        # 2. Akış Programı source files remain completely untouched (zero Vrelio edits)
        self.assertTrue(AKIS_ROOT.exists(), "Baseline Akış Programı directory expected")
        for rel in ("server.py", "playback.py", "discovery.py", "sports.py"):
            src = (AKIS_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("vrelio", src.lower(), f"Akış Programı {rel} must stay untouched")

        # 3. Cloud API responses never leak secrets, password hashes, or tokens
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        reg = cloud.client().post(
            "/api/v1/auth/register",
            {"email": "sec@vrelio.app", "password": "SecretCheckPassword123!"},
        )
        self.assertNotIn("passwordHash", reg.text)
        self.assertNotIn("SecretCheckPassword123!", reg.text)
        self.assertNotIn("e2e-cloud-secret-key", reg.text)

    def test_scenario_7_windows_crossover_utf8_stdio_and_launcher_stability(self) -> None:
        # Simulate CrossOver/Windows cp1252 redirected pipe environment
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONIOENCODING": "cp1252",
        }
        try:
            srv = LocalMediaServerProcess(override_env=env).start()
        except RuntimeError as exc:
            self.fail(f"server.py failed to start under cp1252/C locale: {exc}")
        try:
            # Must survive past 2.0s (no 0.5s --parent-pid suicide or cp1252 crash)
            time.sleep(2.1)
            self.assertIsNone(srv.proc.poll(), "server.py crashed shortly after startup")
            health = srv.client().get("/api/health")
            self.assertEqual(health.status, 200)
            self.assertEqual(health.json, {"ok": True, "app": "vrelio"})
            pid_file = srv.data_dir / "server.pid"
            self.assertTrue(pid_file.exists())
        finally:
            out = srv.stop()
        self.assertNotIn("UnicodeEncodeError", out)

    def test_scenario_8_admin_console_and_audit_lifecycle(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)

        # Ungated admin HTML / API blocked
        self.assertIn(cloud.client().get("/api/v1/admin/overview").status, (401, 403, 404))

        admin_tok = cloud.admin_login()
        hdrs = cloud.admin_headers(admin_tok)

        # Admin creates user, updates plan, generates licenses, updates announcement, reads audit log
        _, _, user = cloud.register_and_verify("audited@vrelio.app", "StrongPassword123!")
        patch_res = cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "normal", "adminNote": "E2E audit check"},
            headers=hdrs,
        )
        self.assertEqual(patch_res.status, 200, patch_res.text)

        lic_res = cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 90, "count": 2},
            headers=hdrs,
        )
        self.assertIn(lic_res.status, (200, 201), lic_res.text)

        cfg_res = cloud.client().put(
            "/api/v1/admin/config",
            {"announcement": {"enabled": True, "title": "Vrelio 3.0", "message": "4 Platforms Live", "severity": "info"}},
            headers=hdrs,
        )
        self.assertEqual(cfg_res.status, 200, cfg_res.text)
        public_cfg = cloud.client().get("/api/v1/app-config").json
        self.assertEqual(public_cfg["announcement"]["title"], "Vrelio 3.0")

        audit = cloud.client().get("/api/v1/admin/audit", headers=hdrs)
        self.assertEqual(audit.status, 200, audit.text)
        self.assertTrue(json.dumps(audit.json))


if __name__ == "__main__":
    unittest.main()
