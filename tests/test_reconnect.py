"""A short HTTP response must resume by byte range instead of ending a film."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from playback import PlaybackManager, find_ffmpeg


class ReconnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = find_ffmpeg()
        if not cls.ffmpeg: raise unittest.SkipTest("FFmpeg is not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="akis-reconnect-")
        cls.video = Path(cls.temp.name) / "recording.mp4"
        subprocess.run([
            cls.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "90", "-c:v", "libx264", "-preset", "ultrafast", "-g", "48",
            "-keyint_min", "48", "-sc_threshold", "0", "-c:a", "aac",
            "-movflags", "+faststart", str(cls.video),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        cls.payload = cls.video.read_bytes()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"): cls.temp.cleanup()

    def test_truncated_http_response_resumes_range_and_finishes_hls_recording(self):
        payload = self.payload
        break_at = len(payload) // 4
        requests = []
        state = {"broken": False}
        lock = threading.Lock()

        class Source(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_args): pass
            def do_GET(self):
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                start = int(match[1]) if match else 0
                end = min(int(match[2]), len(payload) - 1) if match and match[2] else len(payload) - 1
                if start >= len(payload):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(payload)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                with lock:
                    truncate = not state["broken"] and start == 0
                    if truncate: state["broken"] = True
                    requests.append((start, end, truncate))
                self.send_response(206 if match else 200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if match: self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    self.wfile.write(payload[start:break_at if truncate else end + 1])
                    self.wfile.flush()
                    if truncate:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                except (OSError, BrokenPipeError):
                    pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Source)
        upstream.daemon_threads = True
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory(prefix="akis-reconnect-state-") as tmp:
            manager = PlaybackManager(Path(tmp), self.ffmpeg)
            # Let this finite fixture complete so the assertion can distinguish
            # a recovered connection from merely reaching the prefetch cap.
            manager.PREFETCH_SECONDS = 120
            manager.PREFETCH_RESUME_SECONDS = 90
            try:
                result = manager.start(f"http://127.0.0.1:{upstream.server_port}/opaque-recording", duration=90)
                sid = result["sessionId"]
                session = manager._sessions[sid]
                deadline = time.monotonic() + 10
                while session.process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertIsNotNone(session.process.poll(), "FFmpeg did not finish the recovered file")
                window = manager.ping(sid, 0)
                manifest = manager.get_file(sid, "index.m3u8").read_text()
                self.assertIn("#EXT-X-ENDLIST", manifest)
                self.assertGreater(window["cacheEnd"], 88, manifest)
                self.assertTrue(state["broken"])
                self.assertGreaterEqual(len(requests), 2, requests)
                self.assertTrue(any(start == break_at and not truncated for start, _, truncated in requests), requests)
                last_segment = next(line for line in reversed(manifest.splitlines()) if line and not line.startswith("#"))
                decoded = subprocess.run([
                    self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(manager.get_file(sid, last_segment)),
                    "-frames:v", "1", "-f", "null", "-",
                ], capture_output=True, text=True, timeout=10)
                self.assertEqual(decoded.returncode, 0, decoded.stderr)
                self.assertEqual(session.process.returncode, 0)
            finally:
                manager.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(2)


if __name__ == "__main__":
    unittest.main()
