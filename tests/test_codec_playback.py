"""Codec fallback regressions using only temporary state and local fixtures."""

from __future__ import annotations

import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.parse


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from playback import PlaybackManager, find_ffmpeg


class PlaybackSourceFixture(BaseHTTPRequestHandler):
    """A provider that returns a zero-byte recording or an HTML error page."""

    hevc = b""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        body = self.hevc if self.path == "/hevc.mkv" else (b"<html>Recording unavailable</html>" if self.path == "/error.html" else b"")
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/error.html" else "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CodecPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_temp = tempfile.TemporaryDirectory(prefix="akis-codec-import-")
        spec = importlib.util.spec_from_file_location("_akis_codec_test_server", PROJECT / "server.py")
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"AKIS_DATA_DIR": cls.import_temp.name}):
            spec.loader.exec_module(cls.app)
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), PlaybackSourceFixture)
        cls.upstream.daemon_threads = True
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.upstream_thread.join(timeout=2)
        cls.import_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="akis-codec-state-")
        self.app.DATA = Path(self.temp.name)
        self.app.DB = self.app.DATA / "state.sqlite3"
        self.app.CONFIG_FILE = self.app.DATA / "config.json"
        self.app.initialize()
        self.app.media_sessions.clear()
        self.app.internal_sources.clear()
        PlaybackSourceFixture.hevc = b""
        self.app.playback = Mock(available=True)
        self.app.playback.start.side_effect = self.started_playback
        self.app.provider = Mock(configured=True, config={"name": "Fixture", "host": ""})
        self.app.provider.source.return_value = f"http://127.0.0.1:{self.upstream.server_port}/empty.mp4"
        self.app.provider.api.side_effect = AssertionError("A fixture must never contact the IPTV provider")
        self.url_patch = patch.object(self.app, "safe_public_url", side_effect=lambda url: url)
        self.lan_patch = patch.object(self.app, "lan_ips", return_value=[])
        self.url_patch.start()
        self.lan_patch.start()
        with self.app.connect() as db:
            db.execute("INSERT INTO devices VALUES(?,?)", (hashlib.sha256(b"codec-device").hexdigest(), self.app.stamp()))
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.app.Handler)
        self.http.daemon_threads = True
        self.app.HTTP_PORT = self.http.server_port
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.stop_all()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.url_patch.stop()
        self.lan_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def started_playback(_source, *, mode, start, duration, live):
        return {"sessionId": "a" * 32, "url": "/media/fixture/index.m3u8", "type": "hls", "startOffset": start, "duration": duration}

    def episode(self, video=None, pixel_format=None, audio="aac"):
        info = {"duration_secs": 1800}
        if video is not None or pixel_format is not None:
            info["video"] = {"codec_name": video, "pix_fmt": pixel_format}
        if audio is not None:
            info["audio"] = {"codec_name": audio}
        row = self.app.normalize_item({"id": "303", "title": "Codec fixture", "info": info}, "episode", {})
        with self.app.connect() as db:
            db.execute(self.app.UPSERT_ITEM, row)
        return "episode:303"

    def request_play(self, iid, mode="remux"):
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            connection.request("POST", "/api/play", json.dumps({"id": iid, "mode": mode, "start": 125}), {
                "Content-Type": "application/json", "Cookie": "akis_device=codec-device",
            })
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_episode_codec_metadata_is_normalized_and_exposed(self):
        iid = self.episode("hevc", "yuv420p10le", "ac3")
        row = self.app.get_row(iid)
        extra = json.loads(row["extra"])
        item = self.app.item_json(row)
        for key, expected in (("videoCodec", "hevc"), ("audioCodec", "ac3"), ("pixelFormat", "yuv420p10le")):
            self.assertEqual(extra[key], expected)
            self.assertEqual(item[key], expected)

    def test_hevc_remux_request_transcodes_and_reports_actual_mode(self):
        status, result = self.request_play(self.episode("hevc", "yuv420p10le"))
        self.assertEqual(status, 200, result)
        self.assertEqual(self.app.playback.start.call_args.kwargs["mode"], "transcode")
        self.assertEqual(self.app.playback.start.call_args.kwargs["start"], 125)
        self.assertEqual(result["mode"], "transcode")
        self.assertEqual(result["duration"], 1800)
        self.assertEqual(len(self.app.internal_sources), 1)

    def test_next_episode_follows_numeric_seasons_and_does_not_wrap(self):
        self.app.playback.probe.return_value = {"scanned": True, "audio": [], "subtitles": []}
        series = self.app.normalize_item({"series_id": "s", "name": "Fixture series"}, "series", {})
        with self.app.connect() as db:
            db.execute(self.app.UPSERT_ITEM, series)
        parent = self.app.get_row("series:s")
        with self.app.connect() as db:
            for identifier, season, number in (("first", 2, 9), ("second", 2, 10), ("third", 10, 1)):
                data = {"id": identifier, "season": season, "episode_num": number,
                        "info": {"duration_secs": 1800, "video": {"codec_name": "h264"}}}
                db.execute(self.app.UPSERT_ITEM, self.app.normalize_item(data, "episode", {}, parent))
        self.assertEqual(self.request_play("episode:first")[1]["nextEpisode"]["id"], "episode:second")
        self.assertEqual(self.request_play("episode:second")[1]["nextEpisode"]["id"], "episode:third")
        self.assertNotIn("nextEpisode", self.request_play("episode:third")[1])

    def test_play_start_and_progress_retain_the_full_media_duration(self):
        self.app.playback.probe.return_value = {"scanned": True, "audio": [], "subtitles": [], "duration": 700000}
        iid = self.episode("h264", "yuv420p")
        result = self.app.play_item(iid, "remux", 650000)
        self.assertEqual(result["duration"], 700000)
        self.assertEqual(result["startOffset"], 650000)
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            connection.request("POST", "/api/progress", json.dumps({"id": iid, "sessionId": result["sessionId"],
                               "position": 650000, "duration": 700000}),
                               {"Content-Type": "application/json", "Cookie": "akis_device=codec-device"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()
        progress = self.app.item_json(self.app.get_row(iid))["progress"]
        self.assertEqual((progress["position"], progress["duration"]), (650000, 700000))

    def test_unsupported_video_codec_and_pixel_format_transcode(self):
        for codec, pixel_format in (("mpeg4", "yuv420p"), ("h264", "yuv420p10le"), ("h264", "yuv422p")):
            with self.subTest(codec=codec, pixel_format=pixel_format):
                iid = self.episode(codec, pixel_format)
                result = self.app.play_item(iid, "remux", 0)
                self.assertEqual(self.app.playback.start.call_args.kwargs["mode"], "transcode")
                self.assertEqual(result["mode"], "transcode")

    def test_h264_and_unknown_video_codec_keep_remux(self):
        for codec, pixel_format in (("h264", "yuv420p"), ("avc", "yuvj420p"), ("avc1", "nv12"), (None, None), ("", "")):
            with self.subTest(codec=codec, pixel_format=pixel_format):
                iid = self.episode(codec, pixel_format)
                result = self.app.play_item(iid, "remux", 0)
                self.assertEqual(self.app.playback.start.call_args.kwargs["mode"], "remux")
                self.assertEqual(result["mode"], "remux")

    def test_direct_mode_is_retained_for_an_explicit_request(self):
        result = self.app.play_item(self.episode("hevc", "yuv420p10le"), "direct", 0)
        self.assertEqual(result["mode"], "direct")
        self.app.playback.start.assert_not_called()

    def test_playback_start_failure_removes_internal_source(self):
        self.app.playback.start.side_effect = RuntimeError("Fixture startup failed")
        with self.assertRaises(RuntimeError):
            self.app.play_item(self.episode("h264", "yuv420p"), "remux", 0)
        self.assertEqual(self.app.internal_sources, {})
        self.assertEqual(self.app.media_sessions, {})

    def consume_internal_source_and_fail(self, source, **_kwargs):
        parsed = urllib.parse.urlsplit(source)
        connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        try:
            connection.request("GET", parsed.path)
            response = connection.getresponse()
            self.assertEqual(response.status, 502)
            response.read()
        finally:
            connection.close()
        raise RuntimeError("Generic playback startup failure")

    def test_empty_upstream_reports_provider_error_and_actual_mode(self):
        self.app.playback.start.side_effect = self.consume_internal_source_and_fail
        status, result = self.request_play(self.episode("hevc", "yuv420p10le"))
        self.assertEqual(status, 502, result)
        self.assertEqual(result["code"], "upstream_empty")
        self.assertEqual(result["mode"], "transcode")
        self.assertNotEqual(result["error"], "Generic playback startup failure")
        self.assertEqual(self.app.internal_sources, {})
        self.assertEqual(self.app.media_sessions, {})

    def test_html_upstream_error_is_not_treated_as_a_codec_failure(self):
        self.app.provider.source.return_value = f"http://127.0.0.1:{self.upstream.server_port}/error.html"
        self.app.playback.start.side_effect = self.consume_internal_source_and_fail
        status, result = self.request_play(self.episode("h264", "yuv420p"))
        self.assertEqual(status, 502, result)
        self.assertEqual(result["code"], "upstream_unavailable")
        self.assertEqual(result["mode"], "remux")
        self.assertNotIn("<html>", result["error"])
        self.assertEqual(self.app.internal_sources, {})

    def test_synthetic_hevc_10bit_is_transcoded_to_playable_h264(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.skipTest("FFmpeg is not installed")
        encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10)
        if "libx265" not in encoders.stdout:
            self.skipTest("The local FFmpeg does not include the HEVC fixture encoder")
        fixture = self.app.DATA / "hevc-fixture.mkv"
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            "testsrc2=size=160x90:rate=12", "-t", "10", "-c:v", "libx265", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p10le", "-x265-params", "pools=1:frame-threads=1:log-level=error:keyint=24",
            str(fixture),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        PlaybackSourceFixture.hevc = fixture.read_bytes()
        self.app.provider.source.return_value = f"http://127.0.0.1:{self.upstream.server_port}/hevc.mkv"
        manager = PlaybackManager(self.app.DATA, ffmpeg)
        self.app.playback = manager
        try:
            result = self.app.play_item(self.episode("hevc", "yuv420p10le", audio=None), "remux", 0)
            self.assertEqual(result["mode"], "transcode")
            playlist = manager.get_file(result["sessionId"], "index.m3u8").read_text()
            segment = next(line for line in playlist.splitlines() if line and not line.startswith("#"))
            decoded = subprocess.run([
                ffmpeg, "-hide_banner", "-i", str(manager.get_file(result["sessionId"], segment)),
                "-frames:v", "1", "-f", "null", "-",
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            self.assertIn("Video: h264", decoded.stderr)
            self.assertIn("yuv420p", decoded.stderr)
            self.assertNotIn("yuv420p10le", decoded.stderr)
        finally:
            self.app.stop_all()
            manager.close()


if __name__ == "__main__":
    unittest.main()
