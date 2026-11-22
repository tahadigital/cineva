"""Test-only entrypoint for LocalMediaServerProcess when mock upstream routes are enabled.

Leaves production server.py completely unmodified. When MAVIE_E2E_MOCK_PORT is set,
wraps server.safe_public_url to permit ONLY http://127.0.0.1:<mock_port> (with no
embedded username/password), while delegating all other URLs (including localhost,
other 127.0.0.1 ports, 169.254.169.254, 10.0.0.1, etc.) to original safe_public_url.
When MAVIE_E2E_MOCK_BASE is set, points sports.SPOREKRANI_SOURCE and discovery feeds
at the local mock base URL so zero external network traffic can occur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import urllib.parse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import discovery  # noqa: E402
import server  # noqa: E402
import sports  # noqa: E402


def _install_mock_hooks() -> None:
    mock_port_raw = os.environ.get("MAVIE_E2E_MOCK_PORT", "").strip()
    if mock_port_raw:
        mock_port = int(mock_port_raw)
        orig_safe_public_url = server.safe_public_url

        def _e2e_safe_public_url(url: str) -> str:
            u = urllib.parse.urlsplit(url)
            if (
                u.scheme == "http"
                and u.hostname == "127.0.0.1"
                and u.port == mock_port
                and not u.username
                and not u.password
            ):
                return url
            return orig_safe_public_url(url)

        server.safe_public_url = _e2e_safe_public_url

    mock_base = os.environ.get("MAVIE_E2E_MOCK_BASE", "").strip().rstrip("/")
    if mock_base:
        sports.SPOREKRANI_SOURCE = f"{mock_base}/sporekrani/home/day/"
        discovery.CINEMETA = f"{mock_base}/cinemeta"
        discovery.NETFLIX = f"{mock_base}/netflix/tudum/top10/turkey"
        discovery.TMDB_API = f"{mock_base}/tmdb"
        orig_discovery_get = discovery.get

        def _e2e_discovery_get(url: str, timeout: int = 18) -> str:
            if url.startswith("https://www.netflix.com/tr/title/"):
                url = mock_base + "/netflix/tr/title/" + url[len("https://www.netflix.com/tr/title/"):]
            return orig_discovery_get(url, timeout=timeout)

        discovery.get = _e2e_discovery_get


if __name__ == "__main__":
    _install_mock_hooks()
    server.main()
