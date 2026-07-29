# Changelog

Alle wesentlichen Änderungen an Zrzavy Energy Monitor werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/). Die Versionsnummern folgen nach Möglichkeit [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Geändert

- SHRDZM-Adapter verarbeitet bestätigte UTC-Messzeiten, HTTP-200-Fehlerobjekte
  und fehlende Werte ohne erfundene Nullwerte.
- `1.8.0` und `2.8.0` werden nach Hardwarebestätigung bei
  `energy_total_unit=auto` als Wh normalisiert; Betreiberanzeigen in kWh
  ändern die interne Einheit nicht.

## [4.5.3] - 2026-07-29

### Hinzugefügt

- Shelly Plug M Gen3 als optionale, lokale und read-only Anlagen-AC-Quelle
  über `Switch.GetStatus` ergänzt.
- `apower = 0` bleibt ein gültiger Messwert; fehlende oder ungültige Werte
  fallen auf Solakon ONE zurück. Das Relais wird niemals geschaltet.
- Konfiguration, anonymisierte Fixture und Phase-10A-Nachweise ergänzt.

Die reale Hardwarecharakterisierung von Vorzeichen, Rückspeisung und
`ret_aenergy` ist vor der Releasefreigabe noch durchzuführen.

## [4.5.2] - 2026-07-27

### Behoben

- Update-Downloads behandeln Schreib-, API-, Antwort- und Prüffehler als
  konsistente JSON-Fehler und geben keine internen Pfade oder Stacktraces aus.
- Statusdateien werden auch beim ersten Schreibvorgang atomar geschrieben und
  temporäre Dateien nach Fehlern bereinigt.
- Bootstrap und systemd erlauben dem Dienstkonto den Zugriff auf State- und
  Update-Cachepfade, ohne bestehende Nutzdaten rekursiv umzubesitzen.
- Das Frontend prüft HTTP-Status und Content-Type vor dem JSON-Parsing und setzt
  fehlgeschlagene Downloads in einen terminalen Fehlerzustand.

Das direkte Upgrade von 4.5.0 bzw. 4.5.1 ist vorgesehen; bestehende Daten und
Konfigurationen bleiben erhalten. Tag und GitHub-Release werden separat erstellt.

## [4.5.1] - 2026-07-27

### Documentation

- Architekturübersicht für den implementierten 4.5-Stand um Adapterfactory,
  normalisierte Modelle, Validierung, Quellenauswahl, Energiebilanz,
  Zeitreihenpersistenz, Update-/Rollbackgrenzen und direkte Migration ergänzt.
- Lokale standardbibliotheksbasierte Dokumentationsqualitätsverträge für Links,
  Indizes, Versionen, Konfigurationsschlüssel, Architekturpfade und Mermaid-
  Struktur ergänzt.
- Betriebs-, Update-, Persistenz-, Collector-, Web- und Geräte-Schnittstellen
  im priorisierten WP-03-Scope mit englischen PEP-257-/Google-Docstrings
  ergänzt und durch einen AST-Vertragstest abgesichert.
- Die unversionierten HTTP-Schnittstellen von Version 4.5 vollständig nach
  Zielgruppe, Wirkung, Parametern, Antworten, Einheiten und Sicherheitsgrenzen
  dokumentiert und ihre Abdeckung an die registrierten Flask-Routen gebunden.
- Aktive Entwicklungsstandards auf den kanonischen Produktnamen und
  Core-Namespace ausgerichtet sowie Migration und historische
  4.5-Entwicklungsnachweise über zentrale Indizes erschlossen.

### Tests

- Dokumentations-, Docstring-, Versions- und Releasevertragstests für den
  Patch-Release konsistent und versionsdynamisch abgesichert.
- Der vollständige Docstring-Qualitätsvertrag weist 84/84 Module und 425/425
  öffentliche Symbole nach.

4.5.1 enthält keine beabsichtigte Änderung der Laufzeit-, Mess-, Validierungs-,
Persistenz-, Quellenauswahl-, Energiebilanz- oder Datenbankschema-Semantik.
Hardwarevalidierung ist nicht Bestandteil dieses Releasevorbereitungslaufs.

## [4.5.0] - 2026-07-27

### Changed

- Das Projekt wird ab Version 4.5.0 unter dem Namen **Zrzavy Energy Monitor**
  geführt. SolarInspector bleibt ausschließlich als dokumentierter früherer
  Projektname und in zeitlich begrenzter Upgrade-Kompatibilität erhalten.
- Das direkte Upgrade von SolarInspector 4.1.3 auf Zrzavy Energy Monitor 4.5.0
  sichert Installation, Konfiguration, SQLite-Datenbank, Messhistorie und
  Service-Dateien vor der kontrollierten Umschaltung.

### Added

- Kanonische Metadaten für Zrzavy Energy Monitor sowie neue
  `ZRZAVY_ENERGY_MONITOR_*`-Umgebungsvariablen mit priorisierten,
  wertgeschützten Legacy-Fallbacks ergänzt.
- Kanonischen Einstiegspunkt `zrzavy_energy_monitor.py` und Core-Namespace
  `zrzavy_energy_monitor_core` mit schmalen Legacy-Wrappern eingeführt.
- Kanonische Laufzeitpfade und Datei-Basenamen mit expliziter neuer
  Variablenpriorität, Legacy-Erkennung und rücksetzbarer Pfadauswahl ergänzt.
- Direkte, wiederholsichere 4.1.3-zu-4.5.0-Datenmigration mit schreibgeschütztem
  Dry Run, vollständigem Installationsbackup, atomarer SQLite-Kopie,
  Integritätsvergleich und geprüftem Rollback ergänzt.
- Release-Artefakte, Updater, Bootstrap-Installation und konfliktgesicherte
  systemd-Units auf Zrzavy Energy Monitor umgestellt; die Linux-Migration
  prüft den Healthcheck und rollt bei Fehlern auf den alten Dienst zurück.
- Weboberfläche, Laufzeitmeldungen und Exportdateinamen auf den vollständigen
  Produktnamen umgestellt sowie Health- und Versions-API um kanonische
  Produktmetadaten ergänzt.
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
- Vergleichsfenster, Mindestdauer und Mindestanzahl für Quellen mit
  zehnsekündigem Messintervall einschließlich robuster `60/30/4`-Empfehlung
  dokumentiert.

### Fixed

- Die gehärtete systemd-Unit erlaubt atomare Konfigurationsupdates im
  kanonischen Verzeichnis `/etc/zrzavy-energy-monitor`, während das übrige
  System durch `ProtectSystem=strict` schreibgeschützt bleibt.
- Der Debian-Rollback bewahrt fehlgeschlagene Zieldaten als Diagnosekopie,
  entfernt danach deren inaktive kanonische Pfade und ermöglicht eine erneute
  Migration mit einem frischen, unveränderlichen Backup.
- Die systemd-Orchestrierung stoppt vor dem Rollback beide Collector, führt
  Fehler-Rollbacks nur nach abgeschlossenem Daten-Apply aus und erzeugt bei
  privilegierten Läufen keine root-eigenen Bytecode-Caches im Repository.
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
