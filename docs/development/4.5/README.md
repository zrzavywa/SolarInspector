# Entwicklungsarchiv für Version 4.5

## Status und Zweck

Dieses Verzeichnis dokumentiert den Entwicklungsverlauf von SolarInspector
4.1.3 zu Zrzavy Energy Monitor 4.5.0. Historische Produktnamen, Branches und
Zwischenstände sind Bestandteil des Nachweises und nicht zwingend aktuelle
Betriebs- oder Entwicklungsanweisungen.

Für aktuelle verbindliche Regeln gelten die
[Entwicklungsstandards](../../development.md) und die Anweisungen im
Repository. Für den Betrieb gilt der [Dokumentationsindex](../../README.md).
Die folgenden Dokumente sind historische Entwicklungsnachweise, sofern sie
nicht ausdrücklich einen aktuellen Stand oder offenen Handlungsbedarf nennen.

## Aktueller Produktstand

Zrzavy Energy Monitor 4.5.0 ist der dokumentierte aktuelle Produktstand.
SolarInspector 4.1.3 bezeichnet den Migrationsausgangspunkt. Aussagen über
Version 5.0 oder spätere Architekturziele sind geplant und beschreiben keinen
Bestandteil von Version 4.5.0.

## Phasen 02 bis 06

Diese Dokumente halten Charakterisierung, Modularisierung und den Aufbau des
normalisierten Messmodells fest:

- Phase 02:
  [Abschlussbericht](phase-02-completion-report.md),
  [Coverage-Bewertung](phase-02-coverage-assessment.md) und
  [Testinventar](phase-02-test-inventory.md)
- Phase 03:
  [Findings](phase-03-findings.md) und
  [Modularisierung](phase-03-modularization.md)
- Phase 04:
  [Abschluss](phase-04-completion.md) und
  [Messwertinventar](phase-04-measurement-inventory.md)
- Phase 05:
  [Abschluss](phase-05-completion.md)
- Phase 06:
  [Netzfluss](phase-06-current-grid-flow.md) und
  [Findings](phase-06-findings.md)

## Phasen 08 bis 10

Die Abschlussberichte beschreiben den erreichten Stand. Findings und
Hardware-Handoffs können weiterhin offenen Prüfbedarf enthalten:

- Phase 08:
  [Abschlussbericht](phase-08-completion-report.md),
  [Findings](phase-08-findings.md),
  [Hardware-Handoff](phase-08-hardware-handoff.md) und
  [Validierungsanalyse](phase-08-validation-analysis.md)
- Phase 09:
  [Analyse](phase-09-analysis.md),
  [Abschluss](phase-09-completion.md),
  [Findings](phase-09-findings.md) und
  [historische Pilotvorgaben](phase-09-pilot.md)
- Phase 10:
  [Abschlussbericht](phase-10-completion-report.md),
  [Datenfluss](phase-10-data-flow.md),
  [Findings](phase-10-findings.md) und
  [Schemainventar](phase-10-schema-inventory.md)

## Rebranding und Migration

Die Lesereihenfolge für den Namenswechsel ist:

1. [Rebranding-Plan](rebranding-zrzavy-energy-monitor.md)
2. [Verbindlicher historischer Arbeitsauftrag](rebranding-work-order.yaml)
3. [Bestandsinventar](rebranding-inventory.md)
4. [Debian-Migrationsnachweis](rebranding-debian-migration-evidence.md)
5. [Abschlussbericht](rebranding-completion-report.md)

Diese Dokumente bewahren Legacy-Namen, Pfade und Variablen absichtlich als
Migrations- oder Kompatibilitätsnachweis. Aktuelle Betriebsanweisungen stehen
in der [Migrationsanleitung](../../migration-from-solarinspector.md).

## Messmodell und Geräteadapter

- [Messmodell](measurement-model.md)
- [Messkonventionen](measurement-conventions.md)
- [Grid-Meter-Mapping](grid-meter-mapping.md)
- [Shelly-Phasenmessungen](shelly-phase-measurements.md)
- [Tasmota-Grid-Meter](tasmota-grid-meter.md)

Diese Dokumente verbinden Bestandsanalyse und implementierten Stand der
4.5-Reihe. Versionsabhängige Aussagen sind im jeweiligen Dokument zu prüfen.

## Validierung

- [Validierungsengine](validation-engine.md)
- [Validierungsregeln](validation-rules.md)
- [Validierungsprofile](validation-profiles.md)
- [Validierungsereignisse](validation-events.md)

Die Dokumente beschreiben die in den Entwicklungsphasen eingeführten
Validierungsbausteine und dienen als technische Nachweise.

## Persistenz

- [Datenbankschema](database-schema.md)
- [Datenbankmigration](database-migration.md)
- [Zeitreihenpersistenz](time-series.md)

Diese Unterlagen dokumentieren Schema-, Migrations- und
Zeitreihenentscheidungen der Version 4.5.0. Sie ersetzen keine aktuelle
Betriebs- oder Sicherungsanleitung.

## Historische Nachweise und Lesereihenfolge

Für eine fachliche Entscheidung zuerst den Abschlussbericht der betreffenden
Phase lesen, danach Findings und Inventare. Ein als offen dokumentierter Punkt
ist gegen den aktuellen Code, die Tests und `pyproject.toml` zu prüfen; ältere
Findings sind nicht automatisch noch aktuell. Für Rebranding-Fragen gilt die
oben angegebene Migrationsreihenfolge.
