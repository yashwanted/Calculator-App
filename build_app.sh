#!/usr/bin/env bash
# Build dist/Calculator.app and dist/Calculator.dmg with one command: ./build_app.sh
set -euo pipefail

cd "$(dirname "$0")"
APP="dist/Calculator.app"
DMG="dist/Calculator.dmg"
PYTHON=".venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "==> Creating the virtual environment"
    python3 -m venv .venv
fi

echo "==> Installing build dependencies"
"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements.txt

echo "==> Creating the app icon"
"$PYTHON" packaging/make_icns.py

echo "==> Building the app"
"$PYTHON" -m PyInstaller --noconfirm --clean --log-level WARN Calculator.spec

echo "==> Signing the app (ad-hoc)"
# Finder details and similar extras would make codesign refuse the bundle.
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "==> Testing the built app"
REPORT="$(mktemp -t calculator-self-test)"
trap 'rm -f "$REPORT"' EXIT
if ! "$APP/Contents/MacOS/Calculator" --self-test "$REPORT"; then
    echo "The built app failed its self-test:" >&2
    cat "$REPORT" >&2
    exit 1
fi

echo "==> Creating the disk image"
rm -f "$DMG"
"$PYTHON" packaging/make_dmg_background.py build/dmg/background.png
# dmgbuild lays out the window (background, icon positions) without Finder.
# Its output is only shown on failure, as hdiutil prints deprecation notices.
if ! .venv/bin/dmgbuild -s packaging/dmg_settings.py \
    -D app="$APP" -D icon=packaging/Calculator.icns \
    -D background=build/dmg/background.png \
    Calculator "$DMG" > build/dmg/dmgbuild.log 2>&1; then
    cat build/dmg/dmgbuild.log >&2
    exit 1
fi
hdiutil verify -quiet "$DMG"

echo
echo "Done: $PWD/$APP ($(du -sh "$APP" | cut -f1))"
echo "      $PWD/$DMG ($(du -sh "$DMG" | cut -f1))"
