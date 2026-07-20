# Troubleshooting

## Erste Diagnose

Diese Befehle liefern den wichtigsten Überblick:

```bash
sudo systemctl status solarinspector.service --no-pager
journalctl -u solarinspector.service -n 100 --no-pager
curl -v http://127.0.0.1:8787/api/health
readlink -f /opt/solarinspector/current
cat /opt/solarinspector/current/VERSION
df -h /
```

Updater zusätzlich:

```bash
systemctl status solarinspector-updater.path --no-pager
journalctl -u solarinspector-updater.service -n 200 --no-pager
python3 -m json.tool /var/lib/solarinspector/update-status.json
```

## Weboberfläche ist nicht erreichbar

### Symptom

Browser meldet Zeitüberschreitung oder Verbindung abgelehnt.

### Prüfungen

```bash
sudo systemctl status solarinspector.service
sudo ss -ltnp | grep 8787
curl -v http://127.0.0.1:8787/api/health
```

Konfiguration kontrollieren:

```bash
grep -n '"bind_host"\|"port"' \
  /etc/solarinspector/config.json
```

Typische Ursachen:

- Service ist beendet.
- JSON-Konfiguration ist ungültig.
- `bind_host` steht auf `127.0.0.1`, obwohl Zugriff aus dem LAN erwartet wird.
- Port `8787` wird bereits verwendet.
- Firewall oder Client-Isolation blockiert den Zugriff.
- Service-Benutzer kann Konfiguration oder Datenbank nicht lesen.

## Service startet nicht

Logs:

```bash
journalctl -u solarinspector.service -b --no-pager
```

Python-Umgebung prüfen:

```bash
/opt/solarinspector/current/.venv/bin/python --version
/opt/solarinspector/current/.venv/bin/python \
  -c "import flask, requests, waitress, packaging; print('OK')"
```

Symlinks prüfen:

```bash
readlink -f /opt/solarinspector/current
readlink -f /opt/solarinspector/current/app/config.json
readlink -f /opt/solarinspector/current/app/data
```

Häufige Ursachen:

- fehlende Python-Abhängigkeit,
- ungültiger `current`-Symlink,
- zyklischer Symlink,
- falsche Dateirechte,
- beschädigte Konfiguration,
- Datenbank nicht schreibbar.

## Solakon ONE ist nicht erreichbar

```bash
ping -c 3 <SOLAKON-IP>
nc -vz <SOLAKON-IP> 502
ip route
```

Prüfen:

- Modbus TCP am Gerät aktiviert,
- richtige IP-Adresse,
- Port `502`,
- Unit-ID `1`, sofern nicht abweichend,
- keine WLAN-Client-Isolation,
- Raspberry Pi und Solakon in routbaren Netzen,
- keine doppelte IP-Adresse.

Eine offene TCP-Verbindung garantiert noch keine passenden Register oder korrekten Werte.

## Shelly ist nicht erreichbar

PM Mini Gen 3:

```bash
curl -v "http://<SHELLY-IP>/rpc/PM1.GetStatus?id=0"
```

Shelly 3EM Gen 1:

```bash
curl -v "http://<SHELLY-IP>/status"
```

Shelly Pro 3EM:

```bash
curl -v "http://<SHELLY-IP>/rpc/EM.GetStatus?id=0"
```

Prüfen:

- lokale IP,
- Gerätefirmware,
- Authentifizierung,
- HTTP-Zugriff im lokalen Netz,
- Antwortzeit und Timeout,
- korrekter Gerätetyp in `config.json`.

## Netzbezug und Einspeisung sind vertauscht

SolarInspector erwartet:

- positiv = Netzbezug
- negativ = Einspeisung

Test:

1. PV-Erzeugung möglichst klein oder ausgeschaltet.
2. Einen bekannten Verbraucher einschalten.
3. Netzleistung beobachten.
4. Danach bei deutlicher PV-Einspeisung erneut prüfen.

Bei umgekehrtem Verhalten:

```json
"direction_factor": -1
```

Nicht gleichzeitig die Verdrahtung und den Softwarefaktor ändern, sonst ist die Ursache später nicht mehr nachvollziehbar.

## Hausverbrauch ist unplausibel

Prüfen:

- Wird AC- oder PV-Leistung verglichen?
- Haben alle Werte denselben Zeitpunkt?
- Ist die Netzleistung korrekt vorzeichenbehaftet?
- Sind alle drei Phasen enthalten?
- Ist ein Batteriespeicher beteiligt?
- Kommt die Netzleistung vom Solakon-Meter oder vom Shelly-Hauszähler?
- Sind fehlende Werte durch `0` ersetzt worden?

Eine typische Fehlerquelle ist der Vergleich von Solakon-PV-Eingangsleistung mit Shelly-AC-Ausgangsleistung.

## Messwerte bleiben stehen

```bash
date
timedatectl status
journalctl -u solarinspector.service \
  --since "15 minutes ago" --no-pager
```

Prüfen:

- Datenerfassung aktiv,
- Geräte erreichbar,
- Systemzeit korrekt,
- Datenbank beschreibbar,
- Speicherplatz verfügbar,
- Abfrageintervall nicht ungewöhnlich groß,
- keine dauerhaften Timeouts.

## Update bleibt hängen oder schlägt fehl

```bash
python3 -m json.tool \
  /var/lib/solarinspector/update-status.json

journalctl -u solarinspector-updater.service \
  -n 250 --no-pager

readlink -f /opt/solarinspector/current
```

Häufige Ursachen:

- Release-Asset fehlt oder passt nicht zum Manifest.
- Prüfsumme stimmt nicht.
- Download ist unvollständig.
- virtuelle Umgebung kann nicht erstellt werden.
- rekursive Symlinks wurden in ein Release übernommen.
- Service startet mit der neuen Version nicht.
- Healthcheck-Port ist falsch oder bereits belegt.
- persistente Konfiguration oder Datenbank zeigt auf einen falschen Pfad.
- Verzeichnisrechte verhindern Backup oder Aktivierung.

Nach einem fehlgeschlagenen Update zuerst prüfen, ob das vorherige Release aktiv ist und der normale Service läuft. Nicht wiederholt Updates starten, bevor die Ursache verstanden ist.

## Healthcheck meldet `Connection refused`

```bash
sudo systemctl status solarinspector.service
sudo ss -ltnp | grep 8787
journalctl -u solarinspector.service -n 150 --no-pager
```

Das bedeutet üblicherweise, dass zum Prüfzeitpunkt kein Prozess auf dem konfigurierten Port lauscht. Ursachen können Startfehler, falscher Port, falsche Service-Datei oder eine nicht vorbereitete Python-Umgebung sein.

## Datenbankfehler

Integrität prüfen:

```bash
sqlite3 /var/lib/solarinspector/data/solarinspector.db \
  "PRAGMA integrity_check;"
```

Bei einem Fehler:

1. Service stoppen.
2. Datenbank unverändert sichern.
3. letztes bekannt gutes Backup identifizieren.
4. keine Reparaturbefehle auf dem einzigen Exemplar ausführen.
5. Wiederherstellung in einer Kopie testen.

## Diagnose für ein GitHub-Issue vorbereiten

Aufnehmen:

```bash
uname -a
cat /etc/os-release
python3 --version
cat /opt/solarinspector/current/VERSION
sudo systemctl status solarinspector.service --no-pager
journalctl -u solarinspector.service -n 100 --no-pager
```

Vor Veröffentlichung entfernen:

- Kennwörter,
- Tokens,
- Seriennummern,
- private oder öffentliche IP-Adressen, soweit unnötig,
- Standortnamen,
- personenbezogene Daten.
