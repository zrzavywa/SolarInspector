# Phase 09 – Abschlussbericht

## Ergebnis

Phase 09 ergänzt eine zentrale, qualitätsbasierte Quellenwahl und eine
vollständige aktuelle Energiebilanz. Die Implementierung ist additiv:
Legacy-Samples, historische Integrationsformeln, CSV-Export und bestehende
API-Felder bleiben erhalten.

## Quellenprioritäten

| Metrik | Priorität | Fallbackbedingung |
|---|---|---|
| Netzleistung | offizieller Zähler, dann `house_meter` | Hauszähler nur an Position `grid_fallback` |
| Anlagen-AC-Leistung | `solakon_meter`, dann Solakon ONE | Solakon-AC muss validiert und aktuell sein |
| PV-Leistung | Solakon ONE | kein Schätzwert |
| Batterieladung/-entladung/SOC | Solakon ONE | kein Schätzwert |

Die Auswahl berücksichtigt Validierungsentscheidung, Qualität, Rolle,
Messposition, Alter und konfigurierte Reihenfolge. Ein echter Nullwert bleibt
ausgewählt. Jede Auswahl enthält Grund, Quelle, Qualität, Zeitstempel,
Fallbackstatus und verworfene Kandidaten.

## Formeln und Vorzeichen

`GRID_POWER > 0` bedeutet Netzbezug, `< 0` Netzeinspeisung.
`PLANT_AC_POWER > 0` bedeutet AC-Abgabe der Anlage an das Hausnetz.

```text
HOUSE_POWER = PLANT_AC_POWER + GRID_POWER
GRID_IMPORT_POWER = max(GRID_POWER, 0)
GRID_EXPORT_POWER = max(-GRID_POWER, 0)
SELF_CONSUMED_POWER = max(PLANT_AC_POWER - GRID_EXPORT_POWER, 0)
SELF_CONSUMPTION_RATE = SELF_CONSUMED_POWER / PLANT_AC_POWER * 100
AUTONOMY_RATE = SELF_CONSUMED_POWER / HOUSE_POWER * 100
```

Quoten bleiben bei einem Nenner kleiner oder gleich null leer. Anlagen-AC-
Leistung, PV-Eingangsleistung und öffentliche Netzeinspeisung sind getrennte
Größen. Fehlende Werte werden nicht aus anderen Messstellen geschätzt.

## Zeitabgleich und Fallback

Standardmäßig darf ein ausgewählter Messwert höchstens 30 Sekunden alt sein.
Die für Hausleistung verwendeten Netz- und Anlagenwerte dürfen höchstens 10
Sekunden auseinanderliegen. Bei Überschreitung wird keine scheinbar präzise
Hausbilanz erzeugt. Eine optionale Kurzzeitmittelung ist standardmäßig
deaktiviert.

Ein Fallback erfolgt nur zur nächsten konfigurierten und fachlich berechtigten
Quelle. Abgelehnte, veraltete und falsch positionierte Kandidaten bleiben mit
Ablehnungsgrund sichtbar. `SUSPECT` ist separat konfigurierbar. Unvollständige
Eingänge führen zu `INCOMPLETE` oder `UNAVAILABLE`; der Collector läuft weiter.

## Persistenz und API

Die additive Tabelle `energy_balance_samples` speichert Werte, Qualität,
Fallbackstatus, sichere Quellenentscheidungen und Findings atomar zum
Legacy-Sample. Bestehende Tabellen werden nicht umgedeutet.

`GET /api/live` ergänzt `energy_balance`; alle bisherigen Felder bleiben
erhalten. Das Dashboard zeigt Energieflüsse, Kennzahlen sowie Quellen- und
Qualitätsstatus in getrennten Bereichen.

## Verifikation

Die Phase-09-Replays prüfen deterministisch:

- Normal- und Nachtbetrieb;
- Netzeinspeisung;
- Ausfall von Grid Meter, Anlagenmessung und Solakon;
- veraltete, zeitversetzte und abgelehnte Werte;
- echte Nullwerte.

Die vollständige Testsuite, Formatierung, Lint, Typprüfung, Kompilierung und
Whitespace-Prüfung werden über `./scripts/verify.sh` ausgeführt. Die
Abschluss-Coverage des Pakets `solarinspector_core` beträgt 91 Prozent.

## Kompatibilität und technische Schulden

- Historische Energieaggregation verwendet weiterhin das etablierte
  Legacy-Samplemodell; eine nachträgliche Neuberechnung alter Zeiträume aus
  Quellenentscheidungen ist nicht Bestandteil von Phase 09.
- Quellenentscheidungen werden als begrenztes JSON gespeichert. Eine
  normalisierte, frei abfragbare Historientabelle ist bewusst zurückgestellt.
- Die neue Energiebilanz ist aktuell und samplebezogen; eigene historische
  Bilanzendpunkte sind nicht enthalten.
- Geräte- und Installationssemantik kann automatisiert nur mit Fixtures
  geprüft werden. Die reale Messposition, Vorzeichenrichtung und
  Zeitstempelqualität müssen bei der Inbetriebnahme manuell bestätigt werden.
- Die API bleibt innerhalb der 4.x-Reihe additiv, ist aber noch nicht als
  dauerhaft versionierte externe Integrations-API garantiert.

Es wurden keine produktiven Schwellenwerte automatisch verändert, keine neue
Produktionsabhängigkeit eingeführt und keine reale Installation angesprochen.

## Strukturierter Completion Report

```yaml
phase: "09 – Quellenpriorisierung und vollständige Energiebilanz"
status: "completed"
branch: "feature/4.5-09-analysis"
base_commit: "4ae89d9"
final_commit: null
completed_blocks:
  - "09.1"
  - "09.2"
  - "09.3"
  - "09.4"
  - "09.5"
  - "09.6"
  - "09.7"
  - "09.8"
  - "09.9"
  - "09.10"
source_selector:
  implemented: true
  priorities:
    grid_power: ["grid_meter_primary", "house_meter"]
    plant_ac_power: ["solakon_meter", "solakon_one"]
    pv_power: ["solakon_one"]
    battery_power: ["solakon_one"]
time_alignment:
  maximum_age_seconds: 30
  maximum_source_skew_seconds: 10
  method: "Altersgrenze, zeitnächste Auswahl und optionales Kurzzeitmittel"
energy_balance:
  implemented_formulas:
    - "HOUSE_POWER = PLANT_AC_POWER + GRID_POWER"
    - "GRID_IMPORT_POWER = max(GRID_POWER, 0)"
    - "GRID_EXPORT_POWER = max(-GRID_POWER, 0)"
    - "SELF_CONSUMED_POWER = max(PLANT_AC_POWER - GRID_EXPORT_POWER, 0)"
  tolerance_rules:
    - "negative Hausleistung bis 30 W wird auf 0 normalisiert und markiert"
    - "größere negative Hausleistung wird nicht ausgegeben"
  quality_states: ["validated", "calculated", "suspect", "incomplete", "unavailable"]
fallback_behavior:
  grid_power: "nur expliziter grid_fallback oder konfigurierte Legacy-Quelle"
  plant_ac_power: "Solakon-AC nach nicht nutzbarem Anlagenzähler"
persistence:
  schema_changes: ["additive Tabelle energy_balance_samples"]
  migration_result: "idempotent und rückwärtskompatibel getestet"
api_changes: ["additives energy_balance-Objekt in GET /api/live"]
dashboard_changes:
  - "getrennte Energieflüsse und Kennzahlen"
  - "Quellen-, Fallback-, Alters- und Qualitätsanzeige"
tests:
  count_before: null
  count_after: 713
  result: "712 passed, 1 hardware skipped"
coverage:
  total_percent: 91
  critical_modules:
    energy_balance: 96
    energy_balance_collector: 95
    source_selector: 90
ruff:
  result: "passed"
mypy:
  result: "passed"
manual_test:
  result: "keine reale Installation oder Hardware im freigegebenen Umfang"
replay_tests:
  scenarios:
    - "normal_day"
    - "night_operation"
    - "grid_export"
    - "grid_meter_failure"
    - "plant_meter_failure"
    - "solakon_failure"
    - "stale_measurements"
    - "source_time_skew"
    - "rejected_measurements"
    - "zero_power"
  result: "passed"
performance:
  collector_cycle_before_ms: null
  collector_cycle_after_ms: null
  notes: "Kein belastbarer Vorher-Benchmark im freigegebenen Worktree vorhanden."
existing_behavior_changes:
  changed: false
  explanation: "Legacy-Felder und historische Semantik bleiben erhalten; neue Ausgaben sind additiv."
technical_debt:
  - "unterschiedliche Geräteintervalle"
  - "flüchtige Kurzzeitfenster"
  - "noch kein Mehranlagenmodell"
  - "keine belegbare Batterieverlustrechnung"
  - "keine rückwirkende Neuberechnung"
intentionally_not_implemented:
  - "automatische Kalibrierung"
  - "produktiver Hardwarezugriff"
  - "historische Bilanz-API"
impact_on_next_phase:
  - "validierte Quellenentscheidungen und aktuelle Bilanz stehen als Basis bereit"
recommended_next_step: "Review des Abschluss-Diffs; Commit und Draft-PR nur nach ausdrücklichem Auftrag."
```
