# Changelog

Alle wesentlichen Änderungen an SolarInspector werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/). Die Versionsnummern folgen nach Möglichkeit [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Added

- Versionierte Phase-10-Schema-Migrationen, normalisierte Messwert- und
  Quellenentscheidungs-Zeitreihen sowie begrenzte, indexgestützte
  Zeitbereichsabfragen ergänzt.
- Standardmäßig deaktivierte, konfigurierbare und transaktional begrenzte
  Zeitreihenaufbewahrung mit sicherem Rollback ergänzt.
- Additive, begrenzte CSV-Exporte für normalisierte Messwerte, Phasen,
  Grid-Meter, Energiebilanz und sichere Diagnoseereignisse ergänzt.
- Eigenständige Datenbank-CLI für read-only Diagnose, private SQLite-Backups,
  unveränderliche Dry Runs und backup-gesicherte Migrationen ergänzt.
- Datenbankschema-Prüfung und Pflicht-Backup-Migration vor Konstruktion von
  Collector und Webanwendung in den Startablauf integriert.
- Offizieller Netzstromzähler als priorisierte Messquelle mit gekennzeichnetem Fallback ergänzt.
- Read-only SHRDZM-REST-Adapter für `/getLastData` mit Query-, Basic- und optionaler Authentifizierung ergänzt.
- Adapterabhängige OBIS-Mappings, Einheitenkonvertierung und End-to-End-Tests ergänzt.
- Erklärbare Quellenauswahlmodelle und additive, rückwärtskompatible Konfiguration für die Phase-09-Energiebilanz ergänzt.
- Deterministische qualitäts-, rollen- und messpositionsbasierte Quellenauswahl mit transparenten Fallbackgründen ergänzt.
- Begrenzte Altersprüfung, zeitnächste Auswahl, optionale Kurzzeitmittelung und Source-Skew-Bewertung ergänzt.
- Validierte aktuelle Leistungsbilanz mit Hausleistung, getrennten Netzrichtungen, Toleranzbehandlung und diagnostischem Residualwert ergänzt.
- Eigenverbrauch, Eigenverbrauchsquote, Autarkiegrad sowie getrennte Batterieflüsse und SOC mit Widerspruchsfindings ergänzt.
- Source Selector und Energiebilanz additiv in jeden Collector-Zyklus integriert; Bilanzfehler stoppen die Messwerterfassung nicht.
- Additive atomare SQLite-Persistenz für Bilanzwerte, Qualität, Findings und optionale Quellenentscheidungen ergänzt.
- Herstellerunabhängige Live-API und Dashboard-Bereiche für aktuelle Energieflüsse, Kennzahlen, Quellen, Datenalter und Bilanzqualität ergänzt.
- Deterministische Replay-Szenarien für Phase-09-Normal-, Ausfall-, Zeit-, Ablehnungs- und Nullwertfälle ergänzt.

### Documentation

- Zentrale GitHub-Dokumentation mit Installations-, Konfigurations-, Betriebs-, Update-, Sicherheits-, Architektur- und API-Referenz ergänzt.
- Aktuellen Betrieb der 4.1-Reihe klar von der geplanten 5.0-Zielarchitektur getrennt.
- Zentrale Markenhinweise und Herstellerabgrenzung für Solakon, Shelly und Raspberry Pi ergänzt.
- Einrichtung, Sicherheit und Hardwarevalidierung des SHRDZM-Netzstromzählers dokumentiert.

### Fixed

- Quellenmessungen aus demselben Collector-Zyklus werden erst nach Abschluss
  der Geräteabfragen zeitlich bewertet und nicht mehr fälschlich als zukünftige
  Messwerte verworfen.

## [4.1.3] - 2026-07-20

### Fixed

- Download-Schaltfläche wird nach einer erfolgreichen Release-Prüfung zuverlässig aktiviert.
- Verarbeitung und Darstellung des OTA-Update-Status wurden korrigiert.
- Zustandslogik der Update-Oberfläche und Aktivierung der Installationsschaltfläche wurden gehärtet.
- Rekursive beziehungsweise zyklische Verknüpfungen virtueller Python-Umgebungen werden bei der Release-Vorbereitung verhindert.
- Persistente Pfade für Konfiguration und Datenbank bleiben bei Side-by-side-Updates erhalten.

### Changed

- Produktversion auf `4.1.3` angehoben.

## [4.1.2] - 2026-07-20

### Added

- Separater privilegierter Updater für Raspberry Pi und systemd.
- Side-by-side-Installation versionierter Releases.
- Persistenter Update-Status und Update-Anforderung.
- Backup von Konfiguration und SQLite-Datenbank vor der Aktivierung.
- Healthcheck mit automatischem Rollback.
- systemd-Path-Unit zum kontrollierten Start des Updaters.

### Security

- Webprozess und privilegierte Installation sind voneinander getrennt.
- Release-Artefakte werden vor der Aktivierung validiert.
- Allgemeine, vom Browser übergebene Shell-Befehle oder Downloadpfade werden nicht unterstützt.

## [4.1.1] - 2026-07-19

### Fixed

- Verbesserungen an Release-Erkennung, Download und Statusdarstellung.
- Robustere Behandlung fehlgeschlagener Update-Vorgänge.

## [4.1.0] - 2026-07-19

### Added

- GitHub-basierte Prüfung auf neue Releases.
- Anzeige von installierter und verfügbarer Version im Webinterface.
- Download und Prüfung veröffentlichter Release-Artefakte.
- API-Endpunkte für Version, Healthcheck und Update-Status.

### Changed

- Vorbereitung der Anwendung auf ein versioniertes Release- und Rollback-Modell.

## [4.0.1] - 2026-07-19

### Added

- Solakon-ONE-Anbindung über read-only Modbus TCP.
- Auswahl der Datenquelle für Solarleistung sowie Netzbezug und Einspeisung.
- Vergleich von Solakon-ONE-AC-Leistung und Shelly-AC-Messung.
- Automatische Erweiterung bestehender Konfigurationen und Datenbanken.
- Raspberry-Pi-Upgrade, Diagnose, Backup und manuelles Rollback.

### Security

- Solakon-Zugriff verwendet ausschließlich lesende Modbus-Aufrufe.
- Laufzeitdaten und lokale Konfiguration werden aus Release-Archiven ausgeschlossen.

## [3.0.0]

### Added

- Browserbasierte Bedienoberfläche mit Dashboard, Datenerfassung, Konfiguration und Datenverwaltung.
- Unterstützung für Shelly PM Mini Gen 3, Shelly 3EM Gen 1 und Shelly Pro 3EM.
- SQLite-Speicherung, CSV-Export und Demodaten.
