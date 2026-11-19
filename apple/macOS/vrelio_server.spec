# macOS PyInstaller --onedir Build Spec for embedded Vrelio local server
# Usage: pyinstaller --noconfirm apple/macOS/vrelio_server.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..', '..'))
block_cipher = None

a = Analysis(
    [os.path.join(ROOT, 'server.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'public'), 'public'),
        (os.path.join(ROOT, 'legal'), 'legal'),
        *collect_data_files('imageio_ffmpeg'),
        *collect_data_files('tzdata'),
    ],
    hiddenimports=[
        'server',
        'playback',
        'discovery',
        'sports',
        'm3u',
        'local_media',
        'imageio_ffmpeg',
        *collect_submodules('imageio_ffmpeg'),
        'tzdata',
        'zoneinfo',
        'html',
        'html.entities',
        'html.parser',
        'http',
        'http.client',
        'http.cookies',
        'http.server',
        'sqlite3',
        'urllib.error',
        'urllib.parse',
        'urllib.request',
        'xml.etree.ElementTree',
        'xml.parsers.expat',
        'concurrent.futures',
        'dataclasses',
        'ipaddress',
        'mimetypes',
        'secrets',
        'ssl',
        'gzip',
        'unicodedata',
        'uuid',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vrelio-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='vrelio-server',
)
