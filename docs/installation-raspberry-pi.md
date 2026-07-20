# Installation auf Raspberry Pi

## Geltungsbereich

Diese Anleitung beschreibt eine Referenzinstallation der SolarInspector-4.1-Reihe auf Raspberry Pi OS beziehungsweise einem Debian-basierten Linux-System.

Für den produktiven Betrieb wird empfohlen:

- Raspberry Pi 3B oder neuer
- Raspberry Pi OS Bookworm oder neuer
- Python 3.11 oder neuer
- lokaler Netzwerkzugriff auf Solakon ONE und/oder Shelly-Geräte
- Benutzerkonto mit `sudo`-Rechten
- feste oder reservierte IP-Adresse für den Raspberry Pi
- korrekte Systemzeit über NTP

> Die älteren Upgrade-Skripte für SolarInspector 3.x und 4.0.x gehören zum Übergangspfad. Die 4.1-Reihe verwendet zusätzlich ein versioniertes Release-Layout und einen getrennten Updater.

## 1. Betriebssystem vorbereiten

```bash
sudo apt update
sudo apt full-upgrade
sudo apt install python3 python3-venv python3-pip curl ca-certificates
python3 --version
```

Die Ausgabe sollte mindestens Python 3.11 zeigen.

## 2. Service-Benutzer und Verzeichnisse vorbereiten

```bash
sudo useradd --system \
  --home /var/lib/solarinspector \
  --shell /usr/sbin/nologin \
  solarinspector 2>/dev/null || true

sudo install -d -o root -g root /opt/solarinspector/releases
sudo install -d -o solarinspector -g solarinspector /etc/solarinspector
sudo install -d -o solarinspector -g solarinspector /var/lib/solarinspector/data
sudo install -d -o solarinspector -g solarinspector /var/lib/solarinspector/backups
sudo install -d -o solarinspector -g solarinspector /var/cache/solarinspector/updates
sudo install -d -o solarinspector -g solarinspector /var/log/solarinspector
```

Alternativ kann ein vorhandener Benutzer verwendet werden. In diesem Fall müssen Service-Datei, Dateirechte und Besitzverhältnisse konsistent angepasst werden.

## 3. Release herunterladen

Auf der GitHub-Releases-Seite die Dateien der gewünschten Version herunterladen:

- `SolarInspector-<VERSION>.tar.gz`
- `SolarInspector-<VERSION>.tar.gz.sha256`
- `release-manifest.json`

Beispielhaft werden die Dateien zunächst nach `/tmp/solarinspector-release` kopiert.

```bash
mkdir -p /tmp/solarinspector-release
cd /tmp/solarinspector-release
```

## 4. Prüfsumme kontrollieren

```bash
sha256sum -c SolarInspector-<VERSION>.tar.gz.sha256
```

Nur fortfahren, wenn die Prüfung erfolgreich ist.

## 5. Release entpacken

Das veröffentlichte Archiv enthält einen gemeinsamen obersten Projektordner. Für das Side-by-side-Layout wird der Inhalt in einen eindeutig benannten Versionsordner entpackt:

```bash
RELEASE_DIR="/opt/solarinspector/releases/<VERSION>"

sudo install -d -o root -g root "$RELEASE_DIR"
sudo tar -xzf SolarInspector-<VERSION>.tar.gz \
  --strip-components=1 \
  -C "$RELEASE_DIR"
```

Version prüfen:

```bash
cat "$RELEASE_DIR/VERSION"
find "$RELEASE_DIR" -maxdepth 2 -type f -name VERSION -print
```

Nur fortfahren, wenn die angezeigte Version der gewünschten Release-Version entspricht.

## 6. Persistente Konfiguration anlegen

Beim ersten Start:

```bash
sudo cp \
  /opt/solarinspector/releases/<VERSION>/app/config.example.json \
  /etc/solarinspector/config.json

sudo chown solarinspector:solarinspector \
  /etc/solarinspector/config.json

sudo chmod 600 /etc/solarinspector/config.json
```

Die Konfiguration anschließend anhand der [Konfigurationsreferenz](configuration.md) bearbeiten.

```bash
sudoedit /etc/solarinspector/config.json
```

Für einen Raspberry Pi im Heimnetz typischerweise:

```json
{
  "general": {
    "bind_host": "0.0.0.0",
    "port": 8787,
    "open_browser": false
  }
}
```

Die vollständige Datei muss alle benötigten Abschnitte aus `config.example.json` enthalten.

## 7. Persistente Pfade verknüpfen

```bash
RELEASE_DIR="/opt/solarinspector/releases/<VERSION>"

sudo rm -f "$RELEASE_DIR/app/config.json"
sudo ln -s /etc/solarinspector/config.json \
  "$RELEASE_DIR/app/config.json"

sudo rm -rf "$RELEASE_DIR/app/data"
sudo ln -s /var/lib/solarinspector/data \
  "$RELEASE_DIR/app/data"
```

## 8. Virtuelle Python-Umgebung erstellen

```bash
sudo python3 -m venv "$RELEASE_DIR/.venv"

sudo "$RELEASE_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo "$RELEASE_DIR/.venv/bin/python" -m pip install \
  -r "$RELEASE_DIR/app/requirements.txt"
```

## 9. Release aktivieren

```bash
sudo ln -sfn "$RELEASE_DIR" /opt/solarinspector/current
readlink -f /opt/solarinspector/current
```

Die Ausgabe muss auf den erwarteten Release-Ordner zeigen.

## 10. systemd-Service einrichten

Datei `/etc/systemd/system/solarinspector.service`:

```ini
[Unit]
Description=SolarInspector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=solarinspector
Group=solarinspector
WorkingDirectory=/opt/solarinspector/current/app
ExecStart=/opt/solarinspector/current/.venv/bin/python /opt/solarinspector/current/app/solarinspector.py --no-browser
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=SOLARINSPECTOR_CONFIG_PATH=/etc/solarinspector/config.json
Environment=SOLARINSPECTOR_DATABASE_PATH=/var/lib/solarinspector/data/solarinspector.db
Environment=SOLARINSPECTOR_UPDATE_STATUS_PATH=/var/lib/solarinspector/update-status.json
Environment=SOLARINSPECTOR_UPDATE_REQUEST_PATH=/var/lib/solarinspector/update-request.json
Environment=SOLARINSPECTOR_UPDATE_CACHE_DIR=/var/cache/solarinspector/updates

[Install]
WantedBy=multi-user.target
```

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now solarinspector.service
sudo systemctl status solarinspector.service
```

## 11. Healthcheck und Browserzugriff prüfen

Lokal auf dem Raspberry Pi:

```bash
curl --fail http://127.0.0.1:8787/api/health
```

Im Browser:

```text
http://<IP-DES-RASPBERRY-PI>:8787/
```

## 12. Privilegierten Updater installieren

Das Repository enthält dafür das Bootstrap-Skript:

```bash
cd /opt/solarinspector/current
sudo ./scripts/install-updater-bootstrap.sh
```

Danach prüfen:

```bash
systemctl status solarinspector-updater.path
systemctl cat solarinspector-updater.service
```

Der Updater sollte erst aktiviert werden, nachdem der normale Service und der lokale Healthcheck zuverlässig funktionieren.

## 13. Erstkonfiguration

1. Weboberfläche öffnen.
2. Solakon ONE und/oder Shelly-Geräte konfigurieren.
3. Verbindungstests ausführen.
4. Vorzeichen der Hausanschlussmessung prüfen.
5. Messquellen für Solarleistung und Netzleistung auswählen.
6. Datenerfassung zunächst manuell testen.
7. Erst danach Autostart aktivieren.

## Upgrade einer bestehenden Installation

Vor jedem manuellen Upgrade:

```bash
sudo systemctl stop solarinspector.service
sudo tar -czf \
  "$HOME/solarinspector-backup-$(date +%Y%m%d-%H%M%S).tar.gz" \
  /etc/solarinspector \
  /var/lib/solarinspector
```

Bestehende Installationen der 3.x- oder frühen 4.0-Reihe können das enthaltene Upgrade-Skript verwenden. Vorher sollte dessen Zielversion und Installationspfad kontrolliert werden, da es zum Übergangsmodell gehört.

## Deinstallation

Vor der Deinstallation immer Konfiguration und Datenbank sichern.

```bash
sudo systemctl disable --now solarinspector.service
sudo systemctl disable --now solarinspector-updater.path
```

Anschließend können Programm- und Laufzeitverzeichnisse gezielt entfernt werden. `/etc/solarinspector` und `/var/lib/solarinspector` sollten nur gelöscht werden, wenn Sicherung und Messdaten nicht mehr benötigt werden.
