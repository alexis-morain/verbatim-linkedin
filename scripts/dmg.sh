#!/usr/bin/env bash
# Build Verbatim.dmg, the thing somebody downloads.
#
#   scripts/dmg.sh [--out DIR] [--port N]
#
# A staging folder holding the app and a symbolic link to /Applications,
# handed to hdiutil. That is the whole drag and drop window: no background
# image, no icon positions, nothing that needs an AppleScript to place.
#
# The result is NOT signed and NOT notarised. Downloaded through a browser
# it arrives quarantined, and macOS will refuse it with "Verbatim is
# damaged". The release notes carry the one line that clears it. Signing is
# deferred on purpose; when it arrives it is two commands, on the app before
# hdiutil and on the dmg after:
#
#   codesign --force --options runtime --timestamp -s "Developer ID Application: ..."
#   xcrun notarytool submit --wait ... && xcrun stapler staple
set -euo pipefail

OUT="dist"
PORT_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out)  OUT="$2"; shift 2 ;;
    --port) PORT_ARGS=(--port "$2"); shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HERE/$OUT"
OUT="$(cd "$HERE/$OUT" && pwd)"

VERSION="$(awk -F'"' '/^version = "/ { print $2; exit }' "$HERE/app/pyproject.toml")"
[ -n "$VERSION" ] || { echo "no version in app/pyproject.toml" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

"$HERE/scripts/macos-app.sh" --out "$STAGE/root" "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}"
ln -s /Applications "$STAGE/root/Applications"

DMG_PATH="$OUT/Verbatim-$VERSION-arm64.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "Verbatim $VERSION" \
               -srcfolder "$STAGE/root" \
               -ov -quiet -format UDZO "$DMG_PATH"

SIZE="$(du -h "$DMG_PATH" | awk '{ print $1 }')"
echo "built $DMG_PATH ($SIZE)"
echo "  unsigned: a browser download needs"
echo "  xattr -dr com.apple.quarantine /Applications/Verbatim.app"
