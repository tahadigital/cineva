"""Opaque-box E2E test runner and shared process/HTTP harness for Mavie.

Usage:
    python3 -m unittest discover -s tests/e2e -v
    python3 -m tests.e2e.runner --tier all -v
    python3 -m tests.e2e.runner --tier all --baseline-only -v
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
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar
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

_F = TypeVar("_F", bound=Callable[..., Any])


def requires_target(milestone: str) -> Callable[[_F], _F]:
    """Tag a test method or class as requiring an unmerged target milestone (e.g. 'M1', 'M2', 'M3').

    By default (`--tier all`), tagged tests execute normally.
    When `--baseline-only` is passed, tagged tests are skipped cleanly.
    """

    def _decorator(obj: _F) -> _F:
        setattr(obj, "_e2e_requires_target", milestone)
        return obj

    return _decorator


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


class LocalMediaServerProcess:
    """Managed subprocess for server.py (or _mock_server_main) with isolated temp data dir."""

    def __init__(
        self,
        extra_env: Optional[Dict[str, str]] = None,
        override_env: Optional[Dict[str, str]] = None,
        allow_mock_port: Optional[int] = None,
        mock_base_url: Optional[str] = None,
    ) -> None:
        self.extra_env = extra_env or {}
        self.override_env = override_env
        self.allow_mock_port = allow_mock_port
        self.mock_base_url = mock_base_url
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
            env.setdefault("NO_PROXY", "127.0.0.1,localhost")
            env.setdefault("no_proxy", "127.0.0.1,localhost")

        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "MAVIE_DATA_DIR": str(self.data_dir),
                "CINEVA_DATA_DIR": str(self.data_dir),
            }
        )
        if self.allow_mock_port is not None:
            env["MAVIE_E2E_MOCK_PORT"] = str(self.allow_mock_port)
        if self.mock_base_url:
            env["MAVIE_E2E_MOCK_BASE"] = self.mock_base_url
        env.update(self.extra_env)

        use_mock_entry = self.allow_mock_port is not None or bool(self.mock_base_url)
        cmd = (
            [sys.executable, "-m", "tests.e2e._mock_server_main", "--host", "127.0.0.1", "--port", str(self.port)]
            if use_mock_entry
            else [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(self.port)]
        )

        self.proc = subprocess.Popen(
            cmd,
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


def _apply_baseline_filter(suite: unittest.TestSuite) -> None:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            _apply_baseline_filter(item)
            continue
        if isinstance(item, unittest.TestCase):
            method = getattr(item, item._testMethodName, None)
            target = getattr(method, "_e2e_requires_target", None) or getattr(
                item.__class__, "_e2e_requires_target", None
            )
            if target and method is not None:
                skipped = unittest.skip(f"Requires target {target} (--baseline-only)")(method)
                setattr(item, item._testMethodName, skipped)


def build_suite(tier: str = "all", baseline_only: bool = False) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    if tier == "all":
        for key in ("1", "2", "3", "4"):
            suite.addTests(loader.loadTestsFromName(TIER_MODULES[key]))
    elif tier in TIER_MODULES:
        suite.addTests(loader.loadTestsFromName(TIER_MODULES[tier]))
    else:
        raise ValueError(f"Unknown tier: {tier!r}. Expected 1, 2, 3, 4, or all.")
    if baseline_only or os.environ.get("MAVIE_E2E_BASELINE_ONLY") == "1":
        _apply_baseline_filter(suite)
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
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Skip tests tagged @requires_target(...) for pre-merge baseline verification",
    )
    args = parser.parse_args(argv)

    suite = build_suite(args.tier, baseline_only=args.baseline_only)
    verbosity = 2 if args.verbose else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
