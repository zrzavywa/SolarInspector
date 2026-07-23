# SolarInspector 4.5 – Phase 02: Testbestand und Testlücken

## 1. Ausgangsbasis

- Ausgangsversion: SolarInspector 4.1.3
- Ausgangsbranch: `main`
- Ausgangscommit: `095038d`
- Arbeitsbranch: `feature/4.5-02-characterization-tests`
- Bestehende Tests vor Phase 02: 41
- Ausgangsergebnis: 41 Tests bestanden
- Lokale Umgebung: macOS mit Python 3.14.6
- CI-Versionen: Python 3.11, 3.12 und 3.13

Qualitätsstatus vor Änderungen:

- Pytest: bestanden
- Ruff-Formatierung: bestanden
- Ruff-Lintprüfung: bestanden
- Mypy: bestanden

## 2. Bestehende Testdateien

| Datei | Tests | Klassifizierung | Inhalt |
|---|---:|---|---|
| `tests/test_core.py` | 6 | Gemischt | Konfiguration, Zeitraum, Datenbank, Modbus, Collector und Web |
| `tests/test_github_updater.py` | 1 | Unit-Test | GitHub-Release-Erkennung |
| `tests/test_release_installer.py` | 13 | Unit-/Integrationstest | Installation, Healthcheck und Rollback |
| `tests/test_release_verification.py` | 4 | Unit-Test | Prüfsummen und Release-Verifikation |
| `tests/test_update_api.py` | 5 | Web-/API-Test | Version, Health und Update-Prüfung |
| `tests/test_update_download_api.py` | 3 | Web-/API-Test | Download, Status und Installation |
| `tests/test_updater_service.py` | 3 | Integrationstest | Updateauftrag, persistente Pfade und Backup |
| `tests/test_upgrade_script.py` | 5 | Release-/Pakettest | Raspberry-Pi-Upgradeskript |
| `tests/test_version_consistency.py` | 1 | Metadatentest | VERSION und Release-Manifest |

## 3. Bestehende Testverfahren

Verwendete Hilfsmittel:

- `unittest.TestCase`
- pytest-Funktionstests
- `tempfile.TemporaryDirectory`
- pytest-`tmp_path`
- pytest-`monkeypatch`
- `unittest.mock.Mock`
- `unittest.mock.patch`
- Flask-Testclient
- temporäre SQLite-Datenbanken
- lokaler Modbus-TCP-Testserver

Externe GitHub-HTTP-Aufrufe werden gemockt.

Der bestehende Modbus-Test verwendet einen lokalen TCP-Port auf
`127.0.0.1` und einen Hintergrundthread. Es erfolgt kein Zugriff auf reale
Solarkon- oder Shelly-Geräte.

## 4. Auffälligkeiten

### Gemischte Teststile

Das Projekt verwendet sowohl `unittest.TestCase` als auch pytest-Funktionstests.

### Sammeldatei `test_core.py`

Die Datei enthält Tests für mehrere voneinander unabhängige Systembereiche:

- Konfiguration
- Zeitraumlogik
- Datenbank
- Modbus
- Collector
- Webanwendung

### Globale Abhängigkeiten

Der Webtest ersetzt temporär folgende globale Objekte:

- `solarinspector.config_manager`
- `solarinspector.database`
- `solarinspector.collector`

Dies kann spätere parallele oder stärker isolierte Tests erschweren.

### Interner Collector-Zustand

Der bestehende Collector-Test verändert direkt das private Attribut
`collector._previous_epoch`.

### Fehlende gemeinsame Fixtures

Vor Phase 02 gab es:

- kein `tests/conftest.py`
- keine statischen Geräteantworten
- keine Geräte-Fixtures unter `tests/fixtures/`
- keine Datenbank-Fixture für Version 4.1.3

### Fehlende pytest-Marker

Es sind bislang keine Marker für folgende Kategorien registriert:

- `unit`
- `integration`
- `web`
- `database`
- `hardware`
- `slow`

## 5. Testlücken

### Konfiguration

Vor Phase 02 fehlten Tests für:

- nicht vorhandene Konfigurationsdatei
- ältere Teilkonfigurationen
- Ergänzung fehlender Standardwerte
- Erhalt unbekannter Felder
- ungültiges JSON
- tiefe Kopie durch `get()`
- atomisches Speichern
- Host-Normalisierung
- Boolean-Konvertierung

Diese Lücke wurde mit Commit `93c1fa5` teilweise geschlossen.

### Shelly-Kommunikation

Es fehlen eigenständige Tests für:

- Shelly PM Mini Gen 3
- Shelly 3EM Gen 1
- Shelly Pro 3EM
- normale Antworten
- Nullwerte
- negative Werte
- fehlende Felder
- ungültige Datentypen
- HTTP-Timeouts
- HTTP-Fehler
- ungültiges JSON
- `direction_factor`

### Solarkon-Modbus

Ein erfolgreicher Registertest ist vorhanden.

Es fehlen insbesondere:

- Nullwerte
- Lade- und Entladebetrieb
- unvollständige Register
- ungültige Registerantworten
- Timeout
- Verbindungsabbruch
- Wiederverbindung
- vollständiger Kommunikationsausfall

### Quellenpriorität

Es fehlen Tests für:

- Shelly verfügbar oder nicht verfügbar
- Solarkon verfügbar oder nicht verfügbar
- mehrere Quellen gleichzeitig
- Nullwert als gültiger Messwert
- Exception einer Quelle
- Fallback-Auswahl
- Verhalten bei fehlenden Werten

### Energieberechnungen

Es fehlen feste Tests für:

- Netzbezug
- Netzeinspeisung
- Nachtbetrieb
- Nullverbrauch
- negative Hausleistung
- fehlende Eingangsgrößen
- Energieintegration
- erster Messpunkt
- große oder negative Zeitdifferenzen
- Rundung und Einheiten

### Datenbank

Es fehlen Tests für:

- vollständiges Schema von 4.1.3
- wiederholte Initialisierung
- Schreiben und Lesen von Messwerten
- Nullwerte, negative Werte und `None`
- Tageswerte und Zeitreihen
- CSV-Export
- beschädigte oder gesperrte Datenbank

### Collector

Es fehlen Tests für:

- vollständigen Zyklus
- nur Solarkon
- nur Shelly
- keine verfügbare Quelle
- einzelne Gerätefehler
- kontrollierte Zeit
- Energieintegration
- Start und Stop
- Fortsetzung nach Fehlern

### Web und API

Vorhandene Tests prüfen überwiegend Statuscodes.

Es fehlen insbesondere:

- stabile JSON-Strukturen
- Feldnamen und Feldtypen
- Content-Type
- vollständige und partielle Messdaten
- Verhalten ohne Messdaten
- Fehlerantworten
- Konfigurationsspeicherung
- CSV-Header und CSV-Inhalte

### Fehlerverhalten

Noch nicht systematisch dokumentiert ist, welche Fehler:

- geloggt werden
- als Exception weitergegeben werden
- ignoriert werden
- zu `None` führen
- zu `0` führen
- einen Fallback auslösen
- einen Collector-Zyklus abbrechen

## 6. Priorisierte nächste Testpakete

1. Shelly-Fixtures und Shelly-Charakterisierung
2. Solarkon-Modbus-Fixtures und Fehlerfälle
3. Quellenpriorität
4. bestehende Energieberechnungen
5. SQLite-Schema und Persistenz
6. Collector
7. Web- und API-Strukturen
8. Fehler- und Fallback-Verhalten
9. pytest-Marker
10. Coverage-Auswertung

## 7. Stand nach dem ersten Testpaket

Commit:

`93c1fa5 Add configuration characterization tests`

Ergänzt wurden acht Charakterisierungstests für die bestehende
Konfigurationslogik.

Aktueller Teststand:

- 49 Tests gesammelt
- 49 Tests bestanden
- 0 Tests fehlgeschlagen
- 0 Tests übersprungen

Der Produktivcode wurde nicht verändert.
