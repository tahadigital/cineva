"""A paused local decoder must not truncate its provider proxy response."""

from http.client import HTTPConnection
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _TESTS_DIR.parent
for _p in (str(_TESTS_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_codec_playback as codec_fixture


class ProxyPauseTests(unittest.TestCase):
    setUpClass = classmethod(codec_fixture.CodecPlaybackTests.setUpClass.__func__)
    tearDownClass = classmethod(codec_fixture.CodecPlaybackTests.tearDownClass.__func__)
    setUp = codec_fixture.CodecPlaybackTests.setUp
    tearDown = codec_fixture.CodecPlaybackTests.tearDown
    started_playback = staticmethod(codec_fixture.CodecPlaybackTests.started_playback)

    def test_internal_source_survives_downstream_pause_beyond_normal_socket_timeout(self):
        # Scale 35 seconds down to 150 ms. Small socket buffers force a proxy
        # write to block while the decoder intentionally stops reading.
        payload = bytes(range(256)) * 8192
        codec_fixture.PlaybackSourceFixture.hevc = payload
        token = "paused-decoder-fixture"
        self.app.internal_sources[token] = {"url": f"http://127.0.0.1:{self.upstream.server_port}/hevc.mkv", "touched": time.monotonic()}
        original_setup, original_proxy = self.app.Handler.setup, self.app.Handler.proxy
        observed_timeouts = []

        def short_setup(handler):
            original_setup(handler)
            handler.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
            handler.connection.settimeout(0.15)

        def tracked_proxy(handler, *args, **kwargs):
            observed_timeouts.append(handler.connection.gettimeout())
            return original_proxy(handler, *args, **kwargs)

        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        try:
            connection.connect()
            connection.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8192)
            with patch.object(self.app.Handler, "setup", short_setup), patch.object(self.app.Handler, "proxy", tracked_proxy):
                connection.request("GET", "/internal/source/" + token)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(observed_timeouts, [None])
                time.sleep(0.65)
                received = response.read()
                self.assertEqual(len(received), len(payload))
                self.assertEqual(received, payload)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
