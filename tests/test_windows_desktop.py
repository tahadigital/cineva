"""Unit tests for the Windows native desktop launcher (pywebview/WebView2) and web-mode separation."""
from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'desktop') not in sys.path:
    sys.path.insert(0, str(ROOT / 'desktop'))

import mavie_desktop  # noqa: E402
import server  # noqa: E402


class _FakeEventSlot:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def fire(self) -> None:
        for fn in list(self.handlers):
            fn()


class _FakeEvents:
    def __init__(self) -> None:
        self.shown = _FakeEventSlot()
        self.loaded = _FakeEventSlot()
        self.closed = _FakeEventSlot()


class _FakeNativeHandle:
    def __init__(self, value: int) -> None:
        self._value = value

    def ToInt64(self) -> int:
        return self._value


class _FakeWindow:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.events = _FakeEvents()
        self.fullscreen = False
        self.toggle_calls = 0
        self.evaluated_js: list[str] = []
        self.native = types.SimpleNamespace(Handle=_FakeNativeHandle(0x12345678))

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.toggle_calls += 1

    def evaluate_js(self, script: str) -> None:
        self.evaluated_js.append(script)


def _make_fake_webview(start_side_effect=None):
    created: list[_FakeWindow] = []
    start_calls: list[dict] = []
    mod = types.ModuleType('webview')
    mod.settings = {}

    def create_window(**kwargs):
        win = _FakeWindow(kwargs)
        created.append(win)
        return win

    def start(**kwargs):
        start_calls.append(kwargs)
        if start_side_effect is not None:
            return start_side_effect(created[-1], kwargs)
        win = created[-1]
        win.events.shown.fire()
        win.events.loaded.fire()
        win.events.closed.fire()
        return None

    mod.create_window = create_window
    mod.start = start
    return mod, created, start_calls


def _fake_server_runner(started_ports: list[int]):
    def _run_server(*, host, port, install_signals, stop_event, ready_event):
        started_ports.append(port)
        ready_event.set()
        stop_event.wait(5.0)
    return _run_server


class WindowsNativeDesktopTests(unittest.TestCase):
    def test_parse_launch_mode_defaults_and_flags(self) -> None:
        self.assertEqual(mavie_desktop.parse_launch_mode([]), 'native')
        self.assertEqual(mavie_desktop.parse_launch_mode(['--web']), 'web')
        self.assertEqual(mavie_desktop.parse_launch_mode(['--browser']), 'web')
        self.assertEqual(mavie_desktop.parse_launch_mode(['--serve']), 'serve')
        self.assertEqual(mavie_desktop.parse_launch_mode(['--serve', '--port', '9000']), 'serve')

    def test_native_window_launches_pywebview_edgechromium_with_persistent_storage(self) -> None:
        fake_webview, created, start_calls = _make_fake_webview()
        logs: list[str] = []
        stop_event = threading.Event()

        with tempfile.TemporaryDirectory(prefix='mavie-win-native-') as tmp:
            data_dir = Path(tmp)
            with patch.dict(sys.modules, {'webview': fake_webview}), \
                 patch.object(mavie_desktop.sys, 'platform', 'win32'), \
                 patch.object(mavie_desktop, '_set_windows_app_user_model_id') as app_id_mock, \
                 patch.object(mavie_desktop, '_apply_windows_native_chrome', return_value=True) as chrome_mock:
                ok = mavie_desktop.launch_native_window(
                    'http://127.0.0.1:18844',
                    data_dir,
                    stop_event,
                    log_fn=logs.append,
                )

            self.assertTrue(ok)
            self.assertTrue(stop_event.is_set())
            self.assertTrue((data_dir / 'webview2').is_dir())
            app_id_mock.assert_called_once()
            chrome_mock.assert_called_once()

            # Check global pywebview settings
            self.assertTrue(fake_webview.settings['ALLOW_DOWNLOADS'])
            self.assertTrue(fake_webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'])
            self.assertTrue(fake_webview.settings['ALLOW_FILE_URLS'])

            # Check window parameters
            self.assertEqual(len(created), 1)
            win = created[0]
            self.assertEqual(win.kwargs['title'], 'Mavie')
            self.assertEqual(win.kwargs['url'], 'http://127.0.0.1:18844/')
            self.assertEqual(win.kwargs['width'], 1360)
            self.assertEqual(win.kwargs['height'], 840)
            self.assertEqual(win.kwargs['min_size'], (960, 600))
            self.assertTrue(win.kwargs['resizable'])
            self.assertEqual(win.kwargs['background_color'], '#07090F')

            # Check fullscreen JS bridge injection & behavior
            self.assertEqual(len(win.evaluated_js), 1)
            self.assertIn('fullscreenchange', win.evaluated_js[0])
            bridge = win.kwargs['js_api']
            self.assertTrue(bridge.set_fullscreen(True))
            self.assertTrue(win.fullscreen)
            self.assertFalse(bridge.set_fullscreen(False))
            self.assertFalse(win.fullscreen)
            self.assertEqual(win.toggle_calls, 2)

            # Check Edge WebView2 backend & persistent storage args
            self.assertEqual(len(start_calls), 1)
            self.assertEqual(start_calls[0]['gui'], 'edgechromium')
            self.assertFalse(start_calls[0]['private_mode'])
            self.assertEqual(start_calls[0]['storage_path'], str(data_dir / 'webview2'))
            self.assertFalse(any('Traceback' in line for line in logs))

    def test_default_main_uses_native_window_and_never_opens_external_browser(self) -> None:
        fake_webview, created, start_calls = _make_fake_webview()
        started_ports: list[int] = []

        with tempfile.TemporaryDirectory(prefix='mavie-main-native-') as tmp:
            with patch.dict(os.environ, {'MAVIE_DATA_DIR': tmp, 'MAVIE_PORT': '18910'}, clear=False), \
                 patch.dict(sys.modules, {'webview': fake_webview}), \
                 patch.object(mavie_desktop.sys, 'platform', 'win32'), \
                 patch.object(mavie_desktop, '_acquire_windows_mutex', return_value=None), \
                 patch.object(mavie_desktop, '_set_windows_app_user_model_id'), \
                 patch.object(mavie_desktop, '_apply_windows_native_chrome', return_value=True), \
                 patch.object(mavie_desktop, 'find_free_port', return_value=18910), \
                 patch.object(mavie_desktop, 'wait_for_health', return_value=True), \
                 patch.object(server, 'run_server', side_effect=_fake_server_runner(started_ports)), \
                 patch.object(mavie_desktop, 'launch_browser_or_fallback') as browser_fallback_mock, \
                 patch.object(mavie_desktop.webbrowser, 'open') as wb_mock:
                rc = mavie_desktop.main(argv=[])

            self.assertEqual(rc, 0)
            self.assertEqual(started_ports, [18910])
            self.assertEqual(len(created), 1)
            self.assertEqual(start_calls[0]['gui'], 'edgechromium')
            browser_fallback_mock.assert_not_called()
            wb_mock.assert_not_called()
            log_text = (Path(tmp) / 'desktop.log').read_text(encoding='utf-8')
            self.assertIn('Mavie desktop ready at http://127.0.0.1:18910 (mode=native)', log_text)
            self.assertNotIn('Traceback', log_text)

    def test_windows_dark_titlebar_and_icon_chrome_applied_with_fallback_attr(self) -> None:
        dwm_calls: list[int] = []
        icon_calls: list[int] = []

        def fake_dwm(_hwnd, attr, _val_ptr, _size):
            code = attr.value if hasattr(attr, 'value') else int(attr)
            dwm_calls.append(code)
            # Simulate older Windows 10 rejecting attribute 20 and accepting 19
            if code == mavie_desktop.DWMWA_USE_IMMERSIVE_DARK_MODE:
                return -1
            return 0

        fake_dwmapi = types.SimpleNamespace(DwmSetWindowAttribute=fake_dwm)
        fake_user32 = types.SimpleNamespace(
            LoadImageW=MagicMock(return_value=0xBEEF),
            SendMessageW=lambda _hwnd, msg, slot, _hicon: icon_calls.append((msg, slot)),
            FindWindowW=MagicMock(return_value=0),
        )
        fake_windll = types.SimpleNamespace(dwmapi=fake_dwmapi, user32=fake_user32)
        fake_win = _FakeWindow({})

        with patch.object(mavie_desktop.sys, 'platform', 'win32'), \
             patch.object(mavie_desktop.ctypes, 'windll', fake_windll, create=True):
            applied = mavie_desktop._apply_windows_native_chrome(fake_win, ROOT / 'windows' / 'mavie.ico')

        self.assertTrue(applied)
        self.assertIn(mavie_desktop.DWMWA_USE_IMMERSIVE_DARK_MODE, dwm_calls)
        self.assertIn(mavie_desktop.DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, dwm_calls)
        self.assertEqual(
            icon_calls,
            [(mavie_desktop.WM_SETICON, mavie_desktop.ICON_BIG), (mavie_desktop.WM_SETICON, mavie_desktop.ICON_SMALL)],
        )

    def test_webview2_init_failure_falls_back_cleanly_with_zero_traceback_in_log(self) -> None:
        def failing_start(_win, _kwargs):
            raise RuntimeError('WebView2 runtime missing\nTraceback (simulated inner detail)')

        fake_webview, _created, _start_calls = _make_fake_webview(start_side_effect=failing_start)
        started_ports: list[int] = []

        with tempfile.TemporaryDirectory(prefix='mavie-wv-fail-') as tmp:
            with patch.dict(os.environ, {'MAVIE_DATA_DIR': tmp, 'MAVIE_PORT': '18911'}, clear=False), \
                 patch.dict(sys.modules, {'webview': fake_webview}), \
                 patch.object(mavie_desktop.sys, 'platform', 'win32'), \
                 patch.object(mavie_desktop, '_acquire_windows_mutex', return_value=None), \
                 patch.object(mavie_desktop, '_set_windows_app_user_model_id'), \
                 patch.object(mavie_desktop, 'find_free_port', return_value=18911), \
                 patch.object(mavie_desktop, 'wait_for_health', return_value=True), \
                 patch.object(mavie_desktop, 'get_lan_urls', return_value=['http://192.168.1.50:18911']), \
                 patch.object(server, 'run_server', side_effect=_fake_server_runner(started_ports)), \
                 patch.object(mavie_desktop, 'launch_browser_or_fallback', return_value=0) as fallback_mock:
                rc = mavie_desktop.main(argv=[])

            self.assertEqual(rc, 0)
            fallback_mock.assert_called_once()
            args, kwargs = fallback_mock.call_args
            self.assertEqual(args[0], 'http://127.0.0.1:18911')
            self.assertEqual(kwargs.get('lan_urls'), ['http://192.168.1.50:18911'])
            log_text = (Path(tmp) / 'desktop.log').read_text(encoding='utf-8')
            self.assertIn('Native WebView2 window failed', log_text)
            self.assertNotIn('Traceback', log_text)

    def test_missing_pywebview_import_falls_back_cleanly_without_traceback(self) -> None:
        logs: list[str] = []
        stop_event = threading.Event()
        real_import = __import__

        def block_webview(name, *args, **kwargs):
            if name == 'webview':
                raise ImportError("No module named 'webview'")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='mavie-no-wv-') as tmp:
            with patch.dict(sys.modules, {'webview': None}), \
                 patch('builtins.__import__', side_effect=block_webview):
                ok = mavie_desktop.launch_native_window(
                    'http://127.0.0.1:18912',
                    Path(tmp),
                    stop_event,
                    log_fn=logs.append,
                )

        self.assertFalse(ok)
        self.assertFalse(stop_event.is_set())
        self.assertTrue(any('Native desktop window unavailable' in line for line in logs))
        self.assertFalse(any('Traceback' in line for line in logs))

    def test_silent_early_webview_return_without_show_falls_back_cleanly(self) -> None:
        fake_webview, _created, _start_calls = _make_fake_webview(start_side_effect=lambda _w, _kw: None)
        logs: list[str] = []
        stop_event = threading.Event()

        with tempfile.TemporaryDirectory(prefix='mavie-early-ret-') as tmp:
            with patch.dict(sys.modules, {'webview': fake_webview}), \
                 patch.object(mavie_desktop.sys, 'platform', 'win32'), \
                 patch.object(mavie_desktop, '_set_windows_app_user_model_id'), \
                 patch.object(mavie_desktop.time, 'monotonic', side_effect=[10.0, 10.1]):
                ok = mavie_desktop.launch_native_window(
                    'http://127.0.0.1:18913',
                    Path(tmp),
                    stop_event,
                    log_fn=logs.append,
                )

        self.assertFalse(ok)
        self.assertFalse(stop_event.is_set())
        self.assertTrue(any('returned before showing' in line for line in logs))
        self.assertFalse(any('Traceback' in line for line in logs))

    def test_web_and_browser_flags_open_browser_and_control_window_with_lan_urls(self) -> None:
        for flag in ('--web', '--browser'):
            with self.subTest(flag=flag):
                started_ports: list[int] = []
                with tempfile.TemporaryDirectory(prefix='mavie-web-mode-') as tmp:
                    env = {'MAVIE_DATA_DIR': tmp, 'MAVIE_PORT': '18920'}
                    with patch.dict(os.environ, env, clear=False), \
                         patch.object(mavie_desktop, '_acquire_windows_mutex', return_value=None), \
                         patch.object(mavie_desktop, 'find_free_port', return_value=18920), \
                         patch.object(mavie_desktop, 'wait_for_health', return_value=True), \
                         patch.object(mavie_desktop, 'get_lan_urls', return_value=['http://192.168.1.42:18920']), \
                         patch.object(server, 'run_server', side_effect=_fake_server_runner(started_ports)), \
                         patch.object(mavie_desktop, 'launch_native_window') as native_mock, \
                         patch.object(mavie_desktop.webbrowser, 'open') as wb_mock, \
                         patch.object(mavie_desktop, 'show_fallback_window') as ctrl_mock:
                        os.environ.pop('MAVIE_NO_BROWSER', None)
                        rc = mavie_desktop.main(argv=[flag])

                    self.assertEqual(rc, 0)
                    native_mock.assert_not_called()
                    wb_mock.assert_called_once_with('http://127.0.0.1:18920/')
                    ctrl_mock.assert_called_once()
                    c_args, c_kwargs = ctrl_mock.call_args
                    self.assertEqual(c_args[0], 'http://127.0.0.1:18920')
                    self.assertEqual(c_kwargs['lan_urls'], ['http://192.168.1.42:18920'])
                    self.assertEqual(c_kwargs['mode'], 'web')
                    log_text = (Path(tmp) / 'desktop.log').read_text(encoding='utf-8')
                    self.assertIn('Mavie web mode ready at http://127.0.0.1:18920', log_text)
                    self.assertIn('http://192.168.1.42:18920', log_text)
                    self.assertNotIn('Traceback', log_text)

    def test_web_mode_respects_mavie_no_browser_env(self) -> None:
        stop_event = threading.Event()
        with patch.dict(os.environ, {'MAVIE_NO_BROWSER': '1'}), \
             patch.object(mavie_desktop, 'get_lan_urls', return_value=[]), \
             patch.object(mavie_desktop.webbrowser, 'open') as wb_mock, \
             patch.object(mavie_desktop, 'show_fallback_window') as ctrl_mock:
            rc = mavie_desktop.launch_web_mode('http://127.0.0.1:18921', 18921, stop_event)
        self.assertEqual(rc, 0)
        wb_mock.assert_not_called()
        ctrl_mock.assert_called_once()

    def test_serve_flag_delegates_to_server_main_and_strips_flag(self) -> None:
        observed_argv: list[str] = []

        def fake_server_main():
            observed_argv.extend(sys.argv)

        original_argv = list(sys.argv)
        with patch.object(server, 'main', side_effect=fake_server_main) as srv_main:
            rc = mavie_desktop.main(argv=['--serve', '--host', '127.0.0.1', '--port', '18930'])

        self.assertEqual(rc, 0)
        srv_main.assert_called_once()
        self.assertEqual(observed_argv[1:], ['--host', '127.0.0.1', '--port', '18930'])
        self.assertEqual(sys.argv, original_argv)

    def test_port_selection_skips_occupied_port_and_headless_smoke_cleans_up(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
            busy.bind(('0.0.0.0', 0))
            busy.listen(1)
            busy_port = int(busy.getsockname()[1])
            picked = mavie_desktop.find_free_port(busy_port)
            self.assertNotEqual(picked, busy_port)
            self.assertTrue(1 <= picked <= 65535)

        stop_seen = threading.Event()

        def tracking_server(*, host, port, install_signals, stop_event, ready_event):
            ready_event.set()
            if stop_event.wait(3.0):
                stop_seen.set()

        with tempfile.TemporaryDirectory(prefix='mavie-smoke-clean-') as tmp:
            with patch.dict(os.environ, {'MAVIE_DATA_DIR': tmp, 'MAVIE_HEADLESS_SMOKE': '1'}), \
                 patch.object(mavie_desktop, 'find_free_port', return_value=18940), \
                 patch.object(mavie_desktop, 'wait_for_health', return_value=True), \
                 patch.object(server, 'run_server', side_effect=tracking_server), \
                 patch.object(mavie_desktop, 'launch_native_window') as native_mock, \
                 patch.object(mavie_desktop, 'launch_browser_or_fallback') as fb_mock:
                rc = mavie_desktop.main(argv=[])

            self.assertEqual(rc, 0)
            self.assertTrue(stop_seen.is_set(), 'Server stop_event must be triggered during cleanup')
            native_mock.assert_not_called()
            fb_mock.assert_not_called()

    def test_windows_packaging_artifacts_support_webview2_and_web_mode(self) -> None:
        spec_src = (ROOT / 'windows' / 'mavie.spec').read_text(encoding='utf-8')
        iss_src = (ROOT / 'windows' / 'MavieSetup.iss').read_text(encoding='utf-8')
        bat_src = (ROOT / 'windows' / 'Mavie.bat').read_text(encoding='utf-8')
        ci_src = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')

        ast.parse(spec_src, filename='windows/mavie.spec')
        for tok in (
            "collect_all",
            "'webview'",
            "'pythonnet'",
            "'clr_loader'",
            "'webview.platforms.edgechromium'",
            "'webview.platforms.winforms'",
            'webview2loader.dll',
            'console=False',
            'upx=False',
        ):
            self.assertIn(tok, spec_src, f'Missing {tok} in windows/mavie.spec')

        iss_src.encode('ascii')
        self.assertIn('GetWebShortcutName', iss_src)
        self.assertIn('Parameters: "--web"', iss_src)
        self.assertIn("Result := 'Mavie (Web S' + #$00FC + 'r' + #$00FC + 'm' + #$00FC + ')';", iss_src)

        self.assertIn('desktop\\mavie_desktop.py %*', bat_src)
        self.assertIn('--serve', bat_src)
        self.assertIn('--web', bat_src)

        self.assertIn('pywebview', ci_src)
        self.assertIn('pythonnet', ci_src)
        self.assertIn('clr-loader', ci_src)
        self.assertIn('ArgumentList "--web"', ci_src)
        self.assertIn('Mavie web mode ready at', ci_src)


if __name__ == '__main__':
    unittest.main()
