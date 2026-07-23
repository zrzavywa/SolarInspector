#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\n[SolarInspector] %s\n' "$*"; }
warn() { printf '\n[WARNUNG] %s\n' "$*" >&2; }
die() { printf '\n[FEHLER] %s\n' "$*" >&2; return 1; }

if [[ -f "$SCRIPT_DIR/VERSION" ]]; then
  PACKAGE_DIR="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/../VERSION" ]]; then
  PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  die "VERSION-Datei wurde im Paket nicht gefunden."
fi

VERSION_FILE="$PACKAGE_DIR/VERSION"
VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "Ungültige Version in $VERSION_FILE: $VERSION"
fi

APP_SOURCE="$PACKAGE_DIR/app"
SERVICE_NAME="solarinspector.service"
INSTALL_DIR_OVERRIDE=""
NO_START=0

usage() {
  cat <<EOF
SolarInspector ${VERSION} – Raspberry-Pi-Upgrade

Verwendung:
  ./Upgrade-SolarInspector-RaspberryPi.sh [Optionen]

Optionen:
  --install-dir PFAD   Installationsordner explizit angeben
  --service NAME       systemd-Service, Standard: solarinspector.service
  --no-start           Service nach dem Upgrade nicht starten
  -h, --help           Hilfe anzeigen
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 ]] || die "Nach --install-dir fehlt der Pfad."
      INSTALL_DIR_OVERRIDE="$2"; shift 2 ;;
    --service)
      [[ $# -ge 2 ]] || die "Nach --service fehlt der Name."
      SERVICE_NAME="$2"; [[ "$SERVICE_NAME" == *.service ]] || SERVICE_NAME+=".service"; shift 2 ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unbekannte Option: $1" ;;
  esac
done

[[ "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+\.service$ ]] || die "Ungültiger Servicename: $SERVICE_NAME"

[[ -f "$APP_SOURCE/solarinspector.py" ]] || die "Das Verzeichnis app/ ist unvollständig. Bitte das ZIP vollständig entpacken."
[[ -f "$APP_SOURCE/modbus_solakon.py" ]] || die "modbus_solakon.py fehlt."

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  SUDO=""
  RUN_USER="${SUDO_USER:-root}"
else
  command -v sudo >/dev/null 2>&1 || die "sudo ist nicht installiert."
  SUDO="sudo"
  RUN_USER="$(id -un)"
fi

run_as_service_user() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    if [[ "$SERVICE_USER" == "root" ]]; then
      "$@"
    else
      command -v runuser >/dev/null 2>&1 || die "runuser ist nicht verfügbar."
      runuser -u "$SERVICE_USER" -- "$@"
    fi
  else
    sudo -u "$SERVICE_USER" -- "$@"
  fi
}

user_home() {
  getent passwd "$1" | cut -d: -f6
}

service_exists() {
  systemctl cat "$SERVICE_NAME" >/dev/null 2>&1
}

SERVICE_EXISTED=0
OLD_SERVICE_FILE=""
OLD_WORKING_DIR=""
SERVICE_USER=""

if service_exists; then
  SERVICE_EXISTED=1
  OLD_SERVICE_FILE="$(systemctl show "$SERVICE_NAME" -p FragmentPath --value 2>/dev/null || true)"
  OLD_WORKING_DIR="$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value 2>/dev/null || true)"
  SERVICE_USER="$(systemctl show "$SERVICE_NAME" -p User --value 2>/dev/null || true)"
fi

[[ -n "$SERVICE_USER" ]] || SERVICE_USER="$RUN_USER"
SERVICE_GROUP="$(id -gn "$SERVICE_USER" 2>/dev/null || echo "$SERVICE_USER")"
SERVICE_HOME="$(user_home "$SERVICE_USER")"
[[ -n "$SERVICE_HOME" ]] || SERVICE_HOME="$(user_home "$RUN_USER")"
[[ -n "$SERVICE_HOME" ]] || SERVICE_HOME="/home/$RUN_USER"

find_install_dir() {
  if [[ -n "$INSTALL_DIR_OVERRIDE" ]]; then
    printf '%s\n' "$INSTALL_DIR_OVERRIDE"
    return
  fi
  if [[ -n "$OLD_WORKING_DIR" ]]; then
    printf '%s\n' "$OLD_WORKING_DIR"
    return
  fi

  local candidate
  for candidate in \
    "/opt/solarinspector" \
    "$SERVICE_HOME/SolarInspector" \
    "$SERVICE_HOME/SolarInspector_4.0" \
    "$SERVICE_HOME/SolarInspector_3.0" \
    "$SERVICE_HOME/solarinspector"; do
    if [[ -f "$candidate/solarinspector.py" ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  printf '%s\n' "$SERVICE_HOME/SolarInspector"
}

INSTALL_DIR="$(realpath -m "$(find_install_dir)")"
INSTALL_DIR="${INSTALL_DIR%/}"
[[ -n "$INSTALL_DIR" && "$INSTALL_DIR" != "/" ]] || die "Ungültiger Installationspfad."

BACKUP_ROOT="$SERVICE_HOME/SolarInspector-Backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="$BACKUP_ROOT/solarinspector-before-${VERSION}-${TIMESTAMP}.tar.gz"
SERVICE_BACKUP="$BACKUP_ROOT/${SERVICE_NAME}.${TIMESTAMP}.service"
ROLLBACK_REQUIRED=0

on_error() {
  local exit_code=$?
  warn "Upgrade bei Zeile ${BASH_LINENO[0]} fehlgeschlagen (Code ${exit_code})."
  if [[ $ROLLBACK_REQUIRED -eq 1 && -f "$BACKUP_FILE" ]]; then
    warn "Die vorherige Version wird automatisch wiederhergestellt."
    $SUDO systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
    $SUDO tar -xzf "$BACKUP_FILE" -C "$INSTALL_DIR" || true
    $SUDO chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR" || true
    if [[ $SERVICE_EXISTED -eq 1 && -f "$SERVICE_BACKUP" && -n "$OLD_SERVICE_FILE" ]]; then
      $SUDO cp "$SERVICE_BACKUP" "$OLD_SERVICE_FILE" || true
      $SUDO systemctl daemon-reload || true
    elif [[ $SERVICE_EXISTED -eq 0 ]]; then
      $SUDO rm -f "/etc/systemd/system/$SERVICE_NAME" || true
      $SUDO systemctl daemon-reload || true
    fi
    $SUDO systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
    warn "Rollback abgeschlossen. Backup: $BACKUP_FILE"
  elif [[ $SERVICE_EXISTED -eq 1 ]]; then
    $SUDO systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
    warn "Der unveränderte bisherige Service wurde wieder gestartet."
  fi
  exit "$exit_code"
}
trap on_error ERR

log "Zielversion: SolarInspector $VERSION"
echo "Installationsordner: $INSTALL_DIR"
echo "Service:             $SERVICE_NAME"
echo "Service-Benutzer:    $SERVICE_USER"

if [[ $SERVICE_EXISTED -eq 1 ]]; then
  log "Bestehenden Service stoppen"
  $SUDO systemctl stop "$SERVICE_NAME"
fi

log "Backup der bestehenden Installation erstellen"
$SUDO mkdir -p "$BACKUP_ROOT"
$SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$BACKUP_ROOT"

EXISTING_ITEM=""
if [[ -d "$INSTALL_DIR" ]]; then
  EXISTING_ITEM="$($SUDO find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)"
fi
if [[ -n "$EXISTING_ITEM" ]]; then
  $SUDO tar \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='./tests/__pycache__' \
    --exclude='./data/solarinspector.pid' \
    -czf "$BACKUP_FILE" -C "$INSTALL_DIR" .
else
  $SUDO mkdir -p "$INSTALL_DIR"
  $SUDO tar -czf "$BACKUP_FILE" --files-from /dev/null
fi
$SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$BACKUP_FILE"

if [[ $SERVICE_EXISTED -eq 1 && -n "$OLD_SERVICE_FILE" && -f "$OLD_SERVICE_FILE" ]]; then
  $SUDO cp "$OLD_SERVICE_FILE" "$SERVICE_BACKUP"
  $SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$SERVICE_BACKUP"
fi
ROLLBACK_REQUIRED=1

echo "Backup:              $BACKUP_FILE"

log "Python und venv-Unterstützung prüfen"
NEED_APT=0
if ! command -v python3 >/dev/null 2>&1; then
  NEED_APT=1
else
  if ! python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    die "SolarInspector ${VERSION} benötigt Python 3.11 oder neuer."
  fi
  if ! python3 -m venv --help >/dev/null 2>&1; then
    NEED_APT=1
  fi
fi

if [[ $NEED_APT -eq 1 ]]; then
  log "Fehlende Raspberry-Pi-Pakete installieren"
  $SUDO apt-get update
  $SUDO apt-get install -y python3 python3-venv ca-certificates
fi

log "Programmdateien aktualisieren"
$SUDO mkdir -p "$INSTALL_DIR"
# config.json und data/ werden absichtlich nicht überschrieben.
tar --exclude='./config.json' --exclude='./data' -cf - -C "$APP_SOURCE" . | $SUDO tar -xf - -C "$INSTALL_DIR"
if [[ ! -f "$INSTALL_DIR/config.json" ]]; then
  $SUDO cp "$APP_SOURCE/config.json" "$INSTALL_DIR/config.json"
fi
$SUDO mkdir -p "$INSTALL_DIR/data"
$SUDO rm -rf "$INSTALL_DIR/__pycache__" "$INSTALL_DIR/tests/__pycache__"
$SUDO chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"

log "Konfiguration verlustfrei auf Version 4.0 erweitern"
$SUDO python3 "$PACKAGE_DIR/tools/migrate_config.py" "$INSTALL_DIR/config.json"
$SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/config.json"

log "Virtuelle Python-Umgebung vorbereiten"
NEED_PIP=0
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  $SUDO rm -rf "$INSTALL_DIR/.venv"
  run_as_service_user python3 -m venv "$INSTALL_DIR/.venv"
  NEED_PIP=1
elif ! run_as_service_user "$INSTALL_DIR/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import flask
import requests
import waitress
PY
then
  NEED_PIP=1
fi

if [[ $NEED_PIP -eq 1 ]]; then
  log "Python-Abhängigkeiten installieren beziehungsweise reparieren"
  run_as_service_user "$INSTALL_DIR/.venv/bin/python" -m pip install \
    --disable-pip-version-check \
    -r "$INSTALL_DIR/requirements.txt"
else
  log "Vorhandene Python-Abhängigkeiten sind vollständig und werden weiterverwendet"
fi
log "Pakettests ausführen"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT
cp -a "$APP_SOURCE/." "$TEST_DIR/"
(
  cd "$TEST_DIR"
  PYTHONPATH="$TEST_DIR" "$INSTALL_DIR/.venv/bin/python" -m unittest discover -s tests -v
)
rm -rf "$TEST_DIR"
trap - EXIT
trap on_error ERR

log "Datenbankschema von Version 3 auf Version 4 migrieren"
(
  cd "$INSTALL_DIR"
  run_as_service_user "$INSTALL_DIR/.venv/bin/python" - <<'PY'
import solarinspector
stats = solarinspector.database.stats()
print(f"Datenbank bereit: {stats.get('count', 0)} Messpunkte")
PY
)

log "systemd-Service einrichten"
$SUDO tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null <<EOF
[Unit]
Description=SolarInspector ${VERSION}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$INSTALL_DIR
ExecStart="$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/solarinspector.py" --no-browser
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
UMask=0027

[Install]
WantedBy=multi-user.target
EOF

log "systemd-Service-Datei prüfen"
if command -v systemd-analyze >/dev/null 2>&1; then
  $SUDO systemd-analyze verify "/etc/systemd/system/$SERVICE_NAME"
fi

$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME" >/dev/null

if [[ $NO_START -eq 0 ]]; then
  log "SolarInspector ${VERSION} starten"
  $SUDO systemctl restart "$SERVICE_NAME"

  PORT="$(run_as_service_user "$INSTALL_DIR/.venv/bin/python" - "$INSTALL_DIR/config.json" <<'PY'
import json
import sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(int(cfg.get('general', {}).get('port', 8787)))
PY
)"

  log "Weboberfläche prüfen"
  HEALTH_OK=0
  for _ in $(seq 1 25); do
    if "$INSTALL_DIR/.venv/bin/python" - "$PORT" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request
port = int(sys.argv[1])
with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as response:
    payload = json.load(response)
    if "running" not in payload:
        raise RuntimeError("Ungültige Statusantwort")
PY
    then
      HEALTH_OK=1
      break
    fi
    sleep 1
  done

  if [[ $HEALTH_OK -ne 1 ]]; then
    $SUDO journalctl -u "$SERVICE_NAME" -n 80 --no-pager || true
    die "SolarInspector antwortet nach dem Upgrade nicht auf Port $PORT."
  fi
else
  PORT="$(run_as_service_user "$INSTALL_DIR/.venv/bin/python" - "$INSTALL_DIR/config.json" <<'PY'
import json
import sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(int(cfg.get('general', {}).get('port', 8787)))
PY
)"
fi

IP_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -n "$IP_ADDRESS" ]] || IP_ADDRESS="IP-DES-RASPBERRY-PI"

UPGRADE_INFO="$(mktemp)"
cat > "$UPGRADE_INFO" <<EOF
SolarInspector $VERSION
Upgrade: $(date --iso-8601=seconds)
Installationsordner: $INSTALL_DIR
Service: $SERVICE_NAME
Backup: $BACKUP_FILE
Dashboard: http://$IP_ADDRESS:$PORT/
Konfiguration: http://$IP_ADDRESS:$PORT/configuration
EOF
$SUDO mv "$UPGRADE_INFO" "$INSTALL_DIR/upgrade-info.txt"
$SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/upgrade-info.txt"

ROLLBACK_REQUIRED=0
trap - ERR

log "Upgrade erfolgreich abgeschlossen"
echo "Dashboard:      http://$IP_ADDRESS:$PORT/"
echo "Konfiguration:  http://$IP_ADDRESS:$PORT/configuration"
echo "Service-Status: sudo systemctl status $SERVICE_NAME"
echo "Live-Log:       journalctl -u $SERVICE_NAME -f"
echo "Backup:         $BACKUP_FILE"
if [[ $NO_START -eq 1 ]]; then
  echo "Hinweis: Der Service wurde wegen --no-start nicht gestartet."
fi
