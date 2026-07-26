# Phase 09: Bestandsanalyse und fachliche Matrix

## Dokumentstatus

| Merkmal | Wert |
| --- | --- |
| Arbeitspaket | WP09-01 – Bestandsanalyse |
| Ausführungsblock | 09.1 – Bestandsanalyse und fachliche Matrix |
| Analysierte Basis | Phase 08 – zentrale Plausibilitätsprüfung |
| Ausgangscommit | `4ae89d9` |
| Arbeitsbranch | `feature/4.5-09-analysis` |
| Produktivcode geändert | Nein |
| Ausgangsprüfung | `634 passed, 1 skipped` |

Dieses Dokument inventarisiert den tatsächlichen Stand vor einer Änderung der
Quellenwahl oder Energiebilanz. Die Vorgaben aus der Phase-09-Arbeitsanweisung
sind Zielbild, aber noch keine Beschreibung des bestehenden Verhaltens.

## 1. Ergebnis und Abgrenzung

Der bestehende Datenfluss validiert normalisierte Snapshots vor der
Quellenwahl. Abgelehnte und veraltete Messwerte werden aus den Snapshots
entfernt und gelangen dadurch nicht in die nachgelagerte Legacy-Berechnung.
Warnungswerte bleiben als `SUSPECT` verfügbar. Die anschließende Quellenwahl
ist jedoch noch auf mehrere Collector-Funktionen verteilt und verliert bei der
Rückkonvertierung in Legacy-Modelle Qualitäts-, Finding- und Zeitinformationen.

Die aktuelle Energiebilanz:

- unterscheidet den offiziellen Netzanschlusspunkt bereits von der
  Anlagen-AC-Messung;
- priorisiert den offiziellen Grid-Meter vor Legacy-Netzquellen;
- bewahrt echte Nullwerte bei der Quellenwahl;
- prüft vor der Kombination nicht ausdrücklich Datenalter und Zeitversatz;
- kann bei fehlender AC-Anlagenleistung DC-PV-Leistung als letzte
  `solar_power_w`-Quelle verwenden;
- klemmt negative Anlagen- und Hausleistungen auf null;
- integriert fehlende aktuelle oder vorherige Leistungen als `0 Wh`;
- speichert keine vollständige, maschinenlesbare Auswahlbegründung.

Block 09.1 ändert dieses Verhalten nicht.

## 2. Aktueller Datenfluss

```text
Adapter
  -> Measurement / DeviceSnapshot
  -> CollectorValidationBridge
  -> validierter DeviceSnapshot
  -> Legacy-Rückkonvertierung
  -> verteilte Quellenwahl im Collector
  -> aktuelle Leistungsableitungen
  -> trapezförmige Energieintegration
  -> samples plus optionale Detailtabellen
  -> Live-API und Dashboard-Aggregation
```

Die zentrale Validierung liegt damit an der richtigen fachlichen Grenze. Für
Phase 09 muss die Legacy-Rückkonvertierung zwischen Validierung und Auswahl
vermieden oder so erweitert werden, dass Rolle, Zeit, Qualität und Findings
erhalten bleiben.

## 3. Messwert-, Qualitäts- und Validierungsmodell

### 3.1 Normalisierter Messwert

`Measurement` enthält:

- Metrik und endlichen numerischen Wert;
- kanonische Einheit;
- stabile `source_id`;
- Messstellenrolle;
- zeitzonenbewusste Werte für `measured_at` und `received_at`;
- `MeasurementQuality`;
- optionalen Rohwert.

Die strukturellen Invarianten unterscheiden einen echten Wert `0.0` von einem
fehlenden Messwert. Ein fehlender Wert wird durch Abwesenheit der betreffenden
Metrik repräsentiert.

### 3.2 Qualitätswerte

Das vorhandene Enum ist für Phase 09 wiederzuverwenden:

| Qualität | Bedeutung für die aktuelle Auswahl |
| --- | --- |
| `MEASURED`, `REPORTED`, `CALCULATED`, `VALIDATED` | nach erfolgreicher Validierung verwendbar |
| `SUSPECT` | verwendbar, aber Findings müssen weitergereicht werden |
| `REJECTED`, `STALE`, `UNAVAILABLE` | nicht für aktuelle Berechnungen verwendbar |
| `FALLBACK` | für eine spätere Auswahlentscheidung reserviert |

Es ist kein zweites Messwert-Qualitätsenum erforderlich. Eine getrennte
Bilanzqualität ist sinnvoll, weil `INCOMPLETE` den Zustand einer Berechnung und
nicht den Zustand eines einzelnen Messwerts beschreibt.

### 3.3 Validierungsentscheidung

Die Engine kennt `ACCEPT`, `ACCEPT_WITH_WARNING` und `REJECT`.

- `ACCEPT_WITH_WARNING` erzeugt `SUSPECT` und behält den Messwert.
- `REJECT` erzeugt `REJECTED`, `STALE` oder `UNAVAILABLE` und keinen nutzbaren
  Messwert.
- Der Collector erhält nach der Validierungsbrücke nur akzeptierte
  Messungen; Warnungen und Ablehnungen bleiben zusätzlich als
  `ValidationEvent` erhalten.
- Bei deaktivierter Validierung ist die Brücke absichtlich ein No-op. Eine
  Phase-09-Anforderung „nur validierte Werte“ muss daher festlegen, ob die
  Energiebilanz bei deaktivierter Validierung ebenfalls deaktiviert oder
  `UNAVAILABLE` sein muss.

### 3.4 Zeitmodell

Alle normalisierten Werte besitzen Mess- und Empfangszeit. Adapter ohne
vertrauenswürdige Gerätezeit setzen `measured_at = received_at`.

Die Phase-08-Altersregel besitzt profilabhängige `fresh_seconds`- und
`stale_seconds`-Grenzen. Die Cross-Source-Regeln können bereits Zeitfenster
prüfen, dienen aber der Validierung und sind kein allgemeiner
Bilanz-Zeitabgleich. Der offizielle Grid-Meter kann zwischen Collector-Zyklen
aus seinem Polling-Cache wiederverwendet werden. Deshalb können Messungen eines
Zyklus unterschiedliche `measured_at`-Werte besitzen.

Eine neue Phase-09-Auswahl darf nicht nur auf den Collector-Zeitpunkt oder den
Zeitstempel des aggregierten Samples vertrauen.

## 4. Metrik- und Quellenmatrix

Die Priorität in der Spalte „Ziel“ folgt der Arbeitsanweisung. „Ist“ beschreibt
ausschließlich den aktuellen Collector.

| Fachwert | Kandidat | Rolle im Modell | Ist-Verhalten | Zielpriorität und Eignung |
| --- | --- | --- | --- | --- |
| `GRID_POWER` | offizieller Hichi/Tasmota- oder SHRDZM-Zähler, konfigurierbare ID, Standard `grid_meter_primary` | `GRID_METER` | höchste Priorität, wenn `GRID_POWER` nach Validierung vorhanden ist | 1; akzeptiert, aktuell, korrekte Einheit und Zeit |
| `GRID_POWER` | Shelly `house_meter` | derzeit im Collector als `GRID_METER` gelesen | erster Legacy-Fallback bei `auto` | 2 nur bei explizit geeigneter Messposition und erlaubtem Fallback |
| `GRID_POWER` | Solakon Meter, `solakon_one` | normalisiert `SOLAR_SYSTEM` mit `GRID_POWER`; Legacy-Vorzeichen wird zurückübersetzt | zweiter Legacy-Fallback bei `auto`, oder explizite Quelle | 3 nur explizit als Legacy-Quelle |
| `PLANT_AC_POWER` | Shelly PM Mini, `solakon_meter` | `PLANT_METER` | erste Auto-Quelle; negative Werte werden auf null geklemmt | 1; Vorzeichen des normalisierten Werts erhalten |
| `PLANT_AC_POWER` | Solakon ONE AC, `solakon_one` | `SOLAR_SYSTEM` | zweite Auto-Quelle; negative Werte werden für die Bilanz auf null geklemmt | 2; akzeptiert und aktuell |
| derzeitiges `solar_power_w` | Solakon ONE DC-PV | `SOLAR_SYSTEM`, `PV_POWER` | dritte Auto-Quelle, wenn beide AC-Werte fehlen | darf künftig nur `PV_POWER` liefern, nicht `PLANT_AC_POWER` |
| `PV_POWER` | Solakon ONE | `SOLAR_SYSTEM` | separat als `solakon_pv_power_w`, zugleich möglicher Legacy-`solar_power_w`-Fallback | 1; keine Schätzung aus AC- oder Netzleistung |
| Batterieleistung | Solakon ONE | `BATTERY_SYSTEM`; getrennte Lade-/Entlademetriken | Legacy-Wert: positiv Laden, negativ Entladen; Collector erzeugt nichtnegative Kanäle | einzige Quelle; intern getrennte nichtnegative Kanäle beibehalten |
| `BATTERY_SOC` | Solakon ONE | `BATTERY_SYSTEM` | direkt übernommen | einzige Quelle |
| `HOUSE_POWER` | berechnet | berechneter Wert | Netz plus bevorzugte AC-Erzeugung, auf null geklemmt; bei fehlendem Grid optional Solakon-Last | künftig nur aus zeitlich vergleichbarem `GRID_POWER + PLANT_AC_POWER` |

### Rollenabweichung

`house_meter.measurement_role` unterscheidet derzeit unter anderem
`house_total`, `grid_total` und `sub_distribution`. Diese Einstellung wird für
Phasenpersistenz und Cross-Source-Vergleich verwendet. Beim Einlesen übergibt
der Collector dem Adapter dennoch immer `MeasurementRole.GRID_METER`.

Damit reicht die normalisierte Rolle allein aktuell nicht aus, um einen Shelly
an einer Unterverteilung als Netz-Fallback auszuschließen. Der Source Selector
muss zusätzlich die konfigurierte Messposition auswerten, oder die
Adapterrolle muss in einem eigenen, getesteten Arbeitspaket korrekt
normalisiert werden. Eine Unterverteilung darf niemals durch die bloße
`source_id` `house_meter` auswählbar werden.

## 5. Bestehende Quellenwahl und Fallbacks

### 5.1 Anlagenleistung

Konfiguration `general.solar_power_source`:

| Einstellung | Auswahl |
| --- | --- |
| `shelly_ac` | Shelly AC, auch wenn der Wert fehlt |
| `solakon_ac` | Solakon AC, auch wenn der Wert fehlt |
| `solakon_pv` | Solakon DC-PV, auch wenn der Wert fehlt |
| `auto` | Shelly AC, danach Solakon AC, danach Solakon DC-PV |

Eine echte Null löst keinen Fallback aus. Auswahlgründe, Kandidatenablehnungen,
Qualität und Alter werden nicht strukturiert ausgegeben.

### 5.2 Netzleistung

Die aktuelle Reihenfolge ist:

1. gültige `GRID_POWER` des aktivierten offiziellen Grid-Meters;
2. konfigurierte Legacy-Auswahl `house_meter` oder `solakon_one`;
3. bei `auto` zuerst Shelly `house_meter`, dann Solakon Meter;
4. keine Quelle.

Ist der offizielle Zähler aktiviert, aber nicht verfügbar, erhält die
menschenlesbare Quellenbezeichnung den Zusatz `Fallback`. Ein offizieller Wert
`0 W` bleibt primär. Direkte Import-/Exportleistung des offiziellen Zählers
wird bevorzugt; andernfalls gelten:

```text
grid_import_w = max(grid_power_w, 0)
feed_in_w = max(-grid_power_w, 0)
```

Der Fallback prüft heute nicht eigenständig Messposition, Datenalter oder
Zeitversatz. Ablehnung und Stale-Erkennung wirken nur indirekt, weil Phase 08
den betreffenden Messwert vor der Auswahl entfernt.

### 5.3 Weitere implizite Fallbacks

- Fehlt eine Anlagen-AC-Messung, kann `solar_power_w` auf DC-PV fallen.
- Fehlt Netzleistung vollständig, kann `house_power_w` auf
  `SolakonOneReading.load_power_w` fallen.
- Fehlt nur Anlagenleistung bei vorhandener Netzleistung, wird
  `house_power_w = max(grid_power_w, 0)` berechnet.
- Fehlende Integrationswerte werden als `0 Wh` gespeichert, nicht als
  „unverfügbar“ markiert.

Diese Fallbacks sind für die neue fachliche Bilanz nicht zulässig, müssen aber
für bestehende öffentliche Felder bis zu einer ausdrücklich dokumentierten
Kompatibilitätsentscheidung charakterisiert bleiben.

## 6. Bestehende Berechnungen

### 6.1 Aktuelle Leistung

```text
balance_generation =
    Shelly PLANT_AC_POWER
    sonst Solakon PLANT_AC_POWER
    sonst ausgewählte solar_power_w (möglicherweise DC-PV)

house_power_w = max(0, grid_power_w + balance_generation)
self_consumption_w = max(0, min(balance_generation, house_power_w))
```

Wenn nur Netzleistung vorhanden ist:

```text
house_power_w = max(0, grid_power_w)
self_consumption_w = unavailable
```

Wenn Netzleistung fehlt:

```text
house_power_w = Solakon SYSTEM_LOAD_POWER oder unavailable
self_consumption_w = unavailable
```

Die neue fachliche Formel ist dagegen:

```text
HOUSE_POWER = PLANT_AC_POWER + GRID_POWER
```

mit positivem Netzbezug, negativer Netzeinspeisung und positiver
Anlagenlieferung. Ein Ergebnis zwischen `-30 W` und `0 W` soll auf null
normalisiert und als Warnung ausgewiesen werden; ein stärker negatives
Ergebnis macht die Bilanz unbrauchbar. Diese Toleranz ist neue Semantik und
darf nicht verdeckt in die Legacy-Felder eingebaut werden.

### 6.2 Eigenverbrauch und Autarkie

Aktuell wird die momentane Eigenverbrauchsleistung wie oben berechnet. Das
Dashboard berechnet periodenbezogen:

```text
self_consumption_pct = self_consumption_wh / solar_wh * 100
autarky_pct = self_consumption_wh / house_wh * 100
```

jeweils nur bei positivem Nenner. Die neue aktuelle Bilanz soll explizit
berechnen:

```text
grid_export_power_w = max(-GRID_POWER, 0)
self_consumed_power_w = max(PLANT_AC_POWER - grid_export_power_w, 0)
self_consumption_rate_percent =
    self_consumed_power_w / PLANT_AC_POWER * 100
autonomy_rate_percent =
    self_consumed_power_w / HOUSE_POWER * 100
```

Die Quoten sind bei einem Nenner von null nicht verfügbar. Das Klemmen auf
`0..100 %` darf nur numerisches Rauschen begrenzen; ein fachlicher Widerspruch
muss als Finding sichtbar bleiben.

### 6.3 Batterie

Das normalisierte Modell verwendet bereits getrennte, nichtnegative
`BATTERY_CHARGE_POWER`- und `BATTERY_DISCHARGE_POWER`-Werte. Der Legacy-Wert
von Solakon ist positiv beim Laden und negativ beim Entladen; der Collector
teilt ihn entsprechend auf. Das in den Konventionen reservierte signed
`BATTERY_POWER` hätte die umgekehrte Richtung (positiv Entladen).

Für Phase 09 ist die kleinste kompatible Entscheidung, intern die bereits
emittierten getrennten Kanäle beizubehalten. Gleichzeitiges signifikantes Laden
und Entladen wird ein Finding; Verluste und Energie aus SOC-Differenzen werden
nicht berechnet.

### 6.4 Energieintegration

Alle zehn aktuellen Leistungskanäle werden trapezförmig integriert:

```text
energy_wh = (current_power_w + previous_power_w) / 2
            * dt_seconds / 3600
```

`dt_seconds` wird auf `0..3 * poll_interval_seconds` begrenzt. Der erste
Messpunkt, ein fehlender aktueller oder vorheriger Wert und nichtpositive Zeit
erzeugen `0 Wh`. Die Integrationszeit ist der Collector-Zeitpunkt, nicht der
Messzeitpunkt der gewählten Quelle.

Phase 09 darf die historische Energieaggregation nicht unbeabsichtigt ändern.
Vor einer Migration ist festzulegen, ob die neue qualitätsbehaftete Bilanz
zusätzlich gespeichert wird oder bestehende `*_wh`-Kanäle ersetzt. Die
kleinste rückwärtskompatible Variante ist eine additive Speicherung; fehlende
Bilanzwerte bleiben dabei `NULL` statt erfundener Null.

## 7. Persistenz, API und Dashboard

### 7.1 Persistenz

Es existiert keine generische normalisierte Sample-Tabelle.

- `samples` speichert kompatible aktuelle Werte, integrierte `*_wh`-Werte,
  menschenlesbare `solar_source`/`grid_source` und Solakon-Rohableitungen.
- `phase_samples` ist eine spezialisierte Detailtabelle.
- `grid_meter_samples` speichert offiziellen Snapshot, Einzelqualitäten,
  Zeitstempel und `active_source_id`.
- `validation_events` speichert deduplizierte Findings, Entscheidungen und
  Qualitäten.

Die geforderten Bilanzwerte, Bilanzqualität und vollständigen
Quellenmetadaten passen nicht ohne additive Spalten oder Tabelle in das
vorhandene Schema. Eine eigene `energy_balance_samples`-Tabelle wäre fachlich
klarer und atomar mit `samples` verknüpfbar, ist aber eine Schemaänderung und
unterliegt dem Pilot-Entscheidungsgate. Eine allgemeine normalisierte
Messwerttabelle nur für Phase 09 einzuführen wäre größer als erforderlich.

### 7.2 API

`/api/live` liefert heute:

- `latest` mit dem vollständigen Legacy-Sample und dessen `age_seconds`;
- Collector-Status;
- optionalen offiziellen Grid-Meter-Detaildatensatz;
- `active_sources.grid_power` und dessen Bezeichnung.

Eine Phase-09-Antwort kann additiv `energy_balance` ergänzen. Bestehende Felder
dürfen nicht entfernt, umbenannt oder in ihrer Null-/Nullwert-Semantik
stillschweigend geändert werden.

### 7.3 Dashboard

Das Dashboard summiert gespeicherte `*_wh`-Werte je Zeitraum und berechnet
periodische KPIs. SQL-`NULL` wird bei der Aggregation aktuell wie `0.0`
behandelt. Quellenangaben stammen vom letzten Sample des Zeitraums.

Die neue aktuelle Bilanzanzeige muss fehlende Werte, echte Nullwerte,
Fallback, Alter und Qualität unterscheiden. Eine Umstellung der historischen
Dashboard-Serien ist nicht Voraussetzung für die erste aktuelle Bilanz und
sollte getrennt von der Kernberechnung erfolgen.

## 8. Zeit-, Qualitäts- und Doppelzählungsrisiken

| Risiko | Aktueller Zustand | Erforderliche Phase-09-Regel |
| --- | --- | --- |
| veralteter Cache-Wert | Validierungsprofil kann ihn entfernen, aber Quelle hat eigenes Pollingintervall | Altersgrenze am Auswahlzeitpunkt erneut und explizit prüfen |
| Zeitversetzte Netz- und AC-Werte | keine Bilanzprüfung | maximalen Skew prüfen; `INCOMPLETE` oder `SUSPECT`, keine stille Kombination |
| Warnungswert | bleibt nutzbar, Finding nur separat | auswählbar gemäß Arbeitsanweisung; Qualität und Findings weiterreichen |
| abgelehnter Wert | aus Snapshot entfernt | als abgelehnter Kandidat mit Grund erklären, nie berechnen |
| echter Nullwert | wird derzeit korrekt ausgewählt | weiterhin als vorhanden behandeln |
| Shelly-Unterverteilung | normalisierte Rolle kann fälschlich `GRID_METER` sein | Messposition zwingend prüfen |
| AC und DC verwechselt | DC-PV kann Legacy-Solarfallback sein | `PV_POWER` nie als `PLANT_AC_POWER` verwenden |
| mehrere Erzeuger | nicht modelliert | Ergebnis als unvollständig/verdächtig kennzeichnen; keine Rückrechnung |
| parallele Netzrichtungen | getrennte Werte möglich | aus signed Grid-Wert ableiten oder Konsistenz prüfen |
| fehlender Wert bei Integration | wird als `0 Wh` gespeichert | neue Bilanz: unverfügbar kennzeichnen, keine Energie erfinden |
| Qualitätsverlust | Legacy-Brücke verliert Auswahlkontext | direkt auf normalisierten validierten Messungen auswählen |

## 9. Deterministische Ziel-Auswahl

Für jede angeforderte Metrik wird die konfigurierte Prioritätsliste in fester
Reihenfolge geprüft. Ein Kandidat ist nur geeignet, wenn:

1. Metrik, Einheit und fachliche Rolle passen;
2. seine `source_id` für die Metrik konfiguriert ist;
3. Validierung `ACCEPT` oder `ACCEPT_WITH_WARNING` ergeben hat;
4. die Qualität nicht `REJECTED`, `STALE` oder `UNAVAILABLE` ist;
5. `measured_at` und `received_at` gültig sind;
6. sein Alter innerhalb der wirksamen Quellen-/Metrikgrenze liegt;
7. eine Messpositionsanforderung, insbesondere beim Grid-Fallback, erfüllt ist.

Die erste geeignete Quelle gewinnt; ein jüngerer Kandidat verdrängt keine noch
aktuelle höher priorisierte Quelle. `0.0` ist ein geeigneter Wert.

Das Ergebnis muss mindestens Metrik, ausgewählten Messwert, Quelle, Rolle,
Qualität, Grund, Fallbackstatus, abgelehnte Kandidaten sowie Mess- und
Auswahlzeit enthalten. Bei `SUSPECT` werden Findings übernommen. Ohne
geeigneten Kandidaten entsteht ein explizites unverfügbares Ergebnis.

Der Zeitversatz zwischen zwei bereits ausgewählten Bilanzwerten ist eine
separate Berechnungsprüfung. Die Auswahlpriorität wird dadurch nicht
rückwirkend und undurchsichtig verändert.

## 10. Testbare Akzeptanzkriterien

### Quellenwahl

1. Ein akzeptierter primärer Wert wird vor jedem Fallback gewählt.
2. Ein primärer Wert `0 W` löst keinen Fallback aus.
3. `REJECTED`, `STALE` und `UNAVAILABLE` werden nie ausgewählt.
4. `SUSPECT` wird bei erlaubter Warnungspolitik ausgewählt und behält Findings.
5. Eine aktuelle höhere Priorität gewinnt gegen eine jüngere niedrigere.
6. Ein veralteter Primärwert führt mit dokumentiertem Grund zum nächsten
   geeigneten Kandidaten.
7. Ein Shelly mit Messposition `sub_distribution` ist kein Grid-Fallback.
8. Ohne geeignete Quelle ist das Ergebnis explizit unverfügbar.

### Aktuelle Bilanz

1. `600 W` Anlagen-AC plus `900 W` Netzbezug ergibt `1500 W` Hausleistung.
2. `600 W` Anlagen-AC plus `-150 W` Netzeinspeisung ergibt `450 W`
   Hausleistung, `150 W` Export und `450 W` Eigenverbrauch.
3. Nullwerte ergeben eine verfügbare Nullbilanz, nicht „fehlend“.
4. Fehlende Netz- oder Anlagen-AC-Leistung ergibt keine erfundene vollständige
   Hausbilanz.
5. Zu großer Zeitversatz erzeugt mindestens `INCOMPLETE` oder `SUSPECT` und
   wird als Finding ausgewiesen.
6. Hausleistung knapp unter null innerhalb der genehmigten Toleranz wird zu
   null normalisiert und gewarnt.
7. Hausleistung stärker unter null verwirft die Bilanz.
8. Eigenverbrauchs- und Autarkiequote sind bei Nenner null nicht verfügbar.
9. Netzimport und -export sind nicht gleichzeitig positiv.
10. DC-PV-Leistung ersetzt niemals fehlende Anlagen-AC-Leistung.
11. Batteriekanäle bleiben nichtnegativ; gleichzeitiges signifikantes Laden
    und Entladen erzeugt ein Finding.

### Integration und Kompatibilität

1. Der Collector läuft bei `INCOMPLETE` oder `UNAVAILABLE` weiter.
2. Bestehende API-Felder und Daten bleiben erhalten.
3. Neue fehlende Bilanzwerte werden als `NULL`, nicht als `0`, dargestellt.
4. Auswahlentscheidung, Qualität, Alter, Fallback und Findings sind in API und
   Persistenz nachvollziehbar.
5. Alte Konfigurationen ohne `energy_balance` starten mit kompatiblen Defaults;
   unbekannte Felder bleiben erhalten.
6. Bestehende Phase-08-Validierung bleibt unverändert.
7. Normal-, Nacht-, Export-, Ausfall-, Stale-, Skew-, Reject- und
   Nullwertszenarien sind automatisiert abgedeckt.

## 11. Auswirkungen und empfohlene Arbeitspaketgrenzen

| Bereich | Auswirkung | Empfehlung |
| --- | --- | --- |
| Modelle | additive Auswahl- und Bilanzmodelle | eigenes Paket ohne Collector-Änderung |
| Konfiguration | additive `energy_balance`-Sektion | Defaults zunächst deaktiviert oder explizit an Validierungszustand koppeln |
| Source Selector | neuer Service auf validierten `Measurement`-Objekten | keine Legacy-Modelle als Eingabe |
| Zeitabgleich | Alter in Auswahl, Skew in Bilanz | keine Interpolation im ersten Schritt |
| Collector | parallele additive Bilanz erzeugen | Legacy-Felder zunächst beibehalten |
| Datenbank | Schemaerweiterung erforderlich | eigenes Migrationspaket nach Review |
| API | additive `energy_balance`-Struktur | bestehendes `/api/live` erhalten |
| Dashboard | additive aktuelle Anzeige | historische Serien nicht im selben Patch migrieren |

Die in der Arbeitsanweisung erwähnte Kurzzeitmittelung ist optional. Für den
kleinsten deterministischen ersten Stand wird `nearest_valid_measurement` ohne
Interpolation oder Mittelung empfohlen.

## 12. Review- und Entscheidungsgates

Vor Block 09.2 beziehungsweise spätestens vor der jeweiligen Produktivänderung
sind folgende Punkte zu bestätigen:

1. **Validierung deaktiviert:** Empfehlung: Die neue Energiebilanz ist
   `UNAVAILABLE`, solange die zentrale Validierung deaktiviert ist. Andernfalls
   wäre „nur validierte Werte“ nicht erfüllt.
2. **Warnungswerte:** Die Arbeitsanweisung entscheidet bereits für
   standardmäßige Verwendung von `SUSPECT` mit weitergereichten Findings.
3. **Shelly-Messposition:** Nur `grid_total`, `grid_fallback` oder eine
   ausdrücklich gleichwertige Position darf Grid-Fallback sein;
   `house_total` und `sub_distribution` nicht automatisch.
4. **Legacy-Solakon-Netzquelle:** Nur bei expliziter Konfiguration als
   Kompatibilitätsfallback, nicht als implizite dritte Standardquelle.
5. **Persistenzmigration:** Empfehlung: additive
   `energy_balance_samples`-Tabelle mit Fremdschlüssel zu `samples`, atomarer
   Speicherung und JSON-Quellenmetadaten. Das ist eine reversible,
   wiederholbare Schemaerweiterung, benötigt nach dem Pilotplan aber
   ausdrückliche Freigabe.
6. **Einführungsmodus:** Empfehlung: neue Bilanz additiv aktivieren, aber bei
   deaktivierter Validierung als nicht verfügbar ausgeben; bestehende
   Legacy-Berechnung und Felder bis zu einem eigenen Kompatibilitätsentscheid
   erhalten.

Es gibt nach der Arbeitsanweisung keine ungeklärte Vorzeichenkonvention für
Netz-, Anlagen-AC- oder getrennte Batterieleistung. Offen sind die
Einführungs- und Persistenzentscheidungen, nicht die Bilanzgleichung.

## 13. Block-09.1-Abnahme

- Messwerte, Rollen, Einheiten, Qualitätszustände und Zeitstempel sind
  inventarisiert.
- Bestehende Quellenprioritäten und implizite Fallbacks sind dokumentiert.
- Bestehende Leistungs-, KPI- und Energieformeln sind dokumentiert.
- Persistenz-, API- und Dashboard-Abhängigkeiten sind erfasst.
- Normal-, Grenz-, Fehl-, Stale-, Skew-, Widerspruchs- und Fallbackfälle sind
  in Akzeptanzkriterien überführt.
- Produktivcode und Phase-08-Verhalten sind unverändert.
- Die Entscheidungsgates für die folgenden Blöcke sind explizit.

## 14. Block-09.2: Modelle und Konfiguration

Nach Freigabe des Analyse-Gates wurden additiv eingeführt:

- `SourceSelectionResult` für ausgewählte und explizit unverfügbare Werte;
- strukturierte Auswahl- und Kandidatenablehnungsgründe;
- strukturierte Findings ohne Abhängigkeit des Messwertmodells von der
  Validierungsimplementierung;
- unveränderliche Metadaten für Quelle, Rolle, Qualität, Fallback sowie Mess-
  und Auswahlzeitpunkt;
- eine normalisierte `energy_balance`-Konfiguration mit Alters-, Skew-,
  Warnungs-, Fallback-, Toleranz- und Persistenzeinstellungen;
- geordnete, duplikatfreie Prioritäten für Grid, Anlagen-AC, PV, SOC und die
  vorhandenen getrennten Batterieleistungskanäle.

Die Standardprioritäten verwenden die im aktuellen Collector tatsächlich
stabilen IDs `house_meter` und `solakon_meter` statt der noch nicht
existierenden Zielnamen `house_meter_main` und `plant_meter_shelly`. Solakon
ist nicht Teil der Standardpriorität für Netzleistung und bleibt nur über eine
explizite benutzerdefinierte Prioritätsliste als Legacy-Netzquelle möglich.
Benutzerdefinierte IDs bleiben möglich. Bestehende Konfigurationen erhalten die
neue Sektion beim Laden additiv; unbekannte Felder werden bewahrt.

`energy_balance.enabled` ist standardmäßig aktiviert, hat in Block 09.2 aber
noch keinen Laufzeitverbraucher und ändert daher weder Quellenwahl noch
Berechnung. Das Gate aus Abschnitt 12 bleibt bindend: Der spätere Service muss
bei deaktivierter zentraler Validierung eine unverfügbare Bilanz liefern.

## 15. Block-09.3: Source Selector

Der herstellerunabhängige `SourceSelector` arbeitet ausschließlich mit
Kandidaten, die eine explizite Phase-08-Validierungsentscheidung tragen. Er:

- prüft konfigurierte Quellen in stabiler Reihenfolge;
- bevorzugt eine geeignete Primärquelle unabhängig davon, ob ein niedriger
  priorisierter Wert jünger oder größer ist;
- behandelt `0.0` als echten Wert;
- schließt abgelehnte und unbrauchbare Qualitäten aus;
- verwendet `SUSPECT` nur bei erlaubter Warnungsrichtlinie und übernimmt die
  strukturierten Findings;
- prüft die zulässige Rolle je Metrik;
- verlangt für jeden Grid-Fallback eine explizite Messposition
  `grid_fallback`, `grid_total` oder `legacy_grid_source`;
- kann Grid- und Anlagenfallback getrennt abschalten;
- erklärt fehlende, abgelehnte, falsch positionierte und nicht konfigurierte
  Kandidaten;
- weist doppelte Kandidaten derselben Quelle und Metrik zurück.

`legacy_grid_source` ist nur eine explizite Eignungskennzeichnung für eine
benutzerdefiniert konfigurierte Legacy-Quelle; sie fügt Solakon nicht wieder
zur Standardpriorität hinzu. Der Collector verwendet den neuen Selector in
Block 09.3 noch nicht. Alters- und Zeitversatzentscheidungen folgen getrennt in
Block 09.4.

## 16. Block-09.4: Zeitabgleich

Der Selector wertet das Alter gegen den expliziten Auswahlzeitpunkt aus.
Zukunftswerte werden nicht verwendet; Werte exakt auf der Altersgrenze bleiben
gültig. Gibt es für eine priorisierte Quelle mehrere validierte Messpunkte,
wird standardmäßig der zeitlich nächste nicht zukünftige Wert gewählt. Eine
aktuelle Primärquelle bleibt gegenüber jeder niedrigeren Priorität bevorzugt.

Die optionale Kurzzeitmittelung:

- ist mit `0 Sekunden` standardmäßig deaktiviert;
- verwendet ausschließlich bereits geeignete Werte derselben Quelle, Metrik
  und Rolle innerhalb des begrenzten Fensters;
- erzeugt ab zwei Werten einen `CALCULATED`-Messwert;
- bleibt `SUSPECT`, sobald ein Eingangswert `SUSPECT` ist;
- interpoliert nicht und führt keinen langfristigen Carry-Forward durch.

`assess_source_alignment()` prüft die Messzeitpunkte bereits ausgewählter
Fachwerte. Fehlende Werte oder ein Skew oberhalb der konfigurierten Grenze
erzeugen `INCOMPLETE`; Werte exakt auf der Grenze sind ausgerichtet. Sind alle
Zeitpunkte ausgerichtet, aber mindestens ein Eingangswert ist `SUSPECT`, ist
auch das Alignment `SUSPECT`. Findings enthalten den tatsächlichen und
zulässigen Skew. Damit kann die spätere Bilanzberechnung eine unsichere
Kombination ablehnen, ohne Quellenwerte zu erfinden oder zu interpolieren.

## 17. Block-09.5: Energiebilanzmodelle und Grundberechnung

`EnergyBalanceInput` verlangt explizite Auswahlentscheidungen für Netz,
Anlagen-AC, PV, Batterieladung, Batterieentladung und SOC. Fehlende Werte sind
dadurch keine impliziten Nullen, sondern `UNAVAILABLE`-Auswahlresultate. Das
Ergebnis enthält alle für die weiteren Blöcke vorgesehenen Leistungs- und
Kennzahlenfelder sowie Qualität, Berechnungszeit, Quellenmetadaten und
strukturierte Findings.

Die Grundberechnung verwendet ausschließlich zeitlich ausgerichtete
`GRID_POWER`- und `PLANT_AC_POWER`-Werte:

```text
HOUSE_POWER = PLANT_AC_POWER + GRID_POWER
GRID_IMPORT_POWER = max(GRID_POWER, 0)
GRID_EXPORT_POWER = max(-GRID_POWER, 0)
RESIDUAL_POWER = HOUSE_POWER - (PLANT_AC_POWER + GRID_POWER)
```

- Fehlen beide AC-Pflichtwerte, ist die Bilanz `UNAVAILABLE`.
- Fehlt genau ein Wert oder ist der Skew zu groß, ist sie `INCOMPLETE`.
  Vorhandene Einzelwerte und Netzrichtungen bleiben diagnostisch sichtbar,
  Hausleistung und Residualwert bleiben jedoch leer.
- Ein ausgerichteter Warnungswert macht die Berechnung `SUSPECT`.
- Eine Hausleistung zwischen der negativen Toleranzgrenze und `0 W`
  einschließlich Grenzwert wird auf `0 W` normalisiert und als `SUSPECT`
  markiert. Der Residualwert macht diese Normalisierung sichtbar.
- Eine Hausleistung unterhalb der Toleranzgrenze verwirft die vollständige
  Bilanz als `UNAVAILABLE`.
- PV-Leistung wird separat weitergereicht und niemals als Anlagen-AC-Fallback
  verwendet.
- Netzimport und Netzeinspeisung können im Ergebnis nicht gleichzeitig positiv
  sein.

Eigenverbrauch, Autarkie und Batterieausgaben bleiben in diesem Block bewusst
leer und folgen in Block 09.6. Collector, Persistenz und öffentliche API sind
noch unverändert.

## 18. Block-09.6: Eigenverbrauch, Autarkie und Batterie

Bei einer vollständigen AC-Bilanz gelten:

```text
SELF_CONSUMED_POWER =
    max(PLANT_AC_POWER - GRID_EXPORT_POWER, 0)

SELF_CONSUMPTION_RATE =
    SELF_CONSUMED_POWER / PLANT_AC_POWER * 100

AUTONOMY_RATE =
    SELF_CONSUMED_POWER / HOUSE_POWER * 100
```

Die Eigenverbrauchsquote bleibt bei `PLANT_AC_POWER <= 0` leer. Der
Autarkiegrad bleibt bei `HOUSE_POWER <= 0` leer. Die berechneten Prozentsätze
werden auf `0…100 %` begrenzt; die vorangehende Bilanzprüfung verhindert, dass
fachliche Widersprüche dadurch verdeckt werden.

Die Batterieausgabe verwendet ausschließlich die ausgewählten getrennten
Kanäle `BATTERY_CHARGE_POWER`, `BATTERY_DISCHARGE_POWER` und `BATTERY_SOC`:

- Lade- und Entladeleistung sind nichtnegative Werte.
- Negative Kanalwerte werden nicht ausgegeben und erzeugen ein Error-Finding.
- SOC außerhalb `0…100 %` wird nicht ausgegeben und erzeugt ein Error-Finding.
- Gleichzeitig positive Lade- und Entladeleistung bleiben diagnostisch
  sichtbar, markieren das Ergebnis aber als `SUSPECT`.
- Batteriewerte können auch bei einer unvollständigen AC-Bilanz als partielle
  Werte sichtbar bleiben.
- Es werden weder Batterieverluste noch Energie aus SOC-Differenzen berechnet.

Warnungsqualitäten der optionalen PV- oder Batteriewerte werden in die
Gesamtqualität übernommen. `INCOMPLETE` und `UNAVAILABLE` der AC-Bilanz bleiben
stärkere Zustände. Collector, Persistenz und öffentliche API sind weiterhin
unverändert.

## 19. Block-09.7: Collector-Integration

Eine schmale Collector-Brücke übernimmt pro Zyklus ausschließlich
`ValidatedMeasurement`-Ergebnisse aus dem `ValidatedCycle`. Sie erzeugt daraus
Kandidaten mit Validierungsentscheidung und Findings, führt die sechs
Quellenauswahlen aus und übergibt das vollständige `EnergyBalanceInput` an den
Bilanzservice.

Die Messposition für den Shelly-Grid-Fallback stammt aus
`house_meter.measurement_role`. Eine Unterverteilung bleibt dadurch
ausgeschlossen. Eine benutzerdefiniert priorisierte Solakon-Netzquelle erhält
die explizite Legacy-Kennzeichnung; sie ist weiterhin nicht Bestandteil der
Standardpriorität.

Laufzeitverhalten:

- Der Collector erzeugt nach der Phase-08-Validierung in jedem Zyklus eine
  neue Bilanz.
- Die letzte Bilanz ist über den unveränderlichen
  `Collector.energy_balance()`-Rückgabewert verfügbar.
- Bei deaktivierter zentraler Validierung ist die Bilanz explizit
  `UNAVAILABLE` mit Finding `validation_disabled`.
- Bei deaktivierter Energiebilanz ist sie explizit `UNAVAILABLE` mit Finding
  `energy_balance_disabled`.
- Eine interne Bilanzausnahme wird abgefangen, ohne Exceptiontext oder
  Zugangsdaten auszugeben. Der Legacy-Sample wird weiter gespeichert und die
  Bilanz erhält `energy_balance_calculation_failed`.
- Der neue Zustand wird erst nach erfolgreicher Sample-Persistenz als letzter
  Collector-Zustand veröffentlicht und beim Reset gelöscht.

Die bestehenden Legacy-Auswahl-, Leistungs- und Energieintegrationsfelder
bleiben in diesem Block unverändert. Die Bilanz wird noch nicht in SQLite
gespeichert und noch nicht über die öffentliche API ausgegeben; dies folgt in
den Blöcken 09.8 und 09.9.

## 20. Block-09.8: Persistenz

Die freigegebene additive Migration erzeugt
`energy_balance_samples` mit einem eindeutigen Fremdschlüssel auf
`samples.id`. Sie verändert weder die 48 Spalten der Legacy-Tabelle noch
bestehende Detailtabellen oder historische Zeilen. `CREATE TABLE/INDEX IF NOT
EXISTS` macht die Migration wiederholbar.

Pro Collector-Sample werden atomar gespeichert:

- Berechnungszeitpunkt und Bilanzqualität;
- alle aktuellen Bilanzwerte einschließlich Residualwert;
- ein aggregierter Fallbackstatus;
- Quellenentscheidungen je Metrik als strukturiertes JSON;
- Findings als strukturiertes JSON.

Echte Nullwerte werden als `0.0`, fehlende Werte als SQL-`NULL` gespeichert.
Schlägt das Bilanz-Insert fehl, werden auch Aggregate- und andere
Detailinserts derselben Transaktion zurückgerollt. `delete_all()` entfernt
Bilanzdetails vor den Aggregatezeilen.

`persist_source_decisions = false` speichert weiterhin fachliche Werte,
Qualität und Findings, setzt aber den Fallbackindikator auf `0` und die
Quellenmetadaten auf ein leeres Objekt. Finding-Details erlauben nur begrenzte
primitive Werte; schlüsselbasierte Credential-, Host-, Adress- und
URL-Informationen werden redigiert. Eine allgemeine normalisierte
Messwerttabelle wurde nicht eingeführt.

`latest_energy_balance_sample()` stellt den neuesten internen Persistenzdatensatz
für die additive API aus Block 09.9 bereit. Die öffentliche API selbst bleibt
in diesem Block unverändert.

## 21. Block-09.9: Live-API und Dashboard

`GET /api/live` enthält additiv das Objekt `energy_balance`. Bestehende Felder
bleiben unverändert. Das neue Objekt liefert Berechnungszeitpunkt, Datenalter,
Qualität, sämtliche Bilanzwerte, den aggregierten Fallbackstatus, strukturierte
Quellenentscheidungen und Findings. Das Datenalter der jeweils ausgewählten
Messung wird pro Quelle ergänzt. Fehlende Werte bleiben `null`, echte
Nullleistungen bleiben `0.0`; fehlende Bilanzdatensätze werden als
`energy_balance: null` ausgegeben. Fehlerhaftes internes Metadaten-JSON wird
nicht an Clients durchgereicht.

Das bestehende Dashboard zeigt die aktuellen Energieflüsse in einem eigenen
herstellerunabhängigen Bereich. Anlagen-AC-Leistung und Netzeinspeisung sind
ausdrücklich getrennt beschriftet. Eigenverbrauchsleistung,
Eigenverbrauchsquote und Autarkiegrad stehen in einem separaten
Kennzahlenbereich. Ein dritter Bereich zeigt aktive Quellen, Fallbackstatus,
Datenalter, Bilanzqualität und die letzte Warnung mit Textstatus. Fehlende
Werte werden als „Nicht verfügbar“ beziehungsweise als Gedankenstrich
dargestellt und nicht als Null interpretiert. Historische Diagramme,
Herstellerdetails und alle bisherigen Dashboard-Funktionen bleiben erhalten.

## 22. Block-09.10: Replaytests und Abschluss

Die zehn verbindlichen Betriebs- und Fehlerfälle werden aus
`tests/fixtures/energy_balance_replay.jsonl` reproduzierbar über die reale
Brücke `ValidatedCycle → SourceSelector → EnergyBalanceService` abgespielt.
Der Katalog prüft zusätzlich Vollständigkeit und deterministisches Einlesen.

Die konsolidierte Abschlussdokumentation mit Quellenprioritäten, Formeln,
Zeitabgleich, Fallbackverhalten, Kompatibilität und bewusst verbleibender
technischer Schuld steht in
[`phase-09-completion.md`](phase-09-completion.md).
