#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

BUILD_ROOT="$ROOT_DIR/build/macos"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/Mavie.app"
ICONSET_DIR="$BUILD_ROOT/AppIcon.iconset"
DMG_STAGE="$BUILD_ROOT/dmg_stage"

rm -rf "$BUILD_ROOT" "$APP_BUNDLE" "$DIST_DIR/mavie-server"
mkdir -p "$BUILD_ROOT" "$DIST_DIR" "$ICONSET_DIR"

echo "==> 1. Generating Mavie AppIcon (1024x1024 PNG + AppIcon.icns)"
ICON_PNG="$BUILD_ROOT/AppIcon-1024.png"
python3 - "$ICON_PNG" <<'PY'
import math, os, struct, sys, zlib

out_paths = sys.argv[1:]
W = H = 1024
cx = cy = W / 2.0

def clamp(x):
    return 0 if x < 0 else (255 if x > 255 else int(x))

rows = []
for y in range(H):
    row = bytearray(1 + W * 4)
    row[0] = 0
    dy = y - cy
    for x in range(W):
        dx = x - cx
        # Squircle mask (superellipse p=4.5)
        nx = abs(dx) / (W * 0.46)
        ny = abs(dy) / (H * 0.46)
        squircle = (nx ** 4.5 + ny ** 4.5) ** (1.0 / 4.5)
        if squircle > 1.0:
            continue
        alpha = 255
        if squircle > 0.985:
            alpha = clamp((1.0 - squircle) / 0.015 * 255)

        t = (x + y) / (2.0 * W)
        bg_r = 20 + (8 - 20) * t
        bg_g = 24 + (11 - 24) * t
        bg_b = 43 + (20 - 43) * t

        # Subtle radial purple-turquoise glow
        dist = math.hypot(dx, dy)
        glow = max(0.0, 1.0 - dist / (W * 0.45)) * 0.18
        r = bg_r + (124 - bg_r) * glow
        g = bg_g + (58 - bg_g) * glow
        b = bg_b + (237 - bg_b) * glow

        # Purple (#7C3AED) -> Blue (#3B82F6) -> Turquoise (#06B6D4) ring
        ring_r = W * 0.305
        ring_half = W * 0.036
        ring_dist = abs(dist - ring_r)
        if ring_dist <= ring_half:
            grad = max(0.0, min(1.0, (dx + dy + W * 0.4) / (W * 0.8)))
            if grad < 0.5:
                u = grad * 2.0
                rr = 124.0 + (59.0 - 124.0) * u
                rg = 58.0 + (130.0 - 58.0) * u
                rb = 237.0 + (246.0 - 237.0) * u
            else:
                u = (grad - 0.5) * 2.0
                rr = 59.0 + (6.0 - 59.0) * u
                rg = 130.0 + (182.0 - 130.0) * u
                rb = 246.0 + (212.0 - 246.0) * u
            cov = 1.0 if ring_dist < ring_half - 2.0 else max(0.0, (ring_half - ring_dist) / 2.0)
            r = r * (1 - cov) + rr * cov
            g = g * (1 - cov) + rg * cov
            b = b * (1 - cov) + rb * cov

        # Crisp white play triangle centered slightly right
        px = dx - W * 0.022
        py = abs(dy)
        tri_left = -W * 0.105
        tri_right = W * 0.135
        if tri_left <= px <= tri_right:
            frac = 1.0 - (px - tri_left) / (tri_right - tri_left)
            half_h = frac * (W * 0.145)
            if py <= half_h:
                r = g = b = 255.0

        idx = 1 + x * 4
        row[idx] = clamp(r)
        row[idx + 1] = clamp(g)
        row[idx + 2] = clamp(b)
        row[idx + 3] = alpha
    rows.append(bytes(row))

def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
idat = zlib.compress(b"".join(rows), 6)
png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

for path in out_paths:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png_bytes)
PY

for sz in 16 32 128 256 512; do
    sips -z "$sz" "$sz" "$ICON_PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}.png" >/dev/null
    dbl=$((sz * 2))
    sips -z "$dbl" "$dbl" "$ICON_PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET_DIR" -o "$BUILD_ROOT/AppIcon.icns"

echo "==> 2. Building embedded mavie-server (--onedir) via PyInstaller"
if command -v pyinstaller >/dev/null 2>&1; then
    pyinstaller --noconfirm --distpath "$DIST_DIR" --workpath "$BUILD_ROOT/pyi-work" "$SCRIPT_DIR/mavie_server.spec"
else
    echo "ERROR: pyinstaller not found. Install with: pip install pyinstaller imageio-ffmpeg tzdata" >&2
    exit 1
fi

echo "==> 3. Compiling Mavie macOS app"
if command -v xcodebuild >/dev/null 2>&1 && xcodebuild -version >/dev/null 2>&1; then
    if command -v xcodegen >/dev/null 2>&1; then
        xcodegen generate --spec "$ROOT_DIR/apple/project.yml" --project "$ROOT_DIR/apple"
    fi
    xcodebuild \
        -project "$ROOT_DIR/apple/Mavie.xcodeproj" \
        -scheme MavieMacOS \
        -configuration Release \
        -derivedDataPath "$BUILD_ROOT/derived" \
        CODE_SIGNING_ALLOWED=NO \
        CODE_SIGN_IDENTITY="" \
        build
    BUILT_APP="$(find "$BUILD_ROOT/derived/Build/Products" -maxdepth 3 -type d -name "Mavie.app" | head -n 1)"
    if [ -z "$BUILT_APP" ] || [ ! -d "$BUILT_APP" ]; then
        echo "ERROR: Built Mavie.app not found under $BUILD_ROOT/derived/Build/Products" >&2
        exit 1
    fi
    cp -R "$BUILT_APP" "$APP_BUNDLE"
else
    echo "xcodebuild unavailable; falling back to swiftc CommandLineTools bundle build"
    mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
    SDK_PATH=""
    XCRUN_SDK="$(xcrun --show-sdk-path 2>/dev/null || true)"
    for cand in \
        "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk" \
        "$XCRUN_SDK" \
        /Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk; do
        if [ -n "$cand" ] && [ -d "$cand" ]; then
            if echo 'import Foundation' | swiftc -sdk "$cand" -typecheck - >/dev/null 2>&1; then
                SDK_PATH="$cand"
                break
            fi
        fi
    done
    if [ -z "$SDK_PATH" ]; then
        SDK_PATH="${XCRUN_SDK:-/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk}"
    fi
    echo "Using macOS SDK: $SDK_PATH"
    swiftc \
        -sdk "$SDK_PATH" \
        -O \
        -framework Cocoa \
        -framework SwiftUI \
        -framework WebKit \
        -framework Security \
        -framework Combine \
        "$ROOT_DIR"/apple/Shared/*.swift \
        "$ROOT_DIR"/apple/macOS/*.swift \
        -o "$APP_BUNDLE/Contents/MacOS/Mavie"
    cp "$SCRIPT_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
fi

echo "==> 4. Embedding mavie-server, AppIcon.icns, and verifying Info.plist"
mkdir -p "$APP_BUNDLE/Contents/Resources"
rm -rf "$APP_BUNDLE/Contents/Resources/mavie-server"
cp -R "$DIST_DIR/mavie-server" "$APP_BUNDLE/Contents/Resources/mavie-server"
cp "$BUILD_ROOT/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"

PLIST="$APP_BUNDLE/Contents/Info.plist"
set_plist_str() {
    /usr/libexec/PlistBuddy -c "Set :$1 $2" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$1 string $2" "$PLIST"
}
set_plist_str CFBundleIconFile AppIcon
set_plist_str CFBundleIconName AppIcon
set_plist_str CFBundleDisplayName Mavie
set_plist_str CFBundleShortVersionString 2.2.0
set_plist_str CFBundleVersion 220
/usr/libexec/PlistBuddy -c "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads true" "$PLIST" 2>/dev/null || {
    /usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true" "$PLIST" 2>/dev/null || true
}

# Strict guard: fail the build immediately if the icon or Info.plist icon binding is missing.
test -s "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
ICON_VAL="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "$PLIST")"
if [ "$ICON_VAL" != "AppIcon" ]; then
    echo "ERROR: Expected CFBundleIconFile=AppIcon in $PLIST, got '$ICON_VAL'" >&2
    exit 1
fi
touch "$APP_BUNDLE"

echo "==> 5. Ad-hoc signing nested binaries leaf-first and Mavie.app"
find "$APP_BUNDLE/Contents/Resources/mavie-server" -type f \( -perm +111 -o -name "*.dylib" -o -name "*.so" \) -print0 | while IFS= read -r -d '' bin; do
    codesign --force --sign - "$bin" >/dev/null 2>&1 || true
done
codesign --force --deep --sign - "$APP_BUNDLE"
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"

echo "==> 6. Running macOS bundled server smoke tests (--smoke-test + auto port fallback)"
SMOKE_DATA="$BUILD_ROOT/smoke-data"
mkdir -p "$SMOKE_DATA"
MAVIE_DATA_DIR="$SMOKE_DATA" MAVIE_PORT=18846 "$APP_BUNDLE/Contents/MacOS/Mavie" --smoke-test
# Also verify Mavie starts cleanly without MAVIE_PORT even when default port 8844 is occupied!
MAVIE_DATA_DIR="$SMOKE_DATA" "$APP_BUNDLE/Contents/MacOS/Mavie" --smoke-test

echo "==> 7. Creating Mavie-macOS.dmg and Mavie-macOS.zip"
rm -rf "$DMG_STAGE" "$DIST_DIR/Mavie-macOS.dmg" "$DIST_DIR/Mavie-macOS.zip"
mkdir -p "$DMG_STAGE"
cp -R "$APP_BUNDLE" "$DMG_STAGE/Mavie.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname "Mavie" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DIST_DIR/Mavie-macOS.dmg"
ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$DIST_DIR/Mavie-macOS.zip"

echo "==> Done: $DIST_DIR/Mavie-macOS.dmg & $DIST_DIR/Mavie-macOS.zip"
