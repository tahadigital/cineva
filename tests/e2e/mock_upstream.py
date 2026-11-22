"""Deterministic ephemeral mock upstream HTTP server for opaque-box Mavie E2E tests.

Serves synthetic M3U Plus query URLs, gzipped M3U with UTF-8 BOM and attribute commas,
301/302/307 redirect chains and SSRF redirect traps, Xtream API endpoints, XMLTV EPG
(.xml and .xml.gz), Spor Ekranı SSR JSON, Cinemeta/Netflix TR Discovery mocks,
HLS playlists/keys/segments, Range-capable MP4s, PNG posters, and fault-injection routes.

Zero real credentials or external hosts are ever stored or contacted.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    _IST_TZ = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    _IST_TZ = dt.timezone(dt.timedelta(hours=3))

# Minimal valid 1x1 purple PNG (#7C3AED).
VALID_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x88\xaa\xfe"
    b"\x0f\x00\x02\x86\x01\x9e\x1c\xd1\xdf\x98\x00\x00\x00\x00IEND\xaeB`\x82"
)

SAMPLE_MP4 = b"\x00\x00\x00\x18ftypmp42" + (b"MAVIE_MP4_STREAM" * 254)
SAMPLE_TS = b"\x47\x40\x00\x10" + (b"MAVIE_TS_SEGMENT_0_" * 32)
SAMPLE_KEY = b"MAVIE_AES_KEY_16"


@dataclasses.dataclass
class RecordedRequest:
    method: str
    path: str
    query: str
    params: Dict[str, List[str]]
    headers: Dict[str, str]


class MockUpstreamServer:
    """Ephemeral ThreadingHTTPServer on 127.0.0.1:0 with request logging & fault controls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.requests: List[RecordedRequest] = []
        self.image_hits: int = 0
        self.m3u_override: Optional[Tuple[int, str, bytes]] = None
        self.xmltv_override: Optional[Tuple[int, str, bytes]] = None
        self.sporekrani_override: Optional[Tuple[int, str, bytes]] = None
        self.xtream_short_epg_corrupt: bool = False
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0
        self.base_url: str = ""

    def start(self) -> "MockUpstreamServer":
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_HEAD(self) -> None:
                self._dispatch(head_only=True)

            def do_GET(self) -> None:
                self._dispatch(head_only=False)

            def _send(
                self,
                status: int,
                content_type: str,
                body: bytes,
                headers: Optional[Dict[str, str]] = None,
                head_only: bool = False,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if not head_only and body:
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def _send_stream_zeros(self, total_bytes: int, content_type: str, head_only: bool) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(total_bytes))
                self.end_headers()
                if head_only:
                    return
                chunk = b"0" * (256 * 1024)
                remaining = total_bytes
                try:
                    while remaining > 0 and not parent._stop_event.is_set():
                        part = chunk if remaining >= len(chunk) else b"0" * remaining
                        self.wfile.write(part)
                        remaining -= len(part)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _dispatch(self, head_only: bool) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                path = parsed.path
                params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                hdrs = {k.lower(): v for k, v in self.headers.items()}
                with parent._lock:
                    parent.requests.append(
                        RecordedRequest(
                            method=self.command,
                            path=path,
                            query=parsed.query,
                            params=params,
                            headers=hdrs,
                        )
                    )

                base = parent.base_url
                today_ist = dt.datetime.now(_IST_TZ).date()
                tomorrow_ist = today_ist + dt.timedelta(days=1)

                # --- Redirects & SSRF redirect traps ---
                if path == "/redirect/301":
                    self._send(301, "text/plain", b"", {"Location": f"{base}/redirect/302"}, head_only)
                    return
                if path == "/redirect/302":
                    self._send(302, "text/plain", b"", {"Location": f"{base}/redirect/307"}, head_only)
                    return
                if path == "/redirect/307":
                    self._send(307, "text/plain", b"", {"Location": f"{base}/m3u/plain.m3u"}, head_only)
                    return
                if path == "/redirect/m3u-gzip":
                    self._send(302, "text/plain", b"", {"Location": f"{base}/m3u/gzip"}, head_only)
                    return
                if path == "/redirect/m3u-plus":
                    loc = f"{base}/get.php?username=demo_user&password=demo_pass&type=m3u_plus&output=mpegts"
                    self._send(302, "text/plain", b"", {"Location": loc}, head_only)
                    return
                if path == "/redirect/to-metadata":
                    self._send(
                        302,
                        "text/plain",
                        b"",
                        {"Location": "http://169.254.169.254/latest/meta-data/"},
                        head_only,
                    )
                    return
                if path == "/redirect/to-loopback":
                    self._send(
                        302,
                        "text/plain",
                        b"",
                        {"Location": "http://127.0.0.1:8844/api/status"},
                        head_only,
                    )
                    return

                # --- M3U Plus & Gzip & Plain M3U ---
                if path == "/get.php":
                    with parent._lock:
                        ov = parent.m3u_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    user = params.get("username", [""])[0]
                    pwd = params.get("password", [""])[0]
                    if user == "bad_user" or pwd == "bad_pass":
                        self._send(401, "text/plain", b"Unauthorized", head_only=head_only)
                        return
                    payload = parent._build_m3u_plus_playlist().encode("utf-8")
                    self._send(200, "audio/x-mpegurl; charset=utf-8", payload, head_only=head_only)
                    return

                if path == "/m3u/gzip":
                    with parent._lock:
                        ov = parent.m3u_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    raw = parent._build_m3u_plus_playlist().encode("utf-8")
                    gz = gzip.compress(raw)
                    self._send(
                        200,
                        "audio/x-mpegurl; charset=utf-8",
                        gz,
                        {"Content-Encoding": "gzip"},
                        head_only=head_only,
                    )
                    return

                if path == "/m3u/plain.m3u":
                    with parent._lock:
                        ov = parent.m3u_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    payload = parent._build_plain_m3u_playlist().encode("utf-8")
                    self._send(200, "audio/x-mpegurl; charset=utf-8", payload, head_only=head_only)
                    return

                # --- Xtream API ---
                if path == "/player_api.php":
                    self._handle_xtream(params, head_only)
                    return

                if re.match(r"^/(?:live|movie|series)/[^/]+/[^/]+/[^/]+$", path):
                    if path.endswith(".m3u8"):
                        body = parent._build_live_m3u8().encode("utf-8")
                        self._send(200, "application/vnd.apple.mpegurl", body, head_only=head_only)
                    elif path.endswith(".ts"):
                        self._send(200, "video/mp2t", SAMPLE_TS, head_only=head_only)
                    else:
                        self._handle_mp4_range(head_only)
                    return

                # --- XMLTV EPG ---
                if path in ("/guide.xml", "/epg.xml"):
                    with parent._lock:
                        ov = parent.xmltv_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    xml_bytes = parent._build_xmltv(today_ist, tomorrow_ist).encode("utf-8")
                    self._send(200, "application/xml; charset=utf-8", xml_bytes, head_only=head_only)
                    return

                if path in ("/guide.xml.gz", "/epg.xml.gz"):
                    with parent._lock:
                        ov = parent.xmltv_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    xml_bytes = parent._build_xmltv(today_ist, tomorrow_ist).encode("utf-8")
                    self._send(200, "application/gzip", gzip.compress(xml_bytes), head_only=head_only)
                    return

                # --- Spor Ekranı SSR mock ---
                if path.startswith("/sporekrani/home/day/"):
                    with parent._lock:
                        ov = parent.sporekrani_override
                    if ov is not None:
                        self._send(ov[0], ov[1], ov[2], head_only=head_only)
                        return
                    day_str = path.rsplit("/", 1)[-1] or today_ist.isoformat()
                    html_bytes = parent._build_sporekrani_html(day_str).encode("utf-8")
                    self._send(200, "text/html; charset=utf-8", html_bytes, head_only=head_only)
                    return

                # --- Discovery mocks (Cinemeta + Netflix TR) ---
                if path.startswith("/cinemeta/catalog/"):
                    is_series = "/series/" in path
                    metas = [
                        {
                            "id": "tt9000002" if is_series else "tt9000001",
                            "name": "Gece Yolculuğu" if is_series else "Işıklar İçinde",
                            "year": str(today_ist.year),
                            "genres": ["Drama"] if is_series else ["Comedy"],
                            "poster": f"{base}/posters/thumb.png",
                            "released": today_ist.isoformat(),
                        }
                    ]
                    self._send(200, "application/json", json.dumps({"metas": metas}).encode("utf-8"), head_only=head_only)
                    return

                if path == "/cinemeta/manifest.json":
                    self._send(200, "application/json", b'{"id":"mock.cinemeta","name":"Cinemeta"}', head_only=head_only)
                    return

                if path in ("/netflix/tudum/top10/turkey", "/netflix/tudum/top10/turkey/tv"):
                    is_tv = path.endswith("/tv")
                    html_bytes = parent._build_netflix_html(today_ist.isoformat(), is_tv=is_tv).encode("utf-8")
                    self._send(200, "text/html; charset=utf-8", html_bytes, head_only=head_only)
                    return

                if path.startswith("/netflix/tr/title/"):
                    self._send(200, "text/html; charset=utf-8", b"<html><head></head><body></body></html>", head_only=head_only)
                    return

                # --- HLS, MP4, Poster ---
                if path == "/streams/master.m3u8":
                    body = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1200000\nlive.m3u8\n"
                    self._send(200, "application/vnd.apple.mpegurl", body, head_only=head_only)
                    return
                if path == "/streams/live.m3u8":
                    body = parent._build_live_m3u8().encode("utf-8")
                    self._send(200, "application/vnd.apple.mpegurl", body, head_only=head_only)
                    return
                if path == "/streams/key.bin":
                    self._send(200, "application/octet-stream", SAMPLE_KEY, head_only=head_only)
                    return
                if path == "/streams/seg0.ts":
                    self._send(200, "video/mp2t", SAMPLE_TS, head_only=head_only)
                    return
                if path == "/streams/sample.mp4":
                    self._handle_mp4_range(head_only)
                    return
                if path == "/posters/thumb.png":
                    with parent._lock:
                        parent.image_hits += 1
                    self._send(200, "image/png", VALID_PNG_1X1, head_only=head_only)
                    return

                # --- Fault injection routes ---
                if path == "/err/401":
                    self._send(401, "application/json", b'{"error":"Unauthorized"}', head_only=head_only)
                    return
                if path == "/err/403":
                    self._send(403, "application/json", b'{"error":"Forbidden"}', head_only=head_only)
                    return
                if path == "/err/500":
                    self._send(500, "text/plain", b"Internal Server Error", head_only=head_only)
                    return
                if path == "/err/html":
                    self._send(200, "text/html; charset=utf-8", b"<html><body>Sign in</body></html>", head_only=head_only)
                    return
                if path == "/err/empty":
                    self._send(200, "text/plain; charset=utf-8", b"", head_only=head_only)
                    return
                if path == "/err/slow":
                    delay = float(params.get("delay", ["5.0"])[0] or "5.0")
                    parent._stop_event.wait(delay)
                    self._send(200, "audio/x-mpegurl", b"#EXTM3U\n", head_only=head_only)
                    return
                if path == "/err/oversized.m3u":
                    self._send_stream_zeros(201 * 1024 * 1024, "audio/x-mpegurl", head_only)
                    return
                if path == "/err/oversized.xml":
                    self._send_stream_zeros(9 * 1024 * 1024, "application/xml", head_only)
                    return
                if path == "/err/oversized.m3u8":
                    self._send_stream_zeros(3 * 1024 * 1024 + 4096, "application/vnd.apple.mpegurl", head_only)
                    return
                if path == "/err/oversized.png":
                    self._send_stream_zeros(5 * 1024 * 1024 + 4096, "image/png", head_only)
                    return
                if path == "/err/oversized_discovery.json":
                    self._send_stream_zeros(5 * 1024 * 1024 + 4096, "application/json", head_only)
                    return
                if path == "/err/xxe.xml":
                    xxe = (
                        '<?xml version="1.0"?>'
                        '<!DOCTYPE tv [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
                        f'<tv><programme start="{today_ist.strftime("%Y%m%d")}120000 +0300" '
                        f'stop="{today_ist.strftime("%Y%m%d")}130000 +0300" channel="c1">'
                        "<title>&xxe;</title></programme></tv>"
                    ).encode("utf-8")
                    self._send(200, "application/xml", xxe, head_only=head_only)
                    return
                if path == "/err/bad.xml":
                    self._send(200, "application/xml", b"<tv><broken", head_only=head_only)
                    return
                if path == "/err/svg":
                    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><circle r="10"/></svg>'
                    self._send(200, "image/svg+xml", svg, head_only=head_only)
                    return
                if path == "/err/incomplete":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "1024")
                    self.end_headers()
                    if not head_only:
                        try:
                            self.wfile.write(b'{"partial":')
                            self.wfile.flush()
                        except OSError:
                            pass
                    self.close_connection = True
                    return

                self._send(404, "application/json", b'{"error":"Not found"}', head_only=head_only)

            def _handle_mp4_range(self, head_only: bool) -> None:
                size = len(SAMPLE_MP4)
                rng = self.headers.get("Range", "")
                m = re.fullmatch(r"bytes=(\d+)-(\d*)", rng.strip())
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                    if start >= size or start > end:
                        self._send(416, "text/plain", b"Range Not Satisfiable", {"Content-Range": f"bytes */{size}"}, head_only)
                        return
                    end = min(end, size - 1)
                    chunk = SAMPLE_MP4[start : end + 1]
                    self._send(
                        206,
                        "video/mp4",
                        chunk,
                        {"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}"},
                        head_only=head_only,
                    )
                    return
                self._send(200, "video/mp4", SAMPLE_MP4, {"Accept-Ranges": "bytes"}, head_only=head_only)

            def _handle_xtream(self, params: Dict[str, List[str]], head_only: bool) -> None:
                base = parent.base_url
                user = params.get("username", [""])[0]
                pwd = params.get("password", [""])[0]
                action = params.get("action", [""])[0]
                if user != "demo_user" or pwd != "demo_pass":
                    payload = {"user_info": {"auth": 0, "status": "Disabled"}}
                    self._send(200, "application/json", json.dumps(payload).encode("utf-8"), head_only=head_only)
                    return

                if not action:
                    payload: Any = {
                        "user_info": {
                            "auth": 1,
                            "status": "Active",
                            "exp_date": "1893456000",
                            "max_connections": "3",
                            "active_cons": "0",
                        }
                    }
                elif action == "get_live_categories":
                    payload = [
                        {"category_id": "10", "category_name": "Spor"},
                        {"category_id": "11", "category_name": "Haber"},
                    ]
                elif action == "get_live_streams":
                    payload = [
                        {"stream_id": 101, "name": "TR: BeIN Sports 1 FHD", "category_id": "10", "stream_icon": f"{base}/posters/thumb.png"},
                        {"stream_id": 102, "name": "BeIN Sports 1 SD", "category_id": "10", "stream_icon": ""},
                        {"stream_id": 103, "name": "TR: TRT Spor Yıldız HD", "category_id": "10", "stream_icon": ""},
                        {"stream_id": 104, "name": "Haber Kanalı HD", "category_id": "11", "stream_icon": ""},
                    ]
                elif action == "get_vod_categories":
                    payload = [
                        {"category_id": "20", "category_name": "Komedi"},
                        {"category_id": "21", "category_name": "Korku +18"},
                    ]
                elif action == "get_vod_streams":
                    payload = [
                        {
                            "stream_id": 201,
                            "name": "Işıklar İçinde",
                            "category_id": "20",
                            "rating": "8.4",
                            "year": "2025",
                            "added": "1730000200",
                            "container_extension": "mp4",
                            "stream_icon": f"{base}/posters/thumb.png",
                        },
                        {
                            "stream_id": 202,
                            "name": "Çığlık Şöleni",
                            "category_id": "21",
                            "rating": "6.5",
                            "year": "2024",
                            "added": "1730000100",
                            "container_extension": "mp4",
                            "stream_icon": "",
                        },
                    ]
                elif action == "get_vod_info":
                    payload = {
                        "info": {
                            "plot": "Test film açıklaması.",
                            "genre": "Comedy",
                            "duration_secs": 5400,
                            "director": "Test Yönetmen",
                            "cast": "Oyuncu A, Oyuncu B",
                            "rating": "8.4",
                            "releasedate": "2025-01-10",
                            "movie_image": f"{base}/posters/thumb.png",
                        }
                    }
                elif action == "get_series_categories":
                    payload = [{"category_id": "30", "category_name": "Dram"}]
                elif action == "get_series":
                    payload = [
                        {
                            "series_id": 301,
                            "name": "Gece Yolculuğu",
                            "category_id": "30",
                            "rating": "8.9",
                            "releaseDate": "2025-02-01",
                            "cover": f"{base}/posters/thumb.png",
                            "last_modified": "1730000300",
                        }
                    ]
                elif action == "get_series_info":
                    payload = {
                        "info": {
                            "plot": "Test dizi özeti.",
                            "genre": "Drama",
                            "cast": "Oyuncu C",
                            "director": "Yönetmen D",
                            "rating": "8.9",
                        },
                        "episodes": {
                            "1": [
                                {"id": "3011", "episode_num": 1, "title": "1. Bölüm: Başlangıç", "container_extension": "mp4", "info": {"duration_secs": 2400}},
                                {"id": "3012", "episode_num": 2, "title": "2. Bölüm: Devam", "container_extension": "mp4", "info": {"duration_secs": 2500}},
                            ],
                            "2": [
                                {"id": "3021", "episode_num": 1, "title": "2. Sezon İlk Bölüm", "container_extension": "mp4", "info": {"duration_secs": 2600}},
                            ],
                        },
                    }
                elif action == "get_short_epg":
                    title_b64 = base64.b64encode("Şampiyonluk Maçı".encode("utf-8")).decode("ascii")
                    desc_b64 = base64.b64encode("Canlı stadyum yayını.".encode("utf-8")).decode("ascii")
                    listings = [
                        {
                            "title": title_b64,
                            "description": desc_b64,
                            "start_timestamp": 1732000000,
                            "stop_timestamp": 1732007200,
                        }
                    ]
                    if parent.xtream_short_epg_corrupt or params.get("stream_id", [""])[0] == "104":
                        listings.append(
                            {
                                "title": "%%%corrupt-not-base64%%%",
                                "description": "plain-fallback-desc",
                                "start_timestamp": 1732007200,
                                "stop_timestamp": 1732010800,
                            }
                        )
                    payload = {"epg_listings": listings}
                else:
                    payload = []

                self._send(200, "application/json", json.dumps(payload).encode("utf-8"), head_only=head_only)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self.port = int(self._httpd.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="mock-upstream")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def __enter__(self) -> "MockUpstreamServer":
        return self.start()

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def requests_for(self, path_prefix: str) -> List[RecordedRequest]:
        with self._lock:
            return [r for r in self.requests if r.path.startswith(path_prefix)]

    def clear_requests(self) -> None:
        with self._lock:
            self.requests.clear()

    def _build_m3u_plus_playlist(self) -> str:
        base = self.base_url
        return (
            f'\ufeff#EXTM3U url-tvg="{base}/guide.xml?token=epg123"\n'
            f'#EXTINF:-1 tvg-id="bein1.tr" tvg-logo="{base}/posters/thumb.png" group-title="Spor, Canlı",TR: BeIN Sports 1 FHD\n'
            f'{base}/streams/live.m3u8\n'
            f'#EXTINF:-1 tvg-id="bein1sd.tr" group-title="Spor",BeIN Sports 1 SD\n'
            f'{base}/streams/live.m3u8?ch=sd\n'
            f'#EXTINF:-1 tvg-id="yildiz.tr" group-title="Spor",TR: TRT Spor Yıldız HD\n'
            f'{base}/streams/live.m3u8?ch=yildiz\n'
            f'#EXTINF:-1 tvg-id="haber.tr" group-title="Haber, Dünya" tvg-name="Haber",Haber Kanalı (FHD)\n'
            f'{base}/streams/live.m3u8?ch=haber\n'
            f'#EXTINF:-1 group-title="Komedi" type="movie" tvg-logo="{base}/posters/thumb.png",Işıklar İçinde\n'
            f'{base}/streams/sample.mp4\n'
            f'#EXTINF:-1 group-title="Korku +18" type="movie",Korku Gecesi +18\n'
            f'{base}/streams/sample.mp4?m=horror\n'
        )

    def _build_plain_m3u_playlist(self) -> str:
        base = self.base_url
        return (
            f'#EXTM3U\n'
            f'#EXTINF:-1 tvg-id="bein1.tr" tvg-logo="{base}/posters/thumb.png" group-title="Spor",TR: BeIN Sports 1 FHD\n'
            f'{base}/streams/live.m3u8\n'
            f'#EXTINF:-1 tvg-id="bein1sd.tr" group-title="Spor",BeIN Sports 1 SD\n'
            f'{base}/streams/live.m3u8\n'
            f'#EXTINF:-1 tvg-id="yildiz.tr" group-title="Spor",TR: TRT Spor Yıldız HD\n'
            f'{base}/streams/live.m3u8\n'
            f'#EXTINF:-1 tvg-id="haber.tr" group-title="Haber",Haber Kanalı HD\n'
            f'{base}/streams/live.m3u8\n'
            f'#EXTINF:-1 group-title="Komedi" type="movie" tvg-logo="{base}/posters/thumb.png",Işıklar İçinde\n'
            f'{base}/streams/sample.mp4\n'
        )

    def _build_live_m3u8(self) -> str:
        return (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-TARGETDURATION:4\n"
            '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
            "#EXTINF:4.0,\n"
            "seg0.ts\n"
            "#EXT-X-ENDLIST\n"
        )

    def _build_xmltv(self, today: dt.date, tomorrow: dt.date) -> str:
        t_str = today.strftime("%Y%m%d")
        tm_str = tomorrow.strftime("%Y%m%d")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<tv>"
            '<channel id="bein1.tr"><display-name>BeIN Sports 1</display-name></channel>'
            '<channel id="yildiz.tr"><display-name>TRT Spor Star</display-name></channel>'
            '<channel id="trtspor.tr"><display-name>TRT Spor</display-name></channel>'
            f'<programme start="{t_str}190000 +0300" stop="{t_str}210000 +0300" channel="bein1.tr">'
            "<title>Süper Lig Derbisi</title>"
            "<category>Sports</category>"
            "<desc>Haftanın karşılaşması</desc>"
            "</programme>"
            f'<programme start="{t_str}213000 +0300" stop="{t_str}230000 +0300" channel="yildiz.tr">'
            "<title>Basketbol Ligi</title>"
            "<category>Basketball</category>"
            "</programme>"
            f'<programme start="{tm_str}180000 +0300" stop="{tm_str}200000 +0300" channel="bein1.tr">'
            "<title>Yarınki Kupa Maçı</title>"
            "<category>Football</category>"
            "</programme>"
            "</tv>"
        )

    def _build_sporekrani_html(self, day_str: str) -> str:
        state = {
            "common": {
                "eventRows": [
                    {
                        "id": 9001,
                        "date_time": f"{day_str} 20:45:00",
                        "sport_name": "Futbol",
                        "name": "Derbi Karşılaşması",
                        "league_name": "Süper Lig",
                        "event_type_name": "match",
                        "featured": 1,
                        "channels": [1],
                    }
                ],
                "eventChannels": {
                    "1": {"id": 1, "name": "BeIN Sports 1", "active": 1},
                },
            }
        }
        return (
            "<!doctype html><html><head></head><body>"
            f"<script>window.__INITIAL_STATE__={json.dumps(state, ensure_ascii=False)};</script>"
            "</body></html>"
        )

    def _build_netflix_html(self, week_str: str, is_tv: bool = False) -> str:
        if is_tv:
            data = {
                "top10Show": {
                    "top10Video": {
                        "title": "Gece Yolculuğu",
                        "releaseYear": 2025,
                        "videoId": 81000002,
                        "parentShow": {"title": "Gece Yolculuğu", "videoId": 81000002},
                    },
                    "top10": {"category": "TV", "weeklyRank": 1, "weekEndDate": week_str},
                }
            }
        else:
            data = {
                "top10Movie": {
                    "top10Video": {
                        "title": "Işıklar İçinde",
                        "releaseYear": 2025,
                        "videoId": 81000001,
                    },
                    "top10": {"category": "MOVIES", "weeklyRank": 1, "weekEndDate": week_str},
                }
            }
        encoded = json.dumps({"data": data}, ensure_ascii=False).replace("\\", "\\\\").replace("'", "\\'")
        return f"<html><body><script>netflix.reactContext.models.graphql = JSON.parse('{encoded}');</script></body></html>"
