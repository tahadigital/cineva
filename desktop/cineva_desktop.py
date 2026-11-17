#!/usr/bin/env python3
"""Cross-platform Desktop Launcher for Cineva (Windows / macOS / Linux).

Starts the local Cineva media service cleanly, waits for readiness, and opens a
dedicated frameless Edge/Chrome App window (or browser fallback).
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


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
        for app in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'):
            if Path(app).is_file():
                return [app]
    else:
        for exe in ('google-chrome', 'microsoft-edge', 'chromium', 'chromium-browser'):
            found = shutil.which(exe)
            if found:
                return [found]
    return None


def wait_for_health(url: str, proc: subprocess.Popen, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + '/api/health', timeout=0.5) as r:
                data = json.load(r)
                if data.get('app') == 'cineva' and data.get('ok') is True:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> int:
    if '--serve' in sys.argv:
        sys.argv.remove('--serve')
        sys.path.insert(0, str(ROOT))
        import server
        server.main()
        return 0

    port = find_free_port(int(os.environ.get('CINEVA_PORT', '8844')))
    data_dir = Path(os.environ.get('CINEVA_DATA_DIR') or (Path.home() / '.cineva')).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / 'desktop.log'
    env = {**os.environ, 'CINEVA_DATA_DIR': str(data_dir), 'PYTHONUNBUFFERED': '1'}

    server_cmd = (
        [sys.executable, '--serve', '--host', '0.0.0.0', '--port', str(port), '--parent-pid', str(os.getpid())]
        if getattr(sys, 'frozen', False)
        else [sys.executable, str(ROOT / 'server.py'), '--host', '0.0.0.0', '--port', str(port), '--parent-pid', str(os.getpid())]
    )
    creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform.startswith('win') else 0

    with log_path.open('ab') as log:
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=creation_flags,
        )
        try:
            base_url = f'http://127.0.0.1:{port}'
            if not wait_for_health(base_url, server_proc):
                sys.stderr.write('Cineva yerel servisi başlatılamadı.\n')
                return 1
            browser_cmd = find_app_browser()
            if browser_cmd:
                profile_dir = tempfile.mkdtemp(prefix='cineva-app-')
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
                webbrowser.open(base_url + '/')
                print(f'Cineva çalışıyor: {base_url}/ (Kapatmak için Ctrl+C)')
                return server_proc.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if server_proc.poll() is None:
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    server_proc.kill()


if __name__ == '__main__':
    raise SystemExit(main())
