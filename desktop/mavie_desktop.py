#!/usr/bin/env python3
"""Cross-platform Desktop Launcher for Mavie (Windows / macOS / Linux).

Runs the local Mavie media service in-process on a daemon thread, verifies health,
and opens either:
- Native embedded desktop window via pywebview (Microsoft Edge WebView2 on Windows) [default]
- Web mode (`--web` / `--browser`): opens the default browser and shows a control window
  with local + LAN URLs for browser & Smart TV access
- Headless server mode (`--serve`): delegates directly to `server.main()`
"""
from __future__ import annotations

import contextlib
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

WINDOW_TITLE = 'Mavie'
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 840
WINDOW_MIN_SIZE = (960, 600)
WINDOW_BG_HEX = '#07090F'
APP_USER_MODEL_ID = 'app.mavie.desktop'

# Win32 / DWM constants for Windows 10/11 dark titlebar & native icon
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
WIN_CAPTION_COLORREF = 0x000F0907  # #07090F in BGR COLORREF
WIN_TEXT_COLORREF = 0x00FCFAF8     # #F8FAFC in BGR COLORREF
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040

_FULLSCREEN_BRIDGE_JS = """
(() => {
  if (window.__mavieNativeFullscreenHooked) return;
  window.__mavieNativeFullscreenHooked = true;
  const syncFullscreen = () => {
    try {
      const active = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
      const api = window.pywebview && window.pywebview.api;
      if (api && typeof api.set_fullscreen === 'function') {
        api.set_fullscreen(active);
      }
    } catch (_) {}
  };
  document.addEventListener('fullscreenchange', syncFullscreen);
  document.addEventListener('webkitfullscreenchange', syncFullscreen);
})();
"""


def configure_utf8_stdio() -> None:
    if getattr(sys, 'frozen', False):
        if sys.stdout is None:
            with contextlib.suppress(OSError):
                sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        if sys.stderr is None:
            with contextlib.suppress(OSError):
                sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding='utf-8', errors='replace')


configure_utf8_stdio()

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def parse_launch_mode(argv: list[str] | None = None) -> str:
    args = sys.argv[1:] if argv is None else list(argv)
    if '--serve' in args:
        return 'serve'
    if '--web' in args or '--browser' in args:
        return 'web'
    return 'native'


def _sanitize_single_line(exc: BaseException) -> str:
    text = ' '.join(str(exc).splitlines()).strip()
    if not text:
        return type(exc).__name__
    return text.replace('Traceback', 'Error')


def _set_windows_app_user_model_id() -> None:
    if sys.platform.startswith('win'):
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def _extract_hwnd(native_window: Any) -> int | None:
    if native_window is None:
        return None
    handle = getattr(native_window, 'Handle', None)
    if handle is None:
        handle = getattr(native_window, 'handle', None)
    if handle is None:
        return None
    for attr in ('ToInt64', 'ToInt32'):
        fn = getattr(handle, attr, None)
        if callable(fn):
            with contextlib.suppress(Exception):
                val = int(fn())
                if val:
                    return val
    with contextlib.suppress(Exception):
        val = int(handle)
        if val:
            return val
    return None


def _apply_windows_dark_titlebar(hwnd: int) -> bool:
    if not sys.platform.startswith('win') or not hwnd:
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
    except Exception:
        return False
    dark = ctypes.c_int(1)
    hwnd_arg = ctypes.c_void_p(hwnd)
    applied = False
    for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
        try:
            res = dwmapi.DwmSetWindowAttribute(
                hwnd_arg,
                ctypes.c_uint(attr),
                ctypes.byref(dark),
                ctypes.sizeof(dark),
            )
            if res == 0:
                applied = True
                break
        except Exception:
            continue
    # Windows 11 optional caption/text colors matching Mavie obsidian theme
    for attr, color_val in (
        (DWMWA_CAPTION_COLOR, WIN_CAPTION_COLORREF),
        (DWMWA_TEXT_COLOR, WIN_TEXT_COLORREF),
    ):
        with contextlib.suppress(Exception):
            col = ctypes.c_uint(color_val)
            dwmapi.DwmSetWindowAttribute(
                hwnd_arg,
                ctypes.c_uint(attr),
                ctypes.byref(col),
                ctypes.sizeof(col),
            )
    return applied


def _apply_windows_window_icon(hwnd: int, ico_path: Path) -> bool:
    if not sys.platform.startswith('win') or not hwnd or not ico_path.is_file():
        return False
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return False
    with contextlib.suppress(Exception):
        user32.LoadImageW.restype = ctypes.c_void_p
    applied = False
    hwnd_arg = ctypes.c_void_p(hwnd)
    for icon_slot, size_px in ((ICON_BIG, 32), (ICON_SMALL, 16)):
        try:
            hicon = user32.LoadImageW(
                None,
                str(ico_path),
                IMAGE_ICON,
                size_px,
                size_px,
                LR_LOADFROMFILE,
            )
            if not hicon:
                hicon = user32.LoadImageW(
                    None,
                    str(ico_path),
                    IMAGE_ICON,
                    0,
                    0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
            if hicon:
                user32.SendMessageW(hwnd_arg, WM_SETICON, icon_slot, ctypes.c_void_p(hicon))
                applied = True
        except Exception:
            continue
    return applied


def _apply_windows_native_chrome(window: Any, ico_path: Path, log_fn=None) -> bool:
    if not sys.platform.startswith('win'):
        return False
    hwnd = _extract_hwnd(getattr(window, 'native', None))
    if not hwnd:
        with contextlib.suppress(Exception):
            user32 = ctypes.windll.user32
            hwnd = int(user32.FindWindowW(None, WINDOW_TITLE) or 0)
    if not hwnd:
        return False
    dark_ok = _apply_windows_dark_titlebar(hwnd)
    icon_ok = _apply_windows_window_icon(hwnd, ico_path)
    if log_fn and (dark_ok or icon_ok):
        log_fn(f'Applied Windows native chrome (dark_titlebar={dark_ok}, icon={icon_ok})')
    return dark_ok or icon_ok


def show_error_dialog(title: str, message: str) -> None:
    if sys.platform.startswith('win'):
        with contextlib.suppress(Exception):
            ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x10)
            return
    with contextlib.suppress(Exception):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
        return
    if sys.stderr is not None:
        with contextlib.suppress(Exception):
            sys.stderr.write(f'{title}: {message}\n')


def _can_bind_port(port: int) -> bool:
    # 1. If loopback accepts a connection, another process is already listening.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.08)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            return False
    # 2. Verify actual wildcard bind (0.0.0.0) + listen without SO_REUSEADDR.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            with contextlib.suppress(OSError):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(('0.0.0.0', port))
            s.listen(1)
            return True
        except OSError:
            return False


def find_free_port(preferred: int = 8844) -> int:
    for candidate in range(preferred, min(preferred + 21, 65535)):
        if _can_bind_port(candidate):
            return candidate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        return int(s.getsockname()[1])


def get_lan_urls(port: int) -> list[str]:
    ips: list[str] = []
    with contextlib.suppress(Exception):
        import server
        ips = list(server.lan_ips())
    return [f'http://{ip}:{port}' for ip in ips if ip]


def find_app_browser() -> list[str] | None:
    if sys.platform.startswith('win'):
        candidates = [
            Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Microsoft/Edge/Application/msedge.exe',
            Path(os.environ.get('PROGRAMFILES', '')) / 'Microsoft/Edge/Application/msedge.exe',
            Path(os.environ.get('PROGRAMFILES', '')) / 'Google/Chrome/Application/chrome.exe',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
        ]
        for path in candidates:
            if path.is_file():
                return [str(path)]
    elif sys.platform == 'darwin':
        for app in (
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ):
            if Path(app).is_file():
                return [app]
    else:
        for exe in ('google-chrome', 'microsoft-edge', 'chromium', 'chromium-browser'):
            found = shutil.which(exe)
            if found:
                return [found]
    return None


def wait_for_health(
    url: str,
    server_thread: threading.Thread,
    startup_error: list[BaseException],
    timeout: float = 15.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if startup_error or not server_thread.is_alive():
            return False
        try:
            with _LOCAL_OPENER.open(url + '/api/health', timeout=0.5) as r:
                raw = r.read(65536).decode('utf-8', errors='replace')
                data = json.loads(raw)
                if data.get('app') == 'mavie' and data.get('ok') is True:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


class _MavieWindowBridge:
    """JS API bridge synchronizing HTML5 video fullscreen with native window fullscreen."""

    def __init__(self) -> None:
        self.window: Any = None
        self._entered_by_video = False

    def set_fullscreen(self, active: bool) -> bool:
        win = self.window
        if win is None or not hasattr(win, 'toggle_fullscreen'):
            return False
        want = bool(active)
        current = bool(getattr(win, 'fullscreen', False))
        if want and not current:
            self._entered_by_video = True
            with contextlib.suppress(Exception):
                win.toggle_fullscreen()
            return True
        if not want and current and self._entered_by_video:
            self._entered_by_video = False
            with contextlib.suppress(Exception):
                win.toggle_fullscreen()
            return False
        return current


def launch_native_window(
    base_url: str,
    data_dir: Path,
    stop_event: threading.Event,
    log_fn=None,
) -> bool:
    """Open Mavie inside its own embedded native desktop window via pywebview.

    Returns True if the native window started and exited cleanly.
    Returns False if pywebview or Edge WebView2 failed to initialize so the
    caller can fall back gracefully without logging a Python Traceback.
    """
    _set_windows_app_user_model_id()
    try:
        import webview
    except Exception as exc:
        if log_fn:
            log_fn(
                f'Native desktop window unavailable ({type(exc).__name__}: '
                f'{_sanitize_single_line(exc)}); falling back to browser mode'
            )
        return False

    storage_dir = data_dir / 'webview2'
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if log_fn:
            log_fn(f'WebView2 storage directory warning: {_sanitize_single_line(exc)}')

    settings = getattr(webview, 'settings', None)
    if isinstance(settings, dict):
        settings['ALLOW_DOWNLOADS'] = True
        settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        settings['ALLOW_FILE_URLS'] = True

    ico_path = ROOT / 'windows' / 'mavie.ico'
    bridge = _MavieWindowBridge()
    state = {'shown': False, 'chrome_applied': False}

    try:
        window = webview.create_window(
            title=WINDOW_TITLE,
            url=f'{base_url}/',
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=WINDOW_MIN_SIZE,
            resizable=True,
            background_color=WINDOW_BG_HEX,
            text_select=True,
            js_api=bridge,
        )
        bridge.window = window

        def _ensure_chrome() -> None:
            if not state['chrome_applied']:
                state['chrome_applied'] = _apply_windows_native_chrome(window, ico_path, log_fn=log_fn)

        def _on_shown() -> None:
            state['shown'] = True
            _ensure_chrome()

        def _on_loaded() -> None:
            state['shown'] = True
            _ensure_chrome()
            with contextlib.suppress(Exception):
                window.evaluate_js(_FULLSCREEN_BRIDGE_JS)

        def _on_closed() -> None:
            if state['shown']:
                stop_event.set()

        events = getattr(window, 'events', None)
        if events is not None:
            with contextlib.suppress(Exception):
                events.shown += _on_shown
            with contextlib.suppress(Exception):
                events.loaded += _on_loaded
            with contextlib.suppress(Exception):
                events.closed += _on_closed

        start_kwargs: dict[str, Any] = {
            'private_mode': False,
            'storage_path': str(storage_dir),
        }
        if sys.platform.startswith('win'):
            start_kwargs['gui'] = 'edgechromium'
        elif sys.platform.startswith('linux') and ico_path.is_file():
            start_kwargs['icon'] = str(ico_path)

        if log_fn:
            backend = start_kwargs.get('gui', 'default')
            log_fn(f'Starting native Mavie window (backend={backend}, storage={storage_dir})')

        started_at = time.monotonic()
        webview.start(**start_kwargs)
        elapsed = time.monotonic() - started_at
        if not state['shown'] and elapsed < 2.0:
            if log_fn:
                log_fn('Native WebView2 window returned before showing; falling back to browser app mode')
            return False
        stop_event.set()
        return True
    except KeyboardInterrupt:
        stop_event.set()
        raise
    except Exception as exc:
        if log_fn:
            log_fn(
                f'Native WebView2 window failed ({type(exc).__name__}: '
                f'{_sanitize_single_line(exc)}); falling back to browser app mode'
            )
        return False


def show_fallback_window(
    base_url: str,
    stop_event: threading.Event,
    lan_urls: list[str] | None = None,
    mode: str = 'fallback',
) -> None:
    _set_windows_app_user_model_id()
    lan_list = [u for u in (lan_urls or []) if u]
    is_web = mode == 'web'

    try:
        import tkinter as tk

        root = tk.Tk()
        root.title('Mavie — Web Sürümü' if is_web else 'Mavie')
        root.configure(bg=WINDOW_BG_HEX)
        win_height = 315 if lan_list else 270
        root.geometry(f'480x{win_height}')
        root.resizable(False, False)
        ico_path = ROOT / 'windows' / 'mavie.ico'
        if ico_path.is_file():
            with contextlib.suppress(Exception):
                root.iconbitmap(default=str(ico_path))

        if sys.platform.startswith('win'):
            with contextlib.suppress(Exception):
                root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
                _apply_windows_dark_titlebar(int(hwnd))

        frame = tk.Frame(root, bg=WINDOW_BG_HEX, padx=24, pady=20)
        frame.pack(fill='both', expand=True)

        tk.Label(
            frame,
            text='Mavie Web Sürümü' if is_web else 'Mavie Medya Merkezi',
            fg='#f8fafc',
            bg=WINDOW_BG_HEX,
            font=('Segoe UI', 14, 'bold'),
        ).pack(anchor='w')

        subtitle = (
            'Yerel sunucu aktif. Tarayıcıdan veya aynı Wi-Fi ağındaki telefon/TV cihazlarından bağlanabilirsiniz.'
            if is_web
            else 'Yerel sunucu çalışıyor. Tarayıcı açılmadıysa aşağıdaki düğmeden açabilir veya Mavie’yi kapatabilirsiniz.'
        )
        tk.Label(
            frame,
            text=subtitle,
            fg='#94a3b8',
            bg=WINDOW_BG_HEX,
            font=('Segoe UI', 9),
            wraplength=430,
            justify='left',
        ).pack(anchor='w', pady=(4, 12))

        status_var = tk.StringVar(value='')

        def copy_url(target_url: str) -> None:
            with contextlib.suppress(Exception):
                root.clipboard_clear()
                root.clipboard_append(target_url)
                root.update()
                status_var.set(f'Kopyalandı: {target_url}')

        def add_url_row(label: str, url_text: str) -> None:
            card = tk.Frame(frame, bg='#101524', padx=10, pady=8)
            card.pack(fill='x', pady=(0, 8))
            left = tk.Frame(card, bg='#101524')
            left.pack(side='left', fill='x', expand=True)
            tk.Label(
                left,
                text=label,
                fg='#94a3b8',
                bg='#101524',
                font=('Segoe UI', 8),
            ).pack(anchor='w')
            tk.Label(
                left,
                text=url_text,
                fg='#67e8f9',
                bg='#101524',
                font=('Segoe UI', 10, 'bold'),
            ).pack(anchor='w')
            tk.Button(
                card,
                text='Kopyala',
                command=lambda u=url_text: copy_url(u),
                bg='#1e293b',
                fg='#f8fafc',
                activebackground='#334155',
                activeforeground='#ffffff',
                relief='flat',
                padx=10,
                pady=4,
                cursor='hand2',
            ).pack(side='right')

        add_url_row('Bu Bilgisayar (Yerel Adres)', base_url)
        if lan_list:
            add_url_row('Yerel Ağ / Telefon & Smart TV (LAN)', lan_list[0])

        tk.Label(
            frame,
            textvariable=status_var,
            fg='#22d3ee',
            bg=WINDOW_BG_HEX,
            font=('Segoe UI', 8),
        ).pack(anchor='w', pady=(0, 6))

        btn_row = tk.Frame(frame, bg=WINDOW_BG_HEX)
        btn_row.pack(fill='x', pady=(4, 0))

        def open_browser() -> None:
            with contextlib.suppress(Exception):
                webbrowser.open(base_url + '/')

        def quit_app() -> None:
            stop_event.set()
            with contextlib.suppress(Exception):
                root.destroy()

        tk.Button(
            btn_row,
            text='Tarayıcıda Aç / Open in Browser',
            command=open_browser,
            bg='#7c3aed',
            fg='#ffffff',
            activebackground='#6d28d9',
            activeforeground='#ffffff',
            relief='flat',
            padx=14,
            pady=8,
            cursor='hand2',
        ).pack(side='left')

        tk.Button(
            btn_row,
            text='Mavie’yi Kapat / Quit',
            command=quit_app,
            bg='#1a2134',
            fg='#f5f5f5',
            activebackground='#25304d',
            activeforeground='#ffffff',
            relief='flat',
            padx=14,
            pady=8,
            cursor='hand2',
        ).pack(side='right')

        root.protocol('WM_DELETE_WINDOW', quit_app)
        root.mainloop()
        return
    except Exception:
        pass

    if sys.platform.startswith('win'):
        with contextlib.suppress(Exception):
            MB_YESNO = 0x04
            MB_ICONINFORMATION = 0x40
            IDYES = 6
            lan_note = f'\nYerel Ağ (LAN/TV): {lan_list[0]}' if lan_list else ''
            while not stop_event.is_set():
                choice = ctypes.windll.user32.MessageBoxW(
                    0,
                    f'Mavie yerel medya sunucusu çalışıyor:\n{base_url}{lan_note}\n\n'
                    'Tarayıcıda açmak için Evet, Mavie’yi kapatmak için Hayır seçin.',
                    'Mavie',
                    MB_YESNO | MB_ICONINFORMATION,
                )
                if choice == IDYES:
                    with contextlib.suppress(Exception):
                        webbrowser.open(base_url + '/')
                else:
                    stop_event.set()
                    break
            return

    try:
        while not stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        stop_event.set()


def parse_preferred_port(raw: str | None = None) -> int:
    value = raw if raw is not None else (os.environ.get('MAVIE_PORT') or os.environ.get('CINEVA_PORT') or '8844')
    text = str(value).strip()
    if not text:
        return 8844
    try:
        port = int(text)
    except ValueError:
        raise ValueError(f'Geçersiz port numarası: {text!r}. 1 ile 65535 arasında bir tam sayı girin.') from None
    if not 1 <= port <= 65535:
        raise ValueError(f'Port numarası aralık dışında: {port}. 1 ile 65535 arasında olmalıdır.')
    return port


def _acquire_windows_mutex():
    if not sys.platform.startswith('win') or os.environ.get('MAVIE_HEADLESS_SMOKE') == '1':
        return None
    with contextlib.suppress(Exception):
        return ctypes.windll.kernel32.CreateMutexW(None, False, 'MavieDesktopMutex')
    return None


def _release_windows_mutex(handle) -> None:
    if handle:
        with contextlib.suppress(Exception):
            ctypes.windll.kernel32.CloseHandle(handle)


def launch_browser_or_fallback(
    base_url: str,
    stop_event: threading.Event,
    log_fn=None,
    browser_cmd: list[str] | None = None,
    lan_urls: list[str] | None = None,
) -> int:
    cmd = find_app_browser() if browser_cmd is None else browser_cmd
    if cmd:
        profile_dir = tempfile.mkdtemp(prefix='mavie-app-')
        try:
            started_at = time.monotonic()
            app_proc = subprocess.Popen([
                *cmd,
                f'--app={base_url}/',
                f'--user-data-dir={profile_dir}',
                '--no-first-run',
                '--no-default-browser-check',
            ])
            rc = app_proc.wait()
            elapsed = time.monotonic() - started_at
            if elapsed < 2.0:
                if rc != 0:
                    if log_fn:
                        log_fn(f'Browser app exited quickly with code {rc}; falling back to default browser')
                    with contextlib.suppress(Exception):
                        webbrowser.open(base_url + '/')
                elif log_fn:
                    log_fn('Browser handed off to existing session; keeping server alive with fallback window')
                show_fallback_window(base_url, stop_event, lan_urls=lan_urls, mode='fallback')
                return 0
            return rc
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
    with contextlib.suppress(Exception):
        webbrowser.open(base_url + '/')
    show_fallback_window(base_url, stop_event, lan_urls=lan_urls, mode='fallback')
    return 0


def launch_web_mode(
    base_url: str,
    port: int,
    stop_event: threading.Event,
    log_fn=None,
) -> int:
    lan_urls = get_lan_urls(port)
    if log_fn:
        log_fn(f'Mavie web mode ready at {base_url}')
        if lan_urls:
            log_fn(f'Mavie LAN URLs: {", ".join(lan_urls)}')
    if os.environ.get('MAVIE_NO_BROWSER') != '1':
        with contextlib.suppress(Exception):
            webbrowser.open(base_url + '/')
    show_fallback_window(base_url, stop_event, lan_urls=lan_urls, mode='web')
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    mode = parse_launch_mode(argv)
    if mode == 'serve':
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import server
        if argv is None:
            if '--serve' in sys.argv:
                sys.argv.remove('--serve')
            server.main()
        else:
            old_argv = list(sys.argv)
            try:
                sys.argv = [old_argv[0], *[a for a in argv if a != '--serve']]
                server.main()
            finally:
                sys.argv = old_argv
        return 0

    data_dir = Path(
        os.environ.get('MAVIE_DATA_DIR')
        or os.environ.get('CINEVA_DATA_DIR')
        or (Path.home() / '.mavie')
    ).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / 'desktop.log'
    os.environ['MAVIE_DATA_DIR'] = str(data_dir)
    os.environ['CINEVA_DATA_DIR'] = str(data_dir)

    def _log(msg: str) -> None:
        with contextlib.suppress(OSError):
            with log_path.open('a', encoding='utf-8', errors='replace') as fh:
                fh.write(msg.rstrip() + '\n')

    try:
        preferred_port = parse_preferred_port()
    except ValueError as exc:
        msg = f'{exc}\nLog: {log_path}'
        _log(msg)
        show_error_dialog('Mavie Yapılandırma Hatası', msg)
        return 1

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    mutex_handle = _acquire_windows_mutex()
    stop_event = threading.Event()
    ready_event = threading.Event()
    startup_error: list[BaseException] = []
    server_thread: threading.Thread | None = None

    def _run_srv(bind_port: int) -> None:
        try:
            import server
            server.run_server(
                host='0.0.0.0',
                port=bind_port,
                install_signals=False,
                stop_event=stop_event,
                ready_event=ready_event,
            )
        except BaseException as exc:
            startup_error.append(exc)
            _log('Server error:\n' + traceback.format_exc())

    try:
        candidate_start = preferred_port
        port = preferred_port
        base_url = f'http://127.0.0.1:{port}'
        started_ok = False
        for attempt in range(5):
            port = find_free_port(candidate_start)
            startup_error.clear()
            ready_event.clear()
            stop_event.clear()
            server_thread = threading.Thread(target=_run_srv, args=(port,), daemon=True, name='mavie-server')
            server_thread.start()
            base_url = f'http://127.0.0.1:{port}'
            if wait_for_health(base_url, server_thread, startup_error):
                started_ok = True
                break
            if startup_error and isinstance(startup_error[-1], OSError) and attempt < 4:
                _log(f'Port {port} bind race ({startup_error[-1]}); retrying another port')
                stop_event.set()
                server_thread.join(timeout=2)
                candidate_start = port + 1 if port < 65535 else 8844
                continue
            break

        if not started_ok:
            detail = f'\n\nDetay: {startup_error[-1]}' if startup_error else ''
            msg = f'Mavie yerel servisi başlatılamadı.{detail}\nLog: {log_path}'
            _log(msg)
            show_error_dialog('Mavie Başlatma Hatası', msg)
            return 1

        _log(f'Mavie desktop ready at {base_url} (mode={mode})')

        if os.environ.get('MAVIE_HEADLESS_SMOKE') == '1':
            return 0

        if mode == 'web':
            return launch_web_mode(base_url, port, stop_event, log_fn=_log)

        if launch_native_window(base_url, data_dir, stop_event, log_fn=_log):
            return 0

        lan_urls = get_lan_urls(port)
        return launch_browser_or_fallback(base_url, stop_event, log_fn=_log, lan_urls=lan_urls)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_event.set()
        if server_thread is not None:
            server_thread.join(timeout=5)
        _release_windows_mutex(mutex_handle)


if __name__ == '__main__':
    raise SystemExit(main())
