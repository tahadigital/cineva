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
TARGET_TRIPLE="$(uname -m)-apple-macosx13.0"

echo "==> 1. Generating Mavie AppIcon (#7C3AED -> #3B82F6 -> #06B6D4) & syncing Assets.xcassets"
swift -sdk "$SDK_PATH" -target "$TARGET_TRIPLE" \
    "$SCRIPT_DIR/scripts/generate_app_icons.swift" \
    "$ICONSET_DIR" \
    "$SCRIPT_DIR/Assets.xcassets/AppIcon.appiconset" \
    "$ROOT_DIR/apple/iOS/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
iconutil -c icns "$ICONSET_DIR" -o "$BUILD_ROOT/AppIcon.icns"

echo "==> 2. Building embedded mavie-server (--onedir) via PyInstaller"
PYINSTALLER_BIN="$(command -v pyinstaller || true)"
if [ -z "$PYINSTALLER_BIN" ] && [ -x "$ROOT_DIR/.venv/bin/pyinstaller" ]; then
    PYINSTALLER_BIN="$ROOT_DIR/.venv/bin/pyinstaller"
fi
if [ -n "$PYINSTALLER_BIN" ]; then
    "$PYINSTALLER_BIN" --noconfirm --distpath "$DIST_DIR" --workpath "$BUILD_ROOT/pyi-work" "$SCRIPT_DIR/mavie_server.spec"
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
    echo "Using macOS SDK: $SDK_PATH ($TARGET_TRIPLE)"
    swiftc \
        -sdk "$SDK_PATH" \
        -target "$TARGET_TRIPLE" \
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
if [ -f "$APP_BUNDLE/Contents/Resources/Assets.car" ]; then
    set_plist_str CFBundleIconName AppIcon
else
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PLIST" 2>/dev/null || true
fi
set_plist_str CFBundleDisplayName Mavie
set_plist_str CFBundleShortVersionString 2.2.0
set_plist_str CFBundleVersion 220
/usr/libexec/PlistBuddy -c "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads true" "$PLIST" 2>/dev/null || {
    /usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true" "$PLIST" 2>/dev/null || true
}

# Strict guard: fail the build immediately if the icon, Info.plist binding, or deployment target is invalid.
test -s "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
ICON_VAL="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "$PLIST")"
if [ "$ICON_VAL" != "AppIcon" ]; then
    echo "ERROR: Expected CFBundleIconFile=AppIcon in $PLIST, got '$ICON_VAL'" >&2
    exit 1
fi
if [ ! -f "$APP_BUNDLE/Contents/Resources/Assets.car" ] && /usr/libexec/PlistBuddy -c "Print :CFBundleIconName" "$PLIST" >/dev/null 2>&1; then
    echo "ERROR: Unexpected CFBundleIconName in $PLIST when Assets.car is absent" >&2
    exit 1
fi
if ! otool -l "$APP_BUNDLE/Contents/MacOS/Mavie" | grep -q "minos 13.0"; then
    echo "ERROR: Expected minos 13.0 in Mavie binary" >&2
    otool -l "$APP_BUNDLE/Contents/MacOS/Mavie" | grep -A4 LC_BUILD_VERSION >&2 || true
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
