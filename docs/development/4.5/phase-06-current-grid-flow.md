# SolarInspector 4.5 – Phase 06: Aktueller Netzfluss

## Analysierte Basis

- Repository: `zrzavywa/SolarInspector`
- Basisbranch: `main`
- Ausgangscommit: `8a2e0c3cc047ed27b2fc9fe6be705c61e139ae67`
- Ausgangsstand: Merge von Phase 05
- Zielbranch: `feature/4.5-06-grid-meter-tasmota`

## Vorhandenes Messwertmodell

Folgende Netzmetriken sind bereits vorhanden:

- `GRID_POWER`
- `GRID_IMPORT_POWER`
- `GRID_EXPORT_POWER`
- `GRID_IMPORT_TOTAL`
- `GRID_EXPORT_TOTAL`
- `GRID_VOLTAGE`
- `GRID_CURRENT`

Die Messstellenrollen `GRID_METER` und `HOUSE_METER` sind ebenfalls vorhanden.

`Measurement` unterstützt:

- normalisierten Wert und kanonische Einheit,
- stabile `source_id`,
- Messstellenrolle,
- Mess- und Empfangszeitpunkt,
- Messwertqualität,
- optionalen Rohwert für Diagnosezwecke.

`DeviceSnapshot` unterstützt:

- `ONLINE`,
- `DEGRADED`,
- `OFFLINE`,
- `DISABLED`,
- `UNKNOWN`,
- Fehlertext und Metadaten.

## Aktuelle kanonische Einheiten

- Netzleistung: W
- Importleistung: W
- Exportleistung: W
- Importzähler: derzeit Wh
- Exportzähler: derzeit Wh

Der Phase-06-Auftrag fordert kumulierte Zählerstände in kWh. Die notwendige
Umstellung beziehungsweise Kompatibilitätsentscheidung erfolgt zusammen mit
Parser-, Einheiten- und Regressionstests in Block 06.4.

## Aktuelle Netzquellen

Konfigurierbare Auswahl:

1. `auto`
2. `house_meter`
3. `solakon_one`

Automatische Reihenfolge:

1. Shelly `house_meter`
2. Solakon ONE Meter
3. keine Quelle

Ein gültiger Wert von `0 W` löst keinen Fallback aus.

## Aktuelle Rollenverwendung

Der Shelly-`house_meter` wird derzeit über die normalisierte Rolle
`GRID_METER` gelesen.

Zielbild ab Phase 06:

- offizieller Hichi/Tasmota-Zähler: `GRID_METER`
- Shelly 3EM/Pro 3EM: `HOUSE_METER` beziehungsweise gekennzeichneter
  Grid-Fallback

Die Rollenumstellung und Quellenpriorisierung erfolgen erst in Block 06.5.

## Vorzeichen

Interne Konvention:

- positive Netzleistung: Netzbezug
- negative Netzleistung: Netzeinspeisung

Die Solakon-Meterleistung wird dafür im Collector invertiert.

## Reale Hichi/Tasmota-Antwort

Die reale HTTP-Antwort des Hichi/Tasmota-Geräts enthält die Messwerte unter
`StatusSNS.strom`.

Bestätigte Feldzuordnung:

| Bedeutung | Tasmota-Feldpfad | Roh-Einheit |
|---|---|---|
| Aktuelle Netzleistung | `StatusSNS.strom.Pges` | W |
| Netzbezug gesamt | `StatusSNS.strom.VerbrauchT0` | kWh |
| Netzeinspeisung gesamt | `StatusSNS.strom.RetourT0` | kWh |
| Messzeitpunkt | `StatusSNS.Time` | ISO-ähnlicher Zeitstempel |
| Zählerkennung | `StatusSNS.strom.ServerID` | Text, in Fixtures anonymisiert |

Direkte Felder für Import- und Exportleistung werden nicht geliefert. Sie
müssen später aus der vorzeichenbehafteten Gesamtleistung abgeleitet werden.

Ein kontrollierter Lasttest am 24. Juli 2026 bestätigte:

- Grundlast beziehungsweise geringer Netzbezug: `Pges` zwischen `+2 W`
  und `+11 W`
- eingeschalteter Verbraucher: `Pges` zwischen `+1708 W` und `+2114 W`
- nach Abschalten bei PV-Überschuss: `Pges = -298 W`
- der Importzähler erhöhte sich während der Last um ungefähr `0,004 kWh`
- der Exportzähler blieb während des Netzbezugs unverändert

Damit entspricht die reale Tasmota-Konvention bereits der internen
SolarInspector-Konvention:

- `Pges > 0`: Netzbezug
- `Pges < 0`: Netzeinspeisung
- `direction_factor = 1`

Die kumulierten Rohwerte werden vom Gerät bereits in kWh geliefert.

## Bestehende Ableitungen

```text
grid_import_w = max(0, grid_power_w)
feed_in_w = max(0, -grid_power_w)
house_power_w = max(0, grid_power_w + ac_generation_w)
```

Die Berechnungsformel wird in Phase 06 nicht grundsätzlich verändert.

## Persistenz

Die Legacy-Tabelle `samples` enthält unter anderem:

- `grid_power_w`
- `grid_import_w`
- `feed_in_w`
- `grid_import_wh`
- `feed_in_wh`
- `grid_source`

Eine allgemeine normalisierte Messwerttabelle existiert noch nicht.

Die Phase-05-Tabelle `phase_samples` ist speziell für Phasen-Snapshots und
soll nicht als allgemeine Tasmota-Sondertabelle verwendet werden.

## API und Datenalter

Die bestehende Live-API ergänzt den letzten Datensatz um `age_seconds` und
liefert den Collector-Status separat aus. Bestehende Felder dürfen in Phase 06
nicht entfernt oder umbenannt werden.

## Kompatibilitätsgrenzen

Bis Block 06.5 bleiben unverändert:

- bestehende Quellenpriorität,
- bestehende Grid-Source-Auswahl,
- bestehende Energieberechnung,
- bestehende API-Felder,
- bestehende CSV-Felder,
- Shelly- und Solakon-Verhalten.

Bis Block 06.6 bleiben unverändert:

- Datenbankschema,
- Persistenz kumulierter offizieller Zählerstände.

## Geplante Verantwortung der Blöcke

- 06.2: Konfiguration und Migration
- 06.3: HTTP-Transport und Parser
- 06.4: OBIS, Einheiten und Vorzeichen
- 06.5: Collector und Quellenpriorität
- 06.6: Persistenz und API
- 06.7: Konfigurationsoberfläche und Dashboard
- 06.8: Hardwaretest, Dauerprüfung und Abschluss

## Block-06.1-Ergebnis

Block 06.1 führt keine Produktivänderung unter `app/` durch. Er ergänzt nur
Architekturdokumentation, Fixture-Dokumentation und einen lokalen
Diagnosehelfer zur sicheren Erfassung realer Tasmota-Antworten.
