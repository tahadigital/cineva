#!/usr/bin/env python3
"""Canonical Mavie Brand Logo & Multi-Platform App Icon Generator.

Single source of truth for the refined Liquid Glass Mavie monogram:
bold obsidian 'M' with concentric bottom-left arch cradling a circular 'o'
cinema lens ring, outlined in the signature violet -> blue -> cyan prism
(#7C3AED -> #3B82F6 -> #06B6D4).

Regenerates:
  - website/mavie-mark.svg & public/mavie-mark.svg
  - website/icon.svg       & public/icon.svg
  - android/app/src/main/res/drawable/mavie_mark.xml
  - android/app/src/main/res/drawable/ic_launcher_background.xml
  - android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml
  - android/app/src/main/res/mipmap-anydpi-v33/ic_launcher.xml
  - android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png
  - android/app/src/main/res/drawable-xhdpi/tv_banner.png (320x180 Android TV Leanback banner)
  - tv/assets/{icon-512,icon-130,icon-80,splash-1920x1080}.png (Samsung Tizen & LG webOS)
  - windows/mavie.ico (16, 24, 32, 48, 64, 128, 256 px RGBA PNG-in-ICO)
  - apple/macOS/Assets.xcassets/AppIcon.appiconset/* (via generate_app_icons.swift)
  - apple/iOS/Assets.xcassets/AppIcon.appiconset/AppIcon.png (1024x1024 opaque)
"""
from __future__ import annotations

import platform
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Exact canonical cubic Bezier paths in 256x256 coordinate space.
# Shared identically across SVG, Android VectorDrawable, and CoreGraphics (Swift).
M_PATH = (
    "M23.5,40.0 "
    "C23.5,32.5 27.2,29.2 34.5,28.5 "
    "C56.5,26.2 77.5,26.5 95.5,29.0 "
    "C101.0,29.8 103.8,32.8 105.4,38.0 "
    "L129.0,128.5 "
    "L152.6,38.0 "
    "C154.2,32.8 157.0,29.8 162.5,29.0 "
    "C180.5,26.5 201.5,26.2 223.5,28.5 "
    "C230.8,29.2 234.5,32.5 234.5,40.0 "
    "L234.5,207.5 "
    "C234.5,218.5 227.5,224.5 216.0,224.5 "
    "L195.5,224.5 "
    "C188.5,224.5 184.5,220.2 184.5,213.0 "
    "L184.5,110.0 "
    "L180.0,110.0 "
    "L150.5,214.0 "
    "C148.5,221.0 143.5,224.5 136.0,224.5 "
    "L123.5,224.5 "
    "C113.0,224.5 107.5,219.0 107.5,208.5 "
    "L107.5,181.5 "
    "C107.5,160.61 96.99,141.42 80.18,131.61 "
    "C63.36,121.81 42.99,122.98 27.20,134.66 "
    "C24.80,136.44 23.50,134.60 23.50,130.00 "
    "Z"
)


def _ellipse_cubics(cx: float, cy: float, rx: float, ry: float, *, ccw: bool = False) -> str:
    k = 0.5522847498
    kx, ky = rx * k, ry * k
    if not ccw:
        return (
            f"M{cx:.2f},{cy - ry:.2f} "
            f"C{cx + kx:.2f},{cy - ry:.2f} {cx + rx:.2f},{cy - ky:.2f} {cx + rx:.2f},{cy:.2f} "
            f"C{cx + rx:.2f},{cy + ky:.2f} {cx + kx:.2f},{cy + ry:.2f} {cx:.2f},{cy + ry:.2f} "
            f"C{cx - kx:.2f},{cy + ry:.2f} {cx - rx:.2f},{cy + ky:.2f} {cx - rx:.2f},{cy:.2f} "
            f"C{cx - rx:.2f},{cy - ky:.2f} {cx - kx:.2f},{cy - ry:.2f} {cx:.2f},{cy - ry:.2f} Z"
        )
    return (
        f"M{cx:.2f},{cy - ry:.2f} "
        f"C{cx - kx:.2f},{cy - ry:.2f} {cx - rx:.2f},{cy - ky:.2f} {cx - rx:.2f},{cy:.2f} "
        f"C{cx - rx:.2f},{cy + ky:.2f} {cx - kx:.2f},{cy + ry:.2f} {cx:.2f},{cy + ry:.2f} "
        f"C{cx + kx:.2f},{cy + ry:.2f} {cx + rx:.2f},{cy + ky:.2f} {cx + rx:.2f},{cy:.2f} "
        f"C{cx + rx:.2f},{cy - ky:.2f} {cx + kx:.2f},{cy - ry:.2f} {cx:.2f},{cy - ry:.2f} Z"
    )


O_OUTER = _ellipse_cubics(56.0, 181.5, 35.0, 39.0, ccw=False)
O_INNER = _ellipse_cubics(56.0, 181.5, 13.8, 15.6, ccw=False)
O_DONUT = f"{O_OUTER} {_ellipse_cubics(56.0, 181.5, 13.8, 15.6, ccw=True)}"


def build_mavie_mark_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="obsidianCore" x1="18%" y1="0%" x2="82%" y2="100%">
      <stop offset="0%" stop-color="#161C32"/>
      <stop offset="42%" stop-color="#090D18"/>
      <stop offset="100%" stop-color="#03050A"/>
    </linearGradient>
    <linearGradient id="mRim" x1="4%" y1="44%" x2="96%" y2="56%">
      <stop offset="0%" stop-color="#7C3AED"/>
      <stop offset="22%" stop-color="#3B82F6"/>
      <stop offset="50%" stop-color="#06B6D4"/>
      <stop offset="78%" stop-color="#3B82F6"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
    <linearGradient id="oRim" x1="8%" y1="50%" x2="92%" y2="50%">
      <stop offset="0%" stop-color="#7C3AED"/>
      <stop offset="50%" stop-color="#06B6D4"/>
      <stop offset="100%" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="oInnerRim" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop offset="0%" stop-color="#06B6D4"/>
      <stop offset="50%" stop-color="#3B82F6"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
  </defs>
  <path d="{M_PATH}" fill="url(#obsidianCore)" stroke="url(#mRim)" stroke-width="10.8" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="{O_DONUT}" fill="url(#obsidianCore)" fill-rule="evenodd"/>
  <path d="{O_OUTER}" fill="none" stroke="url(#oRim)" stroke-width="10.8"/>
  <path d="{O_INNER}" fill="none" stroke="url(#oInnerRim)" stroke-width="9.2"/>
</svg>
"""


def build_icon_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="cardBg" x1="12%" y1="0%" x2="88%" y2="100%">
      <stop offset="0%" stop-color="#12172C"/>
      <stop offset="48%" stop-color="#0B0E1A"/>
      <stop offset="100%" stop-color="#05070E"/>
    </linearGradient>
    <radialGradient id="violetAura" cx="24%" cy="24%" r="62%">
      <stop offset="0%" stop-color="#7C3AED" stop-opacity="0.30"/>
      <stop offset="55%" stop-color="#3B82F6" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="#05070E" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="cyanAura" cx="62%" cy="68%" r="58%">
      <stop offset="0%" stop-color="#06B6D4" stop-opacity="0.21"/>
      <stop offset="52%" stop-color="#3B82F6" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#05070E" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="glassSheen" x1="25%" y1="0%" x2="55%" y2="58%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.12"/>
      <stop offset="38%" stop-color="#FFFFFF" stop-opacity="0.025"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="cardBorder" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.26"/>
      <stop offset="35%" stop-color="#7C3AED" stop-opacity="0.24"/>
      <stop offset="72%" stop-color="#3B82F6" stop-opacity="0.20"/>
      <stop offset="100%" stop-color="#06B6D4" stop-opacity="0.30"/>
    </linearGradient>
    <linearGradient id="topSpecular" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0"/>
      <stop offset="22%" stop-color="#FFFFFF" stop-opacity="0.30"/>
      <stop offset="50%" stop-color="#FFFFFF" stop-opacity="0.44"/>
      <stop offset="78%" stop-color="#FFFFFF" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="obsidianCore" x1="18%" y1="0%" x2="82%" y2="100%">
      <stop offset="0%" stop-color="#161C32"/>
      <stop offset="42%" stop-color="#090D18"/>
      <stop offset="100%" stop-color="#03050A"/>
    </linearGradient>
    <linearGradient id="mRim" x1="4%" y1="44%" x2="96%" y2="56%">
      <stop offset="0%" stop-color="#7C3AED"/>
      <stop offset="22%" stop-color="#3B82F6"/>
      <stop offset="50%" stop-color="#06B6D4"/>
      <stop offset="78%" stop-color="#3B82F6"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
    <linearGradient id="oRim" x1="8%" y1="50%" x2="92%" y2="50%">
      <stop offset="0%" stop-color="#7C3AED"/>
      <stop offset="50%" stop-color="#06B6D4"/>
      <stop offset="100%" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="oInnerRim" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop offset="0%" stop-color="#06B6D4"/>
      <stop offset="50%" stop-color="#3B82F6"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
    <filter id="rimGlow" x="-22%" y="-22%" width="144%" height="144%">
      <feGaussianBlur stdDeviation="5.2"/>
    </filter>
  </defs>
  <rect x="4" y="4" width="248" height="248" rx="58" fill="url(#cardBg)"/>
  <rect x="4" y="4" width="248" height="248" rx="58" fill="url(#violetAura)"/>
  <rect x="4" y="4" width="248" height="248" rx="58" fill="url(#cyanAura)"/>
  <rect x="4" y="4" width="248" height="248" rx="58" fill="url(#glassSheen)"/>
  <rect x="6.5" y="6.5" width="243" height="243" rx="55.5" fill="none" stroke="url(#cardBorder)" stroke-width="2.5"/>
  <path d="M56,7.5 L200,7.5" stroke="url(#topSpecular)" stroke-width="1.8" stroke-linecap="round"/>
  <g transform="translate(24.5,26.0) scale(0.808)" opacity="0.32" filter="url(#rimGlow)">
    <path d="{M_PATH}" fill="none" stroke="url(#mRim)" stroke-width="12.5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="{O_OUTER}" fill="none" stroke="url(#oRim)" stroke-width="12.5"/>
  </g>
  <g transform="translate(24.5,26.0) scale(0.808)">
    <path d="{M_PATH}" fill="url(#obsidianCore)" stroke="url(#mRim)" stroke-width="10.2" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="{O_DONUT}" fill="url(#obsidianCore)" fill-rule="evenodd"/>
    <path d="{O_OUTER}" fill="none" stroke="url(#oRim)" stroke-width="10.2"/>
    <path d="{O_INNER}" fill="none" stroke="url(#oInnerRim)" stroke-width="8.8"/>
  </g>
</svg>
"""


def build_android_foreground_xml() -> str:
    return f"""<vector xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:aapt="http://schemas.android.com/aapt"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <!-- Centered inside Android 66dp circular adaptive safe zone -->
    <group
        android:translateX="22"
        android:translateY="22.5"
        android:scaleX="0.25"
        android:scaleY="0.25">
        <path
            android:pathData="{M_PATH}"
            android:strokeWidth="11.2"
            android:strokeLineJoin="round"
            android:strokeLineCap="round">
            <aapt:attr name="android:fillColor">
                <gradient
                    android:startX="46"
                    android:startY="26"
                    android:endX="210"
                    android:endY="226"
                    android:type="linear">
                    <item android:offset="0.0" android:color="#FF161C32"/>
                    <item android:offset="0.45" android:color="#FF090D18"/>
                    <item android:offset="1.0" android:color="#FF03050A"/>
                </gradient>
            </aapt:attr>
            <aapt:attr name="android:strokeColor">
                <gradient
                    android:startX="10"
                    android:startY="112"
                    android:endX="246"
                    android:endY="144"
                    android:type="linear">
                    <item android:offset="0.0" android:color="#FF7C3AED"/>
                    <item android:offset="0.22" android:color="#FF3B82F6"/>
                    <item android:offset="0.50" android:color="#FF06B6D4"/>
                    <item android:offset="0.78" android:color="#FF3B82F6"/>
                    <item android:offset="1.0" android:color="#FF7C3AED"/>
                </gradient>
            </aapt:attr>
        </path>
        <path
            android:pathData="{O_DONUT}"
            android:fillType="evenOdd">
            <aapt:attr name="android:fillColor">
                <gradient
                    android:startX="24"
                    android:startY="142"
                    android:endX="88"
                    android:endY="222"
                    android:type="linear">
                    <item android:offset="0.0" android:color="#FF161C32"/>
                    <item android:offset="0.50" android:color="#FF090D18"/>
                    <item android:offset="1.0" android:color="#FF03050A"/>
                </gradient>
            </aapt:attr>
        </path>
        <path
            android:pathData="{O_OUTER}"
            android:fillColor="@android:color/transparent"
            android:strokeWidth="11.2">
            <aapt:attr name="android:strokeColor">
                <gradient
                    android:startX="26"
                    android:startY="181.5"
                    android:endX="86"
                    android:endY="181.5"
                    android:type="linear">
                    <item android:offset="0.0" android:color="#FF7C3AED"/>
                    <item android:offset="0.50" android:color="#FF06B6D4"/>
                    <item android:offset="1.0" android:color="#FF3B82F6"/>
                </gradient>
            </aapt:attr>
        </path>
        <path
            android:pathData="{O_INNER}"
            android:fillColor="@android:color/transparent"
            android:strokeWidth="9.4">
            <aapt:attr name="android:strokeColor">
                <gradient
                    android:startX="56"
                    android:startY="165.9"
                    android:endX="56"
                    android:endY="197.1"
                    android:type="linear">
                    <item android:offset="0.0" android:color="#FF06B6D4"/>
                    <item android:offset="0.50" android:color="#FF3B82F6"/>
                    <item android:offset="1.0" android:color="#FF7C3AED"/>
                </gradient>
            </aapt:attr>
        </path>
    </group>
</vector>
"""


def build_android_background_xml() -> str:
    return """<vector xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:aapt="http://schemas.android.com/aapt"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path android:pathData="M0,0 H108 V108 H0 Z">
        <aapt:attr name="android:fillColor">
            <gradient
                android:startX="14"
                android:startY="0"
                android:endX="94"
                android:endY="108"
                android:type="linear">
                <item android:offset="0.0" android:color="#FF12172C"/>
                <item android:offset="0.48" android:color="#FF0B0E1A"/>
                <item android:offset="1.0" android:color="#FF05070E"/>
            </gradient>
        </aapt:attr>
    </path>
    <path android:pathData="M0,0 H108 V108 H0 Z">
        <aapt:attr name="android:fillColor">
            <gradient
                android:centerX="26"
                android:centerY="26"
                android:gradientRadius="68"
                android:type="radial">
                <item android:offset="0.0" android:color="#4D7C3AED"/>
                <item android:offset="0.55" android:color="#1A3B82F6"/>
                <item android:offset="1.0" android:color="#0005070E"/>
            </gradient>
        </aapt:attr>
    </path>
    <path android:pathData="M0,0 H108 V108 H0 Z">
        <aapt:attr name="android:fillColor">
            <gradient
                android:centerX="68"
                android:centerY="74"
                android:gradientRadius="64"
                android:type="radial">
                <item android:offset="0.0" android:color="#3606B6D4"/>
                <item android:offset="0.52" android:color="#143B82F6"/>
                <item android:offset="1.0" android:color="#0005070E"/>
            </gradient>
        </aapt:attr>
    </path>
</vector>
"""


def build_android_adaptive_v26_xml() -> str:
    return """<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/mavie_mark"/>
</adaptive-icon>
"""


def build_android_adaptive_v33_xml() -> str:
    return """<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/mavie_mark"/>
    <monochrome android:drawable="@drawable/mavie_mark"/>
</adaptive-icon>
"""


def pack_ico(entries: list[tuple[int, bytes]]) -> bytes:
    """Pack RGBA PNG images into a standard Windows multi-resolution .ico file."""
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)
    dir_entries: list[bytes] = []
    offset = 6 + 16 * count
    blobs: list[bytes] = []
    for size, png_bytes in entries:
        dim = 0 if size >= 256 else size
        dir_entries.append(
            struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png_bytes), offset)
        )
        blobs.append(png_bytes)
        offset += len(png_bytes)
    return header + b"".join(dir_entries) + b"".join(blobs)


def _find_macos_swift_cmd() -> list[str]:
    sdk = ""
    try:
        xcrun_sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
    except Exception:
        xcrun_sdk = ""
    candidates = [
        "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
        xcrun_sdk,
    ]
    for cand in candidates:
        if cand and Path(cand).is_dir():
            sdk = cand
            break
    arch = platform.machine() or "arm64"
    cmd = ["swift"]
    if sdk:
        cmd += ["-sdk", sdk]
    cmd += ["-target", f"{arch}-apple-macosx13.0"]
    return cmd


def main() -> None:
    mark_svg = build_mavie_mark_svg()
    icon_svg = build_icon_svg()

    for rel in ("website/mavie-mark.svg", "public/mavie-mark.svg"):
        (ROOT / rel).write_text(mark_svg, encoding="utf-8")
    for rel in ("website/icon.svg", "public/icon.svg"):
        (ROOT / rel).write_text(icon_svg, encoding="utf-8")

    # Android vector drawables & adaptive icon XMLs
    res_dir = ROOT / "android" / "app" / "src" / "main" / "res"
    (res_dir / "drawable" / "mavie_mark.xml").write_text(build_android_foreground_xml(), encoding="utf-8")
    (res_dir / "drawable" / "ic_launcher_background.xml").write_text(build_android_background_xml(), encoding="utf-8")
    (res_dir / "mipmap-anydpi-v26" / "ic_launcher.xml").write_text(build_android_adaptive_v26_xml(), encoding="utf-8")
    (res_dir / "mipmap-anydpi-v33" / "ic_launcher.xml").write_text(build_android_adaptive_v33_xml(), encoding="utf-8")

    swift_script = ROOT / "apple" / "macOS" / "scripts" / "generate_app_icons.swift"
    swift_cmd = _find_macos_swift_cmd()

    with tempfile.TemporaryDirectory(prefix="mavie-brand-gen-") as tmp:
        tmp_path = Path(tmp)
        iconset_dir = tmp_path / "AppIcon.iconset"
        mac_assets = ROOT / "apple" / "macOS" / "Assets.xcassets" / "AppIcon.appiconset"
        ios_icon = ROOT / "apple" / "iOS" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon.png"

        # 1. Generate all 10 macOS icons + 1024x1024 iOS icon
        subprocess.run(
            swift_cmd + [str(swift_script), str(iconset_dir), str(mac_assets), str(ios_icon)],
            check=True,
        )

        # Verify iconutil can compile AppIcon.icns cleanly
        if shutil.which("iconutil"):
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(tmp_path / "AppIcon.icns")],
                check=True,
            )

        # 2. Render crisp native squircle PNGs for Windows ICO & Android mipmaps
        win_sizes = [16, 24, 32, 48, 64, 128, 256]
        android_mips = {
            "mdpi": 48,
            "hdpi": 72,
            "xhdpi": 96,
            "xxhdpi": 144,
            "xxxhdpi": 192,
        }
        all_sizes = sorted(set(win_sizes) | set(android_mips.values()))
        squircles_dir = tmp_path / "squircles"
        subprocess.run(
            swift_cmd + [str(swift_script), "--render-squircles", str(squircles_dir), *(str(s) for s in all_sizes)],
            check=True,
        )
        png_by_size: dict[int, bytes] = {
            sz: (squircles_dir / f"squircle_{sz}.png").read_bytes()
            for sz in all_sizes
        }

        # Write multi-resolution windows/mavie.ico
        ico_path = ROOT / "windows" / "mavie.ico"
        ico_bytes = pack_ico([(sz, png_by_size[sz]) for sz in win_sizes])
        ico_path.write_bytes(ico_bytes)

        # Write Android legacy raster launcher PNGs
        for dpi, sz in android_mips.items():
            dst = res_dir / f"mipmap-{dpi}" / "ic_launcher.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(png_by_size[sz])

        # 3. Generate Smart TV icons/splash & Android TV 320x180 Leanback banner
        tv_assets_dir = ROOT / "tv" / "assets"
        android_tv_banner = res_dir / "drawable-xhdpi" / "tv_banner.png"
        subprocess.run(
            swift_cmd + [str(swift_script), "--render-tv-assets", str(tv_assets_dir), str(android_tv_banner)],
            check=True,
        )

    print("All Mavie brand assets regenerated cleanly (Web SVGs, Windows ICO, macOS, iOS, Android, Smart TV).")


if __name__ == "__main__":
    main()
