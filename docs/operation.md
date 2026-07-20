# Betriebshandbuch

## Service verwalten

Status:

```bash
sudo systemctl status solarinspector.service
```

Start:

```bash
sudo systemctl start solarinspector.service
```

Stopp:

```bash
sudo systemctl stop solarinspector.service
```

Neustart:

```bash
sudo systemctl restart solarinspector.service
```

Autostart prüfen:

```bash
systemctl is-enabled solarinspector.service
```

## Logs anzeigen

Letzte Meldungen:

```bash
journalctl -u solarinspector.service -n 100 --no-pager
```

Live-Ansicht:

```bash
journalctl -u solarinspector.service -f
```

Seit dem letzten Systemstart:

```bash
journalctl -u solarinspector.service -b
```

Updater:

```bash
journalctl -u solarinspector-updater.service -n 200 --no-pager
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
cat /opt/solarinspector/current/VERSION
readlink -f /opt/solarinspector/current
```

Alternativ über die API:

```bash
curl --silent http://127.0.0.1:8787/api/system/version
```

## Wichtige Pfade

| Inhalt | Referenzpfad |
|---|---|
| aktives Release | `/opt/solarinspector/current` |
| versionierte Releases | `/opt/solarinspector/releases/` |
| Konfiguration | `/etc/solarinspector/config.json` |
| SQLite-Datenbank | `/var/lib/solarinspector/data/solarinspector.db` |
| Update-Status | `/var/lib/solarinspector/update-status.json` |
| Update-Anforderung | `/var/lib/solarinspector/update-request.json` |
| Backups | `/var/lib/solarinspector/backups/` |
| Update-Downloads | `/var/cache/solarinspector/updates/` |
| Updater-Logs | `/var/log/solarinspector/` |

Bei älteren Installationen können Konfiguration und Daten noch direkt im Anwendungsordner liegen.

## Manuelles Backup

Anwendung für eine konsistente Sicherung stoppen:

```bash
sudo systemctl stop solarinspector.service
```

Backup erstellen:

```bash
BACKUP="$HOME/solarinspector-$(date +%Y%m%d-%H%M%S).tar.gz"

sudo tar -czf "$BACKUP" \
  /etc/solarinspector \
  /var/lib/solarinspector/data \
  /var/lib/solarinspector/update-status.json 2>/dev/null || true

sudo chown "$USER":"$USER" "$BACKUP"
```

Danach:

```bash
sudo systemctl start solarinspector.service
```

Backup prüfen:

```bash
tar -tzf "$BACKUP"
```

Ein Backup ist erst dann vertrauenswürdig, wenn seine Wiederherstellung mindestens einmal getestet wurde.

## SQLite-Datenbank prüfen

Integrität:

```bash
sqlite3 /var/lib/solarinspector/data/solarinspector.db \
  "PRAGMA integrity_check;"
```

Erwartete Ausgabe:

```text
ok
```

Dateigröße:

```bash
du -h /var/lib/solarinspector/data/solarinspector.db
```

Vor direkten SQL-Änderungen immer ein Backup erstellen. Die Datenbank sollte normalerweise ausschließlich durch SolarInspector verwaltet werden.

## Dateirechte prüfen

```bash
sudo stat /etc/solarinspector/config.json
sudo stat /var/lib/solarinspector/data/solarinspector.db
sudo namei -l /opt/solarinspector/current/app/config.json
sudo namei -l /opt/solarinspector/current/app/data
```

Der SolarInspector-Service-Benutzer benötigt:

- Leserechte auf Programmdateien,
- Leserechte auf die Konfiguration,
- Schreibrechte auf Datenbank und Laufzeitdaten,
- keine allgemeinen Root-Rechte.

## Speicherplatz kontrollieren

```bash
df -h /
du -sh /opt/solarinspector
du -sh /var/lib/solarinspector
du -sh /var/cache/solarinspector
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
