#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Dieses Skript muss mit sudo ausgeführt werden."
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UPDATER_DIR="/opt/solarinspector/updater"
STATE_DIR="/var/lib/solarinspector"
CACHE_DIR="/var/cache/solarinspector/updates"
LOG_DIR="/var/log/solarinspector"

echo "[SolarInspector] Verzeichnisse vorbereiten"

install -d -m 0755 /opt/solarinspector
install -d -m 0755 /opt/solarinspector/releases
install -d -m 0755 "$UPDATER_DIR"
install -d -m 0775 "$STATE_DIR"
install -d -m 0775 "$CACHE_DIR"
install -d -m 0755 "$LOG_DIR"

echo "[SolarInspector] Updater installieren"

install -m 0644 \
  "$SOURCE_DIR/updater/updater_service.py" \
  "$UPDATER_DIR/updater_service.py"

install -m 0644 \
  "$SOURCE_DIR/updater/release_installer.py" \
  "$UPDATER_DIR/release_installer.py"

install -m 0644 \
  "$SOURCE_DIR/updater/update_status.py" \
  "$UPDATER_DIR/update_status.py"

install -m 0644 \
  "$SOURCE_DIR/updater/requirements.txt" \
  "$UPDATER_DIR/requirements.txt"

echo "[SolarInspector] Virtuelle Umgebung erstellen"

python3 -m venv "$UPDATER_DIR/.venv"

"$UPDATER_DIR/.venv/bin/python" -m pip install \
  --upgrade pip

"$UPDATER_DIR/.venv/bin/python" -m pip install \
  -r "$UPDATER_DIR/requirements.txt"

echo "[SolarInspector] systemd Units installieren"

install -m 0644 \
  "$SOURCE_DIR/systemd/solarinspector-updater.service" \
  /etc/systemd/system/solarinspector-updater.service

install -m 0644 \
  "$SOURCE_DIR/systemd/solarinspector-updater.path" \
  /etc/systemd/system/solarinspector-updater.path

systemctl daemon-reload
systemctl enable --now solarinspector-updater.path

echo "[SolarInspector] Updater erfolgreich installiert"
systemctl status solarinspector-updater.path --no-pager
