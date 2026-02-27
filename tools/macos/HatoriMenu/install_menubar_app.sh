#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP_NAME="HatoriMenu"
APP_DIR="$HOME/Applications/${APP_NAME}.app"
BIN_DIR="$APP_DIR/Contents/MacOS"
RES_DIR="$APP_DIR/Contents/Resources"
TMP_SWIFT="/tmp/${APP_NAME}.swift"

mkdir -p "$BIN_DIR" "$RES_DIR"

sed "s#__REPO_ROOT__#${REPO_ROOT}#g" "$REPO_ROOT/tools/macos/HatoriMenu/main.swift.template" > "$TMP_SWIFT"

swiftc "$TMP_SWIFT" -o "$BIN_DIR/${APP_NAME}" -framework AppKit
cp "$REPO_ROOT/tools/macos/HatoriMenu/MaterialSymbolsOutlined.ttf" "$RES_DIR/MaterialSymbolsOutlined.ttf"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>com.hatori.menubar</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

chmod +x "$BIN_DIR/${APP_NAME}"

echo "Installed: $APP_DIR"
echo "Run: open \"$APP_DIR\""
echo "Add auto-launch: System Settings -> General -> Login Items -> '+' -> $APP_DIR"
