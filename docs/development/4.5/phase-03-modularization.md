# SolarInspector 4.5 – Phase 03: Modularisierungsplan

## 1. Zweck

Phase 03 strukturiert die bestehende SolarInspector-Codebasis neu,
ohne das fachliche Verhalten zu verändern.

Grundsatz:

```text
Struktur ändern, Verhalten beibehalten.
```

Neue Geräte, Messwerte, Plausibilitätsregeln, Energieformeln,
Datenbankschemata und Dashboard-Funktionen sind nicht Bestandteil
dieser Phase.

## 2. Ausgangsbasis

| Merkmal | Wert |
|---|---|
| Ausgangsversion | SolarInspector 4.1.3 |
| Ausgangscommit | `66c7a7e` |
| Arbeitsbranch | `feature/4.5-03-modularization` |
| Tests | 222 |
| Teststatus | 222 bestanden |
| Ruff-Formatierung | bestanden |
| Ruff-Lintprüfung | bestanden |
| Mypy | bestanden |

## 3. Analyse der bestehenden Hauptdatei

### 3.1 Imports

Die Hauptdatei importiert gleichzeitig:

- Standardbibliotheken für CLI, Dateien, CSV, JSON und Zeit
- SQLite
- Threading und Prozessbereinigung
- HTTP und Authentifizierung
- Flask
- Waitress
- Solarkon-Modbus
- GitHub-Updatefunktionen
- Update-Statusfunktionen

Dadurch besitzt die Datei Abhängigkeiten zu nahezu allen Schichten
der Anwendung.

### 3.2 Pfade und Konstanten

Enthalten sind unter anderem:

- `BASE_DIR`
- `CONFIG_PATH`
- `DATA_DIR`
- `DB_PATH`
- `LOG_PATH`
- `PID_PATH`
- `UPDATE_STATUS_PATH`
- `UPDATE_CACHE_DIR`
- `UPDATE_REQUEST_PATH`
- `DEFAULT_CONFIG`
- `DEVICE_TYPES`
- `APP_VERSION`

Vorgeschlagenes Ziel:

- reine Pfade und Dateinamen: `solarinspector_core/paths.py`
- Konfigurationsdefaults: `solarinspector_core/config/defaults.py`
- UI-Anzeigenamen zunächst gemeinsam mit der bestehenden Weblogik

Risiko:

Mittel, da Tests und Updatepfade einige Konstanten direkt ersetzen.

### 3.3 Versions- und Updateanforderungslogik

Verantwortlichkeiten:

- installierte Version lesen
- Updateanforderung atomisch schreiben
- Updatepfade aus Umgebungsvariablen ableiten

Abhängigkeiten:

- `Path`
- `json`
- `os.environ`

Globale Zustände:

- `APP_VERSION`
- Updatepfade

Vorgeschlagenes Ziel:

- Pfade zunächst in `paths.py`
- Updateablauf erst gemeinsam mit der Webauslagerung trennen

Risiko:

Mittel, da Release-, Upgrade- und API-Tests davon abhängen.

### 3.4 Logging

Verantwortlichkeiten:

- Zeitstempel erzeugen
- Ausgabe auf stdout
- Schreiben in die bestehende Logdatei

Abhängigkeiten:

- `DATA_DIR`
- `LOG_PATH`
- lokale Zeitzone

Seiteneffekte:

- Verzeichnis wird angelegt
- Datei wird beschrieben

Vorgeschlagenes Ziel:

- zunächst unverändert lassen
- später `solarinspector_core/logging.py`

Risiko:

Niedrig, sofern Ausgabeformat und Pfade unverändert bleiben.

### 3.5 Konfiguration

Verantwortlichkeiten:

- Standardkonfiguration
- rekursive Zusammenführung
- Laden
- Erzeugen einer fehlenden Datei
- Validieren und Normalisieren
- atomisches Speichern
- thread-sicherer Zugriff
- Erhalt unbekannter Felder

Genutzte Konfigurationsbereiche:

- `general`
- `solakon_one`
- `house_meter`
- `solakon_meter`

Abhängigkeiten:

- `json`
- `threading`
- `Path`
- Logging
- `DEVICE_TYPES`

Bestehende Tests:

- `tests/test_config_characterization.py`
- Konfigurationstests in `tests/test_core.py`

Vorgeschlagene Zielmodule:

- `config/defaults.py`
- `config/manager.py`
- `config/migration.py` nur bei tatsächlich vorhandener
  separierbarer Migrationslogik

Risiko:

Mittel.

Kompatibilität:

`DEFAULT_CONFIG`, `deep_merge` und `ConfigManager` werden zunächst
aus `solarinspector.py` re-exportiert.

### 3.6 Legacy-Messwertmodell

Verantwortlichkeit:

- `MeterReading` für normalisierte Shelly-Messwerte

Abhängigkeiten:

- nur Standarddatentypen

Vorgeschlagenes Ziel:

- `models/legacy.py`

Nicht Bestandteil:

- neues Messwertmodell für SolarInspector 4.5

Risiko:

Niedrig.

### 3.7 Shelly-Kommunikation

Verantwortlichkeiten:

- HTTP-Session
- Digest-Authentifizierung
- PM Mini Gen3
- 3EM Gen1
- Pro 3EM
- Simulation
- Antwortnormalisierung
- bestehende Vorzeichenbehandlung

Abhängigkeiten:

- `requests`
- `HTTPDigestAuth`
- `MeterReading`
- Zeit-, Mathematik- und Zufallsfunktionen

Bestehende Tests:

- `tests/test_shelly_characterization.py`
- kombinierte Tests in `tests/test_core.py`

Vorgeschlagenes Ziel:

- `adapters/shelly.py`

Risiko:

Mittel.

Es dürfen weder zusätzliche Messwerte noch geänderte
Fehlerbehandlungen eingeführt werden.

### 3.8 Solarkon-Kommunikation

Die Solarkon-Kommunikation liegt bereits überwiegend im eigenständigen
Modul `app/modbus_solakon.py`.

Vorgeschlagenes Vorgehen:

1. Adaptermodul unter `solarinspector_core/adapters/solarkon.py`
   vorbereiten.
2. Bestehende Implementierung später dorthin verschieben.
3. `modbus_solakon.py` vorübergehend als Kompatibilitätsschicht
   erhalten.

Bestehende Tests:

- `tests/test_solarkon_modbus_characterization.py`
- Modbus-Integrationstest in `tests/test_core.py`

Risiko:

Mittel bis hoch, insbesondere für Importpfade und Upgradepakete.

### 3.9 Datenbank

Verantwortlichkeiten:

- SQLite-Verbindungen
- WAL-Modus
- Schemaerstellung
- bestehende Schemaergänzungen
- Index
- Schreiben von Messpunkten
- letzter Messpunkt
- Zeitraumabfragen
- Statistiken
- Löschen und `VACUUM`

Abhängigkeiten:

- `sqlite3`
- `Path`
- `DATA_DIR`

Globale Kopplung:

Obwohl der Datenbankpfad als Parameter übergeben wird, verwendet der
Konstruktor zusätzlich das globale `DATA_DIR`.

Bestehende Tests:

- `tests/test_database_characterization.py`
- Datenbanktests in `tests/test_core.py`

Vorgeschlagenes Ziel:

- `persistence/database.py`

Risiko:

Mittel.

Das bestehende Schema, SQL, Transaktionsverhalten und die
Bereichsgrenzen bleiben unverändert.

### 3.10 Collector

Verantwortlichkeiten:

- Gerätereader erzeugen
- Laufzeitzustand halten
- Hintergrundthread starten und stoppen
- Quellen abfragen
- Gerätefehler sammeln
- Quellen auswählen
- Leistungswerte berechnen
- Energie integrieren
- Messpunkt erzeugen
- Messpunkt speichern
- Status bereitstellen

Abhängigkeiten:

- Konfiguration
- Datenbank
- Shelly
- Solarkon
- Logging
- Zeit und Threading

Globale oder veränderliche Zustände:

- Thread
- Stop-Event
- letzter Messpunkt
- letzter Fehler
- Zykluszahl
- vorherige Leistungen
- vorheriger Zeitstempel

Bestehende Tests:

- `tests/test_collector_characterization.py`
- `tests/test_source_priority_characterization.py`
- `tests/test_energy_characterization.py`
- kombinierte Tests in `tests/test_core.py`

Vorgeschlagenes Ziel:

- Quellen- und Energielogik: `services/energy.py`
- Orchestrierung und Thread: `services/collector.py`

Risiko:

Hoch.

Der Collector wird erst ausgelagert, nachdem seine Abhängigkeiten
stabil getrennt wurden.

### 3.11 Bestehende Berechnungen

Enthalten sind:

- Auswahl der Solarquelle
- Auswahl der Netzquelle
- Umkehr des Solarkon-Netzvorzeichens
- Trennung von Bezug und Einspeisung
- Hausverbrauch
- Eigenverbrauch
- AC-Präferenz für die Hausbilanz
- Vergleich Shelly AC zu Solarkon AC
- Begrenzung des Integrationsintervalls
- trapezförmige Energieintegration
- Batterie-Lade- und Entladekanäle

Vorgeschlagenes Ziel:

- `services/energy.py`

Risiko:

Hoch.

Keine Formel, Rundung, Nullbehandlung, Vorzeichenkonvention oder
Quellenpriorität darf verändert werden.

### 3.12 Dashboard-Aufbereitung

Verantwortlichkeiten:

- Datumsanker
- Tages-, Wochen- und Jahresgrenzen
- Bucket-Zuordnung
- Zeitreihensummen
- kWh-Umrechnung
- KPI-Berechnung
- Batteriestatistiken
- Quellenanzeige

Abhängigkeiten:

- Datenbank
- Datum und lokale Zeitzone

Bestehende Tests:

- Dashboardtests in `tests/test_energy_characterization.py`
- API-Vertrag in `tests/test_web_api_characterization.py`

Vorgeschlagenes Ziel:

- `services/dashboard.py`

Risiko:

Mittel.

JSON-Strukturen, Rundungen, Titel und Beschriftungen bleiben
unverändert.

### 3.13 Flask-Anwendung

Verantwortlichkeiten:

- Flask-App erzeugen
- Secret prüfen
- Template-Kontext
- HTML-Seiten
- Konfigurationsformular
- Collector-APIs
- Live-API
- Dashboard-API
- Gerätetests
- CSV-Export
- Löschen aller Daten
- Versions- und Update-APIs

Direkte Abhängigkeiten:

- globale Konfiguration
- globale Datenbank
- globaler Collector
- Updatefunktionen
- Flask-Request-Kontext

Bestehende Tests:

- `tests/test_web_api_characterization.py`
- `tests/test_update_api.py`
- `tests/test_update_download_api.py`
- Webtest in `tests/test_core.py`

Vorgeschlagenes Ziel:

- `web/application.py`
- `web/routes.py`
- `web/api.py`

Risiko:

Hoch.

Eine Application Factory wird erst eingeführt, wenn
Konfiguration, Datenbank und Collector sauber importierbar sind.

### 3.14 Demodatengenerierung

Verantwortlichkeiten:

- synthetische PV-, Haus-, Batterie- und Netzdaten
- bestehende Energieintegration
- Schreiben in die globale Datenbank

Vorgeschlagenes Ziel:

- später `demo.py`

Risiko:

Mittel, da die Demo bestehende Fachformeln dupliziert.

Die Duplizierung wird in Phase 03 nicht fachlich bereinigt.

### 3.15 Runtime und Kommandozeile

Verantwortlichkeiten:

- Kommandozeilenargumente
- Host- und Portauswahl
- optionaler Collector-Start
- Browseröffnung
- PID-Datei
- Waitress-Start
- Prozessbereinigung

Vorgeschlagenes Ziel:

- `application.py`
- dünner Einstiegspunkt `solarinspector.py`

Risiko:

Hoch, da systemd, Upgrade-Skripte und bestehende Startaufrufe
kompatibel bleiben müssen.

## 4. Seiteneffekte beim Import

Der Import von `solarinspector.py` führt derzeit aus:

1. Version lesen.
2. Konfiguration laden oder anlegen.
3. Datenbankverzeichnis anlegen.
4. Datenbank öffnen und Schema initialisieren.
5. Collector und Gerätereader erzeugen.
6. Flask-App erzeugen.
7. `SOLARINSPECTOR_SECRET` prüfen.
8. `atexit`-Handler registrieren.

Nicht beim Import gestartet werden:

- Collector-Thread
- Webserver
- Browser
- reale Gerätekommunikation

Ziel der Phase ist, die Import-Seiteneffekte schrittweise zu
reduzieren. Die sofortige vollständige Entfernung ist nicht
erforderlich.

## 5. Abhängigkeitsrichtung

Angestrebt wird:

```text
solarinspector.py / application
            |
            v
          web
            |
            v
        services
         /     \
        v       v
    adapters  persistence
         \      /
          v    v
       config / models
```

Nicht zulässig:

- Persistenz importiert Flask.
- Adapter importieren Web- oder Dashboardlogik.
- Konfiguration importiert Collector.
- Energieberechnung importiert Flask.
- `__init__.py` erzeugt Laufzeitkomponenten.

## 6. Kompatibilitätsstrategie

`app/solarinspector.py` bleibt während Phase 03 bestehen.

Bestehende öffentliche Namen werden dort vorübergehend re-exportiert,
insbesondere:

- `DEFAULT_CONFIG`
- `DEVICE_TYPES`
- `deep_merge`
- `ConfigManager`
- `MeterReading`
- `ShellyReader`
- `Database`
- `Collector`
- `parse_anchor`
- `period_bounds`
- `bucket_index`
- `build_dashboard`
- `app`
- `config_manager`
- `database`
- `collector`

Die Kompatibilitätsschicht enthält keine neue Fachlogik.

## 7. Reihenfolge der Modularisierung

1. Strukturanalyse und Paketstruktur
2. Pfade und unveränderliche Konstanten
3. Konfigurationsdefaults und Konfigurationsmanager
4. Legacy-Datentyp `MeterReading`
5. SQLite-Persistenz
6. Shelly-Kommunikation
7. Solarkon-Modul mit Kompatibilitätspfad
8. bestehende Quellen- und Energieberechnung
9. Collector
10. Dashboard-Aufbereitung
11. Flask-Anwendung und Routen
12. Anwendungskontext
13. Demo und Runtime
14. Reduktion verbleibender globaler Zustände
15. vollständiger Regressionstest

Nach jedem Punkt wird entschieden, ob der nächste Schritt ohne
fachliche Änderung sicher möglich ist.

## 8. Teststrategie

Nach jedem kleinen Schritt:

```bash
python -m pytest -v <betroffene Testdateien>
python -m pytest -v tests
python -m ruff format --check app tests
python -m ruff check app tests
python -m mypy
git diff --check
```

Zusätzlich nach größeren Importänderungen:

```bash
python -c "import sys; sys.path.insert(0, 'app'); import solarinspector"
```

Vor jedem Commit:

```bash
git status
git diff --stat
git diff
```

## 9. Geplante Commits

```text
Create SolarInspector core package structure
Extract application paths and constants
Extract configuration management
Extract legacy measurement model
Extract SQLite persistence
Extract Shelly device communication
Extract Solarkon Modbus communication
Extract legacy energy calculations
Extract collector service
Extract dashboard data preparation
Extract Flask application and routes
Reduce global runtime dependencies
Document Phase 03 completion
```

Jeder Commit muss:

- logisch abgeschlossen sein,
- alle Tests bestehen,
- einzeln rücksetzbar sein,
- keine neue Funktion enthalten,
- das bestehende Verhalten beibehalten.

## 10. Erster Änderungsschritt

Der erste Änderungsschritt legt ausschließlich an:

- die seiteneffektfreie Paketstruktur,
- dieses Modularisierungsdokument,
- die Findings-Datei.

Produktivlogik wird dabei noch nicht verschoben.

Der erste vorgesehene Commit lautet:

```text
Create SolarInspector core package structure
```
