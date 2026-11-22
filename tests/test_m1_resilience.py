"""M1 Python/Windows network resilience, M3U Plus, desktop, pause & packaging unit tests."""
from __future__ import annotations

import ast
import gzip
import hashlib
import http.client
import json
import os
import signal
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server
import playback

ROOT = Path(__file__).resolve().parents[1]


class UrlValidationAndSsrfTests(unittest.TestCase):
    def test_validate_host_vs_validate_source_url(self):
        self.assertEqual(server.validate_host('http://xtream.example:8080/'), 'http://xtream.example:8080')
        with self.assertRaises(ValueError):
            server.validate_host('http://xtream.example:8080/get.php?username=u1&type=m3u_plus')
        with self.assertRaises(ValueError):
            server.validate_host('http://xtream.example:8080/#frag')

        m3u_url = 'http://provider.example:8080/get.php?username=u1&password=p1&type=m3u_plus&output=mpegts'
        self.assertEqual(server.validate_source_url(m3u_url), m3u_url)
        epg_url = 'https://epg.example/xmltv.php?id=123&tz=tr'
        self.assertEqual(server.validate_source_url(epg_url), epg_url)

        for bad in (
            'ftp://provider.example/list.m3u',
            'http://user:pass@provider.example/list.m3u',
            'http://provider.example/list.m3u#fragment',
            'http://provider.example:99999/list.m3u',
            'not-a-url',
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    server.validate_source_url(bad)

    def test_ssrf_blocks_loopback_link_local_multicast_unspecified_and_defaults_lan_off(self):
        for blocked in (
            'http://127.0.0.1:9999/list.m3u?x=1',
            'http://[::1]:9999/list.m3u',
            'http://169.254.169.254/latest/meta-data/',
            'http://0.0.0.0:8080/list.m3u',
            'http://224.0.0.1:8080/list.m3u',
            'http://192.168.1.50:8080/list.m3u',
            'http://10.0.0.5:8080/list.m3u',
            'http://[::ffff:127.0.0.1]:8080/list.m3u',
            'http://provider.example:99999/list.m3u',
        ):
            with self.subTest(blocked=blocked):
                with patch.dict(os.environ, {'MAVIE_ALLOW_LAN_SOURCES': ''}):
                    with self.assertRaises(ValueError):
                        server.safe_public_url(blocked)

    def test_safe_public_url_ipv6_zone_id_and_configurable_lan_opt_in(self):
        with patch.object(
            server.socket,
            'getaddrinfo',
            return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('fe80::1%lo0', 80, 0, 1))],
        ):
            with self.assertRaises(ValueError):
                server.safe_public_url('http://fe80-host.example/list.m3u')

        with patch.dict(os.environ, {'MAVIE_ALLOW_LAN_SOURCES': '1'}):
            for lan_url in (
                'http://192.168.1.50:8080/get.php?type=m3u_plus',
                'http://10.0.0.5:8080/list.m3u',
                'http://172.16.10.4:8080/list.m3u',
            ):
                self.assertEqual(server.safe_public_url(lan_url), lan_url)

            # Even with LAN opt-in, loopback, link-local, multicast, unspecified stay blocked
            for always_blocked in (
                'http://127.0.0.1:8080/list.m3u',
                'http://[::1]:8080/list.m3u',
                'http://[::ffff:127.0.0.1]:8080/list.m3u',
                'http://169.254.169.254/latest/meta-data/',
                'http://0.0.0.0:8080/list.m3u',
                'http://224.0.0.1:8080/list.m3u',
            ):
                with self.subTest(always_blocked=always_blocked):
                    with self.assertRaises(ValueError):
                        server.safe_public_url(always_blocked)


class ServerM3uPlusAndNetworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mavie-m1-net-')
        self.data = Path(self.tmp.name)
        self.orig_data = server.DATA
        self.orig_db = server.DB
        self.orig_cfg = server.CONFIG_FILE
        self.orig_provider = server.provider
        self.orig_playback = server.playback
        self.orig_sync_state = dict(server.sync_state)

        server.DATA = self.data
        server.DB = self.data / 'state.sqlite3'
        server.CONFIG_FILE = self.data / 'config.json'
        server.initialize()
        server.provider = server.Provider({})
        server.playback = playback.PlaybackManager(self.data, ffmpeg_path=None)
        server.sync_state.update(syncing=False, error=None)
        server.media_sessions.clear()
        server.internal_sources.clear()
        with server.connect() as db:
            db.execute('INSERT INTO devices VALUES(?,?)', (hashlib.sha256(b'm1-dev').hexdigest(), server.stamp()))

        self.mock_state = {
            'mode': 'ok',
            'attempts': 0,
            'm3u_fetches': 0,
            'epg_fetches': 0,
            'body': b'',
        }
        state = self.mock_state

        class MockUpstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_args): pass
            def do_GET(self):
                state['attempts'] += 1
                if self.path.startswith('/get.php'):
                    state['m3u_fetches'] += 1
                    mode = state['mode']
                    if mode == 'status_401':
                        self.send_response(401); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'status_403':
                        self.send_response(403); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'status_404':
                        self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'status_429':
                        self.send_response(429); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'status_500':
                        self.send_response(500); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'empty':
                        body = b'#EXTM3U\n'
                        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
                        self.wfile.write(body); return
                    if mode == 'timeout':
                        time.sleep(0.4)
                        return
                    if mode == 'flaky_recover':
                        if state['attempts'] == 1:
                            self.send_response(503); self.send_header('Content-Length', '0'); self.end_headers(); return
                        if state['attempts'] == 2:
                            self.send_response(200); self.send_header('Transfer-Encoding', 'chunked'); self.end_headers()
                            self.wfile.write(b'10\r\n#EXTM3U\n'); self.wfile.flush(); self.close_connection = True; return
                    if mode == 'redirect_ok':
                        self.send_response(302)
                        self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/get.php?final=1')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        state['mode'] = 'ok'
                        return
                    if mode == 'redirect_ssrf':
                        self.send_response(302)
                        self.send_header('Location', 'http://127.0.0.1:9999/secret')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if mode == 'gzip_header':
                        body = gzip.compress(state['body'])
                        self.send_response(200)
                        self.send_header('Content-Encoding', 'GZIP')
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    if mode == 'gzip_magic':
                        body = gzip.compress(state['body'])
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    body = state['body']
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if self.path.startswith('/xmltv.php'):
                    state['epg_fetches'] += 1
                    xml = (
                        b'<?xml version="1.0" encoding="UTF-8"?><tv>'
                        b'<channel id="c1"><display-name>Spor 1</display-name></channel>'
                        b'<programme start="20261121200000 +0300" stop="20261121220000 +0300" channel="c1">'
                        b'<title>Derby Match</title><category>Football</category></programme></tv>'
                    )
                    self.send_response(200); self.send_header('Content-Length', str(len(xml))); self.end_headers()
                    self.wfile.write(xml); return

                if self.path == '/live.m3u8':
                    manifest = gzip.compress(b'#EXTM3U\n#EXTINF:4.0,\nhttp://127.0.0.1:' + str(self.server.server_port).encode() + b'/seg.ts\n')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                    self.send_header('Content-Encoding', 'gzip')
                    self.send_header('Content-Length', str(len(manifest)))
                    self.end_headers()
                    self.wfile.write(manifest)
                    return

                if self.path == '/seg.ts':
                    self.send_response(200)
                    self.send_header('Content-Type', 'video/mp2t')
                    self.send_header('Content-Length', '4')
                    self.end_headers()
                    self.wfile.write(b'TS01')
                    return

                if self.path == '/bad-proxy':
                    self.send_response(403); self.send_header('Content-Length', '0'); self.end_headers(); return

                if self.path.startswith('/player_api.php'):
                    mode = state['mode']
                    if mode == 'xtream_401':
                        self.send_response(401); self.send_header('Content-Length', '0'); self.end_headers(); return
                    if mode == 'xtream_flaky':
                        if state['attempts'] == 1:
                            self.send_response(502); self.send_header('Content-Length', '0'); self.end_headers(); return
                        payload = gzip.compress(b'\xef\xbb\xbf' + json.dumps({'user_info': {'auth': 1, 'status': 'Active'}}).encode('utf-8'))
                        self.send_response(200)
                        self.send_header('Content-Encoding', 'GZIP')
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), MockUpstream)
        self.upstream.daemon_threads = True
        self.up_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.up_thread.start()
        self.up_port = self.upstream.server_port

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.srv.daemon_threads = True
        server.HTTP_PORT = self.srv.server_port
        self.srv_thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.srv_thread.start()

    def tearDown(self):
        server.stop_all()
        if server.playback is not None:
            server.playback.close()
        server.playback = self.orig_playback
        self.srv.shutdown()
        self.srv.server_close()
        self.srv_thread.join(timeout=2)
        self.upstream.shutdown()
        self.upstream.server_close()
        self.up_thread.join(timeout=2)
        server.DATA = self.orig_data
        server.DB = self.orig_db
        server.CONFIG_FILE = self.orig_cfg
        server.provider = self.orig_provider
        server.sync_state.clear()
        server.sync_state.update(self.orig_sync_state)
        self.tmp.cleanup()

    def req(self, method, path, data=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.srv.server_port, timeout=10)
        headers = {'Cookie': 'mavie_device=m1-dev'}
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, hdrs, raw

    def wait_sync_done(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not server.sync_state['syncing']:
                return
            time.sleep(0.02)
        self.fail('sync_catalog did not finish in time')

    def _allow_mock_upstream_only(self, url):
        parsed = server.urllib.parse.urlsplit(url)
        if parsed.hostname == '127.0.0.1' and parsed.port == self.up_port:
            return url
        return self._orig_safe_public_url(url)

    def test_m3u_plus_query_settings_single_fetch_gzip_and_sports_epg(self):
        self._orig_safe_public_url = server.safe_public_url
        sample_m3u = (
            '\ufeff#EXTM3U url-tvg="http://127.0.0.1:' + str(self.up_port) + '/xmltv.php?token=epg1"\n'
            '#EXTINF:-1 tvg-name="News, Sports" group-title="World, News",Spor 1\n'
            f'http://127.0.0.1:{self.up_port}/live/u/p/101?output=mpegts\n'
        ).encode('utf-8') + b'#EXTINF:-1 group-title="BadBytes",Kanal \xff\n' + f'http://127.0.0.1:{self.up_port}/movie/u/p/202\n'.encode('utf-8')
        self.mock_state['body'] = sample_m3u

        with patch.object(server, 'safe_public_url', side_effect=self._allow_mock_upstream_only):
            for mode in ('gzip_header', 'gzip_magic', 'redirect_ok', 'flaky_recover'):
                with self.subTest(mode=mode):
                    self.mock_state['mode'] = mode
                    self.mock_state['attempts'] = 0
                    self.mock_state['m3u_fetches'] = 0
                    m3u_url = f'http://127.0.0.1:{self.up_port}/get.php?username=u1&password=p1&type=m3u_plus&output=mpegts&m={mode}'
                    epg_url = f'http://127.0.0.1:{self.up_port}/xmltv.php?token=custom'
                    with patch.object(server.time, 'sleep'):
                        st, _, raw = self.req('POST', '/api/settings', {
                            'type': 'm3u',
                            'name': 'Test M3U Plus',
                            'm3uUrl': m3u_url,
                            'epgUrl': epg_url,
                        })
                    self.assertEqual(st, 200, raw)
                    self.wait_sync_done()
                    self.assertIsNone(server.sync_state['error'])
                    # Single-shot handoff: sync_catalog must not double-fetch get.php
                    if mode in ('gzip_header', 'gzip_magic'):
                        self.assertEqual(self.mock_state['m3u_fetches'], 1)

            # Query-string EPG URL works on GET /api/sports
            epg_query = f'http://127.0.0.1:{self.up_port}/xmltv.php?token=epg2&fmt=xml'
            import datetime as dt
            with patch.object(server.sports, 'selected_date', return_value=dt.date(2026, 11, 21)):
                st_sp, _, raw_sp = self.req('GET', '/api/sports?' + server.urllib.parse.urlencode({'epgUrl': epg_query}))
            self.assertEqual(st_sp, 200, raw_sp)
            guide = json.loads(raw_sp)
            self.assertEqual(guide['sourceType'], 'xmltv')
            self.assertEqual(guide['events'][0]['title'], 'Derby Match')

            # Gzipped HLS manifest via Handler.proxy
            sid = 'test-hls-gzip'
            with server.resource_lock:
                server.media_sessions[sid] = {'resources': {}, 'reverse': {}, 'touched': time.monotonic()}
            proxy_path = server.resource_for(sid, f'http://127.0.0.1:{self.up_port}/live.m3u8')
            st_px, _, raw_px = self.req('GET', proxy_path)
            self.assertEqual(st_px, 200, raw_px)
            self.assertIn(b'/media/test-hls-gzip/proxy/', raw_px)

            # Upstream 403 on proxy returns 502 with structured JSON, not 500
            bad_proxy_path = server.resource_for(sid, f'http://127.0.0.1:{self.up_port}/bad-proxy')
            st_bad, _, raw_bad = self.req('GET', bad_proxy_path)
            self.assertEqual(st_bad, 502, raw_bad)
            self.assertIn('HTTP 403', json.loads(raw_bad)['error'])

    def test_http_errors_ssrf_timeout_and_non_empty_catalog_guard_preserve_existing_items(self):
        self._orig_safe_public_url = server.safe_public_url
        self.mock_state['body'] = (
            f'#EXTM3U\n#EXTINF:-1,Kanal 1\nhttp://127.0.0.1:{self.up_port}/live/u/p/1\n'.encode('utf-8')
        )
        m3u_url = f'http://127.0.0.1:{self.up_port}/get.php?username=u1&password=p1&type=m3u_plus'
        with patch.object(server, 'safe_public_url', side_effect=self._allow_mock_upstream_only):
            st, _, _ = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': m3u_url})
            self.assertEqual(st, 200)
            self.wait_sync_done()

        with server.connect() as db:
            before_count = db.execute('SELECT count(*) FROM items').fetchone()[0]
        self.assertEqual(before_count, 1)

        # Unpatched SSRF targets return 400 and keep existing catalog
        for ssrf_url in ('http://127.0.0.1:9999/list.m3u?a=1', 'http://169.254.169.254/latest/meta-data/'):
            st, _, raw = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': ssrf_url})
            self.assertEqual(st, 400, raw)

        with patch.object(server, 'safe_public_url', side_effect=self._allow_mock_upstream_only):
            # Redirect to SSRF blocked with 400
            self.mock_state['mode'] = 'redirect_ssrf'
            st, _, raw = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': m3u_url + '&r=1'})
            self.assertEqual(st, 400, raw)

            # Empty M3U rejected with 400 without wiping existing catalog
            self.mock_state['mode'] = 'empty'
            st, _, raw = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': m3u_url + '&e=1'})
            self.assertEqual(st, 400, raw)

            # HTTP 401/403/404/429/500 return 502 with clear Turkish message and keep existing catalog
            for err_mode, expected_tag in (
                ('status_401', '401'),
                ('status_403', '403'),
                ('status_404', '404'),
                ('status_429', '429'),
                ('status_500', '500'),
            ):
                with self.subTest(err_mode=err_mode):
                    self.mock_state['mode'] = err_mode
                    with patch.object(server.time, 'sleep'):
                        st, _, raw = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': m3u_url + '&err=' + err_mode})
                    self.assertEqual(st, 502, raw)
                    self.assertIn(expected_tag, json.loads(raw)['error'])

            # Timeout returns 502
            self.mock_state['mode'] = 'timeout'
            with patch.object(server, 'remote_read', side_effect=lambda url, **kw: server.remote_read.__wrapped__(url, timeout=0.05, retries=0) if hasattr(server.remote_read, '__wrapped__') else (_ for _ in ()).throw(RuntimeError('Kaynak sunucu zaman aşımına uğradı.'))):
                st, _, raw = self.req('POST', '/api/settings', {'type': 'm3u', 'm3uUrl': m3u_url + '&t=1'})
            self.assertEqual(st, 502, raw)

            # Manual sync hitting empty M3U triggers non-empty guard and preserves items
            self.mock_state['mode'] = 'empty'
            server.sync_catalog()
            self.assertTrue(server.sync_state['error'])

        with server.connect() as db:
            after_count = db.execute('SELECT count(*) FROM items').fetchone()[0]
        self.assertEqual(after_count, 1)

    def test_provider_api_handles_gzip_bom_retries_and_http_errors(self):
        self._orig_safe_public_url = server.safe_public_url
        prov = server.Provider({
            'type': 'xtream',
            'host': f'http://127.0.0.1:{self.up_port}',
            'username': 'u1',
            'password': 'p1',
        })
        with patch.object(server, 'safe_public_url', side_effect=self._allow_mock_upstream_only):
            self.mock_state['mode'] = 'xtream_flaky'
            self.mock_state['attempts'] = 0
            with patch.object(server.time, 'sleep'):
                data = prov.api()
            self.assertEqual(self.mock_state['attempts'], 2)
            self.assertEqual(data['user_info']['status'], 'Active')

            self.mock_state['mode'] = 'xtream_401'
            with self.assertRaises(RuntimeError) as ctx:
                prov.api()
            self.assertIn('401', str(ctx.exception))


class DesktopProxyAndWindowsPauseTests(unittest.TestCase):
    def test_desktop_wait_for_health_bypasses_system_proxy(self):
        import sys
        sys.path.insert(0, str(ROOT / 'desktop'))
        import mavie_desktop

        class HealthHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_GET(self):
                body = json.dumps({'app': 'mavie', 'ok': True}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = ThreadingHTTPServer(('127.0.0.1', 0), HealthHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        fake_srv_thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
        fake_srv_thread.start()
        try:
            with patch.dict(os.environ, {
                'HTTP_PROXY': 'http://127.0.0.1:1',
                'HTTPS_PROXY': 'http://127.0.0.1:1',
                'http_proxy': 'http://127.0.0.1:1',
                'https_proxy': 'http://127.0.0.1:1',
            }):
                ok = mavie_desktop.wait_for_health(
                    f'http://127.0.0.1:{srv.server_port}',
                    fake_srv_thread,
                    [],
                    timeout=3.0,
                )
            self.assertTrue(ok)
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=2)
            fake_srv_thread.join(timeout=2)

    def test_windows_pause_without_sigstop_returns_200_soft_pause(self):
        with tempfile.TemporaryDirectory(prefix='mavie-win-pause-') as tmp:
            data = Path(tmp)
            orig_data, orig_db, orig_cfg = server.DATA, server.DB, server.CONFIG_FILE
            orig_playback = server.playback
            server.DATA = data
            server.DB = data / 'state.sqlite3'
            server.CONFIG_FILE = data / 'config.json'
            server.initialize()
            with server.connect() as db:
                db.execute('INSERT INTO devices VALUES(?,?)', (hashlib.sha256(b'win-dev').hexdigest(), server.stamp()))
            mgr = playback.PlaybackManager(data, ffmpeg_path=None)
            server.playback = mgr
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            srv.daemon_threads = True
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()

            class FakeProc:
                def poll(self): return None
                def send_signal(self, _sig): raise AssertionError('Must not send signal when SIGSTOP/SIGCONT is None')
                def terminate(self): pass
                def wait(self, timeout=None): return 0

            sid = 'a' * 32
            session_dir = data / 'playback' / sid
            session_dir.mkdir(parents=True, exist_ok=True)
            sess = playback._Session(sid, session_dir, FakeProc(), time.monotonic())
            with mgr._lock:
                mgr._sessions[sid] = sess
            with server.resource_lock:
                server.media_sessions[sid] = {'resources': {}, 'reverse': {}, 'touched': time.monotonic(), 'sourceToken': 'tok'}

            try:
                # Simulate Windows signal module lacking SIGSTOP and SIGCONT
                with patch.object(playback.signal, 'SIGSTOP', None, create=True), \
                     patch.object(playback.signal, 'SIGCONT', None, create=True):
                    res = mgr.pause(sid, True)
                    self.assertEqual(res, {'paused': True, 'processPaused': False, 'softPause': True})
                    self.assertTrue(sess.paused)
                    self.assertFalse(sess.process_paused)

                    conn = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
                    conn.request('POST', f'/api/play/{sid}/pause', json.dumps({'paused': False}), {
                        'Cookie': 'mavie_device=win-dev',
                        'Content-Type': 'application/json',
                    })
                    resp = conn.getresponse()
                    body = json.loads(resp.read())
                    conn.close()
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(body, {'ok': True, 'paused': False, 'processPaused': False, 'softPause': True})
            finally:
                with mgr._lock:
                    mgr._sessions.pop(sid, None)
                with server.resource_lock:
                    server.media_sessions.pop(sid, None)
                mgr.close()
                srv.shutdown()
                srv.server_close()
                t.join(timeout=2)
                server.playback = orig_playback
                server.DATA, server.DB, server.CONFIG_FILE = orig_data, orig_db, orig_cfg

    def test_all_owned_python_files_specify_utf8_encoding_for_read_and_write_text(self):
        for rel in ('server.py', 'm3u.py', 'discovery.py', 'sports.py', 'playback.py', 'local_media.py', 'desktop/mavie_desktop.py'):
            tree = ast.parse((ROOT / rel).read_text(encoding='utf-8'), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                    kw_names = {kw.arg for kw in node.keywords}
                    self.assertIn('encoding', kw_names, f'{rel}:{node.lineno} calls {node.func.attr} without explicit encoding=')


class WindowsPackagingStaticTests(unittest.TestCase):
    def test_windows_spec_iss_and_bat_are_valid_and_brand_clean(self):
        spec_path = ROOT / 'windows' / 'mavie.spec'
        iss_path = ROOT / 'windows' / 'MavieSetup.iss'
        bat_path = ROOT / 'windows' / 'Mavie.bat'

        spec_src = spec_path.read_text(encoding='utf-8')
        iss_src = iss_path.read_text(encoding='utf-8')
        bat_src = bat_path.read_text(encoding='utf-8')

        ast.parse(spec_src, filename=str(spec_path))

        for path in (
            ROOT / 'desktop' / 'mavie_desktop.py',
            ROOT / 'windows' / 'mavie.ico',
            ROOT / 'public',
            ROOT / 'legal',
        ):
            self.assertTrue(path.exists(), f'Missing packaging target: {path}')

        for mod in ('server', 'playback', 'discovery', 'sports', 'm3u', 'local_media', 'tzdata', 'zoneinfo'):
            self.assertIn(f"'{mod}'", spec_src, f'Missing hiddenimport {mod} in mavie.spec')
        self.assertIn("'X utf8'", spec_src)
        self.assertIn('console=False', spec_src)

        self.assertIn('SetupIconFile=mavie.ico', iss_src)
        self.assertIn('OutputDir=..\\dist', iss_src)
        self.assertIn('MyAppExeName "Mavie.exe"', iss_src)
        self.assertIn('Turkish.isl', iss_src)
        self.assertIn('Default.isl', iss_src)
        iss_src.encode('ascii')

        self.assertIn('desktop\\mavie_desktop.py', bat_src)

        legacy_tokens = ('vre' + 'lio', 'cin' + 'eva', 'ak' + 'is')
        for name, txt in (('mavie.spec', spec_src), ('MavieSetup.iss', iss_src), ('Mavie.bat', bat_src)):
            low = txt.lower()
            for tok in legacy_tokens:
                self.assertNotIn(tok, low, f'Legacy token {tok!r} found in {name}')
