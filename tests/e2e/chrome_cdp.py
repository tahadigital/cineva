"""Zero-dependency stdlib Headless Chrome CDP WebSocket client & UI verification helpers.

Drives Google Chrome / Chromium with `--headless=new --remote-debugging-port=0` via a
pure-stdlib RFC 6455 WebSocket client. Gracefully raises unittest.SkipTest if no
Chrome binary is available (or MAVIE_CHROME_BIN points to a missing path).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence
import unittest
import urllib.request


DEFAULT_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def find_chrome_binary() -> str:
    """Locate Chrome/Chromium binary or raise unittest.SkipTest if absent."""
    override = os.environ.get("MAVIE_CHROME_BIN")
    if override is not None:
        if override.strip() and os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        raise unittest.SkipTest(f"MAVIE_CHROME_BIN not executable: {override!r}")

    if os.path.isfile(DEFAULT_MAC_CHROME) and os.access(DEFAULT_MAC_CHROME, os.X_OK):
        return DEFAULT_MAC_CHROME

    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    raise unittest.SkipTest("Google Chrome / Chromium binary not available on host")


class _StdlibWebSocket:
    """Minimal RFC 6455 client supporting 101 WebSocket Protocol Handshake & fragmented frames."""

    def __init__(self, ws_url: str, timeout: float = 15.0) -> None:
        if not ws_url.startswith("ws://"):
            raise ValueError(f"Unsupported WebSocket URL: {ws_url}")
        rest = ws_url[5:]
        host_port, _, path = rest.partition("/")
        path = "/" + path
        host, _, port_str = host_port.partition(":")
        port = int(port_str or "80")

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = bytearray()

        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self.sock.sendall(req)

        raw_hdr = bytearray()
        while b"\r\n\r\n" not in raw_hdr:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket handshake closed prematurely")
            raw_hdr.extend(chunk)
        sep = raw_hdr.index(b"\r\n\r\n")
        head = raw_hdr[:sep].decode("latin-1")
        self._buf.extend(raw_hdr[sep + 4 :])

        lines = head.split("\r\n")
        if " 101 " not in lines[0]:
            raise ConnectionError(f"WebSocket upgrade failed: {lines[0]}")
        hdrs: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1((key + _WS_MAGIC).encode("ascii")).digest()
        ).decode("ascii")
        if hdrs.get("sec-websocket-accept") != expected_accept:
            raise ConnectionError("Invalid Sec-WebSocket-Accept digest")

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise ConnectionError("WebSocket closed while reading frame")
            self._buf.extend(chunk)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | (opcode & 0x0F)])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = secrets.token_bytes(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self) -> str:
        fragments: List[bytes] = []
        while True:
            b1, b2 = self._recv_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask_key = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == 0x8:  # Close
                raise ConnectionError("WebSocket closed by browser")
            if opcode == 0x9:  # Ping -> Pong
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:  # Pong
                continue
            fragments.append(payload)
            if fin:
                return b"".join(fragments).decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class ChromeCdpSession:
    """Context-managed headless Chrome instance controlled via CDP."""

    def __init__(self, width: int = 1440, height: int = 900) -> None:
        self.width = width
        self.height = height
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self._proc: Optional[subprocess.Popen] = None
        self._ws: Optional[_StdlibWebSocket] = None
        self._next_id = 1
        self.console_errors: List[str] = []
        self.page_errors: List[str] = []

    def start(self) -> "ChromeCdpSession":
        chrome_bin = find_chrome_binary()
        self._tmp = tempfile.TemporaryDirectory(prefix="mavie_chrome_", ignore_cleanup_errors=True)
        profile_dir = Path(self._tmp.name)

        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile_dir}",
            f"--window-size={self.width},{self.height}",
        ]
        if os.name == "posix" and os.uname().sysname == "Linux":
            cmd.append("--no-sandbox")
        cmd.append("about:blank")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name == "posix"),
        )

        port_file = profile_dir / "DevToolsActivePort"
        deadline = time.monotonic() + 12.0
        debug_port: Optional[int] = None
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"Chrome exited prematurely ({self._proc.returncode})")
            if port_file.exists():
                lines = port_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                if lines and lines[0].strip().isdigit():
                    debug_port = int(lines[0].strip())
                    break
            time.sleep(0.08)
        if debug_port is None:
            self.stop()
            raise TimeoutError("Chrome DevToolsActivePort did not appear")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ws_url: Optional[str] = None
        while time.monotonic() < deadline:
            try:
                with opener.open(f"http://127.0.0.1:{debug_port}/json/list", timeout=1.0) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                page = next((t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.08)
        if not ws_url:
            self.stop()
            raise TimeoutError("Chrome page WebSocket debugger URL not found")

        self._ws = _StdlibWebSocket(ws_url, timeout=15.0)
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Log.enable")
        self.call("Network.enable")
        self.set_viewport(self.width, self.height, mobile=False)
        return self

    def stop(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None
        if self._proc is not None:
            pid = self._proc.pid
            if self._proc.poll() is None:
                if os.name == "posix":
                    try:
                        os.killpg(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    self._proc.terminate()
                try:
                    self._proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        try:
                            os.killpg(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        self._proc.kill()
                    self._proc.wait(timeout=2)
            elif os.name == "posix":
                # Clean up any lingering renderer/GPU helper in the Chrome process group.
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._proc = None
        if self._tmp is not None:
            tmp_dir = self._tmp.name
            for _ in range(5):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                if not os.path.exists(tmp_dir):
                    break
                time.sleep(0.05)
            self._tmp.cleanup()
            self._tmp = None

    def __enter__(self) -> "ChromeCdpSession":
        return self.start()

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def _record_event(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails") or {}
            text = details.get("text") or ""
            exc = details.get("exception") or {}
            desc = exc.get("description") or exc.get("value") or text
            self.page_errors.append(str(desc))
        elif method == "Runtime.consoleAPICalled":
            if params.get("type") == "error":
                args = params.get("args") or []
                rendered = " ".join(str(a.get("value") or a.get("description") or "") for a in args).strip()
                if rendered:
                    self.console_errors.append(rendered)
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") == "error":
                self.console_errors.append(str(entry.get("text") or ""))

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Chrome CDP session is not connected")
        req_id = self._next_id
        self._next_id += 1
        self._ws.send_text(json.dumps({"id": req_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv_text())
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error on {method}: {msg['error']}")
                return msg.get("result") or {}
            if "method" in msg:
                self._record_event(msg)

    def clear_errors(self) -> None:
        self.console_errors.clear()
        self.page_errors.clear()

    def clear_cookies(self) -> None:
        self.call("Network.clearBrowserCookies")

    def set_viewport(self, width: int, height: int, mobile: bool = False, device_scale_factor: float = 1.0) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": device_scale_factor,
                "mobile": bool(mobile),
            },
        )

    def evaluate(self, expression: str) -> Any:
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in res:
            details = res["exceptionDetails"]
            raise RuntimeError(f"JS evaluation error: {details}")
        return (res.get("result") or {}).get("value")

    def wait_for(self, js_predicate: str, timeout: float = 8.0, interval: float = 0.1) -> Any:
        deadline = time.monotonic() + timeout
        last_val = None
        while time.monotonic() < deadline:
            last_val = self.evaluate(js_predicate)
            if last_val:
                return last_val
            time.sleep(interval)
        raise TimeoutError(f"Timed out waiting for JS condition: {js_predicate!r} (last={last_val!r})")

    def navigate(self, url: str, wait_selector: Optional[str] = "#main", timeout: float = 8.0) -> None:
        self.call("Page.navigate", {"url": url})
        self.wait_for("document.readyState === 'complete'", timeout=timeout)
        if wait_selector:
            self.wait_for(f"Boolean(document.querySelector({json.dumps(wait_selector)}))", timeout=timeout)

    def check_layout(self, expected_width: int, control_selectors: Sequence[str] = ()) -> Dict[str, Any]:
        """Inspect horizontal overflow and non-clipped controls in current viewport."""
        default_selectors = (
            ".topbar",
            ".topbar-brand",
            ".topbar-actions",
            "#searchForm",
            "#profileAvatarBtn",
            ".setup-panel [type='submit']",
            ".settings-actions [type='submit']",
            ".hero-actions .button",
            ".live-card .button",
            ".mobile-nav a",
            ".mobile-nav button",
        )
        selectors = list(control_selectors) if control_selectors else list(default_selectors)
        js = f"""
        (() => {{
          const innerW = window.innerWidth;
          const scrollW = document.documentElement.scrollWidth;
          const isVisible = (el) => {{
            if (!el) return false;
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          }};
          const clipped = [];
          for (const sel of {json.dumps(selectors)}) {{
            for (const el of document.querySelectorAll(sel)) {{
              if (!isVisible(el)) continue;
              const r = el.getBoundingClientRect();
              if (r.left < -1 || r.right > innerW + 1) {{
                clipped.push({{selector: sel, left: r.left, right: r.right, innerW}});
              }}
            }}
          }}
          const stripClipped = [];
          for (const stripSel of ['.topbar-nav', '.rail-strip', '.sports-dates']) {{
            for (const el of document.querySelectorAll(stripSel)) {{
              if (!isVisible(el)) continue;
              const r = el.getBoundingClientRect();
              if (r.left < -1 || r.right > innerW + 1) {{
                stripClipped.push({{selector: stripSel, left: r.left, right: r.right, innerW}});
              }}
            }}
          }}
          return {{
            innerWidth: innerW,
            scrollWidth: scrollW,
            overflow: scrollW > innerW,
            clipped,
            stripClipped,
          }};
        }})()
        """
        data = self.evaluate(js)
        assert isinstance(data, dict)
        if data["innerWidth"] != expected_width:
            raise AssertionError(f"Expected innerWidth={expected_width}, got {data['innerWidth']}")
        return data

    def inspect_liquid_glass(self, selectors: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        js = f"""
        (() => {{
          const out = {{}};
          for (const sel of {json.dumps(list(selectors))}) {{
            const el = document.querySelector(sel);
            if (!el) {{
              out[sel] = {{present: false}};
              continue;
            }}
            const st = getComputedStyle(el);
            out[sel] = {{
              present: true,
              backdrop: st.backdropFilter || st.webkitBackdropFilter || 'none',
              borderTopWidth: st.borderTopWidth,
              borderTopColor: st.borderTopColor,
              borderRadius: st.borderRadius,
              backgroundColor: st.backgroundColor,
              backgroundImage: st.backgroundImage,
              color: st.color,
            }};
          }}
          return out;
        }})()
        """
        return self.evaluate(js)

    def inspect_palette_and_marks(self) -> Dict[str, Any]:
        js = """
        (async () => {
          let launchSvg = document.querySelector('#mavieLaunch svg')?.outerHTML || '';
          if (!launchSvg) {
            try {
              const html = await fetch('/index.html', {cache: 'no-store'}).then(r => r.text());
              const doc = new DOMParser().parseFromString(html, 'text/html');
              launchSvg = doc.querySelector('#mavieLaunch svg')?.outerHTML || '';
            } catch {}
          }
          const topbarImg = document.querySelector('.topbar-brand img');
          const kickerImg = document.querySelector('.cinema-kicker > img');
          const kickerRect = kickerImg ? kickerImg.getBoundingClientRect() : null;
          const legacyColors = [];
          const badRgb = new Set(['rgb(229, 9, 20)', 'rgb(255, 75, 69)', 'rgb(237, 21, 32)']);
          for (const el of document.querySelectorAll('a, button, .badge, .hero, .panel')) {
            const st = getComputedStyle(el);
            if (badRgb.has(st.color) || badRgb.has(st.backgroundColor)) {
              legacyColors.push({tag: el.tagName, cls: el.className, color: st.color, bg: st.backgroundColor});
            }
          }
          return {
            launchSvg,
            topbarImgOk: Boolean(topbarImg && topbarImg.complete && topbarImg.naturalWidth > 0),
            kickerSize: kickerRect ? {width: Math.round(kickerRect.width), height: Math.round(kickerRect.height)} : null,
            legacyColors,
          };
        })()
        """
        return self.evaluate(js)
