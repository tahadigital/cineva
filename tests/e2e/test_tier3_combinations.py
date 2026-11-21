"""Tier 3: Cross-feature pairwise & multi-component integration E2E tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest

import sports
from tests.e2e.runner import (
    LocalMediaServerProcess,
    REPO_ROOT,
)


class Tier3CrossFeatureCombinationsTests(unittest.TestCase):
    """Cross-feature integration across Local Server, Profiles/PIN, EPG, LAN Pairing, Backup & Website."""

    def test_local_server_kid_profile_pin_epg_playback_export_import(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        with tempfile.TemporaryDirectory(prefix="mavie_combo_") as media_dir:
            mp = Path(media_dir)
            (mp / "Spor").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Spor" / "TRT.Spor.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"SPORT" * 16)
            (mp / "Korku +18" / "Yetiskin.Gerilim.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HORROR" * 16)
            self.assertEqual(c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Combo"}).status, 200)
            cat_items = []
            for _ in range(40):
                st = c.get("/api/status").json or {}
                cat_items = (c.get("/api/catalog").json or {}).get("items", [])
                if len(cat_items) >= 2 and not st.get("catalog", {}).get("syncing"):
                    break
                time.sleep(0.1)
            self.assertEqual(len(cat_items), 2)
            sport_item = next(i for i in cat_items if "TRT Spor" in i["name"])
            c.post("/api/favorites", {"id": sport_item["id"], "favorite": True})

            today_date = datetime.now(timezone.utc).date()
            today = today_date.strftime("%Y%m%d")
            events = sports.parse_xmltv(
                f'<tv><channel id="trt"><display-name>TRT Spor</display-name></channel>'
                f'<programme start="{today}170000 +0000" stop="{today}190000 +0000" channel="trt"><title>Cup Final</title><category>Sports</category></programme></tv>',
                today_date,
            )
            matched = sports.match_channels(events, [(i["id"], i["name"]) for i in cat_items])
            self.assertIn(sport_item["id"], json.dumps(matched))

            kid = c.post("/api/profiles", {"name": "KidSafe", "isKids": True, "pin": "2468"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "2468"}).status, 200)
            names = [i["name"] for i in c.get("/api/catalog").json["items"]]
            self.assertIn(sport_item["name"], names)
            self.assertNotIn("Yetiskin Gerilim", names)

            c.post("/api/profiles/switch", {"id": "default"})
            play = c.post("/api/play", {"id": sport_item["id"]})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            c.post(f"/api/play/{sid}/ping", {"position": 15.0})
            c.post(f"/api/play/{sid}/pause", {"paused": True})
            c.delete(f"/api/play/{sid}")

            exported = c.get("/api/export").json
            self.assertIn(sport_item["id"], json.dumps(exported))
            self.assertEqual(c.post("/api/import", {"data": exported}).status, 200)

    def test_local_media_scan_subtitles_playback_and_restart_persistence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mavie_persist_") as media_dir:
            mp = Path(media_dir)
            (mp / "Documentary.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"PERSIST" * 16)
            (mp / "Documentary.2025.tr.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nMerhaba Mavie\n", encoding="utf-8")

            with tempfile.TemporaryDirectory(prefix="mavie_data_") as fixed_data:
                env = {"MAVIE_DATA_DIR": fixed_data, "CINEVA_DATA_DIR": fixed_data}
                srv1 = LocalMediaServerProcess(extra_env=env).start()
                try:
                    c1 = srv1.paired_client()
                    c1.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Persist"})
                    item_id = None
                    for _ in range(40):
                        st = c1.get("/api/status").json or {}
                        items = (c1.get("/api/catalog").json or {}).get("items", [])
                        if items and not st.get("catalog", {}).get("syncing"):
                            item_id = items[0]["id"]
                            break
                        time.sleep(0.1)
                    self.assertIsNotNone(item_id)
                    play_resp = c1.post("/api/play", {"id": item_id})
                    self.assertEqual(play_resp.status, 200, play_resp.text)
                    sid = play_resp.json["sessionId"]
                    c1.post(f"/api/play/{sid}/ping", {"position": 88.0})
                    c1.post("/api/progress", {"id": item_id, "position": 88.0, "duration": 300})
                    c1.delete(f"/api/play/{sid}")
                    c1.post("/api/favorites", {"id": item_id, "favorite": True})
                finally:
                    srv1.stop()

                srv2 = LocalMediaServerProcess(extra_env=env).start()
                try:
                    c2 = srv2.paired_client()
                    prog = c2.get("/api/progress").text
                    self.assertIn("88", prog)
                    sub = c2.get(f"/api/subtitles/{item_id}/0.vtt")
                    self.assertEqual(sub.status, 200)
                    self.assertIn("Merhaba Mavie", sub.text)
                finally:
                    srv2.stop()

    def test_lan_pairing_grants_full_free_access_to_playback_profiles_multiview_and_sports(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        host_c = srv.paired_client()
        code = host_c.get("/api/status").json["pairingCode"]

        tablet = srv.client()
        self.assertEqual(tablet.post("/api/pair", {"code": code}).status, 200)
        self.assertEqual(host_c.post("/api/demo", {}).status, 200)
        items = tablet.get("/api/catalog").json["items"]
        self.assertGreaterEqual(len(items), 4)

        play = tablet.post("/api/play", {"id": items[0]["id"], "mode": "direct", "multiview": True, "multiviewSlot": 0})
        self.assertEqual(play.status, 200, play.text)
        tablet.delete(f"/api/play/{play.json['sessionId']}")

        self.assertEqual(tablet.get("/api/sports").status, 200)
        p2 = tablet.post("/api/profiles", {"name": "Tablet Kullanıcısı", "pin": "4567"})
        self.assertEqual(p2.status, 201, p2.text)

    def test_website_assets_match_ci_release_assets_and_zero_admin_files(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        ci_yml = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for asset in ("Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"):
            self.assertIn(asset, html)
            self.assertIn(asset, portal_js)
            self.assertIn(asset, ci_yml)
        self.assertFalse((REPO_ROOT / "website/admin.html").exists())
        self.assertFalse((REPO_ROOT / "website/admin.js").exists())


if __name__ == "__main__":
    unittest.main()
