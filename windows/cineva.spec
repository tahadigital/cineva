# Windows PyInstaller Build Spec for standalone Cineva.exe
# Usage on Windows: pyinstaller windows\cineva.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
block_cipher = None

a = Analysis(
    [os.path.join(ROOT, 'desktop', 'cineva_desktop.py')],
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Cineva',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
