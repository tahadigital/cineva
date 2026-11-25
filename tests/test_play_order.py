"""Concurrent seek requests must leave the newest requested content active."""

from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _TESTS_DIR.parent
for _p in (str(_TESTS_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_codec_playback as codec_fixture
from playback import PlaybackManager, find_ffmpeg


class PlayOrderTests(unittest.TestCase):
    # Reuse the isolated HTTP/provider fixture without rediscovering its tests.
    setUpClass = classmethod(codec_fixture.CodecPlaybackTests.setUpClass.__func__)
    tearDownClass = classmethod(codec_fixture.CodecPlaybackTests.tearDownClass.__func__)
    tearDown = codec_fixture.CodecPlaybackTests.tearDown
    episode = codec_fixture.CodecPlaybackTests.episode
    started_playback = staticmethod(codec_fixture.CodecPlaybackTests.started_playback)

    def setUp(self):
        codec_fixture.CodecPlaybackTests.setUp(self)
        self.app.play_clients.clear()
        self.app.latest_play_request = 0
        self.app.playback.probe.return_value = {"scanned": True, "audio": [], "subtitles": []}

    def request(self, path, data):
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        try:
            connection.request("POST", path, json.dumps(data), {
                "Content-Type": "application/json", "Cookie": "akis_device=codec-device",
            })
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    @staticmethod
    def options(generation):
        return {"clientId": "play-order-fixture", "generation": generation}

    def run_play(self, results, key, iid, start, generation):
        try:
            results[key] = self.app.play_item(iid, "remux", start, self.options(generation))
        except Exception as error:
            results[key] = error

    def assert_superseded(self, result):
        self.assertIsInstance(result, self.app.PlaybackError)
        self.assertEqual(result.code, "superseded")

    def test_late_generation_returns_http409_without_stopping_new_playback(self):
        iid = self.episode("h264", "yuv420p")
        with patch.object(self.app, "stop_all", wraps=self.app.stop_all) as stop:
            code, current = self.request("/api/play", {"id": iid, "mode": "remux", "start": 100, **self.options(2)})
            self.assertEqual(code, 200, current)
            sid = current["sessionId"]
            code, late = self.request("/api/play", {"id": iid, "mode": "remux", "start": 10, **self.options(1)})
            self.assertEqual(code, 409, late)
            self.assertEqual(late["code"], "superseded")
            self.assertEqual(stop.call_count, 1)
            self.assertEqual(self.app.playback.start.call_count, 1)
            self.assertIn(sid, self.app.media_sessions)

    def test_metadata_delayed_old_request_cannot_replace_new_content(self):
        row = self.app.normalize_item({"stream_id": "304", "name": "Delayed metadata", "container_extension": "mkv"}, "vod", {})
        with self.app.connect() as db:
            db.execute(self.app.UPSERT_ITEM, row)
        old_iid, new_iid = "vod:304", self.episode("h264", "yuv420p")
        entered, release = threading.Event(), threading.Event()
        results = {}

        def delayed_detail(_iid):
            entered.set()
            if not release.wait(5): raise RuntimeError("Fixture metadata timeout")

        with patch.object(self.app, "detail", side_effect=delayed_detail), patch.object(self.app, "stop_all", wraps=self.app.stop_all) as stop:
            old = threading.Thread(target=self.run_play, args=(results, "old", old_iid, 10, 1))
            old.start()
            try:
                self.assertTrue(entered.wait(3))
                results["new"] = self.app.play_item(new_iid, "remux", 90, self.options(2))
            finally:
                release.set()
                old.join(5)
            self.assertFalse(old.is_alive())
            self.assert_superseded(results["old"])
            self.assertEqual(stop.call_count, 1)
            self.assertEqual(self.app.playback.start.call_count, 1)
            self.assertEqual(self.app.media_sessions[results["new"]["sessionId"]]["item"], new_iid)

    def test_probe_delayed_old_request_does_not_start_after_new_request_arrives(self):
        iid = self.episode("h264", "yuv420p")
        entered, release, registered = threading.Event(), threading.Event(), threading.Event()
        results = {}
        original_register = self.app.register_play_request

        def register(options):
            request = original_register(options)
            if options.get("generation") == 2: registered.set()
            return request

        def delayed_probe(_source):
            entered.set()
            if not release.wait(5): raise RuntimeError("Fixture probe timeout")
            return {"scanned": True, "audio": [], "subtitles": []}

        self.app.playback.probe.side_effect = delayed_probe
        with patch.object(self.app, "register_play_request", side_effect=register):
            old = threading.Thread(target=self.run_play, args=(results, "old", iid, 10, 1))
            new = threading.Thread(target=self.run_play, args=(results, "new", iid, 90, 2))
            old.start()
            try:
                self.assertTrue(entered.wait(3))
                new.start()
                self.assertTrue(registered.wait(3))
            finally:
                release.set()
                old.join(5)
                if new.ident is not None: new.join(5)
            self.assertFalse(old.is_alive())
            self.assertFalse(new.is_alive())
        self.assert_superseded(results["old"])
        self.assertIsInstance(results["new"], dict)
        self.assertEqual(self.app.playback.start.call_count, 1)
        self.assertEqual(self.app.playback.start.call_args.kwargs["start"], 90)
        self.assertEqual(len(self.app.internal_sources), 1)

    def test_superseded_ffmpeg_start_is_stopped_before_new_session_is_published(self):
        iid = self.episode("h264", "yuv420p")
        entered, release, registered = threading.Event(), threading.Event(), threading.Event()
        results = {}
        original_register = self.app.register_play_request

        def register(options):
            request = original_register(options)
            if options.get("generation") == 2: registered.set()
            return request

        def start(_source, **kwargs):
            sid = "a" * 32 if kwargs["start"] == 10 else "b" * 32
            if kwargs["start"] == 10:
                entered.set()
                if not release.wait(5): raise RuntimeError("Fixture start timeout")
            return {"sessionId": sid, "url": "/media/fixture/index.m3u8", "type": "hls", "startOffset": kwargs["start"], "duration": kwargs["duration"]}

        self.app.playback.start.side_effect = start
        with patch.object(self.app, "register_play_request", side_effect=register):
            old = threading.Thread(target=self.run_play, args=(results, "old", iid, 10, 1))
            new = threading.Thread(target=self.run_play, args=(results, "new", iid, 90, 2))
            old.start()
            try:
                self.assertTrue(entered.wait(3))
                new.start()
                self.assertTrue(registered.wait(3))
            finally:
                release.set()
                old.join(5)
                if new.ident is not None: new.join(5)
        self.assert_superseded(results["old"])
        self.assertIsInstance(results["new"], dict)
        self.app.playback.stop.assert_any_call("a" * 32)
        self.assertEqual(set(self.app.media_sessions), {"b" * 32})
        self.assertEqual(len(self.app.internal_sources), 1)

    def test_malformed_ordering_is_rejected_before_current_session_is_stopped(self):
        iid = self.episode("h264", "yuv420p")
        with patch.object(self.app, "stop_all", wraps=self.app.stop_all) as stop:
            for options in ({"clientId": "short", "generation": 1}, {"clientId": "play-order-fixture", "generation": True}, {"clientId": "play-order-fixture", "generation": 0}, {"generation": 1}):
                with self.subTest(options=options):
                    code, result = self.request("/api/play", {"id": iid, "mode": "remux", **options})
                    self.assertEqual(code, 400, result)
            stop.assert_not_called()
            self.app.playback.start.assert_not_called()

    def test_ping_accepts_relative_finite_position_and_rejects_invalid_positions(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg: self.skipTest("FFmpeg is not installed")
        fixture = Path(self.temp.name) / "ping-fixture.mp4"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=navy:s=160x90:r=12:d=10", "-c:v", "libx264", "-g", "24", str(fixture)], check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        manager = PlaybackManager(self.app.DATA, ffmpeg)
        self.app.playback = manager
        try:
            result = manager.start(str(fixture), duration=10)
            sid = result["sessionId"]
            self.app.media_sessions[sid] = {"sourceToken": "fixture", "item": "episode:303", "touched": 0}
            code, window = self.request(f"/api/play/{sid}/ping", {"position": 1.25})
            self.assertEqual(code, 200, window)
            self.assertGreaterEqual(window["cacheEnd"], 4)
            self.assertAlmostEqual(window["bufferAhead"], window["cacheEnd"] - 1.25, places=2)
            self.assertEqual(self.request(f"/api/play/{sid}/ping", {})[0], 200)
            for value in (-1, True, float("nan"), float("inf"), "bad", []):
                with self.subTest(value=value):
                    self.assertEqual(self.request(f"/api/play/{sid}/ping", {"position": value})[0], 400)
            self.assertEqual(manager._sessions[sid].position, 1.25)
        finally:
            self.app.stop_all()
            manager.close()


if __name__ == "__main__":
    unittest.main()
