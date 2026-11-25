# Windows PyInstaller Build Spec for standalone native Mavie.exe (pywebview + Edge WebView2)
# Usage on Windows: pyinstaller --clean windows\mavie.spec

import importlib.util
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
block_cipher = None


def _collect_pkg(package_name):
    try:
        return collect_all(package_name)
    except Exception:
        return [], [], []


wv_datas, wv_binaries, wv_hiddenimports = _collect_pkg('webview')
pn_datas, pn_binaries, pn_hiddenimports = _collect_pkg('pythonnet')
clr_datas, clr_binaries, clr_hiddenimports = _collect_pkg('clr_loader')
cffi_datas, cffi_binaries, cffi_hiddenimports = _collect_pkg('cffi')

# Explicitly gather WebView2 / WinForms DLLs (including WebView2Loader.dll) so
# single-file extraction under _MEIPASS always preserves expected subfolders.
extra_webview_binaries = []
_wv_spec = importlib.util.find_spec('webview')
if _wv_spec and _wv_spec.submodule_search_locations:
    _wv_pkg_dir = list(_wv_spec.submodule_search_locations)[0]
    _wv_lib_dir = os.path.join(_wv_pkg_dir, 'lib')
    if os.path.isdir(_wv_lib_dir):
        for _dirpath, _dirnames, _filenames in os.walk(_wv_lib_dir):
            for _fname in _filenames:
                if _fname.lower().endswith('.dll'):
                    _src = os.path.join(_dirpath, _fname)
                    _rel = os.path.relpath(_dirpath, _wv_pkg_dir)
                    extra_webview_binaries.append((_src, os.path.join('webview', _rel)))
                    if _fname.lower() == 'webview2loader.dll' and 'x64' in _dirpath.lower():
                        extra_webview_binaries.append((_src, '.'))


def _dedupe_pairs(items):
    seen = set()
    out = []
    for src, dest in items:
        key = (os.path.normcase(os.path.abspath(src)), os.path.normpath(dest))
        if key not in seen:
            seen.add(key)
            out.append((src, dest))
    return out


all_datas = _dedupe_pairs(
    [
        (os.path.join(ROOT, 'public'), 'public'),
        (os.path.join(ROOT, 'tv', 'src'), os.path.join('tv', 'src')),
        (os.path.join(ROOT, 'legal'), 'legal'),
        (os.path.join(ROOT, 'windows', 'mavie.ico'), 'windows'),
        *collect_data_files('imageio_ffmpeg'),
        *collect_data_files('tzdata'),
    ]
    + wv_datas
    + pn_datas
    + clr_datas
    + cffi_datas
)
_data_keys = {
    (os.path.normcase(os.path.abspath(src)), os.path.normpath(dest))
    for src, dest in all_datas
}
all_binaries = [
    pair
    for pair in _dedupe_pairs(
        wv_binaries + pn_binaries + clr_binaries + cffi_binaries + extra_webview_binaries
    )
    if (os.path.normcase(os.path.abspath(pair[0])), os.path.normpath(pair[1])) not in _data_keys
]

a = Analysis(
    [os.path.join(ROOT, 'desktop', 'mavie_desktop.py')],
    pathex=[ROOT],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=list(
        dict.fromkeys(
            [
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
                'webview',
                'webview.platforms.winforms',
                'webview.platforms.edgechromium',
                'webview.platforms.mshtml',
                'clr',
                'pythonnet',
                'clr_loader',
                'cffi',
                'pycparser',
                'bottle',
                'proxy_tools',
                'tkinter',
                'tkinter.messagebox',
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
                *wv_hiddenimports,
                *pn_hiddenimports,
                *clr_hiddenimports,
                *cffi_hiddenimports,
            ]
        )
    ),
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
    [('X utf8', None, 'OPTION')],
    name='Mavie',
    icon=os.path.join(ROOT, 'windows', 'mavie.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
