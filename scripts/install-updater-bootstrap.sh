#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Dieses Skript muss mit sudo ausgeführt werden."
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UPDATER_DIR="/opt/zrzavy-energy-monitor/updater"
STATE_DIR="/var/lib/zrzavy-energy-monitor"
CACHE_DIR="/var/cache/zrzavy-energy-monitor/updates"
LOG_DIR="/var/log/zrzavy-energy-monitor"
SERVICE_USER="${ZRZAVY_ENERGY_MONITOR_SERVICE_USER:-solarinspector}"
SERVICE_GROUP="${ZRZAVY_ENERGY_MONITOR_SERVICE_GROUP:-$SERVICE_USER}"

echo "[Zrzavy Energy Monitor] Verzeichnisse vorbereiten"

install -d -m 0755 /opt/zrzavy-energy-monitor
install -d -m 0755 /opt/zrzavy-energy-monitor/releases
install -d -m 0755 "$UPDATER_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0775 "$STATE_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0775 "$(dirname "$CACHE_DIR")"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0775 "$CACHE_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0755 "$LOG_DIR"

echo "[Zrzavy Energy Monitor] Updater installieren"

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

echo "[Zrzavy Energy Monitor] Virtuelle Umgebung erstellen"

python3 -m venv "$UPDATER_DIR/.venv"

"$UPDATER_DIR/.venv/bin/python" -m pip install \
  --upgrade pip

"$UPDATER_DIR/.venv/bin/python" -m pip install \
  -r "$UPDATER_DIR/requirements.txt"

echo "[Zrzavy Energy Monitor] systemd Units installieren"

install -m 0644 \
  "$SOURCE_DIR/systemd/zrzavy-energy-monitor.service" \
  /etc/systemd/system/zrzavy-energy-monitor.service

install -m 0644 \
  "$SOURCE_DIR/systemd/zrzavy-energy-monitor-updater.service" \
  /etc/systemd/system/zrzavy-energy-monitor-updater.service

install -m 0644 \
  "$SOURCE_DIR/systemd/zrzavy-energy-monitor-updater.path" \
  /etc/systemd/system/zrzavy-energy-monitor-updater.path

systemctl daemon-reload
systemctl enable --now zrzavy-energy-monitor-updater.path

echo "[Zrzavy Energy Monitor] Updater erfolgreich installiert"
systemctl status zrzavy-energy-monitor-updater.path --no-pager
