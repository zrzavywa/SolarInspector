#!/usr/bin/env bash
set -Eeuo pipefail

export COPYFILE_DISABLE=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$ROOT_DIR/VERSION"
DIST_DIR="$ROOT_DIR/dist"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "Fehler: VERSION-Datei fehlt."
  exit 1
fi

VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Fehler: Ungültige Version: $VERSION"
  exit 1
fi

PACKAGE_NAME="SolarInspector-${VERSION}"
PACKAGE_DIR="$DIST_DIR/$PACKAGE_NAME"
ARCHIVE="$DIST_DIR/${PACKAGE_NAME}.tar.gz"

rm -rf "$DIST_DIR"
mkdir -p "$PACKAGE_DIR"

mkdir -p "$PACKAGE_DIR/app"

rsync -a \
  --exclude='config.json' \
  --exclude='config.local.json' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.log' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  "$ROOT_DIR/app/" \
  "$PACKAGE_DIR/app/"

cp -R "$ROOT_DIR/scripts" "$PACKAGE_DIR/"
cp -R "$ROOT_DIR/tools" "$PACKAGE_DIR/"
cp -R "$ROOT_DIR/docs" "$PACKAGE_DIR/"
cp -R "$ROOT_DIR/updater" "$PACKAGE_DIR/"
cp -R "$ROOT_DIR/systemd" "$PACKAGE_DIR/"
cp "$ROOT_DIR/VERSION" "$PACKAGE_DIR/"
cp "$ROOT_DIR/LICENSE" "$PACKAGE_DIR/"
cp "$ROOT_DIR/README.md" "$PACKAGE_DIR/"
cp "$ROOT_DIR/release-manifest.json" "$PACKAGE_DIR/"
cp "$ROOT_DIR/CHANGELOG.md" "$PACKAGE_DIR/"

find "$PACKAGE_DIR" \
  -type d -name '__pycache__' \
  -prune -exec rm -rf {} +

find "$PACKAGE_DIR" \
  -type f \( -name '*.pyc' -o -name '.DS_Store' \) \
  -delete

FORBIDDEN_FILES="$(
  find "$PACKAGE_DIR" \
    \( \
      -name 'config.json' \
      -o -name 'config.local.json' \
      -o -name '*.db' \
      -o -name '*.sqlite' \
      -o -name '*.sqlite3' \
      -o -name '*.log' \
      -o -name '*.pyc' \
      -o -name '*.pyo' \
    \) \
    -print
)"

if [[ -n "$FORBIDDEN_FILES" ]]; then
  echo "Fehler: Das Release enthält unzulässige Dateien:"
  echo "$FORBIDDEN_FILES"
  exit 1
fi


find "$PACKAGE_DIR" \
  -type f \
  \( -name '.DS_Store' -o -name '._*' \) \
  -delete

find "$DIST_DIR" \
  -maxdepth 1 \
  -type f \
  -name '._*' \
  -delete

COPYFILE_DISABLE=1 tar -czf "$ARCHIVE" \
  -C "$DIST_DIR" \
  "$PACKAGE_NAME"

if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$ARCHIVE" > "${ARCHIVE}.sha256"
else
  sha256sum "$ARCHIVE" > "${ARCHIVE}.sha256"
fi

echo "Release-Paket erstellt:"
echo "$ARCHIVE"
echo "${ARCHIVE}.sha256"
