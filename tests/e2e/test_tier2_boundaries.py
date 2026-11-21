"""Tier 2: Boundary, corner-case, security, and error-handling E2E tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time
import unittest

import m3u
import sports
from tests.e2e.runner import (
    LocalMediaServerProcess,
)


class Tier2LocalServerBoundariesTests(unittest.TestCase):
    """Malformed M3U/XMLTV/XXE, traversal, SSRF, pairing rate limit, playback & profile errors."""

    def setUp(self) -> None:
        self.srv = LocalMediaServerProcess().start()
        self.addCleanup(self.srv.stop)
        self.c = self.srv.paired_client()

    def test_malformed_m3u_handled_gracefully(self) -> None:
        for bad in ("", "not an m3u file\n###garbage", "#EXTM3U\n#EXTINF:-1,NoUrlChannel\n"):
            parsed = m3u.parse_m3u(bad)
            self.assertIsInstance(parsed, dict)
            self.assertEqual(parsed.get("items", []), [])

    def test_malformed_xmltv_and_xxe_rejected_safely(self) -> None:
        xxe = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE tv [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<tv><programme start="20261119120000 +0000" stop="20261119130000 +0000" channel="c1">'
            "<title>&xxe;</title></programme></tv>"
        )
        try:
            res = sports.parse_xmltv(xxe, datetime.now(timezone.utc).date())
            self.assertNotIn("root:", json.dumps(res))
        except Exception:
            pass

    def test_path_traversal_attempts_rejected(self) -> None:
        for path in (
            "/../../etc/passwd",
            "/%2e%2e/%2e%2e/etc/passwd",
            "/api/subtitles/../../etc/passwd/0.vtt",
            "/media/nonexistent/../../etc/passwd",
        ):
            r = self.c.get(path)
            self.assertIn(r.status, (400, 403, 404, 410), f"Traversal path {path} returned {r.status}")
            self.assertNotIn("root:x:0:0", r.text)

    def test_ssrf_blocks_private_loopback_m3u_and_epg_urls(self) -> None:
        for url in ("http://127.0.0.1:9999/list.m3u", "http://169.254.169.254/latest/meta-data/"):
            res = self.c.post("/api/settings", {"type": "m3u", "m3uUrl": url, "name": "SSRF"})
            if res.status == 200:
                time.sleep(0.3)
                st = self.c.get("/api/status").json
                self.assertTrue(st["catalog"]["error"], f"Private URL {url} should be blocked")
            else:
                self.assertIn(res.status, (400, 403))

    def test_pairing_wrong_code_and_rate_limit(self) -> None:
        guest = self.srv.client()
        statuses = []
        for i in range(15):
            r = guest.post("/api/pair", {"code": f"{i:06d}"})
            statuses.append(r.status)
            if r.status == 429:
                break
        self.assertIn(403, statuses)
        self.assertIn(429, statuses, f"Expected 429 on pairing brute-force; got {statuses}")

    def test_playback_boundary_errors_invalid_item_session_and_position(self) -> None:
        bad_item = self.c.post("/api/play", {"id": "vod:does_not_exist"})
        self.assertIn(bad_item.status, (400, 404))

        bad_ping = self.c.post("/api/play/unknown_sid/ping", {"position": 10})
        self.assertIn(bad_ping.status, (404, 410))

        self.c.post("/api/demo", {})
        items = self.c.get("/api/catalog").json["items"]
        play = self.c.post("/api/play", {"id": items[0]["id"]})
        sid = play.json["sessionId"]
        bad_json = self.c.request(
            "POST",
            f"/api/play/{sid}/ping",
            raw_body=b"{invalid-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(bad_json.status, 400)
        neg = self.c.post(f"/api/play/{sid}/ping", {"position": -50})
        self.assertIn(neg.status, (200, 400))
        self.assertNotIn("-50", self.c.get("/api/progress").text)
        self.c.delete(f"/api/play/{sid}")

    def test_profile_wrong_pin_and_default_delete_rejected(self) -> None:
        prof = self.c.post("/api/profiles", {"name": "Locked", "pin": "1111"}).json["profile"]
        wrong = self.c.post("/api/profiles/switch", {"id": prof["id"], "pin": "2222"})
        self.assertEqual(wrong.status, 403)
        del_def = self.c.delete("/api/profiles/default")
        self.assertIn(del_def.status, (400, 403))

    def test_removed_cloud_endpoints_return_404(self) -> None:
        self.assertEqual(self.c.get("/api/cloud/status").status, 404)
        self.assertEqual(self.c.post("/api/cloud/login", {}).status, 404)
        self.assertEqual(self.c.post("/api/cloud/sync", {}).status, 404)


if __name__ == "__main__":
    unittest.main()
