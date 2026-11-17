# Windows PyInstaller Build Spec for standalone Cineva.exe
# Usage on Windows: pyinstaller windows\cineva.spec

block_cipher = None

a = Analysis(
    ['../desktop/cineva_desktop.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../public', 'public'),
        ('../server.py', '.'),
        ('../playback.py', '.'),
        ('../discovery.py', '.'),
        ('../sports.py', '.'),
        ('../m3u.py', '.'),
        ('../local_media.py', '.'),
        ('../legal', 'legal'),
    ],
    hiddenimports=['imageio_ffmpeg', 'server', 'playback', 'discovery', 'sports', 'm3u', 'local_media'],
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
