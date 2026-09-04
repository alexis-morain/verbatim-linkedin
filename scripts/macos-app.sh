#!/usr/bin/env bash
# Build Verbatim.app, a native macOS window over a Verbatim instance.
#
# The executable is a small WKWebView shell (scripts/VerbatimShell.swift),
# compiled here. On launch it asks which instance directory to serve, then
# runs Resources/start.sh, which installs a pinned release of the engine
# from PyPI using the uv binary carried in Resources, brings the server up
# on loopback, and reports its progress as it goes. The shell shows the app
# in its own window and stops the server on quit.
#
#   scripts/macos-app.sh [--port N] [--out DIR] [--uv-version X]
#
# Nothing about a person is burned in any more: no instance path, no clone,
# no git. The app is the same for everybody and the instance is a question
# it asks. Rebuild only to change the port, the pinned uv, or the shell.
#
# The engine version is read from app/pyproject.toml and pinned into the
# bundle. That wheel must already be on PyPI when somebody launches the app:
# publish first, tag second. See the plan.
#
# Needs macOS with the Xcode command line tools (swiftc, sips, iconutil),
# plus curl and shasum. It does NOT need uv or git on the build machine, and
# neither does the machine that runs the result.
#
# The API key is never read from the instance, exactly as everywhere else in
# this bundle. A launched .app has almost no environment, so start.sh sources
# ~/.config/verbatim/env; the shell's Settings sheet is what writes it.
set -euo pipefail

PORT=8748
OUT=""
UV_VERSION="0.11.19"
# Apple Silicon only, deliberately. uv ships one binary per architecture and
# weighs 47 MB, so a universal build doubles the download for an audience
# nobody has measured yet. Same argument as the deferred certificate.
UV_TRIPLE="aarch64-apple-darwin"
SWIFT_TARGET="arm64-apple-macos12.0"

while [ $# -gt 0 ]; do
  case "$1" in
    --port)       PORT="$2"; shift 2 ;;
    --out)        OUT="$2"; shift 2 ;;
    --uv-version) UV_VERSION="$2"; shift 2 ;;
    -h|--help)    sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")/.." && pwd)"

command -v swiftc >/dev/null \
  || { echo "swiftc not found: install the Xcode command line tools" >&2; exit 1; }

# ------------------------------------------------------- the engine version
# Read from the project file rather than repeated here: the DMG and the wheel
# cannot drift in silence if there is only one place the number lives.
ENGINE_VERSION="$(
  awk -F'"' '/^version = "/ { print $2; exit }' "$HERE/app/pyproject.toml"
)"
[ -n "$ENGINE_VERSION" ] || { echo "no version in app/pyproject.toml" >&2; exit 1; }

if [ -n "$OUT" ]; then
  mkdir -p "$OUT"
  APP_HOME="$(cd "$OUT" && pwd)"
else
  APP_HOME="/Applications"
  [ -w "$APP_HOME" ] || APP_HOME="$HOME/Applications"
  mkdir -p "$APP_HOME"
fi
APP="$APP_HOME/Verbatim.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/LICENSES"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ------------------------------------------------------------------- uv
# Downloaded once into a build cache, checked against the checksum Astral
# publishes beside it. A binary this app carries is a binary this script
# proves, every build, rather than trusting whatever landed in the cache.
CACHE="$HOME/Library/Caches/verbatim-build"
mkdir -p "$CACHE"
UV_TAR="$CACHE/uv-$UV_VERSION-$UV_TRIPLE.tar.gz"
UV_SUM="$UV_TAR.sha256"
BASE="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"

[ -f "$UV_TAR" ] || curl -fsSL -o "$UV_TAR" "$BASE/uv-$UV_TRIPLE.tar.gz"
[ -f "$UV_SUM" ] || curl -fsSL -o "$UV_SUM" "$BASE/uv-$UV_TRIPLE.tar.gz.sha256"

EXPECTED="$(awk '{ print $1; exit }' "$UV_SUM")"
ACTUAL="$(shasum -a 256 "$UV_TAR" | awk '{ print $1 }')"
if [ "$EXPECTED" != "$ACTUAL" ]; then
  echo "uv checksum mismatch: expected $EXPECTED, got $ACTUAL" >&2
  echo "  the cached download is suspect; remove $UV_TAR and build again" >&2
  exit 1
fi

tar -xzf "$UV_TAR" -C "$WORK" --strip-components=1
[ -f "$WORK/uv" ] || { echo "no uv binary in the tarball" >&2; exit 1; }
install -m 755 "$WORK/uv" "$APP/Contents/Resources/uv"

# ------------------------------------------------------------- attribution
# The binary travels inside the app, so its licence travels with it. The
# seven Python dependencies are not redistributed here: they arrive from
# PyPI on the person's own machine.
cat > "$APP/Contents/Resources/LICENSES/README.txt" <<NOTICE
Verbatim.app carries one third party binary.

  uv $UV_VERSION, https://github.com/astral-sh/uv
  Copyright (c) Astral Software Inc.
  Licensed under Apache-2.0 OR MIT, at your option.
  Full terms: https://github.com/astral-sh/uv/blob/$UV_VERSION/LICENSE-MIT

Verbatim itself is MIT, Copyright (c) 2026 Alexis Morain.
The Python engine (verbatim-linkedin $ENGINE_VERSION) and its dependencies
are downloaded from PyPI at first launch and are not redistributed here.
NOTICE
cp "$HERE/LICENSE" "$APP/Contents/Resources/LICENSES/verbatim-MIT.txt"

# ---------------------------------------------------------------- the icon
ICONSET="$WORK/verbatim.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$HERE/assets/icon-1024.png" \
       --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$HERE/assets/icon-1024.png" \
       --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/verbatim.icns"

# --------------------------------------------------------------- the shell
# The shell carries the top level code, so it is the one Swift needs to see
# named main.swift. The config file beside it is the same source the tests
# compile against; there is no second copy of it anywhere.
cp "$HERE/scripts/VerbatimShell.swift" "$WORK/main.swift"
cp "$HERE/scripts/VerbatimConfig.swift" "$WORK/config.swift"
swiftc -O -target "$SWIFT_TARGET" \
       -o "$APP/Contents/MacOS/Verbatim" "$WORK/config.swift" "$WORK/main.swift"

# --------------------------------------------------------------- the plist
# Two numbers, on purpose. VerbatimEngineVersion is the wheel this build
# pins; CFBundleVersion is this build of the shell. A shell fix that changes
# no engine advances the second alone.
BUILD_NUMBER="${VERBATIM_BUILD_NUMBER:-1}"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Verbatim</string>
  <key>CFBundleDisplayName</key><string>Verbatim</string>
  <key>CFBundleIdentifier</key><string>fr.morain.verbatim</string>
  <key>CFBundleShortVersionString</key><string>$ENGINE_VERSION</string>
  <key>CFBundleVersion</key><string>$BUILD_NUMBER</string>
  <key>CFBundleExecutable</key><string>Verbatim</string>
  <key>CFBundleIconFile</key><string>verbatim</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>VerbatimPort</key><string>$PORT</string>
  <key>VerbatimEngineVersion</key><string>$ENGINE_VERSION</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

# ------------------------------------------------------------- start.sh
# Install the pinned engine if it is not already there, bring the server up,
# exit 0 only once the port answers. Takes the instance directory as $1.
#
# Lines beginning with "STATUS " are read by the shell and shown in the
# window; everything else goes to the log. Two phases: the install has no
# deadline because it downloads a Python runtime, the port wait keeps its
# minute because a minute is right for what it measures.
cat > "$APP/Contents/Resources/start.sh" <<LAUNCHER
#!/bin/zsh
# Generated by scripts/macos-app.sh. Not hand edited: rebuild instead.
set -u

INSTANCE="\${1:-}"
SUPPORT="\$HOME/Library/Application Support/Verbatim"
LOG="\$HOME/Library/Logs/verbatim.log"
RES="\$(cd "\$(dirname "\$0")" && pwd)"
UV="\$RES/uv"
PORT=$PORT
WANT="$ENGINE_VERSION"

# The app owns its runtime entirely: it never writes into the person's own
# uv tools and never depends on their PATH. Uninstalling is deleting the app
# and this one directory.
export UV_TOOL_DIR="\$SUPPORT/tools"
export UV_TOOL_BIN_DIR="\$SUPPORT/bin"
export UV_PYTHON_INSTALL_DIR="\$SUPPORT/python"
export UV_CACHE_DIR="\$SUPPORT/cache"

status() { echo "STATUS \$1"; }
fail()   { echo "FAIL \$1"; exit 1; }

# What the engine printed since we started it. providers.py refuses a bad
# configuration with a sentence written to be read, and cli.py returns 2
# rather than serving degraded; without this the person gets "it did not
# start" and the one sentence that would tell them why stays in the log.
# One line: the shell paints it into a window and FAIL is line oriented.
engine_said() {
  [ -n "\${LOGMARK:-}" ] || return 0
  tail -c "+\$((LOGMARK + 1))" "\$LOG" 2>/dev/null \
    | grep -v "^warning:" | grep -v "^ *\$" | tail -1
}

# Both, and Logs is not a formality: a brand new account has no
# ~/Library/Logs, every redirection below fails without it, and the engine
# install fails with them. Found by running this on an empty HOME.
mkdir -p "\$SUPPORT" "\$HOME/Library/Logs"
echo "--- launch \$(date '+%Y-%m-%d %H:%M:%S') engine \$WANT" >> "\$LOG"

[ -n "\$INSTANCE" ] || fail "No instance directory was given."
[ -d "\$INSTANCE" ] || fail "That folder is gone: \$INSTANCE"
[ -x "\$UV" ] || fail "The app bundle is incomplete: no uv in Resources. Rebuild it."

# The key and the model live in the environment, never in the instance. An
# app launched from the Finder has almost none, so this file stands in for
# the shell profile. The Settings sheet is what writes it.
if [ -f "\$HOME/.config/verbatim/env" ]; then
  set -a; . "\$HOME/.config/verbatim/env"; set +a
fi

# ------------------------------------------------------------- the engine
HAVE="\$(cat "\$SUPPORT/engine.version" 2>/dev/null || true)"
BIN="\$UV_TOOL_BIN_DIR/verbatim"
if [ "\$HAVE" != "\$WANT" ] || [ ! -x "\$BIN" ]; then
  status "Installing the engine, version \$WANT. First run only."
  if ! "\$UV" tool install --force "verbatim-linkedin==\$WANT" >> "\$LOG" 2>&1; then
    if ! curl -sS -o /dev/null --max-time 10 https://pypi.org/simple/ 2>/dev/null; then
      fail "The first launch needs a network connection: it downloads the engine from PyPI. Connect and open Verbatim again."
    fi
    fail "Installing the engine failed. See ~/Library/Logs/verbatim.log"
  fi
  echo "\$WANT" > "\$SUPPORT/engine.version"
fi

# ------------------------------------------------------------- the server
# Same version already serving? Nothing to do.
PID="\$(cat "\$SUPPORT/server.pid" 2>/dev/null || true)"
if [ -n "\$PID" ] && kill -0 "\$PID" 2>/dev/null; then
  if [ "\$(cat "\$SUPPORT/server.rev" 2>/dev/null)" = "\$WANT|\$INSTANCE" ]; then
    exit 0
  fi
  kill "\$PID" 2>/dev/null
  sleep 1
fi
# Whatever still holds the port is a stale server of ours.
STALE="\$(lsof -ti tcp:\$PORT || true)"
[ -n "\$STALE" ] && echo "\$STALE" | xargs kill 2>/dev/null && sleep 0.5

status "Starting the engine."
LOGMARK="\$(wc -c < "\$LOG" 2>/dev/null || echo 0)"
( nohup "\$BIN" "\$INSTANCE" --port "\$PORT" >> "\$LOG" 2>&1 & echo \$! > "\$SUPPORT/server.pid" )
echo "\$WANT|\$INSTANCE" > "\$SUPPORT/server.rev"

for _ in {1..120}; do
  curl -s -o /dev/null "http://127.0.0.1:\$PORT" && exit 0
  if ! kill -0 "\$(cat "\$SUPPORT/server.pid")" 2>/dev/null; then
    SAID="\$(engine_said)"
    [ -n "\$SAID" ] \
      && fail "The engine stopped: \$SAID" \
      || fail "The engine did not start. See ~/Library/Logs/verbatim.log"
  fi
  sleep 0.5
done
fail "The engine did not answer within a minute. See ~/Library/Logs/verbatim.log"
LAUNCHER
chmod +x "$APP/Contents/Resources/start.sh"

# Ad hoc, which is all an unnotarised build can be. Signing the nested uv
# first: a bundle is only as signed as the executables inside it.
codesign --force -s - "$APP/Contents/Resources/uv" >/dev/null 2>&1 || true
codesign --force -s - "$APP" >/dev/null 2>&1 || true

echo "built $APP"
echo "  engine   verbatim-linkedin==$ENGINE_VERSION, installed from PyPI at first launch"
echo "  uv       $UV_VERSION ($UV_TRIPLE), carried in Resources"
echo "  port     127.0.0.1:$PORT"
echo "  instance asked for on first launch, remembered afterwards"
