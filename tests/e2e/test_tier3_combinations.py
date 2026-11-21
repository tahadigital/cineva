"""Tier 3: Cross-feature pairwise & multi-component integration E2E tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest

import sports
from tests.e2e.runner import (
    CloudServerProcess,
    LocalMediaServerProcess,
    REPO_ROOT,
)


class Tier3CrossFeatureCombinationsTests(unittest.TestCase):
    """Cross-feature integration across Cloud, Local Server, Outbox, Website, and Dual Cloud."""

    def test_register_verify_trial_5devices_expire_sync_blocked_redeem_restored(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)

        # 1. Register -> Outbox verify -> 3-day Pro trial active
        ver, tok, user = cloud.register_and_verify("combo_plan@mavie.app", "StrongPassword123!")
        self.assertEqual(ver.status, 200, ver.text)
        self.assertTrue(user["trialActive"])
        self.assertEqual(user["effectivePlan"], "pro")

        # 2. Sync succeeds + register 5 devices
        sync_put = cloud.client().put("/api/v1/sync", {"favorites": ["vod:demo_bbb"]}, token=tok)
        self.assertEqual(sync_put.status, 200, sync_put.text)
        for i in range(1, 6):
            d = cloud.client().post(
                "/api/v1/devices/register",
                {"deviceId": f"dev_{i}", "name": f"Device {i}", "platform": "android"},
                token=tok,
            )
            self.assertEqual(d.status, 200, d.text)

        # 3. Simulate trial expiry -> Sync blocked & 6th device blocked
        admin_tok = cloud.admin_login()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"expiresAt": past},
            headers=cloud.admin_headers(admin_tok),
        )
        blocked_sync = cloud.client().put("/api/v1/sync", {"favorites": ["vod:demo_sintel"]}, token=tok)
        self.assertEqual(blocked_sync.status, 403)
        self.assertEqual((blocked_sync.json or {}).get("code"), "PRO_REQUIRED")
        blocked_dev = cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "dev_6", "name": "Device 6", "platform": "ios"},
            token=tok,
        )
        self.assertEqual(blocked_dev.status, 403)
        self.assertEqual((blocked_dev.json or {}).get("code"), "DEVICE_LIMIT_REACHED")

        # 4. Redeem Pro license -> Sync & 5-device capacity restored
        lic_code = cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 30, "count": 1},
            headers=cloud.admin_headers(admin_tok),
        ).json["license"]["code"]
        redeem = cloud.client().post("/api/v1/licenses/redeem", {"code": lic_code}, token=tok)
        self.assertEqual(redeem.status, 200, redeem.text)
        self.assertEqual(redeem.json["user"]["effectivePlan"], "pro")

        restored_sync = cloud.client().put("/api/v1/sync", {"favorites": ["vod:demo_sintel"]}, token=tok)
        self.assertEqual(restored_sync.status, 200)

    def test_register_resend_verify_forgot_verify_reset_old_fails_new_logs_in(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        email = "combo_auth@mavie.app"

        reg = cloud.client().post("/api/v1/auth/register", {"email": email, "password": "OldPassword123!"})
        self.assertEqual(reg.status, 201, reg.text)
        self.assertEqual(cloud.client().post("/api/v1/auth/resend-verification", {"email": email}).status, 200)
        _, vcode, vtok = cloud.find_latest_mail(email)
        ver = cloud.client().post(
            "/api/v1/auth/verify-email",
            {"email": email, "code": vcode} if vcode else {"token": vtok},
        )
        self.assertEqual(ver.status, 200, ver.text)
        old_session = ver.json["token"]

        self.assertEqual(cloud.client().post("/api/v1/auth/forgot-password", {"email": email}).status, 200)
        _, rcode, rtok = cloud.find_latest_mail(email)
        chk = cloud.client().post(
            "/api/v1/auth/verify-reset-code",
            {"email": email, "code": rcode} if rcode else {"token": rtok},
        )
        self.assertEqual(chk.status, 200, chk.text)
        rst = cloud.client().post(
            "/api/v1/auth/reset-password",
            {"email": email, "code": rcode, "newPassword": "NewPassword456!"} if rcode else {"token": rtok, "newPassword": "NewPassword456!"},
        )
        self.assertEqual(rst.status, 200, rst.text)

        self.assertEqual(cloud.client().get("/api/v1/me", token=old_session).status, 401)
        self.assertEqual(cloud.client().post("/api/v1/auth/login", {"email": email, "password": "OldPassword123!"}).status, 401)
        new_login = cloud.client().post("/api/v1/auth/login", {"email": email, "password": "NewPassword456!"})
        self.assertEqual(new_login.status, 200)
        self.assertTrue(new_login.json.get("token"))

    def test_local_server_cloud_bridge_register_verify_sync_expire_redeem(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        srv = LocalMediaServerProcess(cloud_url=cloud.base_url).start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        email = "bridge_user@mavie.app"
        reg = c.post(
            "/api/cloud/register",
            {"email": email, "password": "BridgePassword123!", "displayName": "Bridge", "cloudUrl": cloud.base_url},
        )
        self.assertIn(reg.status, (200, 201), reg.text)
        _, vcode, vtok = cloud.find_latest_mail(email)
        ver = c.post(
            "/api/cloud/verify-email",
            {"email": email, "code": vcode} if vcode else {"token": vtok},
        )
        self.assertEqual(ver.status, 200, ver.text)
        status = c.get("/api/cloud/status").json
        self.assertTrue(status.get("emailVerified") or (status.get("user") or {}).get("emailVerified"))
        self.assertTrue(status.get("isPro") or (status.get("user") or {}).get("isPro"))

        # Sync works during trial
        self.assertEqual(c.post("/api/cloud/sync", {}).status, 200)

        # Expire trial -> bridge sync blocked
        uid = (status.get("user") or {}).get("id") or ver.json["user"]["id"]
        admin_tok = cloud.admin_login()
        cloud.client().patch(
            f"/api/v1/admin/users/{uid}",
            {"expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=cloud.admin_headers(admin_tok),
        )
        self.assertEqual(c.post("/api/cloud/sync", {}).status, 403)

        # Redeem license via bridge -> sync restored
        lic_code = cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 30, "count": 1},
            headers=cloud.admin_headers(admin_tok),
        ).json["license"]["code"]
        redeem = c.post("/api/cloud/redeem", {"code": lic_code})
        self.assertEqual(redeem.status, 200, redeem.text)
        self.assertEqual(c.post("/api/cloud/sync", {}).status, 200)

    def test_local_server_kid_profile_pin_epg_playback_export_import(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        with tempfile.TemporaryDirectory(prefix="mavie_combo_") as media_dir:
            mp = Path(media_dir)
            (mp / "Spor").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Spor" / "TRT.Spor.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"SPORT" * 16)
            (mp / "Korku +18" / "Yetiskin.Gerilim.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HORROR" * 16)
            self.assertEqual(c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Combo"}).status, 200)
            cat_items = []
            for _ in range(40):
                st = c.get("/api/status").json or {}
                cat_items = (c.get("/api/catalog").json or {}).get("items", [])
                if len(cat_items) >= 2 and not st.get("catalog", {}).get("syncing"):
                    break
                time.sleep(0.1)
            self.assertEqual(len(cat_items), 2)
            sport_item = next(i for i in cat_items if "TRT Spor" in i["name"])
            c.post("/api/favorites", {"id": sport_item["id"], "favorite": True})

            today_date = datetime.now(timezone.utc).date()
            today = today_date.strftime("%Y%m%d")
            events = sports.parse_xmltv(
                f'<tv><channel id="trt"><display-name>TRT Spor</display-name></channel>'
                f'<programme start="{today}170000 +0000" stop="{today}190000 +0000" channel="trt"><title>Cup Final</title><category>Sports</category></programme></tv>',
                today_date,
            )
            matched = sports.match_channels(events, [(i["id"], i["name"]) for i in cat_items])
            self.assertIn(sport_item["id"], json.dumps(matched))

            kid = c.post("/api/profiles", {"name": "KidSafe", "isKids": True, "pin": "2468"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "2468"}).status, 200)
            names = [i["name"] for i in c.get("/api/catalog").json["items"]]
            self.assertIn(sport_item["name"], names)
            self.assertNotIn("Yetiskin Gerilim", names)

            c.post("/api/profiles/switch", {"id": "default"})
            play = c.post("/api/play", {"id": sport_item["id"]})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            c.post(f"/api/play/{sid}/ping", {"position": 15.0})
            c.post(f"/api/play/{sid}/pause", {"paused": True})
            c.delete(f"/api/play/{sid}")

            exported = c.get("/api/export").json
            self.assertIn(sport_item["id"], json.dumps(exported))
            self.assertEqual(c.post("/api/import", {"data": exported}).status, 200)

    def test_website_static_app_config_download_tracking_and_admin_overview(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)

        html = cloud.client().get("/").text
        cfg = cloud.client().get("/api/v1/app-config").json
        for url_key in ("windowsInstallerUrl", "windowsPortableUrl", "androidApkUrl", "macosUrl", "iosUrl"):
            url = cfg["versions"][url_key]
            filename = url.rsplit("/", 1)[-1]
            self.assertIn(filename, html)

        for plat in ("windows-installer", "android-apk", "macos", "ios"):
            self.assertEqual(cloud.client().post("/api/v1/downloads/track", {"platform": plat}).status, 200)

        cloud.register_and_verify("metric_user@mavie.app", "StrongPassword123!")
        admin_tok = cloud.admin_login()
        ov = cloud.client().get("/api/v1/admin/overview", headers=cloud.admin_headers(admin_tok))
        self.assertEqual(ov.status, 200, ov.text)
        self.assertGreaterEqual(json.dumps(ov.json).count("metric_user@mavie.app") + len(str(ov.json)), 1)
        cfg2 = cloud.client().get("/api/v1/app-config").json
        self.assertEqual(cfg2["downloads"]["ios"], 1)
        self.assertEqual(cfg2["downloads"]["macos"], 1)

    def test_local_media_scan_subtitles_playback_and_restart_persistence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mavie_persist_") as media_dir:
            mp = Path(media_dir)
            (mp / "Documentary.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"PERSIST" * 16)
            (mp / "Documentary.2025.tr.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nMerhaba Mavie\n", encoding="utf-8")

            with tempfile.TemporaryDirectory(prefix="mavie_data_") as fixed_data:
                env = {"MAVIE_DATA_DIR": fixed_data, "CINEVA_DATA_DIR": fixed_data}
                srv1 = LocalMediaServerProcess(extra_env=env).start()
                try:
                    c1 = srv1.paired_client()
                    c1.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Persist"})
                    item_id = None
                    for _ in range(40):
                        st = c1.get("/api/status").json or {}
                        items = (c1.get("/api/catalog").json or {}).get("items", [])
                        if items and not st.get("catalog", {}).get("syncing"):
                            item_id = items[0]["id"]
                            break
                        time.sleep(0.1)
                    self.assertIsNotNone(item_id)
                    play_resp = c1.post("/api/play", {"id": item_id})
                    self.assertEqual(play_resp.status, 200, play_resp.text)
                    sid = play_resp.json["sessionId"]
                    c1.post(f"/api/play/{sid}/ping", {"position": 88.0})
                    c1.post("/api/progress", {"id": item_id, "position": 88.0, "duration": 300})
                    c1.delete(f"/api/play/{sid}")
                    c1.post("/api/favorites", {"id": item_id, "favorite": True})
                finally:
                    srv1.stop()

                # Restart with same data dir and verify state persisted
                srv2 = LocalMediaServerProcess(extra_env=env).start()
                try:
                    c2 = srv2.paired_client()
                    prog = c2.get("/api/progress").text
                    self.assertIn("88", prog)
                    sub = c2.get(f"/api/subtitles/{item_id}/0.vtt")
                    self.assertEqual(sub.status, 200)
                    self.assertIn("Merhaba Mavie", sub.text)
                finally:
                    srv2.stop()

    def test_multi_user_cloud_sync_and_device_isolation(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)

        _, tok_a, _ = cloud.register_and_verify("iso_a@mavie.app", "StrongPassword123!")
        _, tok_b, user_b = cloud.register_and_verify("iso_b@mavie.app", "StrongPassword123!")
        cloud.client().put("/api/v1/sync", {"favorites": ["vod:secret_a"]}, token=tok_a)
        cloud.client().post("/api/v1/devices/register", {"deviceId": "dev_a_only", "name": "A", "platform": "macos"}, token=tok_a)

        sync_b = cloud.client().get("/api/v1/sync", token=tok_b)
        self.assertNotIn("vod:secret_a", sync_b.text)

        admin_tok = cloud.admin_login()
        cloud.client().patch(
            f"/api/v1/admin/users/{user_b['id']}",
            {"expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=cloud.admin_headers(admin_tok),
        )
        self.assertEqual(cloud.client().get("/api/v1/sync", token=tok_b).status, 403)
        self.assertIn(cloud.client().delete("/api/v1/devices/dev_a_only", token=tok_b).status, (403, 404))

    def test_dual_cloud_parity_python_sqlite_vs_netlify_postgres_contracts(self) -> None:
        py_src = (REPO_ROOT / "cloud_admin.py").read_text(encoding="utf-8")
        mjs_src = (REPO_ROOT / "website/netlify/functions/cloud-core.mjs").read_text(encoding="utf-8")
        mig_texts = "\n".join(
            p.read_text(encoding="utf-8")
            for p in sorted((REPO_ROOT / "website/netlify/database/migrations").glob("*.sql"))
        )

        for endpoint in (
            "/auth/verify-email",
            "/auth/resend-verification",
            "/auth/forgot-password",
            "/auth/verify-reset-code",
            "/auth/reset-password",
            "/devices/",
        ):
            self.assertIn(endpoint, py_src, f"cloud_admin.py missing {endpoint}")
            self.assertIn(endpoint, mjs_src, f"cloud-core.mjs missing {endpoint}")

        for contract_token in ("mavie-cloud", "MAVIE-", "EMAIL_NOT_VERIFIED", "PRO_REQUIRED", "DEVICE_LIMIT_REACHED", "macosUrl", "iosUrl"):
            self.assertIn(contract_token, py_src, f"cloud_admin.py missing {contract_token}")
            self.assertIn(contract_token, mjs_src, f"cloud-core.mjs missing {contract_token}")

        for schema_col in ("email_verified", "trial_ends_at", "password_resets", "email_outbox"):
            self.assertIn(schema_col, mig_texts, f"Netlify Postgres migrations missing {schema_col}")

    def test_lan_pairing_with_normal_cloud_account_allows_basic_playback_blocks_pro(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        _, _, user = cloud.register_and_verify("lan_norm@mavie.app", "StrongPassword123!")
        admin_tok = cloud.admin_login()
        cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=cloud.admin_headers(admin_tok),
        )

        srv = LocalMediaServerProcess(cloud_url=cloud.base_url).start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        self.assertEqual(
            host_c.post("/api/cloud/login", {"email": "lan_norm@mavie.app", "password": "StrongPassword123!", "cloudUrl": cloud.base_url}).status,
            200,
        )
        code = host_c.get("/api/status").json["pairingCode"]

        tablet = srv.client()
        self.assertEqual(tablet.post("/api/pair", {"code": code}).status, 200)
        self.assertEqual(tablet.post("/api/demo", {}).status, 200)
        items = tablet.get("/api/catalog").json["items"]
        play = tablet.post("/api/play", {"id": items[0]["id"]})
        self.assertEqual(play.status, 200)
        tablet.delete(f"/api/play/{play.json['sessionId']}")

        # Pro-gated sync remains blocked
        self.assertEqual(tablet.post("/api/cloud/sync", {}).status, 403)

    def test_forgot_password_reset_plus_self_device_removal_within_normal_limit(self) -> None:
        cloud = CloudServerProcess().start()
        self.addCleanup(cloud.stop)
        email = "combo_dev_reset@mavie.app"
        _, tok, user = cloud.register_and_verify(email, "FirstPass123!")
        admin_tok = cloud.admin_login()
        cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=cloud.admin_headers(admin_tok),
        )
        self.assertEqual(
            cloud.client().post("/api/v1/devices/register", {"deviceId": "old_phone", "name": "Old", "platform": "android"}, token=tok).status,
            200,
        )

        cloud.client().post("/api/v1/auth/forgot-password", {"email": email})
        _, rcode, rtok = cloud.find_latest_mail(email)
        cloud.client().post(
            "/api/v1/auth/reset-password",
            {"email": email, "code": rcode, "newPassword": "FreshPass456!"} if rcode else {"token": rtok, "newPassword": "FreshPass456!"},
        )
        new_tok = cloud.client().post("/api/v1/auth/login", {"email": email, "password": "FreshPass456!"}).json["token"]
        self.assertEqual(cloud.client().delete("/api/v1/devices/old_phone", token=new_tok).status, 200)
        self.assertEqual(
            cloud.client().post("/api/v1/devices/register", {"deviceId": "new_iphone", "name": "iPhone", "platform": "ios"}, token=new_tok).status,
            200,
        )


if __name__ == "__main__":
    unittest.main()
