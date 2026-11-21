#!/usr/bin/env python3
"""Cross-platform Desktop Launcher for Mavie (Windows / CrossOver / macOS / Linux).

Runs the local Mavie media service in-process on a daemon thread, verifies health,
and opens a dedicated Edge/Chrome App window or a visible fallback control window.
"""
from __future__ import annotations

import contextlib
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

os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding='utf-8', errors='replace')


configure_utf8_stdio()

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def show_error_dialog(title: str, message: str) -> None:
    if sys.platform.startswith('win'):
        with contextlib.suppress(Exception):
            import ctypes
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


def find_free_port(preferred: int = 8844) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return int(s.getsockname()[1])


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
            with urllib.request.urlopen(url + '/api/health', timeout=0.5) as r:
                data = json.load(r)
                if data.get('app') == 'mavie' and data.get('ok') is True:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def show_fallback_window(base_url: str, stop_event: threading.Event) -> None:
    if sys.platform.startswith('win'):
        with contextlib.suppress(Exception):
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('app.mavie.desktop')
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title('Mavie')
        root.configure(bg='#0a0d16')
        root.geometry('420x230')
        root.resizable(False, False)
        ico_path = ROOT / 'windows' / 'mavie.ico'
        if ico_path.is_file():
            with contextlib.suppress(Exception):
                root.iconbitmap(default=str(ico_path))

        frame = tk.Frame(root, bg='#0a0d16', padx=24, pady=22)
        frame.pack(fill='both', expand=True)

        tk.Label(
            frame,
            text='Mavie Medya Merkezi',
            fg='#f5f5f5',
            bg='#0a0d16',
            font=('Segoe UI', 14, 'bold'),
        ).pack(anchor='w')

        tk.Label(
            frame,
            text=f'Yerel sunucu çalışıyor: {base_url}',
            fg='#67e8f9',
            bg='#0a0d16',
            font=('Segoe UI', 10),
            pady=8,
        ).pack(anchor='w')

        tk.Label(
            frame,
            text='Tarayıcı açılmadıysa aşağıdaki düğmeden açabilir veya Mavie’yi kapatabilirsiniz.',
            fg='#a8b5d6',
            bg='#0a0d16',
            font=('Segoe UI', 9),
            wraplength=370,
            justify='left',
        ).pack(anchor='w', pady=(0, 14))

        btn_row = tk.Frame(frame, bg='#0a0d16')
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
            padx=12,
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
            padx=12,
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
            import ctypes
            MB_YESNO = 0x04
            MB_ICONINFORMATION = 0x40
            IDYES = 6
            while not stop_event.is_set():
                choice = ctypes.windll.user32.MessageBoxW(
                    0,
                    f'Mavie yerel medya sunucusu çalışıyor:\n{base_url}\n\n'
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


def main() -> int:
    configure_utf8_stdio()
    if '--serve' in sys.argv:
        sys.argv.remove('--serve')
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import server
        server.main()
        return 0

    preferred_port = int(os.environ.get('MAVIE_PORT') or os.environ.get('CINEVA_PORT') or '8844')
    port = find_free_port(preferred_port)
    data_dir = Path(
        os.environ.get('MAVIE_DATA_DIR')
        or os.environ.get('CINEVA_DATA_DIR')
        or (Path.home() / '.mavie')
    ).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / 'desktop.log'
    os.environ['MAVIE_DATA_DIR'] = str(data_dir)
    os.environ['CINEVA_DATA_DIR'] = str(data_dir)

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    stop_event = threading.Event()
    ready_event = threading.Event()
    startup_error: list[BaseException] = []

    def _log(msg: str) -> None:
        with contextlib.suppress(OSError):
            with log_path.open('a', encoding='utf-8', errors='replace') as fh:
                fh.write(msg.rstrip() + '\n')

    def _run_srv() -> None:
        try:
            import server
            server.run_server(
                host='0.0.0.0',
                port=port,
                install_signals=False,
                stop_event=stop_event,
                ready_event=ready_event,
            )
        except BaseException as exc:
            startup_error.append(exc)
            _log('Server error:\n' + traceback.format_exc())

    server_thread = threading.Thread(target=_run_srv, daemon=True, name='mavie-server')
    server_thread.start()

    try:
        base_url = f'http://127.0.0.1:{port}'
        if not wait_for_health(base_url, server_thread, startup_error):
            detail = f'\n\nDetay: {startup_error[0]}' if startup_error else ''
            msg = f'Mavie yerel servisi başlatılamadı.{detail}\nLog: {log_path}'
            _log(msg)
            show_error_dialog('Mavie Başlatma Hatası', msg)
            return 1

        _log(f'Mavie desktop ready at {base_url}')

        if os.environ.get('MAVIE_HEADLESS_SMOKE') == '1':
            return 0

        browser_cmd = find_app_browser()
        if browser_cmd:
            profile_dir = tempfile.mkdtemp(prefix='mavie-app-')
            app_proc = subprocess.Popen([
                *browser_cmd,
                f'--app={base_url}/',
                f'--user-data-dir={profile_dir}',
                '--no-first-run',
                '--no-default-browser-check',
            ])
            try:
                return app_proc.wait()
            finally:
                shutil.rmtree(profile_dir, ignore_errors=True)
        else:
            with contextlib.suppress(Exception):
                webbrowser.open(base_url + '/')
            show_fallback_window(base_url, stop_event)
            return 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop_event.set()
        server_thread.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
