"""Comprehensive security hardening, penetration-check, and multi-platform Mavie brand/icon tests."""
from __future__ import annotations

import base64
import http.client
import json
import os
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cloud_admin


def _png_info(path: Path) -> tuple[int, int, bytes]:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a valid PNG")
    w, h = struct.unpack(">II", raw[16:24])
    return w, h, raw


def _decode_png_rgba(path: Path) -> tuple[int, int, list[bytearray]]:
    w, h, raw = _png_info(path)
    pos = 8
    idat_chunks = []
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        ctype = raw[pos + 4:pos + 8]
        cdata = raw[pos + 8:pos + 8 + length]
        if ctype == b"IDAT":
            idat_chunks.append(cdata)
        pos += 12 + length
    dec = zlib.decompress(b"".join(idat_chunks))
    bpp = 4
    row_bytes = w * bpp
    rows: list[bytearray] = []
    prev = bytearray(row_bytes)
    idx = 0
    for _ in range(h):
        ftype = dec[idx]
        idx += 1
        cur = bytearray(dec[idx:idx + row_bytes])
        idx += row_bytes
        if ftype == 1:
            for i in range(bpp, row_bytes):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(row_bytes):
                cur[i] = (cur[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(row_bytes):
                a = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(row_bytes):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (cur[i] + pr) & 0xFF
        rows.append(cur)
        prev = cur
    return w, h, rows


class SecurityAndHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="mavie-sec-tests-")
        cls.data_dir = Path(cls.temp.name)
        cls.service = cloud_admin.CloudService(
            cls.data_dir / "cloud",
            admin_email="admin@mavie.app",
            admin_password="AdminStrongPass!2026",
            admin_gate_key="sec-gate-token-2026",
        )
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cloud_admin.make_handler(cls.service))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        # Spin up an isolated local Mavie media server subprocess for local security tests
        cls.local_dir = cls.data_dir / "local_srv"
        cls.local_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            cls.local_port = int(s.getsockname()[1])
        env = {**os.environ, "MAVIE_DATA_DIR": str(cls.local_dir)}
        cls.local_proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", str(cls.local_port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15.0
        ready = False
        while time.monotonic() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", cls.local_port, timeout=1)
                conn.request("GET", "/api/health")
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.15)
        if not ready:
            cls.local_proc.terminate()
            raise RuntimeError("Local Mavie server failed to start for security tests")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.local_proc.terminate()
        try:
            cls.local_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.local_proc.kill()
        cls.temp.cleanup()

    def _req(
        self,
        method: str,
        path: str,
        body: dict | bytes | None = None,
        headers: dict[str, str] | None = None,
        port: int | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=10)
        hdrs = dict(headers or {})
        payload = None
        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, (bytes, bytearray)):
            payload = bytes(body)
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, resp_headers, data

    def _outbox_code(self, email: str, kind: str) -> str:
        p = self.data_dir / "cloud" / "email_outbox.json"
        entries = json.loads(p.read_text("utf-8"))
        matches = [e for e in entries if e.get("recipient", "").lower() == email.lower() and e.get("kind") == kind]
        self.assertTrue(matches, f"No outbox mail of kind {kind} for {email}")
        return str(matches[-1]["code"])

    def _register_and_verify(self, email: str, password: str = "StrongPass!2026", name: str = "Sec User") -> tuple[str, dict]:
        st, _, raw = self._req("POST", "/api/v1/auth/register", {
            "email": email,
            "password": password,
            "displayName": name,
        })
        self.assertEqual(st, 201, raw)
        res = json.loads(raw)
        # OTP code must NEVER leak in HTTP registration response
        self.assertNotIn("code", res)
        self.assertNotIn("devVerificationCode", res)
        code = self._outbox_code(email, "verify_email")
        st2, _, raw2 = self._req("POST", "/api/v1/auth/verify-email", {
            "email": email,
            "code": code,
        })
        self.assertEqual(st2, 200, raw2)
        verified = json.loads(raw2)
        return verified["token"], verified["user"]

    def test_01_security_headers_and_static_leak_protection(self) -> None:
        st, hdrs, body = self._req("GET", "/")
        self.assertEqual(st, 200)
        self.assertEqual(hdrs.get("x-content-type-options"), "nosniff")
        self.assertEqual(hdrs.get("x-frame-options"), "DENY")
        self.assertEqual(hdrs.get("referrer-policy"), "no-referrer")
        self.assertIn("script-src 'self'", hdrs.get("content-security-policy", ""))
        self.assertIn(b"Mavie", body)

        # Sensitive backend & traversal paths must all return 404
        blocked_paths = [
            "/netlify.toml",
            "/package.json",
            "/netlify/functions/cloud-core.mjs",
            "/netlify/edge-functions/admin-gate.ts",
            "/netlify/database/migrations/20261119000000_vrelio_plans_verify.sql",
            "/netlify/database/migrations/20261121163000_mavie_brand_urls.sql",
            "/admin.html",
            "/admin",
            "/../server.py",
            "/../../etc/passwd",
            "/%2e%2e/%2e%2e/etc/passwd",
            "/..%5c..%5cserver.py",
            "/.env",
        ]
        for path in blocked_paths:
            code, _, _ = self._req("GET", path)
            self.assertEqual(code, 404, f"Expected 404 for sensitive/traversal path {path}, got {code}")

        # Verify netlify.toml enforces HSTS, CSP, nosniff, X-Frame-Options
        toml_text = (ROOT / "website" / "netlify.toml").read_text("utf-8")
        for header in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security", "Content-Security-Policy"):
            self.assertIn(header, toml_text)

    def test_02_sql_injection_and_malformed_input_resilience(self) -> None:
        sqli_payloads = [
            "' OR '1'='1",
            "admin@mavie.app' --",
            "admin@mavie.app' UNION SELECT 1,2,3 --",
            "'; DROP TABLE users; --",
        ]
        for payload in sqli_payloads:
            st, hdrs, _ = self._req("POST", "/api/v1/auth/login", {
                "email": payload,
                "password": "' OR '1'='1",
            })
            self.assertIn(st, (400, 401, 403, 429), f"Unexpected status {st} for SQLi login {payload!r}")
            self.assertEqual(hdrs.get("cache-control"), "no-store")
            self.assertEqual(hdrs.get("x-content-type-options"), "nosniff")

        # Malformed JSON & non-UTF8 bytes must never cause 500
        for bad_body in (b"{broken json", b"[]", b"\xff\xfe\xfd"):
            st, _, _ = self._req("POST", "/api/v1/auth/login", body=bad_body, headers={"Content-Type": "application/json"})
            self.assertEqual(st, 400, f"Malformed payload {bad_body!r} returned {st}")

        # Admin account must still exist cleanly after SQLi probes
        st_admin, _, raw_admin = self._req("POST", "/api/v1/auth/login", {
            "email": "admin@mavie.app",
            "password": "AdminStrongPass!2026",
        })
        self.assertEqual(st_admin, 200, raw_admin)

    def test_03_jwt_forgery_and_privilege_escalation_blocked(self) -> None:
        user_token, user = self._register_and_verify("normal.sec@mavie.app")

        # Forged alg=none JWT, tampered payload JWT, garbage token
        header_none = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload_admin = base64.urlsafe_b64encode(json.dumps({"sub": user["id"], "role": "admin", "exp": 9999999999}).encode()).decode().rstrip("=")
        forged_none = f"{header_none}.{payload_admin}."
        parts = user_token.split(".")
        tampered_sig = f"{parts[0]}.{payload_admin}.{parts[2]}" if len(parts) == 3 else "bad.token.sig"

        for bad_token in (forged_none, tampered_sig, "not-a-jwt", ""):
            st, _, _ = self._req("GET", "/api/v1/me", headers={"Authorization": f"Bearer {bad_token}"})
            self.assertEqual(st, 401, f"Forged token accepted: {bad_token!r}")

        # Layer 1: Without X-Admin-Gate, all admin API endpoints are stealth-hidden (404)
        admin_endpoints = [
            ("GET", "/api/v1/admin/overview"),
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/licenses"),
            ("POST", "/api/v1/admin/licenses"),
            ("PUT", "/api/v1/admin/config"),
            ("GET", "/api/v1/admin/audit"),
        ]
        for method, path in admin_endpoints:
            st_nogate, _, _ = self._req(method, path, body={} if method != "GET" else None, headers={"Authorization": f"Bearer {user_token}"})
            self.assertEqual(st_nogate, 404, f"Admin route leaked without gate on {method} {path}: {st_nogate}")

        # Layer 2: Even WITH X-Admin-Gate, non-admin JWT is blocked by RBAC (403)
        for method, path in admin_endpoints:
            st, _, _ = self._req(
                method,
                path,
                body={} if method != "GET" else None,
                headers={"Authorization": f"Bearer {user_token}", "X-Admin-Gate": "sec-gate-token-2026"},
            )
            self.assertEqual(st, 403, f"Non-admin allowed on {method} {path}: {st}")

    def test_04_idor_cross_user_isolation_and_secret_non_leakage(self) -> None:
        tok_a, user_a = self._register_and_verify("alice.sec@mavie.app")
        tok_b, user_b = self._register_and_verify("bob.sec@mavie.app")

        # Register device on Alice's account
        st_dev, _, raw_dev = self._req("POST", "/api/v1/devices/register", {
            "deviceId": "alice-device-001",
            "deviceName": "Alice MacBook",
            "platform": "macos",
        }, headers={"Authorization": f"Bearer {tok_a}"})
        self.assertEqual(st_dev, 200, raw_dev)

        # Bob tries to delete Alice's device -> must fail (403/404) and Alice's device must remain
        st_idor, _, _ = self._req("DELETE", "/api/v1/devices/alice-device-001", headers={"Authorization": f"Bearer {tok_b}"})
        self.assertIn(st_idor, (403, 404))

        st_me, _, raw_me = self._req("GET", "/api/v1/me", headers={"Authorization": f"Bearer {tok_a}"})
        self.assertEqual(st_me, 200)
        me_text = raw_me.decode("utf-8")
        self.assertIn("alice-device-001", me_text)
        # Ensure sensitive hashes never leak in API responses
        for forbidden_field in ("password_hash", "passwordHash", "verification_code_hash", "reset_code_hash", "pbkdf2"):
            self.assertNotIn(forbidden_field, me_text)

        # Verify DB stores PBKDF2-SHA256 hashed passwords with unique salts (never plaintext)
        db_path = self.data_dir / "cloud" / "cloud.sqlite3"
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT email, password_hash FROM users WHERE email IN (?, ?)", ("alice.sec@mavie.app", "bob.sec@mavie.app")).fetchall()
        self.assertEqual(len(rows), 2)
        hashes = [r[1] for r in rows]
        for h in hashes:
            self.assertNotIn("StrongPass!2026", h)
            self.assertTrue(h.startswith("pbkdf2") or "$" in h, f"Weak password hash format: {h}")
        self.assertNotEqual(hashes[0], hashes[1], "Identical passwords must produce distinct salted hashes")

    def test_05_password_reset_revokes_previous_tokens(self) -> None:
        old_tok, _ = self._register_and_verify("revoke.sec@mavie.app", "InitialPass!2026")
        st_req, _, raw_req = self._req("POST", "/api/v1/auth/forgot-password", {"email": "revoke.sec@mavie.app"})
        self.assertEqual(st_req, 200, raw_req)
        req_json = json.loads(raw_req)
        self.assertNotIn("code", req_json)
        self.assertNotIn("devResetCode", req_json)
        reset_code = self._outbox_code("revoke.sec@mavie.app", "password_reset")

        st_rst, _, raw_rst = self._req("POST", "/api/v1/auth/reset-password", {
            "email": "revoke.sec@mavie.app",
            "code": reset_code,
            "newPassword": "RotatedPass!2026",
        })
        self.assertEqual(st_rst, 200, raw_rst)

        # Old JWT issued prior to reset must be rejected immediately
        st_old, _, _ = self._req("GET", "/api/v1/me", headers={"Authorization": f"Bearer {old_tok}"})
        self.assertEqual(st_old, 401, "Pre-reset JWT should be revoked after password reset")

    def test_06_local_server_traversal_and_ssrf_protection(self) -> None:
        # Local server static path traversal must be blocked
        for path in ("/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/../server.py"):
            st, hdrs, _ = self._req("GET", path, port=self.local_port)
            self.assertIn(st, (400, 403, 404), f"Local traversal {path} returned {st}")
            self.assertEqual(hdrs.get("x-content-type-options"), "nosniff")
            self.assertEqual(hdrs.get("x-frame-options"), "DENY")

        # Local server /api/local/stream must reject unauthenticated/arbitrary host file reads
        st_loc, _, _ = self._req("GET", "/api/local/stream?path=" + urllib.parse.quote("/etc/passwd"), port=self.local_port)
        self.assertIn(st_loc, (400, 401, 403, 404))

        # Local server /api/health returns strict Mavie identity and security headers
        st_h, hdrs_h, raw_h = self._req("GET", "/api/health", port=self.local_port)
        self.assertEqual(st_h, 200)
        self.assertEqual(json.loads(raw_h).get("app"), "mavie")
        self.assertEqual(hdrs_h.get("x-content-type-options"), "nosniff")
        self.assertEqual(hdrs_h.get("x-frame-options"), "DENY")
        self.assertEqual(hdrs_h.get("referrer-policy"), "no-referrer")

    def test_07_git_secret_hygiene_and_xss_safe_frontend(self) -> None:
        tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        forbidden_exts = (".jks", ".keystore", ".p12", ".pem", ".key")
        for f in tracked:
            low = f.lower()
            self.assertFalse(low.endswith(forbidden_exts), f"Secret/signing file tracked in Git: {f}")
            self.assertNotIn("android/signing/", low, f"Signing directory tracked in Git: {f}")

        portal_js = (ROOT / "website" / "portal.js").read_text("utf-8")
        self.assertIn("const esc = v =>", portal_js)
        self.assertIn("https?:\\/\\/", portal_js)
        self.assertIn("\\/(?!\\/)", portal_js)


class MavieBrandPaletteAndIconsTests(unittest.TestCase):
    def test_01_zero_vrelio_and_zero_legacy_red_orange_colors(self) -> None:
        tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        for rel in tracked:
            if (
                rel.startswith("tests/test_security_and_brand.py")
                or rel.startswith("tests/test_player_features_frontend.mjs")
                or rel == "website/netlify/database/migrations/20261119000000_vrelio_plans_verify.sql"
            ):
                continue
            p = ROOT / rel
            if not p.is_file() or p.suffix.lower() in (".png", ".ico", ".icns", ".jpg", ".webp", ".woff2", ".mp4", ".ts"):
                continue
            txt = p.read_text("utf-8", errors="ignore")
            self.assertNotIn("vrelio", txt.lower(), f"Stray 'vrelio' string in {rel}")

        ui_files = [
            "website/styles.css",
            "website/index.html",
            "website/mavie-mark.svg",
            "website/icon.svg",
            "public/cinema.css",
            "public/player.css",
            "public/sports.css",
            "public/styles.css",
            "public/mavie-mark.svg",
            "public/icon.svg",
            "android/app/src/main/res/drawable/mavie_mark.xml",
            "android/app/src/main/java/app/mavie/player/ui/MavieTheme.kt",
            "apple/Shared/BrandTheme.swift",
            "apple/iOS/PlayerView.swift",
        ]
        legacy_warm = re.compile(r"#(ff4b45|e50914|ed1520|ff9933|ff7438|ff0b19|ff535a|ff5b64|941120|601014)\b", re.IGNORECASE)
        for rel in ui_files:
            txt = (ROOT / rel).read_text("utf-8")
            m = legacy_warm.search(txt)
            self.assertIsNone(m, f"Legacy red/orange color {m.group(0) if m else ''} found in {rel}")

    def test_02_website_entrance_layout_order_and_brand_display(self) -> None:
        html = (ROOT / "website" / "index.html").read_text("utf-8")
        css = (ROOT / "website" / "styles.css").read_text("utf-8")

        self.assertIn('class="hero-brand-display"', html)
        self.assertIn('class="hero-slogan"', html)
        self.assertIn("Neden Mavie'yi Tercih Etmelisiniz?", html)
        self.assertIn("4 Platform için Mavie'yi İndirin", html)

        # Verify section ordering: Hero Brand -> Slogan -> Downloads -> Features -> Plans
        idx_brand = html.index('hero-brand-display')
        idx_slogan = html.index('hero-slogan')
        idx_dl = html.index('id="downloads"')
        idx_feat = html.index('id="features"')
        idx_plans = html.index('id="plans"')
        self.assertLess(idx_brand, idx_slogan)
        self.assertLess(idx_slogan, idx_dl)
        self.assertLess(idx_dl, idx_feat)
        self.assertLess(idx_feat, idx_plans)

        # Verify purple-blue-turquoise palette tokens in website CSS
        for token in ("#7c3aed", "#3b82f6", "#06b6d4"):
            self.assertIn(token, css.lower())

    def test_03_all_four_platform_logos_valid_and_purple_blue_turquoise(self) -> None:
        # 1. Web & PWA SVGs
        for rel in ("website/mavie-mark.svg", "website/icon.svg", "public/mavie-mark.svg", "public/icon.svg"):
            svg = (ROOT / rel).read_text("utf-8").lower()
            self.assertIn("#7c3aed", svg, f"Missing purple in {rel}")
            self.assertIn("#3b82f6", svg, f"Missing blue in {rel}")
            self.assertIn("#06b6d4", svg, f"Missing turquoise in {rel}")

        # 2. Windows ICO + PyInstaller spec + Inno Setup wiring
        ico = ROOT / "windows" / "mavie.ico"
        self.assertTrue(ico.is_file(), "Missing windows/mavie.ico")
        ico_bytes = ico.read_bytes()
        reserved, icon_type, count = struct.unpack("<HHH", ico_bytes[:6])
        self.assertEqual((reserved, icon_type), (0, 1), "Invalid ICO magic header")
        self.assertGreaterEqual(count, 6, f"Expected >= 6 icon resolutions in mavie.ico, found {count}")
        spec_txt = (ROOT / "windows" / "mavie.spec").read_text("utf-8")
        iss_txt = (ROOT / "windows" / "MavieSetup.iss").read_text("utf-8")
        self.assertIn("mavie.ico", spec_txt)
        self.assertIn("SetupIconFile=mavie.ico", iss_txt)
        self.assertIn("UninstallDisplayIcon={app}\\{#MyAppExeName}", iss_txt)

        # 3. Android vector adaptive icon + 5 density raster mipmap PNGs
        android_xml = (ROOT / "android" / "app" / "src" / "main" / "res" / "drawable" / "mavie_mark.xml").read_text("utf-8").lower()
        for tok in ("#ff7c3aed", "#ff3b82f6", "#ff06b6d4"):
            self.assertIn(tok, android_xml)
        for vdir in ("mipmap-anydpi-v26", "mipmap-anydpi-v33"):
            ic_xml = (ROOT / "android" / "app" / "src" / "main" / "res" / vdir / "ic_launcher.xml").read_text("utf-8")
            self.assertIn("@drawable/mavie_mark", ic_xml)
        for dpi, expected_sz in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
            png_path = ROOT / "android" / "app" / "src" / "main" / "res" / f"mipmap-{dpi}" / "ic_launcher.png"
            self.assertTrue(png_path.is_file(), f"Missing Android raster icon {png_path}")
            w, h, _ = _png_info(png_path)
            self.assertEqual((w, h), (expected_sz, expected_sz), f"Wrong size for {png_path}")

        # 4. iOS 1024x1024 AppIcon.png + AccentColor
        ios_icon = ROOT / "apple" / "iOS" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon.png"
        self.assertTrue(ios_icon.is_file(), "Missing iOS AppIcon.png")
        w, h, rows = _decode_png_rgba(ios_icon)
        self.assertEqual((w, h), (1024, 1024))
        # Confirm vibrant purple/blue/turquoise pixels exist and no red-dominant ring pixels exist
        purple_blue_cyan_hits = 0
        red_orange_hits = 0
        for y in range(160, 864, 16):
            row = rows[y]
            for x in range(160, 864, 16):
                off = x * 4
                r, g, b, a = row[off], row[off + 1], row[off + 2], row[off + 3]
                if a > 200 and b > 170 and b > r + 40:
                    purple_blue_cyan_hits += 1
                if a > 200 and r > 180 and r > b + 70:
                    red_orange_hits += 1
        self.assertGreater(purple_blue_cyan_hits, 20, "iOS AppIcon.png should contain purple-blue-turquoise ring pixels")
        self.assertEqual(red_orange_hits, 0, "iOS AppIcon.png must not contain red/orange pixels")

        # 5. macOS Info.plist + build_macos.sh icon generation
        mac_plist = (ROOT / "apple" / "macOS" / "Info.plist").read_text("utf-8")
        self.assertIn("<string>AppIcon</string>", mac_plist)
        self.assertIn("<string>Mavie</string>", mac_plist)
        mac_script = (ROOT / "apple" / "macOS" / "build_macos.sh").read_text("utf-8")
        self.assertIn("AppIcon.icns", mac_script)
        self.assertIn("#7C3AED", mac_script)


if __name__ == "__main__":
    unittest.main()
