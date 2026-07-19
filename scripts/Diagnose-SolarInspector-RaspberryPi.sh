#!/usr/bin/env bash
set -u
SERVICE_NAME="${1:-solarinspector.service}"
[[ "$SERVICE_NAME" == *.service ]] || SERVICE_NAME+=".service"

INSTALL_DIR="$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value 2>/dev/null || true)"
echo "=== SolarInspector Diagnose ==="
echo "Datum:        $(date --iso-8601=seconds)"
echo "Hostname:     $(hostname)"
echo "IP-Adresse:   $(hostname -I 2>/dev/null || true)"
echo "Service:      $SERVICE_NAME"
echo "Installation: ${INSTALL_DIR:-nicht gefunden}"
echo

systemctl --no-pager --full status "$SERVICE_NAME" 2>&1 || true

echo
echo "=== Letzte Logmeldungen ==="
journalctl -u "$SERVICE_NAME" -n 80 --no-pager 2>&1 || true

if [[ -n "$INSTALL_DIR" && -f "$INSTALL_DIR/config.json" ]]; then
  echo
echo "=== Konfiguration ohne Kennwörter ==="
  python3 - "$INSTALL_DIR/config.json" <<'PY' 2>&1 || true
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for section in ("house_meter", "solakon_meter"):
    if section in cfg and "password" in cfg[section]:
        cfg[section]["password"] = "***" if cfg[section]["password"] else ""
print(json.dumps(cfg, indent=2, ensure_ascii=False))
PY
fi
