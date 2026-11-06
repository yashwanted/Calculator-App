#!/usr/bin/env bash
# Build dist/Calculator.app with one command: ./build_app.sh
set -euo pipefail

cd "$(dirname "$0")"
APP="dist/Calculator.app"
PYTHON=".venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "==> Creating the virtual environment"
    python3 -m venv .venv
fi

echo "==> Installing build dependencies"
"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt

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

echo
echo "Done: $PWD/$APP ($(du -sh "$APP" | cut -f1))"
