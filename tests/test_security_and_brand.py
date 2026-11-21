"""Comprehensive security hardening, zero-account verification, and multi-platform Mavie brand/icon tests."""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.local_port, timeout=10)
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

    def test_01_netlify_security_headers_and_admin_completely_removed(self) -> None:
        for removed in (
            "cloud_admin.py",
            "website/admin.html",
            "website/admin.js",
            "website/netlify/edge-functions/admin-gate.ts",
            "website/netlify/functions/api.mts",
            "website/netlify/functions/cloud-core.mjs",
            "android/app/src/main/java/app/mavie/player/data/CloudClient.kt",
            "apple/Shared/CloudClient.swift",
            "apple/iOS/CloudAccountView.swift",
        ):
            self.assertFalse((ROOT / removed).exists(), f"Removed account/admin file still exists: {removed}")

        toml_text = (ROOT / "website" / "netlify.toml").read_text("utf-8")
        for header in (
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Strict-Transport-Security",
            "Content-Security-Policy",
        ):
            self.assertIn(header, toml_text)
        for blocked in ("/admin", "/admin.html", "/api/*", "/netlify/*", "/package.json", "/netlify.toml"):
            self.assertIn(f'from = "{blocked}"', toml_text)

    def test_02_local_server_traversal_malformed_json_and_ssrf_protection(self) -> None:
        for path in ("/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/../server.py"):
            st, hdrs, _ = self._req("GET", path)
            self.assertIn(st, (400, 403, 404), f"Local traversal {path} returned {st}")
            self.assertEqual(hdrs.get("x-content-type-options"), "nosniff")
            self.assertEqual(hdrs.get("x-frame-options"), "DENY")

        # Obtain local device cookie, then verify removed cloud endpoints return 404
        _, hdrs_root, _ = self._req("GET", "/")
        cookie_hdr = hdrs_root.get("set-cookie", "").split(";", 1)[0]
        auth_headers = {"Cookie": cookie_hdr} if cookie_hdr else {}
        for cloud_path in ("/api/cloud/status", "/api/cloud/login", "/api/cloud/register"):
            method = "GET" if cloud_path.endswith("status") else "POST"
            st_c, _, _ = self._req(method, cloud_path, body={} if method == "POST" else None, headers=auth_headers)
            self.assertEqual(st_c, 404, f"Removed cloud endpoint {cloud_path} returned {st_c}")

        # Local server /api/local/stream must reject arbitrary host file reads
        st_loc, _, _ = self._req("GET", "/api/local/stream?path=" + urllib.parse.quote("/etc/passwd"))
        self.assertIn(st_loc, (400, 401, 403, 404))

        # Malformed JSON must never cause 500
        for bad_body in (b"{broken json", b"\xff\xfe\xfd"):
            st_bad, _, _ = self._req("POST", "/api/pair", body=bad_body, headers={"Content-Type": "application/json"})
            self.assertEqual(st_bad, 400)

        # Local server /api/health returns strict Mavie identity and security headers
        st_h, hdrs_h, raw_h = self._req("GET", "/api/health")
        self.assertEqual(st_h, 200)
        self.assertEqual(json.loads(raw_h).get("app"), "mavie")
        self.assertEqual(hdrs_h.get("x-content-type-options"), "nosniff")
        self.assertEqual(hdrs_h.get("x-frame-options"), "DENY")
        self.assertEqual(hdrs_h.get("referrer-policy"), "no-referrer")

    def test_03_git_secret_hygiene_and_xss_safe_frontend(self) -> None:
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

    def test_02_website_entrance_layout_order_and_free_brand_display(self) -> None:
        html = (ROOT / "website" / "index.html").read_text("utf-8")
        css = (ROOT / "website" / "styles.css").read_text("utf-8")

        self.assertIn('class="hero-brand-display"', html)
        self.assertIn('class="hero-slogan"', html)
        self.assertIn("Neden Mavie'yi Tercih Etmelisiniz?", html)
        self.assertIn("4 Platform için Mavie'yi İndirin", html)
        self.assertIn("Tamamen Ücretsiz", html)
        self.assertNotIn("Mavie Pro", html)
        self.assertNotIn("accountModal", html)

        # Verify section ordering: Hero Brand -> Slogan -> Downloads -> Features -> Free Forever
        idx_brand = html.index('hero-brand-display')
        idx_slogan = html.index('hero-slogan')
        idx_dl = html.index('id="downloads"')
        idx_feat = html.index('id="features"')
        idx_free = html.index('id="free-forever"')
        self.assertLess(idx_brand, idx_slogan)
        self.assertLess(idx_slogan, idx_dl)
        self.assertLess(idx_dl, idx_feat)
        self.assertLess(idx_feat, idx_free)

        # Verify purple-blue-turquoise palette tokens in website CSS
        for token in ("#7c3aed", "#3b82f6", "#06b6d4"):
            self.assertIn(token, css.lower())

    def test_03_all_four_platform_logos_valid_and_purple_blue_turquoise(self) -> None:
        for rel in ("website/mavie-mark.svg", "website/icon.svg", "public/mavie-mark.svg", "public/icon.svg"):
            svg = (ROOT / rel).read_text("utf-8").lower()
            self.assertIn("#7c3aed", svg, f"Missing purple in {rel}")
            self.assertIn("#3b82f6", svg, f"Missing blue in {rel}")
            self.assertIn("#06b6d4", svg, f"Missing turquoise in {rel}")

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

        ios_icon = ROOT / "apple" / "iOS" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon.png"
        self.assertTrue(ios_icon.is_file(), "Missing iOS AppIcon.png")
        w, h, rows = _decode_png_rgba(ios_icon)
        self.assertEqual((w, h), (1024, 1024))
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

        mac_plist = (ROOT / "apple" / "macOS" / "Info.plist").read_text("utf-8")
        self.assertIn("<string>AppIcon</string>", mac_plist)
        self.assertIn("<key>CFBundleIconFile</key>", mac_plist)
        self.assertIn("<key>CFBundleIconName</key>", mac_plist)
        self.assertIn("<string>Mavie</string>", mac_plist)
        self.assertIn("<key>NSAllowsArbitraryLoads</key>", mac_plist)

        ios_plist = (ROOT / "apple" / "iOS" / "Info.plist").read_text("utf-8")
        self.assertIn("<key>NSAllowsArbitraryLoads</key>", ios_plist)
        self.assertIn("<string>audio</string>", ios_plist)

        # Regression guard: XcodeGen `info:` blocks wipe Info.plist and strip CFBundleIconFile!
        proj_yml = (ROOT / "apple" / "project.yml").read_text("utf-8")
        self.assertIn("INFOPLIST_FILE: macOS/Info.plist", proj_yml)
        self.assertIn("INFOPLIST_FILE: iOS/Info.plist", proj_yml)
        self.assertIn("GENERATE_INFOPLIST_FILE: NO", proj_yml)
        self.assertNotIn("\n    info:\n", proj_yml)

        mac_asset_dir = ROOT / "apple" / "macOS" / "Assets.xcassets" / "AppIcon.appiconset"
        self.assertTrue((mac_asset_dir / "Contents.json").is_file())
        self.assertTrue((mac_asset_dir / "icon_512x512@2x.png").is_file())

        mac_script = (ROOT / "apple" / "macOS" / "build_macos.sh").read_text("utf-8")
        self.assertIn("AppIcon.icns", mac_script)
        self.assertIn("CFBundleIconFile", mac_script)
        self.assertIn("#7C3AED", mac_script)

    def test_04_desktop_port_allocator_skips_occupied_wildcard_port(self) -> None:
        sys.path.insert(0, str(ROOT / "desktop"))
        import mavie_desktop

        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("0.0.0.0", 0))
        blocker.listen(5)
        try:
            busy_port = int(blocker.getsockname()[1])
            chosen = mavie_desktop.find_free_port(busy_port)
            self.assertNotEqual(chosen, busy_port, "find_free_port must skip a port occupied on 0.0.0.0")
            self.assertGreater(chosen, 0)
        finally:
            blocker.close()


if __name__ == "__main__":
    unittest.main()
