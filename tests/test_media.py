"""Server/media integration with local fake upstreams; never contacts IPTV."""

from __future__ import annotations

import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.parse


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from playback import PlaybackManager, find_ffmpeg


class FakeUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    fixture = bytes(range(256)) * 8
    requests = []
    stalled = threading.Event()
    disconnected = threading.Event()
    opening = threading.Event()
    release_headers = threading.Event()

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.__class__.requests.append((self.path, dict(self.headers)))
        name = urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1]
        if name == "101.m3u8":
            content = (
                '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="a",'
                'URI="audio.m3u8?username=demo-user&password=demo-pass"\n'
                '#EXT-X-STREAM-INF:BANDWIDTH=500000,AUDIO="a"\n'
                'child/level.m3u8?password=demo-pass\n'
            ).encode()
            return self.reply(content, "application/vnd.apple.mpegurl")
        if name in {"level.m3u8", "audio.m3u8"}:
            content = (
                '#EXTM3U\n#EXT-X-TARGETDURATION:2\n'
                '#EXT-X-MAP:URI="../init.mp4?password=demo-pass"\n'
                '#EXT-X-KEY:METHOD=AES-128,URI="../key.bin?username=demo-user"\n'
                '#EXTINF:2,\n../seg0.ts?password=demo-pass\n#EXT-X-ENDLIST\n'
            ).encode()
            return self.reply(content, "application/vnd.apple.mpegurl")
        if name == "error.html":
            return self.reply(b'<script>fetch("/api/export")</script>', "text/html")
        if name == "pending.mp4":
            self.__class__.opening.set()
            self.__class__.release_headers.wait(4)
            return self.reply(b"stale-provider-response", "video/mp4")
        if name == "stall.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", "1000000")
            self.end_headers()
            self.wfile.write(b"x")
            self.wfile.flush()
            self.__class__.stalled.set()
            self.connection.settimeout(6)
            try:
                if self.connection.recv(1) == b"":
                    self.__class__.disconnected.set()
            except OSError:
                pass
            self.close_connection = True
            return
        payload = self.fixture if name == "202.mp4" else b"segment-fixture"
        headers = {"Accept-Ranges": "bytes", "ETag": '"fixture"'}
        status = 200
        if self.headers.get("Range"):
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers["Range"])
            if not match:
                return self.reply(b"", "video/mp4", 416)
            start = int(match[1])
            end = min(int(match[2]) if match[2] else len(payload) - 1, len(payload) - 1)
            if start >= len(payload):
                return self.reply(b"", "video/mp4", 416)
            headers["Content-Range"] = f"bytes {start}-{end}/{len(payload)}"
            payload = payload[start:end + 1]
            status = 206
        return self.reply(payload, "video/mp4" if name.endswith(".mp4") else "video/mp2t", status, headers)

    def reply(self, body, content_type, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_dir = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location("_akis_media_test_server", PROJECT / "server.py")
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"AKIS_DATA_DIR": cls.import_dir.name}):
            spec.loader.exec_module(cls.app)
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        cls.upstream.daemon_threads = True
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()
        cls.upstream_base = f"http://127.0.0.1:{cls.upstream.server_port}"
        cls.synthetic = None
        if ffmpeg := find_ffmpeg():
            cls.synthetic = Path(cls.import_dir.name) / "fixture.mp4"
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
                "-f", "lavfi", "-i", "sine=sample_rate=48000",
                "-t", "30", "-c:v", "libx264", "-preset", "ultrafast", "-g", "48",
                "-c:a", "aac", "-movflags", "+faststart", str(cls.synthetic),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.upstream_thread.join(timeout=2)
        cls.import_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app.DATA = Path(self.tmp.name)
        self.app.DB = self.app.DATA / "state.sqlite3"
        self.app.CONFIG_FILE = self.app.DATA / "config.json"
        self.app.initialize()
        self.app.media_sessions.clear()
        self.app.internal_sources.clear()
        FakeUpstream.requests.clear()
        FakeUpstream.stalled.clear()
        FakeUpstream.disconnected.clear()
        FakeUpstream.opening.clear()
        FakeUpstream.release_headers.clear()
        FakeUpstream.fixture = bytes(range(256)) * 8
        self.url_patch = patch.object(self.app, "safe_public_url", side_effect=lambda url: url)
        self.lan_patch = patch.object(self.app, "lan_ips", return_value=[])
        self.url_patch.start()
        self.lan_patch.start()
        self.app.playback = PlaybackManager(self.app.DATA)
        base = self.upstream_base

        class TestProvider:
            configured = True
            config = {"name": "Fixture", "host": base}

            def source(self, row, hls=False):
                extension = "m3u8" if row["kind"] == "live" and hls else "mp4"
                return f'{base}/source/demo-user/demo-pass/{row["provider_id"]}.{extension}'

        self.app.provider = TestProvider()
        with self.app.connect() as db:
            for kind, stream_id in (("live", "101"), ("vod", "202")):
                row = self.app.normalize_item({"stream_id": stream_id, "name": "Fixture", "info": {"duration_secs": 30}}, kind, {})
                db.execute(self.app.UPSERT_ITEM, row)
            db.execute("INSERT INTO devices VALUES(?,?)", (hashlib.sha256(b"fixture-device").hexdigest(), self.app.stamp()))
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.app.Handler)
        self.http.daemon_threads = True
        self.app.HTTP_PORT = self.http.server_port
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.stop_all()
        self.app.playback.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.url_patch.stop()
        self.lan_patch.stop()
        self.tmp.cleanup()

    def request(self, path, method="GET", data=None, headers=None, authorized=True):
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=8)
        request_headers = {"Cookie": "akis_device=fixture-device"} if authorized else {}
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection.request(method, path, json.dumps(data) if data is not None else None, request_headers)
        response = connection.getresponse()
        body = response.read()
        result = (response.status, dict(response.getheaders()), body)
        connection.close()
        return result

    def play(self, kind="vod", mode="direct", start=0):
        code, _, body = self.request("/api/play", "POST", {"id": f"{kind}:{'101' if kind == 'live' else '202'}", "mode": mode, "start": start})
        self.assertEqual(code, 200, body)
        return json.loads(body)

    def assert_private(self, payload):
        if isinstance(payload, bytes):
            payload = payload.decode()
        for secret in ("demo-user", "demo-pass", self.upstream_base):
            self.assertNotIn(secret, payload)

    def test_direct_heartbeat_auth_and_session_replacement(self):
        first = self.play()
        self.assert_private(json.dumps(first))
        code, _, body = self.request(first["url"], authorized=False)
        self.assertEqual(code, 401)
        self.assert_private(body)
        code, _, body = self.request(f'/api/play/{first["sessionId"]}/ping', "POST", {})
        self.assertEqual(code, 200, body)
        second = self.play()
        self.assertNotEqual(first["sessionId"], second["sessionId"])
        self.assertEqual(self.request(first["url"])[0], 410)
        self.assertEqual(len(self.app.media_sessions), 1)

    def test_range_headers_and_partial_body_are_preserved(self):
        playback = self.play()
        code, headers, body = self.request(playback["url"], headers={"Range": "bytes=4-11", "If-Range": '"fixture"'})
        self.assertEqual(code, 206)
        self.assertEqual(body, FakeUpstream.fixture[4:12])
        self.assertEqual(headers.get("Content-Range"), f"bytes 4-11/{len(FakeUpstream.fixture)}")
        self.assertEqual(headers.get("Accept-Ranges"), "bytes")
        self.assertEqual(FakeUpstream.requests[-1][1].get("If-Range"), '"fixture"')
        self.assert_private(json.dumps(headers))
        self.assertEqual(self.request(playback["url"], headers={"Range": "bytes=99999-"})[0], 416)

    def test_hls_nested_manifests_keys_and_maps_use_opaque_routes(self):
        playback = self.play("live")
        code, _, master = self.request(playback["url"])
        self.assertEqual(code, 200)
        self.assert_private(master)
        master_text = master.decode()
        audio = re.search(r'URI="([^"]+)"', master_text)[1]
        variant = next(line for line in master_text.splitlines() if line and not line.startswith("#"))
        for manifest in (audio, variant):
            code, _, media = self.request(manifest)
            self.assertEqual(code, 200)
            self.assert_private(media)
            resources = re.findall(r'URI="([^"]+)"', media.decode())
            resources += [line for line in media.decode().splitlines() if line and not line.startswith("#")]
            self.assertEqual(len(resources), 3)
            for resource in resources:
                self.assertTrue(resource.startswith(f'/media/{playback["sessionId"]}/proxy/'))
                self.assertEqual(self.request(resource)[0], 200)

    def test_switching_title_closes_inflight_upstream_connection(self):
        playback = self.play()
        stalled_url = self.app.resource_for(playback["sessionId"], self.upstream_base + "/stall.mp4")
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=8)
        try:
            connection.request("GET", stalled_url, headers={"Cookie": "akis_device=fixture-device"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(FakeUpstream.stalled.wait(2))
            self.play()
            self.assertTrue(FakeUpstream.disconnected.wait(2), "Previous upstream socket remained open")
        finally:
            connection.close()

    def test_provider_html_is_not_served_as_active_same_origin_content(self):
        playback = self.play()
        url = self.app.resource_for(playback["sessionId"], self.upstream_base + "/error.html")
        code, headers, body = self.request(url)
        self.assertTrue(code >= 400 or "sandbox" in headers.get("Content-Security-Policy", ""))
        if code >= 400:
            self.assertNotIn(b"<script>", body)

    def test_upstream_opening_after_session_stop_is_rejected(self):
        playback = self.play()
        url = self.app.resource_for(playback["sessionId"], self.upstream_base + "/pending.mp4")
        outcome = {}

        def fetch():
            try:
                outcome["response"] = self.request(url)
            except Exception as error:
                outcome["error"] = error

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        try:
            self.assertTrue(FakeUpstream.opening.wait(2))
            self.play()
            FakeUpstream.release_headers.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertNotIn("error", outcome)
            self.assertEqual(outcome["response"][0], 410)
            self.assertNotIn(b"stale-provider-response", outcome["response"][2])
        finally:
            FakeUpstream.release_headers.set()
            thread.join(timeout=5)

    def test_real_remux_uses_internal_proxy_and_returns_private_hls(self):
        if self.synthetic is None:
            self.skipTest("FFmpeg is not installed")
        FakeUpstream.fixture = self.synthetic.read_bytes()
        playback = self.play(mode="remux", start=2)
        self.assertEqual(playback["startOffset"], 2)
        self.assert_private(json.dumps(playback))
        code, _, body = self.request(playback["url"])
        self.assertEqual(code, 200)
        self.assertIn(b"#EXTM3U", body)
        self.assert_private(body)
        segment = next(line for line in body.decode().splitlines() if line and not line.startswith("#"))
        segment_url = playback["url"].rsplit("/", 1)[0] + "/" + segment
        self.assertEqual(self.request(segment_url)[0], 200)
        code, _, body = self.request(f'/api/play/{playback["sessionId"]}/ping', "POST", {})
        self.assertEqual(code, 200, body)
        code, _, body = self.request(f'/api/play/{playback["sessionId"]}/pause', "POST", {"paused": True})
        self.assertEqual(code, 200, body)
        self.assertTrue(self.app.playback._sessions[playback["sessionId"]].paused)
        code, _, body = self.request(f'/api/play/{playback["sessionId"]}/pause', "POST", {"paused": False})
        self.assertEqual(code, 200, body)
        self.assertFalse(self.app.playback._sessions[playback["sessionId"]].paused)
        self.assertEqual(len(self.app.internal_sources), 1)
        self.play()
        self.assertEqual(self.app.internal_sources, {})


if __name__ == "__main__":
    unittest.main()
