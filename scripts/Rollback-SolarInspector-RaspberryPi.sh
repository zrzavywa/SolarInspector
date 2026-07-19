#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="solarinspector.service"
BACKUP_FILE="${1:-}"
INSTALL_DIR="${2:-}"

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

run_as_service_user() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    if [[ "$SERVICE_USER" == "root" ]]; then "$@"; else runuser -u "$SERVICE_USER" -- "$@"; fi
  else
    sudo -u "$SERVICE_USER" -- "$@"
  fi
}

if [[ -z "$INSTALL_DIR" ]]; then
  INSTALL_DIR="$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value 2>/dev/null || true)"
fi
[[ -n "$INSTALL_DIR" && -d "$INSTALL_DIR" ]] || { echo "Installationsordner nicht gefunden. Als zweiten Parameter angeben." >&2; exit 1; }

SERVICE_USER="$(systemctl show "$SERVICE_NAME" -p User --value 2>/dev/null || true)"
[[ -n "$SERVICE_USER" ]] || SERVICE_USER="${SUDO_USER:-$(id -un)}"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"

if [[ -z "$BACKUP_FILE" ]]; then
  BACKUP_FILE="$(find "$SERVICE_HOME/SolarInspector-Backups" -maxdepth 1 -type f -name 'solarinspector-before-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
fi
[[ -f "$BACKUP_FILE" ]] || { echo "Kein Backup gefunden. Backup-Datei als ersten Parameter angeben." >&2; exit 1; }

echo "SolarInspector wird zurückgesetzt."
echo "Installation: $INSTALL_DIR"
echo "Backup:       $BACKUP_FILE"

$SUDO systemctl stop "$SERVICE_NAME" || true
$SUDO tar -xzf "$BACKUP_FILE" -C "$INSTALL_DIR"
$SUDO chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"

if [[ -f "$INSTALL_DIR/requirements.txt" && -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  if ! run_as_service_user "$INSTALL_DIR/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import flask
import requests
import waitress
PY
  then
    run_as_service_user "$INSTALL_DIR/.venv/bin/python" -m pip install \
      --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"
  fi
fi

$SUDO systemctl daemon-reload
$SUDO systemctl restart "$SERVICE_NAME"
$SUDO systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "Rollback abgeschlossen."
