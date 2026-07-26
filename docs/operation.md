# Betriebshandbuch

## Service verwalten

Status:

```bash
sudo systemctl status zrzavy-energy-monitor.service
```

Start:

```bash
sudo systemctl start zrzavy-energy-monitor.service
```

Stopp:

```bash
sudo systemctl stop zrzavy-energy-monitor.service
```

Neustart:

```bash
sudo systemctl restart zrzavy-energy-monitor.service
```

Autostart prüfen:

```bash
systemctl is-enabled zrzavy-energy-monitor.service
```

## Logs anzeigen

Letzte Meldungen:

```bash
journalctl -u zrzavy-energy-monitor.service -n 100 --no-pager
```

Live-Ansicht:

```bash
journalctl -u zrzavy-energy-monitor.service -f
```

Seit dem letzten Systemstart:

```bash
journalctl -u zrzavy-energy-monitor.service -b
```

Updater:

```bash
journalctl -u zrzavy-energy-monitor-updater.service -n 200 --no-pager
```

Vor der Veröffentlichung von Logs Zugangsdaten, interne Adressen und Seriennummern entfernen.

## Healthcheck

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:8787/api/health
```

Der Kern-Healthcheck soll den Zustand der Anwendung, nicht die permanente Erreichbarkeit aller externen Messgeräte bewerten. Ein ausgeschalteter Shelly darf daher als Warnung erscheinen, ohne automatisch ein Release-Rollback auszulösen.

## Installierte Version

```bash
cat /opt/zrzavy-energy-monitor/current/VERSION
readlink -f /opt/zrzavy-energy-monitor/current
```

Alternativ über die API:

```bash
curl --silent http://127.0.0.1:8787/api/system/version
```

## Wichtige Pfade

| Inhalt | Referenzpfad |
|---|---|
| aktives Release | `/opt/zrzavy-energy-monitor/current` |
| versionierte Releases | `/opt/zrzavy-energy-monitor/releases/` |
| Konfiguration | `/etc/zrzavy-energy-monitor/config.json` |
| SQLite-Datenbank | `/var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db` |
| Update-Status | `/var/lib/zrzavy-energy-monitor/update-status.json` |
| Update-Anforderung | `/var/lib/zrzavy-energy-monitor/update-request.json` |
| Backups | `/var/lib/zrzavy-energy-monitor/backups/` |
| Update-Downloads | `/var/cache/zrzavy-energy-monitor/updates/` |
| Updater-Logs | `/var/log/zrzavy-energy-monitor/` |

Bei älteren Installationen können Konfiguration und Daten noch direkt im Anwendungsordner liegen.

## Manuelles Backup

Anwendung für eine konsistente Sicherung stoppen:

```bash
sudo systemctl stop zrzavy-energy-monitor.service
```

Backup erstellen:

```bash
BACKUP="$HOME/zrzavy-energy-monitor-$(date +%Y%m%d-%H%M%S).tar.gz"

sudo tar -czf "$BACKUP" \
  /etc/zrzavy-energy-monitor \
  /var/lib/zrzavy-energy-monitor/data \
  /var/lib/zrzavy-energy-monitor/update-status.json 2>/dev/null || true

sudo chown "$USER":"$USER" "$BACKUP"
```

Danach:

```bash
sudo systemctl start zrzavy-energy-monitor.service
```

Backup prüfen:

```bash
tar -tzf "$BACKUP"
```

Ein Backup ist erst dann vertrauenswürdig, wenn seine Wiederherstellung mindestens einmal getestet wurde.

## SQLite-Datenbank prüfen

Integrität:

```bash
sqlite3 /var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db \
  "PRAGMA integrity_check;"
```

Erwartete Ausgabe:

```text
ok
```

Dateigröße:

```bash
du -h /var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db
```

Vor direkten SQL-Änderungen immer ein Backup erstellen. Die Datenbank sollte normalerweise ausschließlich durch Zrzavy Energy Monitor verwaltet werden.

## Dateirechte prüfen

```bash
sudo stat /etc/zrzavy-energy-monitor/config.json
sudo stat /var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db
sudo namei -l /opt/zrzavy-energy-monitor/current/app/config.json
sudo namei -l /opt/zrzavy-energy-monitor/current/app/data
```

Der Zrzavy-Energy-Monitor-Service-Benutzer benötigt:

- Leserechte auf Programmdateien,
- Leserechte auf die Konfiguration,
- Schreibrechte auf Datenbank und Laufzeitdaten,
- keine allgemeinen Root-Rechte.

## Speicherplatz kontrollieren

```bash
df -h /
du -sh /opt/zrzavy-energy-monitor
du -sh /var/lib/zrzavy-energy-monitor
du -sh /var/cache/zrzavy-energy-monitor
```

Alte Release-Downloads im Cache können nach erfolgreicher Sicherung und Prüfung entfernt werden. Das aktive Release, das unmittelbar vorherige Release und mindestens ein funktionierendes Backup sollten erhalten bleiben.

## Regelmäßige Betriebsprüfung

Empfohlen mindestens monatlich:

- Service läuft und ist aktiviert.
- Healthcheck antwortet.
- Gerätewerte sind aktuell.
- Systemzeit stimmt.
- Datenbankintegrität ist `ok`.
- Freier Speicherplatz ist ausreichend.
- Backup ist vorhanden.
- Update-Status enthält keinen dauerhaften Fehler.
- Raspberry Pi und Abhängigkeiten erhalten Sicherheitsupdates.
