"""Opaque-box E2E test runner and shared process/HTTP/outbox harness for Mavie.

Usage:
    python3 -m unittest discover -s tests/e2e -v
    python3 -m tests.e2e.runner --tier all -v
    python3 -m tests.e2e.runner --tier 1 -v
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest
import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[2]
AKIS_ROOT = Path("/Users/tahay/Documents/projelerim/Akış Programı")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TIER_MODULES = {
    "1": "tests.e2e.test_tier1_features",
    "2": "tests.e2e.test_tier2_boundaries",
    "3": "tests.e2e.test_tier3_combinations",
    "4": "tests.e2e.test_tier4_scenarios",
}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_iso_dt(value: str) -> datetime:
    """Parse ISO-8601 timestamp safely on Python 3.9+ (including trailing 'Z')."""
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclasses.dataclass
class HttpResponse:
    status: int
    headers: Dict[str, str]
    raw: bytes
    text: str
    json_data: Any

    @property
    def json(self) -> Any:
        return self.json_data


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    """Stdlib HTTP + CookieJar client that captures HTTP error bodies cleanly."""

    def __init__(
        self,
        base_url: str,
        origin: Optional[str] = None,
        follow_redirects: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.origin = origin or self.base_url
        self.cookie_jar = http.cookiejar.CookieJar()
        handlers: List[Any] = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]
        if not follow_redirects:
            handlers.append(_NoRedirectHandler())
        self.opener = urllib.request.build_opener(*handlers)
        self.default_headers: Dict[str, str] = {}

    def cookies_dict(self) -> Dict[str, str]:
        return {c.name: c.value for c in self.cookie_jar}

    def request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        raw_body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        url = path if path.startswith("http://") or path.startswith("https://") else f"{self.base_url}{path}"
        hdrs: Dict[str, str] = {"Origin": self.origin}
        hdrs.update(self.default_headers)
        if headers:
            hdrs.update(headers)
        if token:
            hdrs["Authorization"] = f"Bearer {token}"

        data: Optional[bytes] = raw_body
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif method.upper() in ("POST", "PUT", "PATCH") and data is None:
            data = b""

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return self._build_response(int(resp.status), resp_headers, raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            resp_headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
            return self._build_response(int(exc.code), resp_headers, raw)

    @staticmethod
    def _build_response(status: int, headers: Dict[str, str], raw: bytes) -> HttpResponse:
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        return HttpResponse(status=status, headers=headers, raw=raw, text=text, json_data=parsed)

    def get(self, path: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json_body: Any = None, **kwargs: Any) -> HttpResponse:
        return self.request("POST", path, json_body=json_body, **kwargs)

    def put(self, path: str, json_body: Any = None, **kwargs: Any) -> HttpResponse:
        return self.request("PUT", path, json_body=json_body, **kwargs)

    def patch(self, path: str, json_body: Any = None, **kwargs: Any) -> HttpResponse:
        return self.request("PATCH", path, json_body=json_body, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> HttpResponse:
        return self.request("DELETE", path, **kwargs)


def _extract_code_and_token(entry: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract 6-digit verification/reset code and token from an outbox entry."""
    if isinstance(entry, dict):
        code = entry.get("code") or entry.get("verificationCode") or entry.get("resetCode")
        token = entry.get("token") or entry.get("verificationToken") or entry.get("resetToken")
        blob = " ".join(
            str(entry.get(k, ""))
            for k in ("subject", "text", "body", "html", "message", "link", "url")
        )
    else:
        code = None
        token = None
        blob = str(entry)

    if not code:
        m_code = re.search(r"(?<!\d)(\d{6})(?!\d)", blob)
        if m_code:
            code = m_code.group(1)
    if not token:
        m_tok = re.search(r"[?&]token=([A-Za-z0-9_.-]{8,})", blob)
        if m_tok:
            token = m_tok.group(1)
    return (str(code) if code else None, str(token) if token else None)


class CloudServerProcess:
    """Managed subprocess for cloud_admin.py with isolated temp dir and outbox."""

    def __init__(
        self,
        admin_email: str = "admin@mavie.app",
        admin_password: str = "MavieAdminPass!2026",
        gate_key: str = "mavie-e2e-gate-key",
        extra_env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.gate_key = gate_key
        self.extra_env = extra_env or {}
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self.data_dir: Optional[Path] = None
        self.outbox_file: Optional[Path] = None
        self.port: int = 0
        self.base_url: str = ""
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> "CloudServerProcess":
        self._tmp = tempfile.TemporaryDirectory(prefix="mavie_e2e_cloud_")
        self.data_dir = Path(self._tmp.name)
        self.outbox_file = self.data_dir / "email_outbox.json"
        self.port = find_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

        env = {k: v for k, v in os.environ.items() if "SMTP" not in k.upper()}
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "MAVIE_CLOUD_DATA_DIR": str(self.data_dir),
                "CINEVA_CLOUD_DATA_DIR": str(self.data_dir),
                "MAVIE_ADMIN_EMAIL": self.admin_email,
                "CINEVA_ADMIN_EMAIL": self.admin_email,
                "MAVIE_ADMIN_PASSWORD": self.admin_password,
                "CINEVA_ADMIN_PASSWORD": self.admin_password,
                "MAVIE_ADMIN_GATE_KEY": self.gate_key,
                "CINEVA_ADMIN_GATE_KEY": self.gate_key,
                "MAVIE_CLOUD_SECRET": "e2e-cloud-secret-key-0123456789",
                "CINEVA_CLOUD_SECRET": "e2e-cloud-secret-key-0123456789",
                "MAVIE_EMAIL_MODE": "outbox",
                "MAVIE_EMAIL_OUTBOX_FILE": str(self.outbox_file),
            }
        )
        env.update(self.extra_env)

        self.proc = subprocess.Popen(
            [
                sys.executable,
                "cloud_admin.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--data-dir",
                str(self.data_dir),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    out = self.proc.stdout.read() if self.proc.stdout else ""
                    raise RuntimeError(f"cloud_admin.py exited prematurely ({self.proc.returncode}): {out}")
                try:
                    resp = self.client().get("/api/v1/health", timeout=0.5)
                    if resp.status == 200:
                        return self
                except Exception:
                    pass
                time.sleep(0.1)
            raise TimeoutError("cloud_admin.py did not become ready within 8s")
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
            if self.proc.stdout:
                self.proc.stdout.close()
            self.proc = None
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def client(self, follow_redirects: bool = True) -> HttpClient:
        return HttpClient(self.base_url, follow_redirects=follow_redirects)

    def admin_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Admin-Gate": self.gate_key,
        }

    def admin_login(self) -> str:
        resp = self.client().post(
            "/api/v1/auth/login",
            {"email": self.admin_email, "password": self.admin_password},
        )
        if resp.status != 200 or not isinstance(resp.json, dict) or not resp.json.get("token"):
            raise AssertionError(f"Admin login failed: status={resp.status} body={resp.text}")
        return str(resp.json["token"])

    def read_outbox(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        candidates: List[Path] = []
        if self.outbox_file is not None:
            candidates.append(self.outbox_file)
        if self.data_dir is not None:
            for name in ("email_outbox.json", "outbox.json"):
                p = self.data_dir / name
                if p not in candidates:
                    candidates.append(p)

        for path in candidates:
            if path.exists():
                raw = path.read_text(encoding="utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        entries.extend([x for x in data if isinstance(x, dict)])
                    elif isinstance(data, dict):
                        for key in ("messages", "emails", "outbox", "items"):
                            if isinstance(data.get(key), list):
                                entries.extend([x for x in data[key] if isinstance(x, dict)])
                                break
                        else:
                            entries.append(data)
                except ValueError:
                    for line in raw.splitlines():
                        line = line.strip()
                        if line:
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict):
                                    entries.append(obj)
                            except ValueError:
                                pass
                if entries:
                    return entries

        # Fallback: inspect email_outbox table in cloud SQLite DB if present
        if self.data_dir is not None:
            db_files = [
                p for p in sorted(self.data_dir.iterdir())
                if p.is_file() and p.suffix.lower() in (".sqlite", ".sqlite3", ".db")
            ]
            for db_path in db_files:
                try:
                    con = sqlite3.connect(str(db_path))
                    con.row_factory = sqlite3.Row
                    tables = [
                        r[0]
                        for r in con.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    ]
                    if "email_outbox" in tables:
                        rows = con.execute("SELECT * FROM email_outbox ORDER BY rowid ASC").fetchall()
                        entries = [dict(r) for r in rows]
                    con.close()
                    if entries:
                        return entries
                except sqlite3.Error:
                    pass
        return entries

    def find_latest_mail(
        self,
        recipient_email: str,
        kind_hint: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        target = recipient_email.strip().lower()
        matched: List[Dict[str, Any]] = []
        for entry in self.read_outbox():
            to_val = str(
                entry.get("to")
                or entry.get("recipient")
                or entry.get("email")
                or entry.get("to_email")
                or ""
            ).lower()
            if target in to_val or target in json.dumps(entry).lower():
                if kind_hint:
                    haystack = json.dumps(entry).lower()
                    if kind_hint.lower() not in haystack:
                        continue
                matched.append(entry)
        if not matched:
            return None, None, None
        latest = matched[-1]
        code, token = _extract_code_and_token(latest)
        return latest, code, token

    def register_and_verify(
        self,
        email: str,
        password: str,
        display_name: str = "E2E User",
    ) -> Tuple[HttpResponse, Optional[str], Optional[Dict[str, Any]]]:
        c = self.client()
        reg = c.post(
            "/api/v1/auth/register",
            {"email": email, "password": password, "displayName": display_name},
        )
        if reg.status not in (200, 201):
            return reg, None, None
        _, code, token = self.find_latest_mail(email)
        payload: Dict[str, Any] = {"email": email}
        if code:
            payload["code"] = code
        elif token:
            payload = {"token": token}
        ver = c.post("/api/v1/auth/verify-email", payload)
        if ver.status == 200 and isinstance(ver.json, dict):
            return ver, ver.json.get("token"), ver.json.get("user")
        return ver, None, None

    def expire_tokens_in_db(self, table_keyword: str) -> int:
        """Backdate expires_at / expiresAt in verification/reset tables for expiry boundary tests."""
        if self.data_dir is None:
            return 0
        updated = 0
        past = "2020-01-01T00:00:00+00:00"
        db_files = [
            p for p in sorted(self.data_dir.iterdir())
            if p.is_file() and p.suffix.lower() in (".sqlite", ".sqlite3", ".db")
        ]
        for db_path in db_files:
            con = sqlite3.connect(str(db_path))
            try:
                tables = [
                    r[0]
                    for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                for tbl in tables:
                    if table_keyword.lower() not in tbl.lower():
                        continue
                    cols = [r[1] for r in con.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
                    for col in ("expires_at", "expiresAt", "expires"):
                        if col in cols:
                            cur = con.execute(f"UPDATE '{tbl}' SET '{col}' = ?", (past,))
                            updated += cur.rowcount
                con.commit()
            finally:
                con.close()
        return updated


class LocalMediaServerProcess:
    """Managed subprocess for server.py with isolated temp data dir."""

    def __init__(
        self,
        cloud_url: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
        override_env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.cloud_url = cloud_url
        self.extra_env = extra_env or {}
        self.override_env = override_env
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self.data_dir: Optional[Path] = None
        self.port: int = 0
        self.base_url: str = ""
        self.proc: Optional[subprocess.Popen] = None
        self.startup_output: str = ""

    def start(self, wait_seconds: float = 8.0) -> "LocalMediaServerProcess":
        self._tmp = tempfile.TemporaryDirectory(prefix="mavie_e2e_local_")
        self.data_dir = Path(self._tmp.name)
        self.port = find_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

        if self.override_env is not None:
            env = dict(self.override_env)
        else:
            env = dict(os.environ)
            env.setdefault("PYTHONIOENCODING", "utf-8")

        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "MAVIE_DATA_DIR": str(self.data_dir),
                "CINEVA_DATA_DIR": str(self.data_dir),
            }
        )
        if self.cloud_url:
            env["MAVIE_CLOUD_URL"] = self.cloud_url
            env["CINEVA_CLOUD_URL"] = self.cloud_url
        env.update(self.extra_env)

        self.proc = subprocess.Popen(
            [
                sys.executable,
                "server.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        try:
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    out = self.proc.stdout.read() if self.proc.stdout else ""
                    self.startup_output = out
                    raise RuntimeError(f"server.py exited prematurely ({self.proc.returncode}): {out}")
                try:
                    resp = self.client().get("/api/health", timeout=0.5)
                    if resp.status == 200:
                        return self
                except Exception:
                    pass
                time.sleep(0.1)
            raise TimeoutError("server.py did not become ready within timeout")
        except Exception:
            self.stop()
            raise

    def stop(self) -> str:
        output = self.startup_output
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
            if self.proc.stdout:
                try:
                    output += self.proc.stdout.read()
                except Exception:
                    pass
                self.proc.stdout.close()
            self.proc = None
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None
        return output

    def client(self) -> HttpClient:
        return HttpClient(self.base_url)

    def paired_client(self) -> HttpClient:
        c = self.client()
        c.get("/")
        return c


def build_suite(tier: str = "all") -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    if tier == "all":
        for key in ("1", "2", "3", "4"):
            suite.addTests(loader.loadTestsFromName(TIER_MODULES[key]))
    elif tier in TIER_MODULES:
        suite.addTests(loader.loadTestsFromName(TIER_MODULES[tier]))
    else:
        raise ValueError(f"Unknown tier: {tier!r}. Expected 1, 2, 3, 4, or all.")
    return suite


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Mavie 4-tier opaque-box E2E test suite")
    parser.add_argument(
        "--tier",
        choices=("1", "2", "3", "4", "all"),
        default="all",
        help="Run a specific tier (1..4) or all tiers",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test output")
    args = parser.parse_args(argv)

    suite = build_suite(args.tier)
    verbosity = 2 if args.verbose else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
