# SolarInspector 4.5 – Phase 02: Coverage-Bewertung

## 1. Zweck

Dieses Dokument bewertet die Testabdeckung nach Abschluss der
Charakterisierungstests für SolarInspector 4.5, Phase 02.

Coverage wird dabei als Hilfsmittel zur Risikobewertung verwendet. Ziel ist
nicht, einen möglichst hohen Prozentwert durch Tests für triviale
Kommandozeilen-, Prozess- oder Demo-Wrapper zu erzeugen. Entscheidend ist, ob
das bestehende fachliche und technische Verhalten vor der geplanten
Modularisierung ausreichend abgesichert ist.

## 2. Messbasis

- Ausgangsversion: SolarInspector 4.1.3
- Ausgangscommit: `095038d`
- Arbeitsbranch: `feature/4.5-02-characterization-tests`
- Abschlusscommit der Testkategorien: `731db2d`
- Lokale Umgebung: macOS mit Python 3.14.6
- Gemessene Tests: 222
- Teststatus: 222 bestanden
- Gesamt-Coverage: 86 %
- Anweisungen: 1.431
- Nicht abgedeckte Anweisungen: 197

Verwendeter Aufruf:

```bash
SOLARINSPECTOR_SECRET=phase-02-test-secret \
python -m pytest -q tests \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=html:/tmp/solarinspector-coverage-html \
  --cov-report=xml:/tmp/solarinspector-coverage.xml
```

## 3. Coverage nach Modul

| Modul | Anweisungen | Nicht abgedeckt | Coverage | Bewertung |
|---|---:|---:|---:|---|
| `app/solarinspector.py` | 769 | 77 | 90 % | Gute Absicherung der zentralen Laufzeitlogik |
| `app/modbus_solakon.py` | 228 | 9 | 96 % | Sehr gute Protokoll- und Registerabsicherung |
| `app/update_status.py` | 27 | 0 | 100 % | Vollständig abgedeckt |
| `app/github_updater.py` | 116 | 13 | 89 % | Gute Abdeckung der Updateprüfung und Verifikation |
| `app/release_installer.py` | 182 | 61 | 66 % | Wesentliche Kernfälle getestet; viele Systemprozesspfade offen |
| `app/updater_service.py` | 109 | 37 | 66 % | Kernabläufe getestet; Dienst- und Prozesspfade teilweise offen |
| **Gesamt** | **1.431** | **197** | **86 %** | Gute risikobasierte Ausgangslage für Phase 03 |

## 4. Bewertung der zentralen Laufzeitmodule

### 4.1 `solarinspector.py` – 90 %

Das zentrale Anwendungsmodul ist in den für die Modularisierung besonders
kritischen Bereichen abgesichert:

- Konfigurationsladen, Validierung und Speichern
- Shelly-Kommunikation und Antwortinterpretation
- Quellenpriorität und Fallback-Auswahl
- Collector-Lebenszyklus und Fehlerbehandlung
- Energieintegration
- SQLite-Schema und Persistenz
- Dashboard-Aggregation
- Web- und API-Verträge
- CSV-Export
- Update-API-Fehlerpfade

Die verbleibenden Lücken betreffen überwiegend:

- einzelne Validierungszweige für ungültige Gerätedaten
- seltene Gerätefehler, die bereits in angrenzenden Tests indirekt
  charakterisiert sind
- Demo-Datengenerierung
- Kommandozeilenargumente und Programmstart
- Browserstart und Serverprozess
- Aufräumen der PID-Datei
- den Importschutz bei fehlendem `SOLARINSPECTOR_SECRET`

Diese Pfade sind für die geplante interne Modularisierung weniger kritisch als
die bereits abgedeckte Mess-, Auswahl-, Berechnungs- und Persistenzlogik.

### 4.2 `modbus_solakon.py` – 96 %

Die Solakon-Modbus-Integration ist sehr gut abgesichert. Charakterisiert sind
unter anderem:

- feste Registerblöcke
- Messwertkonvertierungen
- Lade- und Entladebetrieb
- Nullerzeugung
- unvollständige Register
- moderne und historische Energiezähler
- Batterie-Leistungsprioritäten
- Teilfehler und vollständiger Kommunikationsausfall
- ungültige Registerbereiche
- Protokollfehler und Verbindungsprobleme

Nicht abgedeckt bleiben nur einzelne seltene Varianten ungültiger
Modbus-Antwortköpfe sowie wenige interne Konvertierungszweige. Das verbleibende
Risiko wird als niedrig bewertet.

### 4.3 `github_updater.py` – 89 %

Abgedeckt sind:

- Erkennung neuer Releases
- ungültige Release-Versionen
- fehlende Assets
- Netzwerkfehler
- maximale Downloadgröße
- Abbruch bei Stream-Übergröße
- Berechnung und Prüfung von SHA-256
- ungültige oder fremde Prüfsummendateien
- fehlende Archiv- oder Prüfsummenassets

Nicht vollständig abgedeckt ist der erfolgreiche kombinierte
Download-und-Verifikationsablauf mit zwei realistisch simulierten Downloads.
Die Einzelbestandteile sind separat abgesichert. Das verbleibende Risiko ist
überschaubar.

### 4.4 `release_installer.py` – 66 %

Die geringere Coverage entsteht vor allem durch Betriebssystem- und
Prozessintegration:

- Systembefehle und Rückgabecodes
- Service-Stopp und Service-Start
- Healthcheck-Wartepfade
- Archivextraktion und Dateisystemfehler
- Aktivierung und Rollback
- Fehler während mehrstufiger Installationsabläufe
- Kommandozeilen-Einstiegspfade

Die kritischen Kernverträge für Vorbereitung, Healthcheck, Aktivierung,
Rollback und Fehlerbehandlung sind bereits getestet. Eine weitere Erhöhung
würde umfangreichere Systemprozess-Simulationen oder echte
Linux-Integrationstests erfordern.

Diese Lücken sollten nicht durch triviale Mock-Tests geschlossen werden, die
nur Implementierungsdetails reproduzieren. Sinnvoller wäre später eine kleine
Linux-Testumgebung für den vollständigen Installations- und Rollbackprozess.

### 4.5 `updater_service.py` – 66 %

Abgedeckt sind insbesondere:

- Lesen von Updateaufträgen
- Backup-Erstellung
- persistente Konfigurations- und Datenpfade
- erfolgreiche Updateorchestrierung
- wesentliche Fehlerfälle

Offen bleiben vor allem:

- reale Service-Steuerung
- mehrere Prozess- und Dateisystemfehler
- vollständige Orchestrierungs- und Rollbackzweige
- Kommandozeilen-Einstiegspunkt

Auch hier ist eine spätere Linux-Integration aussagekräftiger als zusätzliche
feingranulare Mock-Tests.

### 4.6 `update_status.py` – 100 %

Folgende Verträge sind vollständig abgesichert:

- fehlende Statusdatei
- ungültiges JSON
- Ergänzung fehlender Standardfelder
- Erhalt unbekannter Felder
- atomisches Schreiben über eine temporäre Datei
- Aktualisierung des Zeitstempels

## 5. Testkategorien

Die Suite ist mit registrierten und strikt geprüften pytest-Markern
strukturiert:

| Marker | Tests | Zweck |
|---|---:|---|
| `characterization` | 181 | Bestehendes Verhalten vor Refactoring festschreiben |
| `integration` | 6 | Mehrere Komponenten oder lokales Protokoll gemeinsam testen |
| `release` | 35 | Update-, Upgrade-, Paket- und Releaseabläufe prüfen |
| **Gesamt** | **222** | |

Die Kategorien überschneiden sich nicht. Jeder Test ist genau einer Kategorie
zugeordnet.

Beispiele:

```bash
python -m pytest -q -m characterization
python -m pytest -q -m integration
python -m pytest -q -m release
```

## 6. Bewusst nicht maximierte Coverage

In Phase 02 wurden keine zusätzlichen Tests allein zur Steigerung des
Prozentwertes erstellt für:

- `argparse`-Definitionen
- den direkten `main()`-Aufruf
- den Waitress-Serverstart
- automatisches Öffnen des Browsers
- PID-Datei-Aufräumlogik
- vollständige Demo-Datengenerierung über lange Zeiträume
- triviale `if __name__ == "__main__"`-Zweige
- Betriebssystemkommandos, die ohne Linux-Umgebung nur vollständig gemockt
  würden

Diese Entscheidung vermeidet fragile Tests, die Implementierungsdetails
duplizieren, aber wenig Schutz für die geplante Modularisierung liefern.

## 7. Bekannte Beobachtung: `ResourceWarning`

Beim finalen Coverage-Lauf wurde unter Python 3.14.6 einmal folgender Warnungstyp
beobachtet:

```text
ResourceWarning: unclosed database in <sqlite3.Connection ...>
```

Die Warnung wurde während eines Energietests ausgegeben, muss aber wegen der
verzögerten Freigabe durch den Garbage Collector nicht zwingend dort verursacht
worden sein.

Bewertung:

- alle 222 Tests bestanden
- Ruff und Mypy blieben fehlerfrei
- es wurde kein reproduzierbarer funktionaler Fehler festgestellt
- die konkrete Herkunft der nicht geschlossenen SQLite-Verbindung ist noch
  nicht lokalisiert

Empfehlung:

- als technische Beobachtung nach Phase 02 weiterführen
- unter Python 3.11 bis 3.13 in CI beobachten
- bei reproduzierbarem Auftreten mit `tracemalloc` oder
  `pytest -W error::ResourceWarning` gezielt analysieren
- nicht durch eine ungesicherte Produktcodeänderung innerhalb von Phase 02
  beheben

## 8. Restrisiken und Empfehlungen

### Niedriges Risiko

- zentrale Mess- und Berechnungslogik
- Shelly-Interpretation
- Solakon-Modbus-Auswertung
- Quellenpriorität
- SQLite-Persistenz
- Web- und API-Verträge
- Statusdateiverarbeitung

### Mittleres Risiko

- reale Updateinstallation auf Linux
- Dienststeuerung und Rollback bei mehreren aufeinanderfolgenden Fehlern
- vollständiger erfolgreicher Download-und-Verifikationsablauf
- nicht reproduzierter SQLite-`ResourceWarning`

### Empfehlungen für spätere Phasen

1. Charakterisierungstests während der Modularisierung unverändert weiterführen.
2. Refactorings in kleinen Schritten durchführen und nach jedem Schritt
   mindestens `pytest -m characterization` ausführen.
3. Release- und Upgradepfade zusätzlich in einer Linux-CI- oder
   Containerumgebung prüfen.
4. Den `ResourceWarning` beobachten und bei Reproduzierbarkeit separat
   untersuchen.
5. Coverage künftig als Trendsignal verwenden, nicht als alleinige
   Qualitätskennzahl.

## 9. Fazit

Die Gesamt-Coverage von 86 % und insbesondere die Abdeckung von 90 % im
zentralen Anwendungsmodul sowie 96 % in der Solakon-Modbus-Integration bilden
eine belastbare Grundlage für die geplante Modularisierung.

Die verbleibenden Lücken liegen überwiegend in Kommandozeilen-, Prozess-,
Demo- und betriebssystemabhängigen Releasepfaden. Sie rechtfertigen keine
Blockade von Phase 03, sollten aber für spätere Linux-Integrationstests sichtbar
bleiben.
