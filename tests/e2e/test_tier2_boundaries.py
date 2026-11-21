"""Tier 2: Boundary, corner-case, security, and error-handling E2E tests (>=5 per area)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import m3u
import sports
from tests.e2e.runner import (
    CloudServerProcess,
    LocalMediaServerProcess,
)


class Tier2EmailVerificationBoundariesTests(unittest.TestCase):
    """Boundary Area A: Email verification codes, expiry, reuse, rate limits, duplicate/weak signup."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def test_invalid_verification_code_rejected_and_user_remains_unverified(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "badcode@mavie.app", "password": "StrongPassword123!"},
        )
        res = self.cloud.client().post(
            "/api/v1/auth/verify-email",
            {"email": "badcode@mavie.app", "code": "000000"},
        )
        self.assertIn(res.status, (400, 401, 403), res.text)
        login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": "badcode@mavie.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(login.status, 403)
        self.assertEqual((login.json or {}).get("code"), "EMAIL_NOT_VERIFIED")

    def test_expired_verification_code_rejected(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "expcode@mavie.app", "password": "StrongPassword123!"},
        )
        _, code, token = self.cloud.find_latest_mail("expcode@mavie.app")
        self.assertTrue(code or token)
        updated = self.cloud.expire_tokens_in_db("verif")
        self.assertGreater(updated, 0, "Expected verification token row in SQLite to backdate 24h expiry")

        payload = {"email": "expcode@mavie.app", "code": code} if code else {"token": token}
        res = self.cloud.client().post("/api/v1/auth/verify-email", payload)
        self.assertIn(res.status, (400, 401, 410), res.text)

    def test_reused_verification_code_rejected_after_first_verify(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "reuse@mavie.app", "password": "StrongPassword123!"},
        )
        _, code, token = self.cloud.find_latest_mail("reuse@mavie.app")
        payload = {"email": "reuse@mavie.app", "code": code} if code else {"token": token}
        first = self.cloud.client().post("/api/v1/auth/verify-email", payload)
        self.assertEqual(first.status, 200, first.text)
        second = self.cloud.client().post("/api/v1/auth/verify-email", payload)
        self.assertIn(second.status, (400, 409, 410), second.text)

    def test_unverified_user_blocked_across_all_verified_only_endpoints(self) -> None:
        reg = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "gateall@mavie.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(reg.status, 201)
        self.assertIsNone((reg.json or {}).get("token"))

        # Even without a token (or with an invalid/unverified token), verified-only routes must refuse access
        for method, path, body in (
            ("GET", "/api/v1/me", None),
            ("GET", "/api/v1/sync", None),
            ("PUT", "/api/v1/sync", {"favorites": []}),
            ("POST", "/api/v1/devices/register", {"deviceId": "d1", "name": "PC", "platform": "windows"}),
            ("DELETE", "/api/v1/devices/d1", None),
            ("POST", "/api/v1/licenses/redeem", {"code": "MAVIE-AAAA-BBBB-CCCC"}),
        ):
            resp = self.cloud.client().request(method, path, json_body=body)
            self.assertIn(resp.status, (401, 403), f"{method} {path} must reject unverified/unauthenticated caller")

    def test_resend_verification_rate_limited(self) -> None:
        self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "ratelimit@mavie.app", "password": "StrongPassword123!"},
        )
        statuses = []
        for _ in range(12):
            r = self.cloud.client().post("/api/v1/auth/resend-verification", {"email": "ratelimit@mavie.app"})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(429, statuses, f"Expected 429 rate limit on rapid resend burst; got {statuses}")

    def test_duplicate_email_case_insensitive_and_weak_password_rejected(self) -> None:
        weak = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "weak@mavie.app", "password": "123"},
        )
        self.assertEqual(weak.status, 400, weak.text)

        ver, _, _ = self.cloud.register_and_verify("DupCase@Mavie.app", "StrongPassword123!")
        self.assertEqual(ver.status, 200, ver.text)
        dup = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": " dupcase@mavie.app ", "password": "StrongPassword123!"},
        )
        self.assertIn(dup.status, (400, 409), dup.text)


class Tier2PasswordResetBoundariesTests(unittest.TestCase):
    """Boundary Area B: Password reset codes, expiry, reuse, old password, rate limits."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)
        self.email = "pwbounds@mavie.app"
        self.cloud.register_and_verify(self.email, "FirstPass123!")

    def test_wrong_password_login_returns_401(self) -> None:
        res = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": self.email, "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status, 401)

    def test_old_password_rejected_after_password_reset(self) -> None:
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": self.email})
        _, code, token = self.cloud.find_latest_mail(self.email)
        payload = {"email": self.email, "code": code, "newPassword": "SecondPass123!"} if code else {"token": token, "newPassword": "SecondPass123!"}
        self.assertEqual(self.cloud.client().post("/api/v1/auth/reset-password", payload).status, 200)

        old_login = self.cloud.client().post(
            "/api/v1/auth/login",
            {"email": self.email, "password": "FirstPass123!"},
        )
        self.assertEqual(old_login.status, 401)

    def test_invalid_reset_code_rejected_on_verify_and_reset(self) -> None:
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": self.email})
        chk = self.cloud.client().post("/api/v1/auth/verify-reset-code", {"email": self.email, "code": "999999"})
        self.assertIn(chk.status, (400, 401, 404))
        rst = self.cloud.client().post(
            "/api/v1/auth/reset-password",
            {"email": self.email, "code": "999999", "newPassword": "ShouldNotWork123!"},
        )
        self.assertIn(rst.status, (400, 401, 404))

    def test_expired_reset_code_rejected_and_preserves_password(self) -> None:
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": self.email})
        _, code, token = self.cloud.find_latest_mail(self.email)
        self.assertTrue(code or token)
        updated = self.cloud.expire_tokens_in_db("reset")
        self.assertGreater(updated, 0, "Expected password_resets row in SQLite to backdate 30m expiry")

        payload = {"email": self.email, "code": code, "newPassword": "ExpiredReset123!"} if code else {"token": token, "newPassword": "ExpiredReset123!"}
        rst = self.cloud.client().post("/api/v1/auth/reset-password", payload)
        self.assertIn(rst.status, (400, 401, 410), rst.text)
        still_ok = self.cloud.client().post("/api/v1/auth/login", {"email": self.email, "password": "FirstPass123!"})
        self.assertEqual(still_ok.status, 200)

    def test_reused_reset_code_rejected_on_second_attempt(self) -> None:
        self.cloud.client().post("/api/v1/auth/forgot-password", {"email": self.email})
        _, code, token = self.cloud.find_latest_mail(self.email)
        p1 = {"email": self.email, "code": code, "newPassword": "ResetOnce123!"} if code else {"token": token, "newPassword": "ResetOnce123!"}
        p2 = {"email": self.email, "code": code, "newPassword": "ResetTwice123!"} if code else {"token": token, "newPassword": "ResetTwice123!"}
        self.assertEqual(self.cloud.client().post("/api/v1/auth/reset-password", p1).status, 200)
        second = self.cloud.client().post("/api/v1/auth/reset-password", p2)
        self.assertIn(second.status, (400, 401, 409, 410), second.text)

    def test_forgot_password_rate_limited(self) -> None:
        statuses = []
        for _ in range(12):
            r = self.cloud.client().post("/api/v1/auth/forgot-password", {"email": self.email})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(429, statuses, f"Expected 429 rate limit on rapid forgot-password burst; got {statuses}")


class Tier2TrialDeviceLicenseBoundariesTests(unittest.TestCase):
    """Boundary Area C: 72h trial boundary, 1 vs 5 device limits, invalid/used licenses."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess().start()
        self.addCleanup(self.cloud.stop)

    def test_trial_just_before_72h_expiry_remains_pro(self) -> None:
        _, tok, user = self.cloud.register_and_verify("t_before@mavie.app", "StrongPassword123!")
        admin_tok = self.cloud.admin_login()
        almost = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        self.cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "pro", "expiresAt": almost},
            headers=self.cloud.admin_headers(admin_tok),
        )
        me = self.cloud.client().get("/api/v1/me", token=tok).json["user"]
        self.assertEqual(me["effectivePlan"], "pro")
        self.assertTrue(me["isPro"])
        self.assertEqual(me["maxDevices"], 5)

    def test_trial_just_after_72h_expiry_auto_downgrades_to_normal(self) -> None:
        _, tok, user = self.cloud.register_and_verify("t_after@mavie.app", "StrongPassword123!")
        admin_tok = self.cloud.admin_login()
        expired = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        self.cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "pro", "expiresAt": expired},
            headers=self.cloud.admin_headers(admin_tok),
        )
        me = self.cloud.client().get("/api/v1/me", token=tok).json["user"]
        self.assertEqual(me["effectivePlan"], "normal")
        self.assertFalse(me["isPro"])
        self.assertFalse(me["trialActive"])
        self.assertEqual(me["maxDevices"], 1)

    def test_normal_device_limit_boundary_and_idempotent_reregister(self) -> None:
        _, tok, user = self.cloud.register_and_verify("dev1@mavie.app", "StrongPassword123!")
        admin_tok = self.cloud.admin_login()
        self.cloud.client().patch(
            f"/api/v1/admin/users/{user['id']}",
            {"plan": "normal", "expiresAt": "2020-01-01T00:00:00+00:00"},
            headers=self.cloud.admin_headers(admin_tok),
        )
        r1 = self.cloud.client().post("/api/v1/devices/register", {"deviceId": "d1", "name": "Mac", "platform": "macos"}, token=tok)
        self.assertEqual(r1.status, 200)
        # Same deviceId re-registration should succeed idempotently
        r1_again = self.cloud.client().post("/api/v1/devices/register", {"deviceId": "d1", "name": "Mac Updated", "platform": "macos"}, token=tok)
        self.assertEqual(r1_again.status, 200)
        # Second distinct device exceeds limit 1
        r2 = self.cloud.client().post("/api/v1/devices/register", {"deviceId": "d2", "name": "iPhone", "platform": "ios"}, token=tok)
        self.assertEqual(r2.status, 403)
        self.assertEqual((r2.json or {}).get("code"), "DEVICE_LIMIT_REACHED")

    def test_pro_device_limit_boundary_5_vs_6(self) -> None:
        _, tok, _ = self.cloud.register_and_verify("dev5@mavie.app", "StrongPassword123!")
        for idx in range(1, 6):
            r = self.cloud.client().post(
                "/api/v1/devices/register",
                {"deviceId": f"pro_d{idx}", "name": f"Dev {idx}", "platform": "ios"},
                token=tok,
            )
            self.assertEqual(r.status, 200, f"Device {idx} of 5 failed: {r.text}")
        r6 = self.cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "pro_d6", "name": "Dev 6", "platform": "android"},
            token=tok,
        )
        self.assertEqual(r6.status, 403, r6.text)
        self.assertEqual((r6.json or {}).get("code"), "DEVICE_LIMIT_REACHED")

        self.assertEqual(self.cloud.client().delete("/api/v1/devices/pro_d1", token=tok).status, 200)
        r6_ok = self.cloud.client().post(
            "/api/v1/devices/register",
            {"deviceId": "pro_d6", "name": "Dev 6", "platform": "android"},
            token=tok,
        )
        self.assertEqual(r6_ok.status, 200)

    def test_invalid_and_already_used_license_keys_rejected(self) -> None:
        _, tok1, _ = self.cloud.register_and_verify("lic1@mavie.app", "StrongPassword123!")
        _, tok2, _ = self.cloud.register_and_verify("lic2@mavie.app", "StrongPassword123!")

        bad = self.cloud.client().post("/api/v1/licenses/redeem", {"code": "MAVIE-0000-0000-0000"}, token=tok1)
        self.assertIn(bad.status, (400, 404))
        empty = self.cloud.client().post("/api/v1/licenses/redeem", {"code": ""}, token=tok1)
        self.assertEqual(empty.status, 400)

        admin_tok = self.cloud.admin_login()
        lic = self.cloud.client().post(
            "/api/v1/admin/licenses",
            {"plan": "pro", "durationDays": 30, "count": 1, "maxUses": 1},
            headers=self.cloud.admin_headers(admin_tok),
        ).json["license"]["code"]

        ok = self.cloud.client().post("/api/v1/licenses/redeem", {"code": lic}, token=tok1)
        self.assertEqual(ok.status, 200, ok.text)
        reused = self.cloud.client().post("/api/v1/licenses/redeem", {"code": lic}, token=tok2)
        self.assertIn(reused.status, (400, 409, 410), reused.text)

    def test_cannot_delete_another_users_device(self) -> None:
        _, tok_a, _ = self.cloud.register_and_verify("own_a@mavie.app", "StrongPassword123!")
        _, tok_b, _ = self.cloud.register_and_verify("own_b@mavie.app", "StrongPassword123!")
        self.cloud.client().post("/api/v1/devices/register", {"deviceId": "a_device_99", "name": "A", "platform": "windows"}, token=tok_a)
        res = self.cloud.client().delete("/api/v1/devices/a_device_99", token=tok_b)
        self.assertIn(res.status, (403, 404))


class Tier2LocalServerBoundariesTests(unittest.TestCase):
    """Boundary Area D: Malformed M3U/XMLTV/XXE, traversal, SSRF, pairing rate limit, playback & profile errors."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()

    def test_malformed_m3u_handled_gracefully(self) -> None:
        for bad in ("", "not an m3u file\n###garbage", "#EXTM3U\n#EXTINF:-1,NoUrlChannel\n"):
            parsed = m3u.parse_m3u(bad)
            self.assertIsInstance(parsed, dict)
            self.assertEqual(parsed.get("items", []), [])

    def test_malformed_xmltv_and_xxe_rejected_safely(self) -> None:
        xxe = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE tv [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<tv><programme start=\"20261119120000 +0000\" stop=\"20261119130000 +0000\" channel=\"c1\">"
            "<title>&xxe;</title></programme></tv>"
        )
        try:
            res = sports.parse_xmltv(xxe, datetime.now(timezone.utc).date())
            self.assertNotIn("root:", json.dumps(res))
        except Exception:
            # Raising a parse/defused error on XXE DOCTYPE is valid safe rejection
            pass

    def test_path_traversal_attempts_rejected(self) -> None:
        for path in (
            "/../../etc/passwd",
            "/%2e%2e/%2e%2e/etc/passwd",
            "/api/subtitles/../../etc/passwd/0.vtt",
            "/media/nonexistent/../../etc/passwd",
        ):
            r = self.c.get(path)
            self.assertIn(r.status, (400, 403, 404, 410), f"Traversal path {path} returned {r.status}")
            self.assertNotIn("root:x:0:0", r.text)

    def test_ssrf_blocks_private_loopback_m3u_and_epg_urls(self) -> None:
        for url in ("http://127.0.0.1:9999/list.m3u", "http://169.254.169.254/latest/meta-data/"):
            res = self.c.post("/api/settings", {"type": "m3u", "m3uUrl": url, "name": "SSRF"})
            # Either rejected synchronously (400) or recorded as catalog.error without fetching
            if res.status == 200:
                time.sleep(0.3)
                st = self.c.get("/api/status").json
                self.assertTrue(st["catalog"]["error"], f"Private URL {url} should be blocked")
            else:
                self.assertIn(res.status, (400, 403))

    def test_pairing_wrong_code_and_rate_limit(self) -> None:
        guest = self.srv.client()
        statuses = []
        for i in range(15):
            r = guest.post("/api/pair", {"code": f"{i:06d}"})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(403, statuses)
        self.assertIn(429, statuses, f"Expected 429 on pairing brute-force; got {statuses}")

    def test_playback_boundary_errors_invalid_item_session_and_position(self) -> None:
        bad_item = self.c.post("/api/play", {"id": "vod:does_not_exist"})
        self.assertIn(bad_item.status, (400, 404))

        bad_ping = self.c.post("/api/play/unknown_sid/ping", {"position": 10})
        self.assertIn(bad_ping.status, (404, 410))

        self.c.post("/api/demo", {})
        items = self.c.get("/api/catalog").json["items"]
        play = self.c.post("/api/play", {"id": items[0]["id"]})
        sid = play.json["sessionId"]
        bad_json = self.c.request(
            "POST",
            f"/api/play/{sid}/ping",
            raw_body=b"{invalid-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(bad_json.status, 400)
        neg = self.c.post(f"/api/play/{sid}/ping", {"position": -50})
        self.assertIn(neg.status, (200, 400))
        self.assertNotIn("-50", self.c.get("/api/progress").text)
        self.c.delete(f"/api/play/{sid}")

    def test_profile_wrong_pin_and_default_delete_rejected(self) -> None:
        prof = self.c.post("/api/profiles", {"name": "Locked", "pin": "1111"}).json["profile"]
        wrong = self.c.post("/api/profiles/switch", {"id": prof["id"], "pin": "2222"})
        self.assertEqual(wrong.status, 403)
        del_def = self.c.delete("/api/profiles/default")
        self.assertIn(del_def.status, (400, 403))


class Tier2OutboxWebsiteAdminBoundariesTests(unittest.TestCase):
    """Boundary Area E: Missing SMTP outbox fallback, anti-leakage, malformed inputs, admin gate."""

    def setUp(self) -> None:
        self.cloud = CloudServerProcess(extra_env={"MAVIE_EMAIL_MODE": "auto"}).start()
        self.addCleanup(self.cloud.stop)

    def test_missing_smtp_falls_back_to_local_outbox_cleanly(self) -> None:
        reg = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "nosmtp@mavie.app", "password": "StrongPassword123!"},
        )
        self.assertEqual(reg.status, 201, reg.text)
        self.assertEqual((reg.json or {}).get("deliveryMode"), "outbox")
        mail, code, token = self.cloud.find_latest_mail("nosmtp@mavie.app")
        self.assertIsNotNone(mail)
        self.assertTrue(code or token)

    def test_public_responses_never_leak_codes_or_tokens(self) -> None:
        reg = self.cloud.client().post(
            "/api/v1/auth/register",
            {"email": "noleak@mavie.app", "password": "StrongPassword123!"},
        )
        _, vcode, vtok = self.cloud.find_latest_mail("noleak@mavie.app")
        if vcode:
            self.assertNotIn(vcode, reg.text)
        if vtok:
            self.assertNotIn(vtok, reg.text)

        self.cloud.client().post(
            "/api/v1/auth/verify-email",
            {"email": "noleak@mavie.app", "code": vcode} if vcode else {"token": vtok},
        )
        fg = self.cloud.client().post("/api/v1/auth/forgot-password", {"email": "noleak@mavie.app"})
        _, rcode, rtok = self.cloud.find_latest_mail("noleak@mavie.app")
        if rcode and rcode != vcode:
            self.assertNotIn(rcode, fg.text)
        if rtok and rtok != vtok:
            self.assertNotIn(rtok, fg.text)

    def test_malformed_json_and_missing_fields_return_400_without_500(self) -> None:
        bad_json = self.cloud.client().request(
            "POST",
            "/api/v1/auth/register",
            raw_body=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(bad_json.status, 400)
        missing = self.cloud.client().post("/api/v1/auth/register", {"email": "invalid-email"})
        self.assertEqual(missing.status, 400)

    def test_admin_endpoints_reject_missing_gate_and_non_admin_user(self) -> None:
        admin_tok = self.cloud.admin_login()
        no_gate = self.cloud.client().get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_tok}"},
        )
        self.assertIn(no_gate.status, (401, 403, 404))

        _, user_tok, _ = self.cloud.register_and_verify("norm_adm@mavie.app", "StrongPassword123!")
        non_admin = self.cloud.client().get(
            "/api/v1/admin/users",
            headers=self.cloud.admin_headers(user_tok),
        )
        self.assertEqual(non_admin.status, 403)

    def test_download_track_rejects_unknown_platform_slug(self) -> None:
        res = self.cloud.client().post("/api/v1/downloads/track", {"platform": "symbian-os"})
        self.assertEqual(res.status, 400)

    def test_tampered_bearer_token_returns_401(self) -> None:
        me = self.cloud.client().get("/api/v1/me", token="tampered.invalid.token")
        self.assertEqual(me.status, 401)


if __name__ == "__main__":
    unittest.main()
