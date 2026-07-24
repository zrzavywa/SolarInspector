# Phase-06-Findings und technische Schulden

## Reale Beobachtungen

Der kontrollierte Lasttest am 24. Juli 2026 bestätigte:

- `Pges` ist bei Netzbezug positiv.
- `Pges` ist bei Netzeinspeisung negativ.
- Eine zusätzliche Last erhöhte `Pges` auf ungefähr 1,7 bis 2,1 kW.
- Nach Abschalten wurde bei PV-Überschuss ungefähr `-298 W` beobachtet.
- `VerbrauchT0` stieg während der Last nachvollziehbar.
- `RetourT0` blieb während des Netzbezugs unverändert.
- Das bestätigte Mapping verwendet `StatusSNS.strom.*`.
- Direkte Import-/Exportleistungen und Phasenwerte wurden nicht geliefert.

## Technische Schulden

### TM-001 – Direkte Richtungsleistungen fehlen

| Feld | Inhalt |
|---|---|
| Gerät | Hichi/Tasmota, konkretes Zählermodell nicht im Repository gespeichert |
| Bereich | Momentanleistung |
| Aktuelles Verhalten | Import und Export werden aus `Pges` abgeleitet. |
| Risiko | Geräte mit anderer Nettokonvention benötigen korrekten `direction_factor`. |
| Test vorhanden | Ja, Unit- und Collector-Tests |
| Entscheidung Phase 06 | Ableitung ist zulässig; direkte Werte haben Vorrang. |
| Zielphase | Phase 08 oder gerätespezifische Erweiterung |
| Priorität | Mittel |

### TM-002 – Feldnamen hängen vom Tasmota-Script ab

| Feld | Inhalt |
|---|---|
| Gerät | alle Tasmota-Smart-Meter-Scripts |
| Bereich | Mapping |
| Aktuelles Verhalten | Explizite Punktpfade sind konfigurierbar. |
| Risiko | Firmware- oder Scriptwechsel kann Pfade verändern. |
| Test vorhanden | Ja, Mapping- und Diagnose-Tests |
| Entscheidung Phase 06 | Keine heuristische Feldauswahl. |
| Zielphase | Phase 09, optionale Mappingprofile |
| Priorität | Mittel |

### TM-003 – Interne und öffentliche Energieeinheit unterscheiden sich

| Feld | Inhalt |
|---|---|
| Gerät | alle offiziellen Grid-Meter |
| Bereich | Einheiten/Persistenz |
| Aktuelles Verhalten | `Measurement` nutzt Wh; Grid-Detail und API zeigen kWh. |
| Risiko | Entwickler können an der Systemgrenze eine falsche Einheit annehmen. |
| Test vorhanden | Ja, Normalisierungs- und Persistenztests |
| Entscheidung Phase 06 | Kompatibilität zum bestehenden Messwertmodell. |
| Zielphase | Phase 09, generische normalisierte Persistenz prüfen |
| Priorität | Mittel |

### TM-004 – Gerätezeit ist noch nicht autoritativ

| Feld | Inhalt |
|---|---|
| Gerät | bestätigter Hichi/Tasmota |
| Bereich | Zeitstempel |
| Aktuelles Verhalten | `StatusSNS.Time` wird diagnostisch gespeichert; Messzeit ist Empfangszeit. |
| Risiko | Zeitversatz zwischen Gerät und SolarInspector bleibt unerkannt. |
| Test vorhanden | Empfangszeit und Zeitzone werden getestet. |
| Entscheidung Phase 06 | Keine ungeprüfte Übernahme der Gerätezeit. |
| Zielphase | Phase 08 |
| Priorität | Mittel |

### TM-005 – Quellen besitzen unterschiedliche Pollingintervalle

| Feld | Inhalt |
|---|---|
| Gerät | Tasmota, Shelly, Solakon |
| Bereich | Collector |
| Aktuelles Verhalten | Tasmota besitzt ein eigenes Intervall und kann Snapshots wiederverwenden. |
| Risiko | Werte einer Energiebilanz können unterschiedlich alt sein. |
| Test vorhanden | Ja, Polling-Cache-Tests |
| Entscheidung Phase 06 | Bestehende Berechnung bleibt kompatibel. |
| Zielphase | Phase 08/09, Synchronisations- und Stale-Regeln |
| Priorität | Hoch |

### TM-006 – Fallback kann einen anderen Messzeitpunkt besitzen

| Feld | Inhalt |
|---|---|
| Gerät | offizieller Grid-Meter plus Shelly/Solakon |
| Bereich | Quellenfallback |
| Aktuelles Verhalten | Bei fehlender offizieller Kernleistung wird die bestehende Quelle verwendet. |
| Risiko | Umschaltung kann einen zeitlichen Sprung erzeugen. |
| Test vorhanden | Ja, Fallback- und Offline-Tests |
| Entscheidung Phase 06 | Wechsel wird sichtbar mit `Fallback` gekennzeichnet. |
| Zielphase | Phase 09, vollständiger Source Selector |
| Priorität | Hoch |

### TM-007 – Optionale Frequenz- und Phasenwerte nicht produktiv emittiert

| Feld | Inhalt |
|---|---|
| Gerät | bestätigter Hichi/Tasmota |
| Bereich | optionale elektrische Werte |
| Aktuelles Verhalten | Konfiguration reserviert Pfade; Kernadapter emittiert fünf Grid-Metriken. |
| Risiko | Nutzer könnten reservierte Felder mit bereits unterstützten Feldern verwechseln. |
| Test vorhanden | Dokumentations- und Kerntests |
| Entscheidung Phase 06 | Ohne reale Werte keine spekulative Implementierung. |
| Zielphase | gerätespezifische Folgephase |
| Priorität | Niedrig |

### TM-008 – Dauerprüfung noch separat auszuführen

| Feld | Inhalt |
|---|---|
| Gerät | reales Hichi/Tasmota-Gerät |
| Bereich | Betriebsstabilität |
| Aktuelles Verhalten | Hardwaretest und Soak-Skript sind vorbereitet. |
| Risiko | Langzeitverhalten und Netzwerkunterbrechungen sind noch nicht vollständig belegt. |
| Test vorhanden | Optionaler pytest-Hardwaretest; separates Soak-Skript |
| Entscheidung Phase 06 | 2–4 Stunden lokal; 24–72 Stunden späteres Staging. |
| Zielphase | Abschluss Phase 06 beziehungsweise Staging |
| Priorität | Hoch |

## Bewusst nicht umgesetzt

- SHRDZM und physischer M-Bus
- allgemeine MQTT-Infrastruktur
- automatische Zählererkennung
- zentrale Plausibilitäts- und Grenzwert-Engine
- automatische Shelly-Kalibrierung
- vollständige zeitliche Synchronisierung
- generisches Plugin-System
- Cloudzugriff
