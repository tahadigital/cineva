"""Regression checks for bounded VOD prefetch and long-GOP startup latency."""

from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from playback import PlaybackManager, _Session, find_ffmpeg


class BufferingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = find_ffmpeg()
        if not cls.ffmpeg:
            raise unittest.SkipTest("FFmpeg is not installed")
        cls.fixture_dir = tempfile.TemporaryDirectory()
        cls.video = Path(cls.fixture_dir.name) / "long-gop.mp4"
        subprocess.run([
            cls.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "360", "-c:v", "libx264", "-preset", "ultrafast",
            "-g", "240", "-keyint_min", "240", "-sc_threshold", "0",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.video),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "fixture_dir"):
            cls.fixture_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.manager = PlaybackManager(Path(self.directory.name), self.ffmpeg)

    def tearDown(self):
        self.manager.close()
        self.directory.cleanup()

    def wait_for(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.025)
        self.fail("Timed out waiting for the prefetch controller")

    def test_long_gop_starts_without_real_time_wait(self):
        began = time.monotonic()
        result = self.manager.start(str(self.video), duration=360)
        elapsed = time.monotonic() - began
        self.assertLess(elapsed, 8.0, f"Long-GOP startup took {elapsed:.2f}s")
        self.assertGreaterEqual(result["cacheEnd"], 10)
        self.assertEqual(result["startOffset"], 0)
        self.assertEqual(result["cacheStart"], 0)
        command = self.manager._command(str(self.video), Path(self.directory.name), "remux", 0, False)
        self.assertNotIn("-re", command)
        self.assertNotIn("-readrate_initial_burst", command)
        self.assertEqual(command[command.index("-hls_list_size") + 1], "64")

    def test_prefetch_stops_and_refills_when_consumer_advances(self):
        result = self.manager.start(str(self.video), duration=360)
        sid = result["sessionId"]
        session = self.manager._sessions[sid]
        self.wait_for(lambda: session.flow_paused and session.process_paused)
        first_end = self.manager.ping(sid, 0)["cacheEnd"]
        self.assertGreaterEqual(first_end, self.manager.PREFETCH_SECONDS)
        self.assertLess(first_end, 150)
        time.sleep(0.2)  # Allow an in-flight atomic manifest rename to finish.
        stopped_end = self.manager.ping(sid)["cacheEnd"]
        time.sleep(0.25)
        self.assertEqual(self.manager.ping(sid)["cacheEnd"], stopped_end)
        self.manager.ping(sid, stopped_end - self.manager.PREFETCH_RESUME_SECONDS)
        self.wait_for(lambda: session.cache_end > stopped_end)
        self.wait_for(lambda: session.flow_paused and session.process_paused)
        self.assertIsNone(session.process.poll())

    def test_user_pause_is_not_released_by_prefetch_resume(self):
        result = self.manager.start(str(self.video), duration=360)
        sid = result["sessionId"]
        session = self.manager._sessions[sid]
        self.wait_for(lambda: session.flow_paused)
        self.manager.pause(sid, True)
        self.manager.ping(sid, session.cache_end)
        self.assertFalse(session.flow_paused)
        self.assertTrue(session.paused)
        self.assertTrue(session.process_paused)
        time.sleep(0.2)
        frozen = session.cache_end
        self.manager.pause(sid, False)
        self.wait_for(lambda: session.cache_end > frozen)
        self.assertFalse(session.paused)

    def test_rolling_manifest_keeps_session_relative_time(self):
        class Process:
            def __init__(self): self.signals = []
            def poll(self): return None
            def send_signal(self, value): self.signals.append(value)

        directory = Path(self.directory.name)
        process = Process()
        session = _Session("test", directory, process, time.monotonic())
        manifest = directory / "index.m3u8"
        manifest.write_text("#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:3,\na.ts\n#EXTINF:5,\nb.ts\n")
        self.manager._update_buffer(session)
        self.assertEqual((session.cache_start, session.cache_end), (0, 8))
        manifest.write_text("#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:1\n#EXTINF:5,\nb.ts\n#EXTINF:2,\nc.ts\n")
        self.manager._update_buffer(session)
        self.assertEqual((session.cache_start, session.cache_end), (3, 10))
        self.manager._update_buffer(session)
        self.assertEqual((session.cache_start, session.cache_end), (3, 10))
        live_command = self.manager._command("local", directory, "remux", 0, True)
        self.assertIn("-re", live_command)
        self.assertEqual(live_command[live_command.index("-hls_list_size") + 1], "8")

    def test_ready_uses_duration_and_accepts_completed_short_clip(self):
        directory = Path(self.directory.name)
        (directory / "seg_000000000.ts").write_bytes(b"segment")
        manifest = directory / "index.m3u8"
        manifest.write_text("#EXTM3U\n#EXTINF:10,\nseg_000000000.ts\n")
        self.assertTrue(self.manager._ready(manifest, directory, minimum_duration=4))
        manifest.write_text("#EXTM3U\n#EXTINF:2,\nseg_000000000.ts\n")
        self.assertFalse(self.manager._ready(manifest, directory, minimum_duration=4))
        manifest.write_text(manifest.read_text() + "#EXT-X-ENDLIST\n")
        self.assertTrue(self.manager._ready(manifest, directory, minimum_duration=4))


if __name__ == "__main__":
    unittest.main()
