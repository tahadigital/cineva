#!/usr/bin/env python3
"""Stdlib-only Multi-TV Packager for Mavie.

Builds BOTH:
  - dist/Mavie-Tizen.wgt  (Samsung Tizen 5.5+ / TU8500 Web Application widget ZIP)
  - dist/Mavie-webOS.ipk  (LG webOS 4.0+ OPKG / Debian ar archive)

Zero external pip packages or SDK binaries required — runs cleanly on macOS, Linux CI, and Windows.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TV_SRC = ROOT / 'tv' / 'src'
TV_ASSETS = ROOT / 'tv' / 'assets'
TIZEN_DIR = ROOT / 'tv' / 'tizen'
WEBOS_DIR = ROOT / 'tv' / 'webos'
HLS_VENDOR = ROOT / 'public' / 'vendor' / 'hls.min.js'

DETERMINISTIC_ZIP_DATE = (2026, 1, 1, 0, 0, 0)
DETERMINISTIC_MTIME = 1767225600
WEBOS_APP_ID = 'app.mavie.tv'
WEBOS_INSTALL_PREFIX = f'usr/palm/applications/{WEBOS_APP_ID}'


def _read_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f'Required TV build asset missing: {path}')
    return path.read_bytes()


def _render_platform_index(head_snippet: str, bridge_snippet: str) -> bytes:
    html = (TV_SRC / 'index.html').read_text(encoding='utf-8')
    if '<!--TV_PLATFORM_HEAD-->' not in html or '<!--TV_PLATFORM_BRIDGE-->' not in html:
        raise ValueError('tv/src/index.html is missing platform injection placeholders.')
    html = html.replace('<!--TV_PLATFORM_HEAD-->', head_snippet)
    html = html.replace('<!--TV_PLATFORM_BRIDGE-->', bridge_snippet)
    return html.encode('utf-8')


def _collect_shared_web_files() -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for p in sorted(TV_SRC.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(TV_SRC).as_posix()
        if rel == 'index.html':
            continue
        files.append((rel, p.read_bytes()))
    files.append(('vendor/hls.min.js', _read_bytes(HLS_VENDOR)))
    return files


def build_tizen_wgt(out_dir: Path) -> Path:
    config_bytes = _read_bytes(TIZEN_DIR / 'config.xml')
    # Validate XML structure before packaging
    ET.fromstring(config_bytes)

    icon_bytes = _read_bytes(TV_ASSETS / 'icon-512.png')
    bridge_bytes = _read_bytes(TIZEN_DIR / 'tizen-bridge.js')
    index_bytes = _render_platform_index(
        '<script type="text/javascript" src="$WEBAPIS/webapis/webapis.js"></script>',
        '<script src="tizen-bridge.js" defer></script>',
    )

    entries: list[tuple[str, bytes]] = [
        ('config.xml', config_bytes),
        ('icon.png', icon_bytes),
        ('index.html', index_bytes),
        ('tizen-bridge.js', bridge_bytes),
    ]
    splash_path = TV_ASSETS / 'splash-1920x1080.png'
    if splash_path.is_file():
        entries.append(('splash.png', splash_path.read_bytes()))
    entries.extend(_collect_shared_web_files())

    out_dir.mkdir(parents=True, exist_ok=True)
    wgt_path = out_dir / 'Mavie-Tizen.wgt'
    with zipfile.ZipFile(wgt_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for arcname, payload in entries:
            zi = zipfile.ZipInfo(filename=arcname, date_time=DETERMINISTIC_ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o100644 << 16
            zf.writestr(zi, payload)
    return wgt_path


def _make_tar_gz(entries: list[tuple[str, bytes]]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode='w', format=tarfile.USTAR_FORMAT) as tf:
        for name, payload in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = DETERMINISTIC_MTIME
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = 'root'
            info.gname = 'root'
            tf.addfile(info, io.BytesIO(payload))
    gz_buf = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=gz_buf, mtime=DETERMINISTIC_MTIME) as gz:
        gz.write(tar_buf.getvalue())
    return gz_buf.getvalue()


def _make_ar_archive(members: list[tuple[str, bytes]]) -> bytes:
    chunks = [b'!<arch>\n']
    for name, payload in members:
        if len(name) > 16:
            raise ValueError(f'ar member name too long: {name}')
        header = (
            f'{name:<16}'
            f'{DETERMINISTIC_MTIME:<12d}'
            f'{"0":<6}'
            f'{"0":<6}'
            f'{"100644":<8}'
            f'{len(payload):<10d}'
            '`\n'
        ).encode('ascii')
        assert len(header) == 60
        chunks.append(header)
        chunks.append(payload)
        if len(payload) % 2 == 1:
            chunks.append(b'\n')
    return b''.join(chunks)


def build_webos_ipk(out_dir: Path) -> Path:
    appinfo_bytes = _read_bytes(WEBOS_DIR / 'appinfo.json')
    appinfo = json.loads(appinfo_bytes.decode('utf-8'))
    app_id = str(appinfo.get('id') or WEBOS_APP_ID)
    version = str(appinfo.get('version') or '2.2.0')
    install_prefix = f'./usr/palm/applications/{app_id}'

    icon80_bytes = _read_bytes(TV_ASSETS / 'icon-80.png')
    icon130_bytes = _read_bytes(TV_ASSETS / 'icon-130.png')
    splash_bytes = _read_bytes(TV_ASSETS / 'splash-1920x1080.png')
    bridge_bytes = _read_bytes(WEBOS_DIR / 'webos-bridge.js')
    index_bytes = _render_platform_index(
        '',
        '<script src="webos-bridge.js" defer></script>',
    )

    data_entries: list[tuple[str, bytes]] = [
        (f'{install_prefix}/appinfo.json', appinfo_bytes),
        (f'{install_prefix}/icon-80.png', icon80_bytes),
        (f'{install_prefix}/icon-130.png', icon130_bytes),
        (f'{install_prefix}/splash-1920x1080.png', splash_bytes),
        (f'{install_prefix}/index.html', index_bytes),
        (f'{install_prefix}/webos-bridge.js', bridge_bytes),
    ]
    for rel, payload in _collect_shared_web_files():
        data_entries.append((f'{install_prefix}/{rel}', payload))

    installed_kb = max(1, (sum(len(p) for _, p in data_entries) + 1023) // 1024)
    control_text = (
        f'Package: {app_id}\n'
        f'Version: {version}\n'
        'Section: misc\n'
        'Priority: optional\n'
        'Architecture: all\n'
        f'Installed-Size: {installed_kb}\n'
        'Maintainer: Mavie <support@mavie.app>\n'
        'Description: Mavie Akilli TV Medya Merkezi\n'
        'webOS-Package-Format-Version: 2\n'
        'webOS-Packager-Version: 1.0\n'
    ).encode('utf-8')

    control_tar_gz = _make_tar_gz([('./control', control_text)])
    data_tar_gz = _make_tar_gz(data_entries)
    ipk_bytes = _make_ar_archive([
        ('debian-binary', b'2.0\n'),
        ('control.tar.gz', control_tar_gz),
        ('data.tar.gz', data_tar_gz),
    ])

    out_dir.mkdir(parents=True, exist_ok=True)
    ipk_path = out_dir / 'Mavie-webOS.ipk'
    ipk_path.write_bytes(ipk_bytes)
    return ipk_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build Mavie Samsung Tizen (.wgt) and LG webOS (.ipk) packages.')
    parser.add_argument('--out-dir', default=str(ROOT / 'dist'), help='Output directory (default: dist/)')
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir).resolve()

    wgt = build_tizen_wgt(out_dir)
    ipk = build_webos_ipk(out_dir)
    print(f'Built {wgt} ({wgt.stat().st_size:,} bytes)')
    print(f'Built {ipk} ({ipk.stat().st_size:,} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
