# Tasmota Grid-Meter Fixtures

## Zweck

Dieser Ordner enthält bereinigte Antworten eines realen Hichi/Tasmota-
Smartmeters. Die Daten bilden die Grundlage für Parser-, Mapping- und
Regressionstests in Phase 06.

## Erfassung

Die Aufnahme erfolgt mit:

```bash
python tools/capture_tasmota_grid_meter.py \
  --host "$SOLARINSPECTOR_TEST_TASMOTA_HOST" \
  --port "${SOLARINSPECTOR_TEST_TASMOTA_PORT:-80}"
```

Optionale Zugangsdaten werden über Umgebungsvariablen bereitgestellt:

```bash
export SOLARINSPECTOR_TEST_TASMOTA_USERNAME='...'
export SOLARINSPECTOR_TEST_TASMOTA_PASSWORD='...'
```

Das Passwort wird nicht als Befehlszeilenargument unterstützt und erscheint
somit nicht in der Shell-Historie oder Prozessliste.

## Erwartete Dateien nach der Erfassung

```text
grid_meter_status2.json
grid_meter_status10_sample_01.json
grid_meter_status10_sample_02.json
grid_meter_status10_sample_03.json
detected-field-paths.txt
```

Unbereinigte Antworten werden ausschließlich unter `.phase06-capture/`
gespeichert. Dieser Ordner darf nicht committed werden.

## Herkunft

Vor dem Fixture-Commit ausfüllen:

- real oder synthetisch: reale Geräteantwort
- Stromzählermodell: noch separat zu bestätigen
- Hichi-Lesekopf: Hichi/Tasmota, exaktes Modell noch zu bestätigen
- Tasmota-Version: siehe `grid_meter_status2.json`
- Tasmota-Build: siehe `grid_meter_status2.json`
- Smart-Meter-Protokoll: noch separat zu bestätigen
- Smart-Meter-Script geprüft: reale Feldstruktur über `Status 10` bestätigt
- Aktualisierungsintervall: beim Lasttest sekündlich abgefragt

## Bestätigtes Mapping

Erst nach Prüfung der realen Antwort ausfüllen:

| SolarInspector-Wert | Tasmota-Feldpfad | Roh-Einheit | Vorzeichen |
|---|---|---|---|
| Netzleistung | `StatusSNS.strom.Pges` | W | positiv = Bezug, negativ = Einspeisung |
| Netzbezug gesamt | `StatusSNS.strom.VerbrauchT0` | kWh | positiv |
| Netzeinspeisung gesamt | `StatusSNS.strom.RetourT0` | kWh | positiv |

Für die reale Installation gilt `direction_factor = 1`.

## Erwartete SolarInspector-Konvention

- `GRID_POWER > 0`: Netzbezug
- `GRID_POWER < 0`: Netzeinspeisung
- `GRID_IMPORT_POWER >= 0`
- `GRID_EXPORT_POWER >= 0`
- kumulierte Werte werden in Phase 06 intern in kWh normalisiert

## Datenschutzprüfung

Vor jedem Commit prüfen, dass keine der folgenden Informationen enthalten ist:

- Passwörter oder Benutzernamen
- Tokens oder Zugangsschlüssel
- Zähler- oder Seriennummern
- MAC- oder BSSID-Werte
- WLAN- oder MQTT-Namen
- reale private oder öffentliche IP-Adressen
- öffentlich erreichbare URLs

Die automatische Bereinigung ist eine Hilfe, ersetzt aber keine manuelle
Prüfung.

## Parserregeln für spätere Blöcke

- Fehlende Felder sind nicht `0`.
- Ein tatsächlicher Wert `0` bleibt gültig.
- Import- und Exportzähler werden unabhängig voneinander ausgewertet.
- Momentanleistung und Zählerstände dürfen unabhängig voneinander vorhanden
  sein.
- Es wird nicht stillschweigend das erste numerische Feld ausgewählt.
