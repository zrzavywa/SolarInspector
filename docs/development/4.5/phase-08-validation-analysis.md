# SolarInspector 4.5 – Phase 08: Bestandsanalyse und Regelkatalog

## Dokumentstatus

| Merkmal | Wert |
|---|---|
| Phase | 08 – Zentrale Plausibilitätsprüfung aller Messwerte |
| Ausführungsblock | 08.1 – Bestandsanalyse und Regelkatalog |
| Analysierte Basis | Phase 07 – SHRDZM-Netzstromzähler |
| Ausgangsbranch | `main` |
| Ausgangscommit | `48dad9350f131f16c07112f8f361e84642a12e57` |
| Zielbranch | `feature/4.5-08-validation-engine` |
| Zielversion | 4.5.0 |
| Produktivcode in Block 08.1 geändert | Nein |

Alle Grenzwerte in diesem Dokument sind fachliche Anforderungen oder ausdrücklich
gekennzeichnete Beispielwerte. Sie stellen keine gesetzlichen, normativen oder
eichrechtlichen Grenzwerte dar.

---

## 1. Zusammenfassung

SolarInspector verfügt seit Phase 04 über ein geräteunabhängiges Messwertmodell.
Die Geräteadapter erzeugen `DeviceSnapshot`-Objekte mit normalisierten
`Measurement`-Objekten. Seit Phase 05 werden Shelly-Phasenwerte zusätzlich
gespeichert. Seit Phase 06 und 07 kann ein offizieller Netzstromzähler über
Hichi/Tasmota beziehungsweise SHRDZM REST als primäre Netzreferenz verwendet
werden.

Eine zentrale Plausibilitätsgrenze zwischen normalisiertem Adapterergebnis und
fachlicher Verwendung existiert noch nicht.

Aktueller Datenfluss:

```text
Geräteantwort
    ↓
gerätespezifischer Parser
    ↓
Measurement / DeviceSnapshot
    ↓
temporäre Rückkonvertierung in Legacy-Modelle
    ↓
Quellenwahl
    ↓
Hausverbrauch und Eigenverbrauch
    ↓
Energieintegration
    ↓
SQLite / API / Dashboard
```

Zielbild Phase 08:

```text
Geräteantwort
    ↓
normalisierter Messwertkandidat
    ↓
zentrale Validierungs-Engine
    ↓
ValidatedMeasurement / ValidatedDeviceSnapshot
    ↓
temporäre Legacy-Kompatibilität
    ↓
Quellenwahl und Berechnung
    ↓
Persistenz / API / Dashboard
```

---

## 2. Bestehendes Messwertmodell

### 2.1 `Measurement`

Pfad:

```text
app/solarinspector_core/models/measurement.py
```

Das Modell enthält:

- `metric`
- `value`
- `unit`
- `source_id`
- `role`
- `measured_at`
- `received_at`
- `quality`
- `raw_value`

Bereits vorhandene strukturelle Invarianten:

- `source_id` darf nicht leer sein.
- Boolesche Werte sind keine gültigen Messwerte.
- `value` muss eine reelle Zahl sein.
- `value` muss endlich sein.
- `measured_at` und `received_at` müssen Zeitzonen besitzen.
- Die Einheit muss der kanonischen Einheit der Metrik entsprechen.

### Bewertung

`Measurement` ist bereits ein Modell für strukturell gültige und kanonisch
normalisierte Messwerte. Es ist ungeeignet, um fehlerhafte Eingaben wie
`None`, `NaN`, Listen, leere Strings oder falsche Einheiten zunächst
aufzunehmen und anschließend regelbasiert zu klassifizieren.

### Entscheidung

Das bestehende Modell wird nicht aufgeweicht.

Vor `Measurement` soll eine schlanke validierbare Eingabestufe eingeführt
werden, beispielsweise:

```text
MeasurementCandidate
```

Diese sollte enthalten:

- erwartete Metrik,
- Kandidatenwert,
- deklarierte Einheit,
- Rohwert,
- Quelle,
- Rolle,
- Messzeit,
- Empfangszeit,
- Adapterdiagnosen.

Erst ein akzeptierter Kandidat darf zu einem fachlich nutzbaren
`Measurement` beziehungsweise `ValidatedMeasurement` werden.

---

## 3. Bestehendes Qualitätsmodell

Pfad:

```text
app/solarinspector_core/models/quality.py
```

Vorhandene Zustände:

```text
MEASURED
REPORTED
CALCULATED
VALIDATED
SUSPECT
REJECTED
STALE
FALLBACK
UNAVAILABLE
```

Diese Zustände sind für Phase 08 ausreichend. Eine zweite konkurrierende
Qualitäts-Enumeration wird nicht eingeführt.

### Verbindliche Zuordnung

| Validierungsentscheidung | Abgeleitete Qualität |
|---|---|
| `ACCEPT` ohne Quellenvergleich | ursprüngliche Qualität beibehalten |
| `ACCEPT` nach erfolgreichem Vergleich | `VALIDATED` |
| `ACCEPT_WITH_WARNING` | `SUSPECT` |
| `REJECT` wegen physikalischer oder technischer Verletzung | `REJECTED` |
| `REJECT` wegen fehlendem Wert | `UNAVAILABLE` |
| `REJECT` wegen veraltetem Wert | `STALE` |

`FALLBACK` entsteht nicht durch eine Einzelregel, sondern durch die spätere
Quellenwahl.

---

## 4. Gerätestatus und Messwertqualität

Vorhandene Gerätestatus:

```text
ONLINE
DEGRADED
OFFLINE
DISABLED
UNKNOWN
```

Gerätestatus und Messwertqualität bleiben getrennt.

Beispiele:

```text
Gerät ONLINE, einzelne Metrik REJECTED
Gerät DEGRADED, L1 VALIDATED, L2 REJECTED, L3 VALIDATED
Gerät OFFLINE, keine aktuellen Messwerte
```

Ein ungültiger Einzelwert darf nicht automatisch den vollständigen Snapshot
unbrauchbar machen.

---

## 5. Rollen, Metriken und Einheiten

### Rollen

```text
GRID_METER
HOUSE_METER
PLANT_METER
SOLAR_SYSTEM
BATTERY_SYSTEM
```

### Kanonische Einheiten

| Metrikgruppe | Interne Einheit |
|---|---|
| Leistung | W |
| kumulierte Energie | Wh |
| Spannung | V |
| Strom | A |
| Ladezustand | % |
| Frequenz | Hz |
| Leistungsfaktor | ratio |
| Temperatur | °C |

Die `ExpectedUnitRule` muss gegen die kanonische Einheit aus
`unit_for_metric()` prüfen. API- oder Dashboard-Darstellungen in kWh ändern
nicht die interne Einheit Wh.

---

## 6. Analyse der Adapter

### 6.1 Shelly PM Mini Gen3

Aktuelles Verhalten:

- `apower` wird in `float` umgewandelt.
- Ein fehlendes `apower` erzeugt intern einen Ersatzwert von `0.0`, wird aber
  über `power_available=False` als nicht verfügbar markiert.
- Optionale elektrische Werte werden ebenfalls numerisch konvertiert.
- Rohwerte werden nicht konsistent in `Measurement.raw_value` übernommen.
- numerische Strings werden akzeptiert,
- Boolesche Werte können durch `float(True)` zu `1.0` werden,
- NaN und Infinity können bis zum strengen `Measurement`-Konstruktor gelangen.

Risiko:

Ein fehlerhafter optionaler Wert kann die Snapshot-Erzeugung stärker
beeinträchtigen als nur die betroffene Metrik.

### 6.2 Shelly 3EM Gen1

Aktuelles Verhalten:

- drei Positionsphasen werden geparst,
- der gemeldete Gesamtwert wird bevorzugt,
- fehlt der Gesamtwert, wird aus den Phasen summiert,
- Energiezähler werden summiert,
- Phasenwerte werden zusätzlich normalisiert.

Risiko:

Unvollständige Phasenantworten dürfen nicht wie vollständige
Dreiphasenmessungen behandelt werden. Fehlende Phasen dürfen nicht
stillschweigend als echte Nullwerte in eine fachliche Bewertung eingehen.

### 6.3 Shelly Pro 3EM

Aktuelles Verhalten:

- Phasenwerte, Gerätefehler, Flags und `is_valid` werden ausgewertet,
- einzelne ungültige Phasen werden als `SUSPECT` markiert,
- gültige andere Phasen bleiben erhalten,
- die Phasensumme wird gegen den Gerätesummenwert verglichen.

Offen:

Die Toleranz der Phasensummenprüfung ist fest im Code hinterlegt.

### 6.4 Solakon ONE

Aktuelles Verhalten:

- Modbus-Register werden technisch gelesen und skaliert,
- vorzeichenbehaftete Register werden als `i16` beziehungsweise `i32`
  interpretiert,
- kumulierte kWh-Werte werden intern in Wh konvertiert,
- Rohwerte werden teilweise gespeichert,
- teilweise lesbare Registerblöcke führen zu einem degradierten Gerät.

Offen:

- keine zentralen Leistungsgrenzen,
- keine SOC-Grenzprüfung,
- keine Fehlerwertprüfung je Register,
- keine Sprungprüfung,
- keine Zählerstandsprüfung,
- keine Aktualitätsprüfung,
- kein zentraler Vergleich gegen den Shelly PM Mini.

### 6.5 Hichi/Tasmota

Aktuelles Verhalten:

- konfigurierbare JSON-Pfade,
- Bool, `None`, nicht numerische und nicht endliche Werte werden im Parser
  abgewiesen,
- numerische Strings werden akzeptiert,
- falsche Werte werden als Adapterdiagnose vermerkt,
- die betroffene Metrik wird nicht erzeugt,
- Gerätezeit wird nur als Metadatum gespeichert,
- `measured_at` entspricht der lokalen Empfangszeit.

Offen:

Ein nicht numerischer Rohwert wird nicht als strukturiertes
Validierungsereignis mit Quelle, Metrik, Rohwert und Regel-ID persistiert.

### 6.6 SHRDZM REST

Aktuelles Verhalten:

- konfigurierbare OBIS-Pfade,
- endliche numerische Werte werden akzeptiert,
- Energieeinheiten werden normalisiert,
- zweifelhafte Energieeinheiten führen zu einer Diagnose,
- negative Richtungsbeträge werden verworfen,
- Gerätezeit wird nur als Metadatum gespeichert,
- `measured_at` entspricht der Empfangszeit.

Offen:

- kein zentraler Wertebereich,
- kein Zählerstandsvergleich,
- kein Alter aus Gerätezeit,
- keine strukturierte Persistenz verworfener Rohwerte,
- keine gerätespezifischen Fehlerwerte.

### 6.7 SHRDZM Modbus TCP

Der Phase-08-Auftrag nennt SHRDZM Modbus TCP als mögliche Adaptervariante.
Im analysierten Phase-07-Stand ist der produktive SHRDZM-Adapter als
REST-Adapter implementiert.

Ein zusätzlicher Modbus-TCP-Adapter ist nicht Bestandteil von Phase 08.
Die Validierungsarchitektur muss jedoch transportneutral bleiben.

---

## 7. Bestehende Phasensummenprüfung

Pfad:

```text
app/solarinspector_core/services/phase_power.py
```

Vorhandene Logik:

```text
Toleranz = Maximum aus 20 W und 5 % des Referenzwertes
```

Die Prüfung erfolgt nur:

- bei genau drei Phasen,
- bei vollständigen Phasenwerten,
- wenn ein echter Gerätesummenwert vorhanden ist,
- wenn Gesamt- und Phasenwerte dieselbe Vorzeichenkonfiguration verwenden.

### Entscheidung

Die mathematische Logik wird nicht dupliziert.

`PhaseSumConsistencyRule` soll dieselbe Berechnungsfunktion verwenden.
Absolute und relative Warn- und Ablehnungstoleranzen werden aus dem
Validierungsprofil übergeben.

---

## 8. Collector-Verarbeitung

Der Collector führt aktuell aus:

1. Geräte lesen.
2. Snapshots in Legacy-Modelle zurückkonvertieren.
3. Solarkon-, Shelly- und Netzquellen auswählen.
4. Netzbezug und Einspeisung ableiten.
5. Hausverbrauch und Eigenverbrauch berechnen.
6. Differenzen zwischen Solakon und Shelly berechnen.
7. Energie per Trapezregel integrieren.
8. Ergebnisse persistieren.

Aktuell können strukturell gültige und endliche Werte grundsätzlich
weiterverarbeitet werden, unabhängig von:

- technischer Messgrenze,
- installierter Anlagenleistung,
- Alter,
- zeitlichem Versatz,
- Sprunghöhe,
- vorherigem Zählerstand,
- Vergleich mit redundanten Quellen,
- Energiebilanz.

Der offizielle Netzstromzähler wird verwendet, sobald ein `GRID_POWER`-Wert
vorhanden ist. Qualität, Alter und Findings werden bei der Quellenwahl noch
nicht bewertet.

### Nullwerte

Ein echter Wert von `0 W` wird in zentralen Pfaden korrekt über
`is not None` von einem fehlenden Wert unterschieden. Dieser Vertrag bleibt
erhalten.

### Problematische Nullbegrenzung

Mehrere Solakon- und Berechnungswerte werden mit `max(0.0, value)` begrenzt.
Diese fachliche Richtungsableitung darf erst nach der Plausibilitätsentscheidung
erfolgen:

```text
Rohwert
→ Validierung
→ gegebenenfalls fachliche Richtungsableitung
→ Berechnung
```

### Energieintegration

Ein abgelehnter Wert darf:

- nicht integriert werden,
- nicht als neuer historischer Referenzwert dienen,
- den letzten akzeptierten Wert nicht überschreiben.

---

## 9. Historischer Zustand

Der Collector besitzt derzeit nur begrenzten Laufzeitzustand. Für Phase 08
wird ein eigener `ValidationStateStore` benötigt.

Mindestens zu speichern:

```text
(source_id, role, metric)
→ letzter akzeptierter Messwert
→ Zeitpunkt
→ Qualität
```

Optional für Quellenvergleiche:

```text
(source_id, metric)
→ begrenztes Zeitfenster akzeptierter Werte
```

Der Store darf nicht als unkontrolliertes globales Dictionary implementiert
werden.

---

## 10. Persistenz

### Tabelle `samples`

Speichert ausgewählte und bereits berechnete Werte, aber keine:

- Validierungsentscheidung,
- Regel-ID,
- Findings,
- akzeptierten gegenüber abgelehnten Rohwerte,
- Qualität je Aggregatfeld.

### Tabelle `phase_samples`

Enthält bereits Phasenqualität, Phasensumme, Differenz, Vollständigkeit und
Metadaten.

### Tabelle `grid_meter_samples`

Enthält bereits Gerätestatus, Gesamtqualität, Qualität je Netzmetrik,
Zeitstempel, normalisierte Werte und Metadaten.

Nicht enthalten:

- Rohwert je Metrik,
- `accepted_value`,
- Entscheidung,
- Regel-Findings,
- Ereignisaggregation.

Die allgemeine Ereignispersistenz folgt erst in Block 08.8.

---

## 11. API und Dashboard

Bereits sichtbar sind:

- Grid-Meter-Quelle und Adapter,
- Gerätestatus,
- Qualität,
- Aktualisierung und Datenalter,
- Phasenqualität,
- Phasensumme und Differenz,
- Solakon-/Shelly-Einzelwertvergleich.

Fehlend sind:

- Validierungsentscheidung,
- strukturierte Findings,
- Regel-ID,
- akzeptierter und abgelehnter Wert,
- aktive Validierungsprobleme,
- Dauer und Häufigkeit eines Problems,
- aktive Fallbackbegründung,
- Datenqualitätsübersicht über alle Quellen.

---

## 12. Umgang mit `None`, `0`, NaN und Exceptions

| Eingabe oder Ereignis | Zielverhalten Phase 08 |
|---|---|
| echter Wert `0` | `ACCEPT`, sofern keine andere Regel verletzt ist |
| `None` | `UNAVAILABLE`; bei Pflichtmetrik Finding erzeugen |
| NaN | metrikspezifisches `REJECT` mit Rohwert |
| positive/negative Infinity | metrikspezifisches `REJECT` |
| boolescher Wert | immer ablehnen |
| numerischer String | Adapter darf kontrolliert normalisieren |
| leerer String | `UNAVAILABLE` oder `REJECT`, abhängig vom Pflichtfeld |
| Parserfehler | nur betroffene Metrik ablehnen |
| Adapterexception | Geräteverfügbarkeit getrennt behandeln |
| Regel-Exception | internes Finding; Collector läuft weiter |

---

## 13. Rohwertbehandlung

Jedes Validierungsergebnis soll nachvollziehbar enthalten können:

```text
raw_value
normalized_candidate_value
accepted_value
decision
quality
findings
```

Nicht gespeichert werden dürfen:

- Passwörter,
- Authentifizierungsparameter,
- vollständige URLs mit Zugangsdaten,
- unnötige vollständige Geräteantworten.

---

## 14. Architekturentscheidungen

### A-08-001: Strenges `Measurement` erhalten

`Measurement` bleibt das Modell eines strukturell korrekten, kanonischen
Messwertes.

### A-08-002: Validierbaren Kandidaten einführen

Format-, Typ- und Einheitenfehler werden vor der Konstruktion eines regulären
`Measurement` ausgewertet.

### A-08-003: Qualitätsmodell wiederverwenden

`MeasurementQuality` bleibt die einzige fachliche Qualitätsklassifikation.

### A-08-004: Entscheidung und Qualität trennen

`ValidationDecision` beschreibt die Verwendbarkeit.
`MeasurementQuality` beschreibt den resultierenden Zustand.

### A-08-005: Engine bleibt zustandslos

Historische Daten werden über `ValidationContext` und `ValidationStateStore`
bereitgestellt.

### A-08-006: Keine Datenbank in Regeln

Regeln erhalten ausschließlich vorbereiteten Kontext.

### A-08-007: Validierung vor Legacy-Kompatibilität

Legacy-Modelle dürfen nur akzeptierte Werte erhalten.

### A-08-008: Kein automatisches Nullsetzen

Ein abgelehnter Wert wird nicht zu `0`.

### A-08-009: Keine automatische Korrektur

Phase 08 skaliert, kalibriert oder repariert keine plausibilitätsverletzenden
Werte.

### A-08-010: Interne Einheit bleibt kanonisch

Leistung bleibt W, kumulierte Energie bleibt Wh.

### A-08-011: Profile und Installationslimits trennen

Gerätetechnische und installationsbezogene Grenzen werden getrennt modelliert.

### A-08-012: Bestehende Phasenlogik wiederverwenden

Die vorhandene Phasensummenberechnung wird parametrisiert oder aufgerufen.

### A-08-013: Rückwärtskompatible Einführung

Eine alte Konfiguration ohne `validation`-Bereich muss weiterhin starten.
Für die Einführung ist vorgesehen:

```text
validation.enabled = false
```

---

## 15. Vorgesehene Regelreihenfolge

```text
1. Quellenidentität und Kandidatenstruktur
2. Wert vorhanden
3. Datentyp und endliche Zahl
4. bekannte Gerätefehlerwerte
5. erwartete Einheit
6. Geräte- und Registerdiagnosen
7. technische und installationsbezogene Wertebereiche
8. Zeitstempel
9. Datenalter
10. Sprung und Änderungsrate
11. Zählerstandsmonotonie
12. Energieänderung pro Zeit
13. Phasenvollständigkeit
14. Phasensummenkonsistenz
15. Richtungs- und Leistungszusammenhang
16. zeitliche Vergleichbarkeit redundanter Quellen
17. Solakon-/Shelly-Vergleich
18. Grid-Meter-/Shelly-Vergleich
19. vorbereitende Energiebilanzprüfung
```

Eine frühere Ablehnung darf spätere Regeln nicht mit einem erfundenen
Ersatzwert weiterrechnen lassen.

---

## 16. Vollständiger Regelkatalog

| Regel-ID | Regel | Betroffene Metriken | Benötigter Kontext | Warnbedingung | Ablehnungsbedingung | Konfigurierbare Werte | Reaktion |
|---|---|---|---|---|---|---|---|
| `VAL-STRUCT-001` | `SourceIdentityRule` | alle | erwartete Quelle, Rolle und Metrik | unerwartete, aber bekannte Rolle | leere oder widersprüchliche Identität | erlaubte Rollen je Quelle | `REJECT`; Integrations-Finding |
| `VAL-STRUCT-002` | `RequiredValueRule` | Pflichtmetriken | Quellprofil | optionale Metrik fehlt | erforderliche Metrik fehlt | Pflichtmetriken je Profil | `UNAVAILABLE`; andere Metriken bleiben |
| `VAL-FMT-001` | `FiniteNumberRule` | alle numerischen Metriken | Kandidaten- und Rohwert | kontrolliert normalisierter String | Bool, leerer String, Objekt, Liste, nicht numerisch, NaN, Infinity | numerische Strings zulassen | `REJECT`; Rohwert erhalten |
| `VAL-FMT-002` | `KnownDeviceErrorValueRule` | profilabhängig | Gerät, Register oder Mapping | – | konfigurierter Sentinelwert | Fehlerwerte je Quelle/Metrik/Register | `REJECT` |
| `VAL-UNIT-001` | `ExpectedUnitRule` | alle | kanonische Einheit | – | Einheit fehlt oder ist falsch | zentrale Metrikzuordnung | `REJECT`; keine Annahme |
| `VAL-DEVICE-001` | `DeviceDiagnosticRule` | betroffene Gerätemetriken | Fehler, `is_valid`, Flags | nicht kritische Warnung | Metrik vom Gerät ungültig markiert | Fehlerklassifikation je Profil | `SUSPECT` oder `REJECTED` |
| `VAL-RANGE-001` | `RangeRule` | konfigurierte Metriken | technische und Installationslimits | außerhalb Warnbereich | außerhalb Ablehnungsbereich | Min/Max, Warn-Min/Max | Warnung oder Ablehnung |
| `VAL-TIME-001` | `TimestampRule` | alle | Messzeit, Empfangszeit, Jetzt | geringe Abweichung | naive/fehlende Zeit, deutlich zukünftig, unzulässige Reihenfolge | Zukunftstoleranz, max. Differenz | Warnung oder Ablehnung |
| `VAL-TIME-002` | `MeasurementAgeRule` | aktuelle Werte | Jetzt, Messzeit, Profil | älter als frisch | älter als stale | Fresh- und Stale-Grenze | `SUSPECT` oder `STALE` |
| `VAL-DELTA-001` | `MaximumDeltaRule` | Leistung, Spannung, Strom, SOC, Frequenz | letzter akzeptierter Wert und Zeitabstand | Warnänderung überschritten | Ablehnungsänderung überschritten | Delta, Delta/s, relativ, Mindestreferenz | Warnung oder Ablehnung |
| `VAL-COUNTER-001` | `MonotonicCounterRule` | kumulierte Energie | letzter Stand, Quelle, Resetinfo | kleiner möglicher Reset | Rücksprung ohne Ausnahme | Überlauf, Resetmarker, Baseline | Ablehnung; Reset-Finding |
| `VAL-COUNTER-002` | `EnergyDeltaRule` | kumulierte Energie | vorheriger Stand, Zeit, Maximalleistung | nahe plausibler Maximalenergie | Zuwachs über Leistung × Zeit × Toleranz | maximale Leistung, Faktor | Warnung oder Ablehnung |
| `VAL-PHASE-001` | `PhaseCompletenessRule` | L1–L3 | aktueller Snapshot | einzelne Phase fehlt/ungültig | keine pauschale Ablehnung anderer Phasen | erforderliche Phasenanzahl | fehlende Phase `UNAVAILABLE` |
| `VAL-PHASE-002` | `PhaseSumConsistencyRule` | Phasen- und Gesamtleistung | drei gültige Phasen plus echter Gesamtwert | über Warntoleranz | über Ablehnungstoleranz | absolute/relative Toleranzen | Gesamtwert warnen/ablehnen |
| `VAL-DIRECTION-001` | `DirectionalPowerConsistencyRule` | Netzleistung und Richtungsbeträge | gleicher Snapshot | kleine Rundungsabweichung | gleichzeitig hoher Import/Export oder Widerspruch | Null- und Differenztoleranz | betroffene Werte warnen/ablehnen |
| `VAL-XTIME-001` | `CrossSourceTimeAlignmentRule` | redundante Leistungen | Zeitfenster beider Quellen | eingeschränkt vergleichbar | Zeitabstand zu groß | maximaler Versatz, Fenster | Vergleich überspringen |
| `VAL-XPLANT-001` | `PlantPowerCrossCheckRule` | Solakon AC und Shelly PM | gültige Fensterwerte | temporäre Abweichung | dauerhafte große Abweichung | absolut/relativ, Dauer, Fenster | warnen; keine automatische Korrektur |
| `VAL-XGRID-001` | `GridMeterCrossCheckRule` | offizielles Grid und Shelly 3EM | vergleichbare Messposition und Zeit | wiederholte Abweichung | dauerhafte sehr große Abweichung sekundär | absolut/relativ, Dauer, Freigabe | offizieller Zähler bleibt Referenz, wenn eigenständig gültig |
| `VAL-BALANCE-001` | `EnergyBalanceRule` | Netz, Anlagen-AC, Hausverbrauch | zeitlich vergleichbare Werte | kleiner negativer Rest | deutlich negative oder widersprüchliche Bilanz | Nulltoleranz, weitere Quellen, Fenster | abgeleitete Bilanz warnen/ablehnen |
| `VAL-ENGINE-001` | `RuleExecutionFailure` | alle | Regel und Exception | – | Regel nicht kontrolliert ausführbar | keine | ERROR-Finding; Collector läuft weiter |

---

## 17. Metrikbezogene Mindestregeln

### Netzleistung

```text
GRID_POWER
GRID_IMPORT_POWER
GRID_EXPORT_POWER
```

Mindestens:

- endliche Zahl,
- Einheit,
- Wertebereich,
- Alter,
- Sprung,
- Richtungskonsistenz,
- optionaler Quellenvergleich.

### Kumulierte Netzenergie

```text
GRID_IMPORT_TOTAL
GRID_EXPORT_TOTAL
```

Mindestens:

- endliche Zahl,
- Einheit Wh,
- nicht negativer Bereich,
- Monotonie,
- Energieänderung gegen Zeit,
- bekannte Fehlerwerte.

### Anlagenleistung

```text
PLANT_AC_POWER
PV_POWER
PV_INPUT_POWER_1..4
```

Mindestens:

- endliche Zahl,
- Einheit,
- Anlagenprofil,
- Alter,
- Sprung,
- optionaler Quellenvergleich.

### Batterie

```text
BATTERY_SOC
BATTERY_CHARGE_POWER
BATTERY_DISCHARGE_POWER
BATTERY_CHARGE_TOTAL
BATTERY_DISCHARGE_TOTAL
```

Mindestens:

- SOC-Bereich,
- nicht negative getrennte Lade-/Entladeleistung,
- keine gleichzeitig hohe Lade- und Entladeleistung,
- Zählerstandsmonotonie,
- Energiedelta.

### Phase

```text
PHASE_POWER_L1..L3
PHASE_VOLTAGE_L1..L3
PHASE_CURRENT_L1..L3
PHASE_POWER_FACTOR_L1..L3
```

Mindestens:

- endliche Zahl,
- Einheit,
- technische und Installationsgrenzen,
- Alter,
- Vollständigkeit,
- Phasensumme,
- Leistungsfaktorbereich.

---

## 18. Entwurf der Standardprofile

Alle Zahlen in diesem Abschnitt sind **Beispielwerte**.

### 18.1 `solarkon_800w`

| Metrik | Warnbereich | Ablehnungsbereich |
|---|---|---|
| `PLANT_AC_POWER` | über 800 W bis 960 W | unter -100 W oder über 960 W |
| `BATTERY_SOC` | optional enger Betriebsbereich | unter 0 % oder über 100 % |
| Leistungsfaktor | optional enger Betriebsbereich | außerhalb -1 bis 1 |

Ein kleiner negativer AC-Wert kann je nach Betriebszustand Standby-Verbrauch
darstellen und darf nicht pauschal auf null gesetzt werden.

### 18.2 `shelly_pm_plant_meter`

| Metrik | Warnbereich | Ablehnungsbereich |
|---|---|---|
| `PLANT_AC_POWER` | über 800 W bis 960 W | unter -100 W oder über 960 W |

Die technische Maximalleistung des Shelly ist nicht der fachliche
Plausibilitätsrahmen der angeschlossenen 800-W-Anlage.

### 18.3 `shelly_3em_house_meter` und `shelly_pro_3em_house_meter`

Keine universelle harte Hausleistungsgrenze.

Optionale Installationsparameter:

```text
nominal_voltage_v
main_fuse_a
phase_count
safety_factor
```

Nur bei vollständiger Konfiguration darf eine installationsbezogene Grenze
abgeleitet werden:

```text
max_phase_power_w =
nominal_voltage_v × main_fuse_a × safety_factor
```

Beim Pro 3EM werden zusätzlich Gerätestatus, Phasenfehler, Flags und
`is_valid` berücksichtigt.

### 18.4 `official_grid_meter`

Keine universelle harte Netzleistungsgrenze.

Immer mögliche Grundregeln:

- endliche Zahl,
- kanonische Einheit,
- Zeitstempel,
- Alter,
- nicht negative Richtungsbeträge,
- nicht negative kumulierte Energie,
- Monotonie.

Harte Leistungsgrenzen nur bei expliziter Installationskonfiguration.

---

## 19. Beispielhafte Zeitprofile

Beispielwerte:

```text
fresh_seconds: 15
stale_seconds: 60
maximum_future_seconds: 5
```

Empfohlene Semantik:

```text
Alter <= fresh_seconds:
    ACCEPT

fresh_seconds < Alter <= stale_seconds:
    ACCEPT_WITH_WARNING

Alter > stale_seconds:
    REJECT mit Qualität STALE
```

Widersprüchliche Zeitgrenzen müssen durch die Konfigurationsvalidierung
abgelehnt werden.

---

## 20. Vergleichstoleranzen

### Phasensumme – Beispiel

```text
warning_absolute_w: 20
warning_relative_percent: 3
reject_absolute_w: 100
reject_relative_percent: 10
```

### Solakon gegen Shelly PM Mini – Beispiel

```text
warning_absolute_w: 30
warning_relative_percent: 10
window_seconds: 30
minimum_duration_seconds: 30
```

### Offizieller Netzstromzähler gegen Shelly 3EM

Nur aktiv, wenn:

```text
measurement_position_comparable = true
```

Mögliche Vergleichsfenster:

```text
10 Sekunden
30 Sekunden
60 Sekunden
```

Ein nicht vergleichbar eingebauter Shelly wird nicht durch diesen Vergleich
abgewertet.

---

## 21. Konfigurationsmodell – Anforderungen für Block 08.2

Vorgesehene additive Form:

```json
{
  "validation": {
    "enabled": false,
    "profiles": {},
    "sources": {}
  }
}
```

Anforderungen:

- alte Konfigurationen laden weiterhin,
- unbekannte zukünftige Felder werden nicht unnötig zerstört,
- Minimum darf Maximum nicht überschreiten,
- Warngrenzen müssen innerhalb der Ablehnungsgrenzen liegen,
- negative Werte können explizit erlaubt werden,
- Zeitgrenzen müssen monoton sein,
- Delta- und Prozentwerte dürfen nicht negativ sein,
- Sentinelwerte werden quell- und metrikspezifisch definiert,
- keine Magic Numbers in Regelimplementierungen.

---

## 22. Ergebnis- und Qualitätsmodell für Block 08.2

Das dreistufige Ergebnis:

```text
ACCEPT
ACCEPT_WITH_WARNING
REJECT
```

reicht für die Verwendungsentscheidung aus.

Empfehlung:

```text
ValidationDecision entscheidet über Verwendbarkeit.
ValidationFinding klassifiziert den Grund.
Eine zentrale Funktion leitet MeasurementQuality ab.
```

Beispiele:

```text
REJECT + value_missing   → UNAVAILABLE
REJECT + stale_value     → STALE
REJECT + range_violation → REJECTED
```

---

## 23. Festgestellte technische Schulden

| ID | Quelle | Thema | Risiko | Zielphase | Priorität |
|---|---|---|---|---|---|
| `VAL-001` | Solakon/Shelly | unterschiedliche Messfenster | falsche kurzfristige Abweichungswarnungen | 08/09 | Hoch |
| `VAL-002` | offizieller Zähler | Polling gegen tatsächliche Aktualisierung | alter Wert erscheint aktuell | 08 | Hoch |
| `VAL-003` | Shelly 3EM | Messposition | unzulässiger Quellenvergleich | 08 | Hoch |
| `VAL-004` | Energiezähler | bestätigter Reset fehlt | legitimer Wechsel wird als Fehler gewertet | 08/09 | Mittel |
| `VAL-005` | Modbus/Adapter | Sentinelwerte nicht registerbezogen | Fehlerwert wird echte Leistung | 08 | Hoch |
| `VAL-006` | Vergleichsfenster | Neustart verliert Ringpuffer | vorübergehend keine Quellenvalidierung | 08 | Niedrig |
| `VAL-007` | Installation | Hausgrenzen nicht konfiguriert | Fehlalarme oder zu lockere Prüfung | Betreiberkonfiguration | Hoch |
| `VAL-008` | Messmodell | ungültige Kandidaten vor `Measurement` | kein persistierbares Finding | 08.2/08.3 | Kritisch |
| `VAL-009` | Shelly | Rohwerte fehlen | eingeschränkte Diagnose | 08.3/08.5 | Mittel |
| `VAL-010` | Collector | qualitätsblinde Quellenwahl | verdächtiger Wert wird verwendet | 08.7 | Kritisch |
| `VAL-011` | Collector | unqualifizierter Integrationszustand | falsche Energieintegration | 08.7 | Kritisch |
| `VAL-012` | Phasenservice | feste 20 W/5 % | nicht installationsgerecht | 08.5 | Mittel |
| `VAL-013` | Tasmota/SHRDZM | Gerätezeit nur Metadatum | Alter nicht zuverlässig prüfbar | 08.3 | Hoch |
| `VAL-014` | Persistenz | kein allgemeines Ereignis | Ablehnung nicht nachvollziehbar | 08.8 | Hoch |
| `VAL-015` | Dokumentation | Version zeigt 4.1.3 | Entwicklungsstand missverständlich | Abschluss 4.5 | Niedrig |

---

## 24. Nicht Bestandteil von Block 08.1

Nicht umgesetzt werden:

- Validierungsmodelle,
- Regeln,
- Engine,
- Collector-Integration,
- Datenbankmigration,
- API-Änderung,
- Dashboard-Änderung,
- Konfigurationsoberfläche,
- neue Adapter,
- Quellenpriorisierung,
- automatische Korrektur,
- automatische Kalibrierung.

---

## 25. Vorbereitung von Block 08.2

Block 08.2 soll als gemeinsamer, commitfähiger Schritt mindestens enthalten:

```text
app/solarinspector_core/validation/__init__.py
app/solarinspector_core/validation/result.py
app/solarinspector_core/validation/base.py
app/solarinspector_core/validation/context.py
app/solarinspector_core/validation/config.py
tests/test_validation_models.py
tests/test_validation_configuration.py
```

Zusätzlich sind kleine, eindeutige Änderungen vorgesehen an:

```text
app/solarinspector_core/config/defaults.py
app/solarinspector_core/config/manager.py
pyproject.toml
```

Block 08.2 darf noch nicht:

- Adapter verändern,
- den Collector umstellen,
- Werte verwerfen,
- Datenbanktabellen hinzufügen,
- bestehende Berechnungen verändern.

### Abnahmepunkte vor Block 08.2

- Baseline vollständig grün.
- Ausgangscommit bestätigt.
- Regel-IDs bestätigt.
- Kandidatenmodell als notwendige Vorstufe bestätigt.
- kanonische Einheit Wh bestätigt.
- Mapping von Entscheidung zu Qualität bestätigt.
- keine Produktivänderung in Block 08.1.

