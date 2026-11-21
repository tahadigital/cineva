"""Tier 4: End-to-end real-world application scenarios for free account-less Mavie."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

import sports
from tests.e2e.runner import (
    AKIS_ROOT,
    LocalMediaServerProcess,
    REPO_ROOT,
)


class Tier4EndToEndScenariosTests(unittest.TestCase):
    """Full real-world journeys across free local engine, LAN sync, household profiles, packaging, and hygiene."""

    def test_scenario_1_zero_account_onboarding_demo_playback_and_backup_restore(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)

        # User starts local desktop/web app with zero login or registration required
        local_client = srv.paired_client()
        self.assertEqual(local_client.post("/api/demo", {}).status, 200)
        items = local_client.get("/api/catalog").json["items"]
        self.assertGreaterEqual(len(items), 4)

        play = local_client.post("/api/play", {"id": items[0]["id"]}, timeout=30.0)
        self.assertEqual(play.status, 200)
        sid = play.json["sessionId"]
        local_client.post(f"/api/play/{sid}/ping", {"position": 65.0})
        local_client.post("/api/progress", {"id": items[0]["id"], "position": 65.0, "duration": 600})
        local_client.delete(f"/api/play/{sid}")
        local_client.post("/api/favorites", {"id": items[0]["id"], "favorite": True})

        exported = local_client.get("/api/export").json
        self.assertEqual(exported.get("version"), 1)
        self.assertIn(items[0]["id"], json.dumps(exported))

        # Restore into a brand-new server instance without any cloud account
        srv2 = LocalMediaServerProcess().start()
        self.addCleanup(srv2.stop)
        c2 = srv2.paired_client()
        self.assertEqual(c2.post("/api/demo", {}).status, 200)
        self.assertEqual(c2.post("/api/import", {"data": exported}).status, 200)
        self.assertIn(items[0]["id"], json.dumps(c2.get("/api/favorites").json))
        self.assertIn("65", c2.get("/api/progress").text)

    def test_scenario_2_household_kid_safe_sports_epg_and_playback_flow(self) -> None:
        srv = LocalMediaServerProcess().start()
        self.addCleanup(srv.stop)
        c = srv.paired_client()

        with tempfile.TemporaryDirectory(prefix="mavie_family_") as media_dir:
            mp = Path(media_dir)
            (mp / "Belgesel").mkdir()
            (mp / "Spor").mkdir()
            (mp / "Korku +18").mkdir()
            (mp / "Belgesel" / "Nature.Doc.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"NATURE" * 32)
            (mp / "Belgesel" / "Nature.Doc.2025.tr.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nDoğa Belgeseli\n", encoding="utf-8")
            (mp / "Spor" / "BeIN.Sports.Haber.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"SPORT" * 16)
            (mp / "Korku +18" / "Korku.Filmi.2025.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"HORROR" * 16)
            self.assertEqual(c.post("/api/settings", {"type": "local", "localDir": media_dir, "name": "Family"}).status, 200)
            cat_items = []
            for _ in range(40):
                st = c.get("/api/status").json or {}
                cat_items = (c.get("/api/catalog").json or {}).get("items", [])
                if len(cat_items) >= 3 and not st.get("catalog", {}).get("syncing"):
                    break
                time.sleep(0.1)
            self.assertEqual(len(cat_items), 3)
            doc_item = next(i for i in cat_items if "Nature Doc" in i["name"])
            sport_item = next(i for i in cat_items if "BeIN Sports" in i["name"])

            today_date = datetime.now(timezone.utc).date()
            today = today_date.strftime("%Y%m%d")
            epg_events = sports.parse_xmltv(
                f'<tv><channel id="sp1"><display-name>BeIN Sports Haber</display-name></channel>'
                f'<programme start="{today}160000 +0000" stop="{today}180000 +0000" channel="sp1"><title>Derbi Özetleri</title><category>Sports</category></programme></tv>',
                today_date,
            )
            matched = sports.match_channels(epg_events, [(i["id"], i["name"]) for i in cat_items])
            self.assertIn(sport_item["id"], json.dumps(matched))

            # Multiple PIN-locked profiles & Kid profile work freely without any account
            parent = c.post("/api/profiles", {"name": "Ebeveyn", "pin": "9999"}).json["profile"]
            self.assertTrue(parent["hasPin"])
            kid = c.post("/api/profiles", {"name": "Minik", "isKids": True, "pin": "1357"}).json["profile"]
            self.assertEqual(c.post("/api/profiles/switch", {"id": kid["id"], "pin": "1357"}).status, 200)
            kid_names = [i["name"] for i in c.get("/api/catalog").json["items"]]
            self.assertNotIn("Korku Filmi", kid_names)
            self.assertIn(sport_item["name"], kid_names)

            doc_id = doc_item["id"]
            sub = c.get(f"/api/subtitles/{doc_id}/0.vtt")
            self.assertEqual(sub.status, 200)
            self.assertIn("Doğa Belgeseli", sub.text)
            play = c.post("/api/play", {"id": doc_id})
            self.assertEqual(play.status, 200, play.text)
            sid = play.json["sessionId"]
            c.post(f"/api/play/{sid}/ping", {"position": 33.0})
            c.post("/api/progress", {"id": doc_id, "position": 33.0, "duration": 200})
            c.post(f"/api/play/{sid}/pause", {"paused": True})
            c.delete(f"/api/play/{sid}")
            self.assertIn("33", c.get("/api/progress").text)

    def test_scenario_3_cross_platform_release_packaging_and_4_platform_downloads(self) -> None:
        html = (REPO_ROOT / "website/index.html").read_text(encoding="utf-8")
        portal_js = (REPO_ROOT / "website/portal.js").read_text(encoding="utf-8")
        ci_yml = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        for asset_name in (
            "Mavie-Setup.exe",
            "Mavie.exe",
            "Mavie-Android.apk",
            "Mavie-macOS.dmg",
            "Mavie-iOS.ipa",
        ):
            self.assertIn(asset_name, html)
            self.assertIn(asset_name, portal_js)
            self.assertIn(asset_name, ci_yml)

    def test_scenario_4_secret_hygiene_and_akis_programi_untouched(self) -> None:
        tracked = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files"], text=True).splitlines()
        for f in tracked:
            self.assertFalse(
                bool(re.search(r"(^android/signing/|\.jks$|\.keystore$|^data/|^cloud_data/|^\.venv/|^\.env$)", f)),
                f"Tracked sensitive/local path found: {f}",
            )

        if AKIS_ROOT.exists():
            for rel in ("server.py", "playback.py", "discovery.py", "sports.py"):
                src = (AKIS_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("mavie", src.lower(), f"Akış Programı {rel} must stay untouched")

    def test_scenario_5_windows_crossover_utf8_stdio_and_launcher_stability(self) -> None:
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONIOENCODING": "cp1252",
        }
        try:
            srv = LocalMediaServerProcess(override_env=env).start()
        except RuntimeError as exc:
            self.fail(f"server.py failed to start under cp1252/C locale: {exc}")
        try:
            time.sleep(2.1)
            self.assertIsNone(srv.proc.poll(), "server.py crashed shortly after startup")
            health = srv.client().get("/api/health")
            self.assertEqual(health.status, 200)
            self.assertEqual(health.json, {"ok": True, "app": "mavie"})
            pid_file = srv.data_dir / "server.pid"
            self.assertTrue(pid_file.exists())
        finally:
            out = srv.stop()
        self.assertNotIn("UnicodeEncodeError", out)


if __name__ == "__main__":
    unittest.main()
