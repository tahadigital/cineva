"""Tests for Mavie redesigned website routes, assets, 4-platform portal, and browser layout/flows."""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cloud_admin


def _find_chrome() -> str | None:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class _MinimalCDP:
    """Tiny RFC 6455 WebSocket client over Python stdlib for headless Chrome CDP."""

    def __init__(self, ws_url: str) -> None:
        m = re.match(r"^ws://([^:/]+):(\d+)(/.*)$", ws_url)
        if not m:
            raise RuntimeError(f"Unsupported ws url: {ws_url}")
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("WebSocket handshake EOF")
            buf += chunk
        if b"101 " not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket handshake failed: {buf!r}")
        self._extra = buf.split(b"\r\n\r\n", 1)[1]
        self._next_id = 1
        self.events: list[dict] = []

    def _read_exact(self, n: int) -> bytes:
        out = bytearray()
        if self._extra:
            take = min(n, len(self._extra))
            out.extend(self._extra[:take])
            self._extra = self._extra[take:]
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise RuntimeError("WebSocket EOF")
            out.extend(chunk)
        return bytes(out)

    def _recv_frame(self) -> tuple[int, bytes]:
        b1, b2 = self._read_exact(2)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = bytearray(self._read_exact(length))
        if masked:
            for i in range(length):
                payload[i] ^= mask[i % 4]
        return opcode, bytes(payload)

    def _send_text(self, text: str) -> None:
        data = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        header.extend(mask)
        masked_data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(header) + masked_data)

    def call(self, method: str, params: dict | None = None) -> dict:
        cid = self._next_id
        self._next_id += 1
        self._send_text(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            op, payload = self._recv_frame()
            if op == 8:
                raise RuntimeError("WebSocket closed")
            if op == 9:
                # Pong
                continue
            if op != 1:
                continue
            msg = json.loads(payload.decode("utf-8"))
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP error {method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class WebsitePortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="mavie-web-tests-")
        cls.service = cloud_admin.CloudService(
            Path(cls.temp.name),
            admin_email="admin@mavie.app",
            admin_password="AdminStrongPass!2026",
            admin_gate_key="gate-secret-mavie",
        )
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cloud_admin.make_handler(cls.service))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.temp.cleanup()

    def get(self, path: str, headers: dict | None = None) -> tuple[int, str, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", path, headers=headers or {})
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, {k.lower(): v for k, v in resp.getheaders()}
        finally:
            conn.close()

    def test_1_static_assets_and_rebrand_integrity(self) -> None:
        website = ROOT / "website"
        self.assertFalse((website / "cineva-mark.svg").exists())
        self.assertTrue((website / "mavie-mark.svg").is_file())
        self.assertTrue((website / "icon.svg").is_file())

        for route, ctype_sub, must_have in (
            ("/", "text/html", ("Mavie", "Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa", "Normal", "Mavie Pro")),
            ("/privacy", "text/html", ("Mavie", "privacy@mavie.app")),
            ("/terms", "text/html", ("Mavie", "legal@mavie.app")),
            ("/styles.css", "text/css", (".grid-4", "overflow-x: clip", "prefers-reduced-motion")),
            ("/portal.js", "javascript", ("mavie_user_token", "/api/v1/auth/verify-email", "/api/v1/auth/reset-password", "/api/v1/devices/")),
            ("/mavie-mark.svg", "image/svg+xml", ("mavieGrad",)),
            ("/icon.svg", "image/svg+xml", ("mavieBg", "mavieRing")),
            ("/robots.txt", "text/plain", ("Disallow: /admin",)),
        ):
            code, body, hdrs = self.get(route)
            self.assertEqual(code, 200, route)
            self.assertIn(ctype_sub, hdrs.get("content-type", ""), route)
            for needle in must_have:
                self.assertIn(needle, body, f"{needle} missing in {route}")

        # Public index hides /admin and has zero cineva strings
        _, home_html, _ = self.get("/")
        self.assertNotIn('href="/admin"', home_html)
        self.assertNotIn("cineva", home_html.lower())

    def test_2_admin_portal_assets_and_4_platform_config(self) -> None:
        code_blocked, _, _ = self.get("/admin")
        self.assertEqual(code_blocked, 404)

        code_adm, adm_html, _ = self.get("/admin", headers={"X-Admin-Gate": "gate-secret-mavie"})
        self.assertEqual(code_adm, 200)
        self.assertIn("Mavie Yönetim Paneli", adm_html)
        self.assertIn("MAVIE-", adm_html)
        self.assertIn("cfgMacosUrl", adm_html)
        self.assertIn("cfgIosUrl", adm_html)
        self.assertIn("euVerified", adm_html)
        self.assertNotIn("cineva", adm_html.lower())

        code_js, adm_js, _ = self.get("/admin.js")
        self.assertEqual(code_js, 200)
        self.assertIn("mavie_admin_token", adm_js)
        self.assertIn("trialUsers", adm_js)
        self.assertIn("verifiedUsers", adm_js)
        self.assertNotIn("cineva", adm_js.lower())

    def test_3_headless_chrome_desktop_mobile_layout_and_interactive_flows(self) -> None:
        chrome = _find_chrome()
        if not chrome:
            self.skipTest("Google Chrome binary not available")

        with tempfile.TemporaryDirectory(prefix="mavie-chrome-") as prof_dir:
            proc = subprocess.Popen(
                [
                    chrome,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={prof_dir}",
                    "about:blank",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                debug_port = None
                deadline = time.monotonic() + 10.0
                # Chrome logs DevTools listening URL on stderr
                while time.monotonic() < deadline:
                    line = proc.stderr.readline()
                    if not line:
                        if proc.poll() is not None:
                            break
                        continue
                    m = re.search(r"ws://127\.0\.0\.1:(\d+)/", line)
                    if m:
                        debug_port = int(m.group(1))
                        break
                self.assertIsNotNone(debug_port, "Chrome DevTools port did not appear")

                conn = http.client.HTTPConnection("127.0.0.1", debug_port, timeout=5)
                conn.request("GET", "/json/list")
                targets = json.loads(conn.getresponse().read().decode("utf-8"))
                conn.close()
                ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page")

                cdp = _MinimalCDP(ws_url)
                try:
                    cdp.call("Page.enable")
                    cdp.call("Runtime.enable")
                    cdp.call("Network.enable")

                    for label, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
                        cdp.events.clear()
                        cdp.call("Emulation.setDeviceMetricsOverride", {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": width < 600,
                        })
                        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/"})
                        time.sleep(0.8)

                        res = cdp.call("Runtime.evaluate", {
                            "expression": """(() => {
                                const imgs = [...document.querySelectorAll('img')].map(i => ({
                                    src: i.getAttribute('src'),
                                    ok: i.complete && i.naturalWidth > 0
                                }));
                                const dlBtns = [...document.querySelectorAll('[data-dl]')].map(b => b.dataset.dl);
                                return {
                                    title: document.title,
                                    scrollWidth: document.documentElement.scrollWidth,
                                    innerWidth: window.innerWidth,
                                    overflow: document.documentElement.scrollWidth > window.innerWidth,
                                    imgs,
                                    dlBtns,
                                    hasCinevaText: /cineva/i.test(document.body.innerText || '')
                                };
                            })()""",
                            "returnByValue": True,
                        })
                        val = res["result"]["value"]
                        self.assertFalse(val["overflow"], f"{label} overflow: {val['scrollWidth']} > {val['innerWidth']}")
                        self.assertFalse(val["hasCinevaText"], f"{label} leaked Cineva text")
                        self.assertTrue(all(img["ok"] for img in val["imgs"]), f"{label} broken imgs: {val['imgs']}")
                        self.assertEqual(
                            set(val["dlBtns"]),
                            {"windows-installer", "windows-portable", "android-apk", "macos", "ios"},
                        )

                        # Check zero console exceptions or HTTP >= 400 asset failures
                        exceptions = [e for e in cdp.events if e["method"] == "Runtime.exceptionThrown"]
                        self.assertEqual(exceptions, [], f"{label} JS exceptions: {exceptions}")
                        failed_net = [
                            e for e in cdp.events
                            if e["method"] == "Network.responseReceived"
                            and e["params"]["response"]["status"] >= 400
                        ]
                        self.assertEqual(failed_net, [], f"{label} HTTP >=400 responses: {failed_net}")

                        if label == "mobile":
                            dot_box = cdp.call("Runtime.evaluate", {
                                "expression": "(() => { const r = document.querySelector('.eyebrow .pulse-dot').getBoundingClientRect(); return { w: r.width, h: r.height }; })()",
                                "returnByValue": True,
                            })["result"]["value"]
                            self.assertGreaterEqual(dot_box["w"], 7.9, f"Squished pulse-dot on mobile: {dot_box}")
                            self.assertAlmostEqual(dot_box["w"], dot_box["h"], delta=0.5, msg=f"Non-circular pulse-dot: {dot_box}")

                        # Check /privacy and /terms viewport overflow & zero errors
                        for sub_route in ("/privacy", "/terms"):
                            cdp.events.clear()
                            cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{self.port}{sub_route}"})
                            time.sleep(0.4)
                            sub_val = cdp.call("Runtime.evaluate", {
                                "expression": "({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, overflow: document.documentElement.scrollWidth > window.innerWidth, hasCineva: /cineva/i.test(document.body.innerText || '') })",
                                "returnByValue": True,
                            })["result"]["value"]
                            self.assertFalse(sub_val["overflow"], f"{label} {sub_route} overflow: {sub_val['scrollWidth']} > {sub_val['innerWidth']}")
                            self.assertFalse(sub_val["hasCineva"], f"{label} {sub_route} leaked Cineva")
                            sub_exc = [e for e in cdp.events if e["method"] == "Runtime.exceptionThrown"]
                            self.assertEqual(sub_exc, [], f"{label} {sub_route} JS exceptions: {sub_exc}")

                    # Desktop interactive E2E: check computed CSS visibility of [hidden] elements & full auth flows
                    cdp.call("Emulation.setDeviceMetricsOverride", {
                        "width": 1440,
                        "height": 900,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    })
                    cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/"})
                    time.sleep(0.6)

                    # Login view: #regNameWrap must have computed display === 'none'
                    login_vis = cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('openAccountBtn').click();
                            return {
                                authView: document.getElementById('accountLoggedOut').dataset.authView,
                                regNameDisplay: getComputedStyle(document.getElementById('regNameWrap')).display,
                                tabsDisplay: getComputedStyle(document.getElementById('authViewTabs')).display,
                            };
                        })()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(login_vis["authView"], "login")
                    self.assertEqual(login_vis["regNameDisplay"], "none")
                    self.assertEqual(login_vis["tabsDisplay"], "flex")

                    # Register view -> submit -> verify view (#authViewTabs must have display === 'none')
                    cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('closeAccountModal').click();
                            document.getElementById('heroTrialBtn').click();
                            document.getElementById('uName').value = 'Chrome User';
                            document.getElementById('uEmail').value = 'chrome_e2e@mavie.app';
                            document.getElementById('uPass').value = 'ChromePass123!';
                            document.getElementById('userAuthForm').dispatchEvent(new Event('submit', { cancelable: true }));
                        })()""",
                    })
                    time.sleep(0.5)
                    verify_vis = cdp.call("Runtime.evaluate", {
                        "expression": """(() => ({
                            authView: document.getElementById('accountLoggedOut').dataset.authView,
                            tabsDisplay: getComputedStyle(document.getElementById('authViewTabs')).display,
                            verifyDisplay: getComputedStyle(document.getElementById('verifyEmailPanel')).display,
                        }))()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(verify_vis["authView"], "verify")
                    self.assertEqual(verify_vis["tabsDisplay"], "none")
                    self.assertNotEqual(verify_vis["verifyDisplay"], "none")

                    outbox = json.loads((Path(self.temp.name) / "email_outbox.json").read_text(encoding="utf-8"))
                    code = [m for m in outbox if m["recipient"] == "chrome_e2e@mavie.app" and m["kind"] == "verify_email"][-1]["code"]
                    cdp.call("Runtime.evaluate", {
                        "expression": f"""(() => {{
                            document.getElementById('verifyCodeInput').value = {json.dumps(code)};
                            document.getElementById('verifyEmailForm').dispatchEvent(new Event('submit', {{ cancelable: true }}));
                        }})()""",
                    })
                    time.sleep(0.6)
                    logged_in_state = cdp.call("Runtime.evaluate", {
                        "expression": """(() => ({
                            loggedInVisible: !document.getElementById('accountLoggedIn').hidden,
                            trialVisible: !document.getElementById('uTrialCountdownBox').hidden,
                            trialHtml: document.getElementById('uTrialCountdownBox').innerText,
                            profileHtml: document.getElementById('uProfileSummary').innerText,
                        }))()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertTrue(logged_in_state["loggedInVisible"])
                    self.assertTrue(logged_in_state["trialVisible"])
                    self.assertIn("Pro", logged_in_state["trialHtml"])
                    self.assertIn("E-posta Doğrulandı", logged_in_state["profileHtml"])

                    # Immediate post-verify #uLogoutBtn click must return cleanly to login view
                    post_verify_logout = cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('uLogoutBtn').click();
                            return {
                                authView: document.getElementById('accountLoggedOut').dataset.authView,
                                formDisplay: getComputedStyle(document.getElementById('userAuthForm')).display,
                                verifyDisplay: getComputedStyle(document.getElementById('verifyEmailPanel')).display,
                                regNameDisplay: getComputedStyle(document.getElementById('regNameWrap')).display,
                                celHidden: document.getElementById('uVerifyCelebration').hidden,
                            };
                        })()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(post_verify_logout["authView"], "login")
                    self.assertNotEqual(post_verify_logout["formDisplay"], "none")
                    self.assertEqual(post_verify_logout["verifyDisplay"], "none")
                    self.assertEqual(post_verify_logout["regNameDisplay"], "none")
                    self.assertTrue(post_verify_logout["celHidden"])

                    # Log back in with verified credentials, register device via API, and test self-service removal
                    cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('uEmail').value = 'chrome_e2e@mavie.app';
                            document.getElementById('uPass').value = 'ChromePass123!';
                            document.getElementById('userAuthForm').dispatchEvent(new Event('submit', { cancelable: true }));
                        })()""",
                    })
                    time.sleep(0.5)
                    token = cdp.call("Runtime.evaluate", {
                        "expression": "localStorage.getItem('mavie_user_token')",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertTrue(token and token != "undefined")
                    conn_dev = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                    conn_dev.request(
                        "POST",
                        "/api/v1/devices/register",
                        body=json.dumps({"deviceId": "dev-chrome-1", "deviceName": "Test Mac", "platform": "macos"}),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    )
                    dev_resp = conn_dev.getresponse()
                    dev_resp.read()
                    self.assertEqual(dev_resp.status, 200)
                    conn_dev.close()

                    cdp.call("Runtime.evaluate", {
                        "expression": "document.getElementById('openAccountBtn').click()",
                    })
                    time.sleep(0.4)
                    has_rm_btn = cdp.call("Runtime.evaluate", {
                        "expression": "!!document.querySelector('[data-rm-user-dev=\"dev-chrome-1\"]')",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertTrue(has_rm_btn)
                    cdp.call("Runtime.evaluate", {
                        "expression": "document.querySelector('[data-rm-user-dev=\"dev-chrome-1\"]').click()",
                    })
                    time.sleep(0.4)
                    still_there = cdp.call("Runtime.evaluate", {
                        "expression": "!!document.querySelector('[data-rm-user-dev=\"dev-chrome-1\"]')",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertFalse(still_there)

                    # Logout -> Forgot Password -> Verify tabs hidden -> Reset Password -> Verify tabs hidden -> Login
                    forgot_vis = cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('uLogoutBtn').click();
                            document.getElementById('openForgotBtn').click();
                            const res = {
                                authView: document.getElementById('accountLoggedOut').dataset.authView,
                                tabsDisplay: getComputedStyle(document.getElementById('authViewTabs')).display,
                            };
                            document.getElementById('forgotEmailInput').value = 'chrome_e2e@mavie.app';
                            document.getElementById('forgotPassForm').dispatchEvent(new Event('submit', { cancelable: true }));
                            return res;
                        })()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(forgot_vis["authView"], "forgot")
                    self.assertEqual(forgot_vis["tabsDisplay"], "none")
                    time.sleep(0.5)
                    reset_vis = cdp.call("Runtime.evaluate", {
                        "expression": "({ view: document.getElementById('accountLoggedOut').dataset.authView, tabsDisplay: getComputedStyle(document.getElementById('authViewTabs')).display })",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(reset_vis["view"], "reset")
                    self.assertEqual(reset_vis["tabsDisplay"], "none")

                    outbox2 = json.loads((Path(self.temp.name) / "email_outbox.json").read_text(encoding="utf-8"))
                    reset_code = [m for m in outbox2 if m["recipient"] == "chrome_e2e@mavie.app" and m["kind"] == "password_reset"][-1]["code"]
                    cdp.call("Runtime.evaluate", {
                        "expression": f"""(() => {{
                            document.getElementById('resetCodeInput').value = {json.dumps(reset_code)};
                            document.getElementById('resetNewPassInput').value = 'ChromeNewPass!2026';
                            document.getElementById('resetPassForm').dispatchEvent(new Event('submit', {{ cancelable: true }}));
                        }})()""",
                    })
                    time.sleep(0.5)
                    back_to_login = cdp.call("Runtime.evaluate", {
                        "expression": "({ view: document.getElementById('accountLoggedOut').dataset.authView, msg: document.getElementById('uAuthOk').innerText })",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(back_to_login["view"], "login")
                    self.assertIn("Parolanız güncellendi", back_to_login["msg"])

                    # Admin page before login: #adminLogoutBtn must have computed display === 'none'
                    cdp.events.clear()
                    cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/admin?access=gate-secret-mavie"})
                    time.sleep(0.6)
                    adm_pre = cdp.call("Runtime.evaluate", {
                        "expression": """(() => ({
                            logoutDisplay: getComputedStyle(document.getElementById('adminLogoutBtn')).display,
                            dashboardDisplay: getComputedStyle(document.getElementById('adminDashboard')).display,
                            overflow: document.documentElement.scrollWidth > window.innerWidth,
                        }))()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertEqual(adm_pre["logoutDisplay"], "none")
                    self.assertEqual(adm_pre["dashboardDisplay"], "none")
                    self.assertFalse(adm_pre["overflow"])

                    # Regression: clicking [data-rm-dev] on 403 closes editUserModal cleanly with 0 JS exceptions
                    conn_u = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                    conn_u.request(
                        "POST",
                        "/api/v1/auth/login",
                        body=json.dumps({"email": "chrome_e2e@mavie.app", "password": "ChromeNewPass!2026"}),
                        headers={"Content-Type": "application/json"},
                    )
                    u_login_resp = json.loads(conn_u.getresponse().read().decode("utf-8"))
                    conn_u.close()
                    user_token = u_login_resp["token"]
                    user_id = u_login_resp["user"]["id"]

                    conn_d = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                    conn_d.request(
                        "POST",
                        "/api/v1/devices/register",
                        body=json.dumps({"deviceId": "dev-rm-403", "deviceName": "403 Probe Device", "platform": "macos"}),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {user_token}"},
                    )
                    d_resp = conn_d.getresponse()
                    d_resp.read()
                    self.assertEqual(d_resp.status, 200)
                    conn_d.close()

                    cdp.call("Runtime.evaluate", {
                        "expression": """(() => {
                            document.getElementById('adminEmail').value = 'admin@mavie.app';
                            document.getElementById('adminPassword').value = 'AdminStrongPass!2026';
                            document.getElementById('adminLoginForm').dispatchEvent(new Event('submit', { cancelable: true }));
                        })()""",
                    })
                    time.sleep(0.6)
                    cdp.call("Runtime.evaluate", {
                        "expression": f"document.querySelector('[data-edit-user={json.dumps(user_id)}]').click()",
                    })
                    time.sleep(0.5)
                    rm_ready = cdp.call("Runtime.evaluate", {
                        "expression": "({ modalHidden: document.getElementById('editUserModal').hidden, hasRmBtn: !!document.querySelector('[data-rm-dev=\"dev-rm-403\"]') })",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertFalse(rm_ready["modalHidden"])
                    self.assertTrue(rm_ready["hasRmBtn"])

                    # Swap admin token for non-admin user token -> DELETE /api/v1/admin/... returns 403
                    cdp.events.clear()
                    cdp.call("Runtime.evaluate", {
                        "expression": f"""(() => {{
                            localStorage.setItem('mavie_admin_token', {json.dumps(user_token)});
                            document.querySelector('[data-rm-dev="dev-rm-403"]').click();
                        }})()""",
                    })
                    time.sleep(0.5)
                    rm_403 = cdp.call("Runtime.evaluate", {
                        "expression": """(() => ({
                            editModalHidden: document.getElementById('editUserModal').hidden,
                            editModalDisplay: getComputedStyle(document.getElementById('editUserModal')).display,
                            loginHidden: document.getElementById('adminLoginCard').hidden,
                            dashHidden: document.getElementById('adminDashboard').hidden,
                        }))()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    self.assertTrue(rm_403["editModalHidden"])
                    self.assertEqual(rm_403["editModalDisplay"], "none")
                    self.assertFalse(rm_403["loginHidden"])
                    self.assertTrue(rm_403["dashHidden"])
                    rm_exc = [e for e in cdp.events if e["method"] == "Runtime.exceptionThrown"]
                    self.assertEqual(rm_exc, [], f"Uncaught JS exceptions on [data-rm-dev] 403: {rm_exc}")

                    # Regression: protocol-relative //evil.example/payload.ipa is blocked in startDownload
                    script_id = cdp.call("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """(() => {
                            const origFetch = window.fetch.bind(window);
                            window.fetch = async (url, opts) => {
                                if (typeof url === 'string' && url.endsWith('/api/v1/app-config')) {
                                    return new Response(JSON.stringify({
                                        versions: { iosUrl: '//evil.example/payload.ipa' },
                                        downloads: {},
                                        plans: {},
                                    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
                                }
                                return origFetch(url, opts);
                            };
                        })()""",
                    })["identifier"]
                    cdp.events.clear()
                    cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/"})
                    time.sleep(0.6)
                    cdp.call("Runtime.evaluate", {
                        "expression": "document.querySelector('[data-dl=\"ios\"]').click()",
                    })
                    time.sleep(0.4)
                    proto_res = cdp.call("Runtime.evaluate", {
                        "expression": """(() => ({
                            href: window.location.href,
                            noticeHidden: document.getElementById('downloadNotice').hidden,
                        }))()""",
                        "returnByValue": True,
                    })["result"]["value"]
                    cdp.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": script_id})
                    self.assertEqual(proto_res["href"], f"http://127.0.0.1:{self.port}/")
                    self.assertTrue(proto_res["noticeHidden"])
                    proto_exc = [e for e in cdp.events if e["method"] == "Runtime.exceptionThrown"]
                    self.assertEqual(proto_exc, [], f"JS exceptions during protocol-relative block: {proto_exc}")
                finally:
                    cdp.close()
            finally:
                proc.terminate()
                proc.wait(timeout=5)
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
