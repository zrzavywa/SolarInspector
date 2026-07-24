# Grid-Meter-Mapping für Hichi/Tasmota

## Reales Phase-06-Antwortformat

Der am 24. Juli 2026 erfasste Hichi/Tasmota-Zähler liefert Smart-Meter-Werte
unter `StatusSNS.strom`.

| Fachwert | Bestätigter Feldpfad | Roh-Einheit | SolarInspector |
|---|---|---|---|
| Netto-Netzleistung | `StatusSNS.strom.Pges` | W | `GRID_POWER` in W |
| Bezug gesamt | `StatusSNS.strom.VerbrauchT0` | kWh | `GRID_IMPORT_TOTAL` in Wh |
| Einspeisung gesamt | `StatusSNS.strom.RetourT0` | kWh | `GRID_EXPORT_TOTAL` in Wh |
| Gerätezeit | `StatusSNS.Time` | Text | Diagnosemetadatum |

Die anonymisierte reale Fixture liegt unter:

```text
tests/fixtures/tasmota/grid_meter_status10_sample_01.json
```

## Fachliche OBIS-Zuordnung

Typische OBIS-Bezeichnungen sind:

| OBIS | Bedeutung | Phase-06-Mapping |
|---|---|---|
| `16.7.0` | aktuelle Wirkleistung | möglicher Pfad für `grid_power_w` |
| `1.8.0` | kumulierter Netzbezug | möglicher Pfad für `grid_import_total_kwh` |
| `2.8.0` | kumulierte Einspeisung | möglicher Pfad für `grid_export_total_kwh` |

SolarInspector nimmt nicht an, dass jeder Tasmota-Scriptbereich diese Namen
direkt verwendet. Maßgeblich sind die explizit konfigurierten Punktpfade.

## Punktpfade

Unterstützt wird eine einfache, deterministische Syntax:

```text
StatusSNS.strom.Pges
StatusSNS.SML.16.7.0
SML.1.8.0
```

Der Resolver kann Schlüssel verarbeiten, die selbst Punkte enthalten. Es gibt
kein `eval`, keinen beliebigen JSONPath-Ausdruck und keine automatische Auswahl
des ersten numerischen Feldes.

## Skalierung

Für das bestätigte Gerät gilt:

| Wert | Rohwert | Normalisierung |
|---|---:|---:|
| Leistung | W | Faktor 1 |
| Zählerstand | kWh | Multiplikation mit 1000 zu Wh |
| API/Persistenz | Wh intern | Division durch 1000 zu kWh |

Zählerstände werden niemals aus Momentanleistung zurückgerechnet.

## Vorzeichen und Richtungswerte

Bei `direction_factor = 1`:

```text
Pges = +900 W
GRID_POWER = +900 W
GRID_IMPORT_POWER = 900 W
GRID_EXPORT_POWER = 0 W
```

```text
Pges = -250 W
GRID_POWER = -250 W
GRID_IMPORT_POWER = 0 W
GRID_EXPORT_POWER = 250 W
```

Ein echter Nullwert bleibt erhalten:

```text
Pges = 0 W
GRID_POWER = 0 W
GRID_IMPORT_POWER = 0 W
GRID_EXPORT_POWER = 0 W
```

Bei `direction_factor = -1` wird zuerst `GRID_POWER` invertiert und danach in
Import und Export aufgeteilt.

## Fehlende Werte

- Fehlender Exportzähler verhindert den Importzähler nicht.
- Fehlende Momentanleistung verhindert vorhandene kumulierte Werte nicht.
- Fehlende Werte bleiben abwesend beziehungsweise SQL `NULL`.
- Ein nicht numerischer Wert erzeugt eine Diagnose und Status `DEGRADED`.
- Ein konfigurierter, nicht vorhandener Pfad erzeugt keine erfundene Null.

## Direkte Import- und Exportleistung

Die Felder `grid_import_power_w` und `grid_export_power_w` sind optional. Sind
sie gemappt und nicht negativ, haben sie Vorrang vor der aus `GRID_POWER`
berechneten Aufteilung. Ein direkt gemeldeter Nullwert ist dabei autoritativ.

## Optionale elektrische Werte

Die Konfiguration reserviert weitere Pfade für Frequenz sowie Phasenwerte.
Das bestätigte Phase-06-Gerät liefert diese Werte im verwendeten Status-10-
Bereich nicht. Der produktive Kernadapter emittiert in Phase 06 daher nur die
fünf Grid-Kernmetriken. Eine Erweiterung muss durch reale Fixtures und
gerätespezifische Tests abgesichert werden.
