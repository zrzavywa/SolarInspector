# Installation auf Raspberry Pi

## Geltungsbereich

Diese Anleitung beschreibt eine Referenzinstallation von Zrzavy Energy Monitor 4.5 auf Raspberry Pi OS beziehungsweise einem Debian-basierten Linux-System.

Für den produktiven Betrieb wird empfohlen:

- Raspberry Pi 3B oder neuer
- Raspberry Pi OS Bookworm oder neuer
- Python 3.11 oder neuer
- lokaler Netzwerkzugriff auf Solakon ONE und/oder Shelly-Geräte
- Benutzerkonto mit `sudo`-Rechten
- feste oder reservierte IP-Adresse für den Raspberry Pi
- korrekte Systemzeit über NTP

> Für eine vorhandene SolarInspector-4.1.3-Installation gilt ausschließlich die [direkte Migrationsanleitung](migration-from-solarinspector.md). Die folgenden Schritte beschreiben eine neue Installation.

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
  --home /var/lib/zrzavy-energy-monitor \
  --shell /usr/sbin/nologin \
  zemonitor 2>/dev/null || true

sudo install -d -o root -g root /opt/zrzavy-energy-monitor/releases
sudo install -d -o zemonitor -g zemonitor /etc/zrzavy-energy-monitor
sudo install -d -o zemonitor -g zemonitor /var/lib/zrzavy-energy-monitor/data
sudo install -d -o zemonitor -g zemonitor /var/lib/zrzavy-energy-monitor/backups
sudo install -d -o zemonitor -g zemonitor /var/cache/zrzavy-energy-monitor/updates
sudo install -d -o zemonitor -g zemonitor /var/log/zrzavy-energy-monitor
```

Alternativ kann ein vorhandener Benutzer verwendet werden. In diesem Fall müssen Service-Datei, Dateirechte und Besitzverhältnisse konsistent angepasst werden.

## 3. Release herunterladen

Auf der GitHub-Releases-Seite die Dateien der gewünschten Version herunterladen:

- `zrzavy-energy-monitor-<VERSION>.tar.gz`
- `zrzavy-energy-monitor-<VERSION>.tar.gz.sha256`
- `release-manifest.json`

Beispielhaft werden die Dateien zunächst nach `/tmp/zrzavy-energy-monitor-release` kopiert.

```bash
mkdir -p /tmp/zrzavy-energy-monitor-release
cd /tmp/zrzavy-energy-monitor-release
```

## 4. Prüfsumme kontrollieren

```bash
sha256sum -c zrzavy-energy-monitor-<VERSION>.tar.gz.sha256
```

Nur fortfahren, wenn die Prüfung erfolgreich ist.

## 5. Release entpacken

Das veröffentlichte Archiv enthält einen gemeinsamen obersten Projektordner. Für das Side-by-side-Layout wird der Inhalt in einen eindeutig benannten Versionsordner entpackt:

```bash
RELEASE_DIR="/opt/zrzavy-energy-monitor/releases/<VERSION>"

sudo install -d -o root -g root "$RELEASE_DIR"
sudo tar -xzf zrzavy-energy-monitor-<VERSION>.tar.gz \
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
  /opt/zrzavy-energy-monitor/releases/<VERSION>/app/config.example.json \
  /etc/zrzavy-energy-monitor/config.json

sudo chown zemonitor:zemonitor \
  /etc/zrzavy-energy-monitor/config.json

sudo chmod 600 /etc/zrzavy-energy-monitor/config.json
```

Die Konfiguration anschließend anhand der [Konfigurationsreferenz](configuration.md) bearbeiten.

```bash
sudoedit /etc/zrzavy-energy-monitor/config.json
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
RELEASE_DIR="/opt/zrzavy-energy-monitor/releases/<VERSION>"

sudo rm -f "$RELEASE_DIR/app/config.json"
sudo ln -s /etc/zrzavy-energy-monitor/config.json \
  "$RELEASE_DIR/app/config.json"

sudo rm -rf "$RELEASE_DIR/app/data"
sudo ln -s /var/lib/zrzavy-energy-monitor/data \
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
sudo ln -sfn "$RELEASE_DIR" /opt/zrzavy-energy-monitor/current
readlink -f /opt/zrzavy-energy-monitor/current
```

Die Ausgabe muss auf den erwarteten Release-Ordner zeigen.

## 10. systemd-Service einrichten

Die mitgelieferte Datei `systemd/zrzavy-energy-monitor.service` wird nach
`/etc/systemd/system/zrzavy-energy-monitor.service` installiert.

```ini
[Unit]
Description=Zrzavy Energy Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zemonitor
Group=zemonitor
WorkingDirectory=/opt/zrzavy-energy-monitor/current
ExecStart=/opt/zrzavy-energy-monitor/current/.venv/bin/python /opt/zrzavy-energy-monitor/current/app/zrzavy_energy_monitor.py --no-browser
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=ZRZAVY_ENERGY_MONITOR_CONFIG_PATH=/etc/zrzavy-energy-monitor/config.json
Environment=ZRZAVY_ENERGY_MONITOR_DATABASE_PATH=/var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db
Environment=ZRZAVY_ENERGY_MONITOR_UPDATE_STATUS_PATH=/var/lib/zrzavy-energy-monitor/update-status.json
Environment=ZRZAVY_ENERGY_MONITOR_UPDATE_REQUEST_PATH=/var/lib/zrzavy-energy-monitor/update-request.json
Environment=ZRZAVY_ENERGY_MONITOR_UPDATE_CACHE_DIR=/var/cache/zrzavy-energy-monitor/updates

[Install]
WantedBy=multi-user.target
```

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zrzavy-energy-monitor.service
sudo systemctl status zrzavy-energy-monitor.service
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
cd /opt/zrzavy-energy-monitor/current
sudo ./scripts/install-updater-bootstrap.sh
```

Danach prüfen:

```bash
systemctl status zrzavy-energy-monitor-updater.path
systemctl cat zrzavy-energy-monitor-updater.service
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
sudo systemctl stop zrzavy-energy-monitor.service
sudo tar -czf \
  "$HOME/zrzavy-energy-monitor-backup-$(date +%Y%m%d-%H%M%S).tar.gz" \
  /etc/zrzavy-energy-monitor \
  /var/lib/zrzavy-energy-monitor
```

Bestehende Installationen der 3.x- oder frühen 4.0-Reihe können das enthaltene Upgrade-Skript verwenden. Vorher sollte dessen Zielversion und Installationspfad kontrolliert werden, da es zum Übergangsmodell gehört.

## Deinstallation

Vor der Deinstallation immer Konfiguration und Datenbank sichern.

```bash
sudo systemctl disable --now zrzavy-energy-monitor.service
sudo systemctl disable --now zrzavy-energy-monitor-updater.path
```

Anschließend können Programm- und Laufzeitverzeichnisse gezielt entfernt werden. `/etc/zrzavy-energy-monitor` und `/var/lib/zrzavy-energy-monitor` sollten nur gelöscht werden, wenn Sicherung und Messdaten nicht mehr benötigt werden.
