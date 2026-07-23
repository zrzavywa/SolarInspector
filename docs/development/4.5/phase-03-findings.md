# SolarInspector 4.5 – Phase 03: Technische Findings

Dieses Dokument erfasst Beobachtungen aus der Modularisierung.
Findings werden in Phase 03 nicht nebenbei fachlich korrigiert.

## MOD-001 – Import initialisiert Konfiguration und Datenbank

**Betroffener Bereich:** `app/solarinspector.py`

**Problem:** Beim Modulimport werden `ConfigManager`, `Database`,
`Collector` und Flask global erzeugt.

**Auswirkung:** Der Import besitzt Dateisystem- und
Datenbankseiteneffekte und benötigt `SOLARINSPECTOR_SECRET`.

**Warum nicht sofort behoben:** Tests und Webrouten greifen direkt
auf diese globalen Objekte zu.

**Vorgeschlagene Zielphase:** schrittweise Phase 03

**Priorität:** hoch

## MOD-002 – Collector besitzt mehrere Verantwortlichkeiten

**Betroffener Bereich:** `Collector.collect_once()`

**Problem:** Gerätezugriff, Fehlerbehandlung, Quellenwahl,
Leistungsberechnung, Energieintegration, Messwertaufbau und
Persistenz befinden sich in einer Methode.

**Auswirkung:** Hohe Kopplung und hohes Refactoring-Risiko.

**Warum nicht sofort behoben:** Die Abhängigkeiten werden zuerst
einzeln ausgelagert.

**Vorgeschlagene Zielphase:** Phase 03

**Priorität:** hoch

## MOD-003 – Globale Webabhängigkeiten werden in Tests ersetzt

**Betroffener Bereich:** Flask-Routen und Webtests

**Problem:** Routen verwenden direkt `config_manager`, `database`
und `collector`. Tests ersetzen diese globalen Objekte.

**Auswirkung:** Eine unmittelbare Application Factory würde zahlreiche
Import- und Testpfade gleichzeitig verändern.

**Warum nicht sofort behoben:** Eine Kompatibilitätsschicht wird bis
zur Webauslagerung benötigt.

**Vorgeschlagene Zielphase:** spätere Arbeitspakete von Phase 03

**Priorität:** hoch

## MOD-004 – Database verwendet globales Datenverzeichnis

**Betroffener Bereich:** `Database.__init__()`

**Problem:** Die Datenbank erhält einen Pfad als Parameter, legt aber
zusätzlich das globale `DATA_DIR` an.

**Auswirkung:** Versteckte Abhängigkeit und unnötiger
Dateisystemseiteneffekt bei temporären Testdatenbanken.

**Warum nicht in Phase 03 nebenbei korrigiert:** Das bestehende
Verhalten ist durch Charakterisierungstests eingefroren.

**Vorgeschlagene Zielphase:** gesonderte technische Bereinigung nach
erfolgreicher Persistenzauslagerung

**Priorität:** mittel

## MOD-005 – Secret-Prüfung erfolgt beim Import

**Betroffener Bereich:** Flask-Initialisierung

**Problem:** Ein fehlendes `SOLARINSPECTOR_SECRET` verhindert bereits
den Modulimport.

**Auswirkung:** Bibliotheksartige Nutzung und isolierte Tests benötigen
eine Laufzeit-Umgebungsvariable.

**Warum nicht sofort behoben:** Eine Verschiebung kann Start- und
Fehlerverhalten verändern.

**Vorgeschlagene Zielphase:** Web- und Anwendungskontext in Phase 03

**Priorität:** mittel

## MOD-006 – Demo dupliziert bestehende Energielogik

**Betroffener Bereich:** `generate_demo_data()`

**Problem:** Die Demodatengenerierung enthält eigene Leistungs- und
Energieformeln.

**Auswirkung:** Formeln können langfristig auseinanderlaufen.

**Warum nicht in Phase 03 korrigiert:** Eine Zusammenführung wäre
potenziell eine fachliche Verhaltensänderung.

**Vorgeschlagene Zielphase:** spätere technische Bereinigung

**Priorität:** niedrig

## Abschlussbewertung der Findings

Die Findings bleiben als technische Entscheidungsgrundlage erhalten.
Ihr Status nach Abschluss von Phase 03 ist:

| Finding | Status | Bewertung |
|---|---|---|
| MOD-001 | teilweise entschärft | Pfade, Konfiguration, Datenbank und Services wurden ausgelagert. Die globale Instanziierung im kompatiblen Einstiegspunkt bleibt bewusst bestehen. |
| MOD-002 | strukturell entschärft | Der Collector liegt jetzt in `services/collector.py`. Eine weitere fachliche Zerlegung wurde wegen des Refactoring-Auftrags nicht vorgenommen. |
| MOD-003 | bewusst akzeptiert | Weblogik wurde in Hilfsmodule ausgelagert. Flask-Routen und dynamische Monkeypatch-Punkte bleiben im Einstiegspunkt kompatibel. |
| MOD-004 | offen | Das historisch charakterisierte Verhalten des Datenbank-Datenverzeichnisses wurde nicht verändert. |
| MOD-005 | offen | Die Prüfung von `SOLARINSPECTOR_SECRET` erfolgt weiterhin beim Import des Einstiegspunkts. |
| MOD-006 | bewusst akzeptiert | Die Demodatengenerierung wurde nach `services/demo.py` verschoben. Ihre Formeln bleiben unverändert. |

## MOD-007 – Legacy-Importpfade sind Teil der Schnittstelle

**Betroffener Bereich:** `solarinspector.py` und `modbus_solakon.py`

**Beobachtung:** Charakterisierungstests und bestehende Integrationen
verwenden nicht nur öffentliche Klassen und Funktionen, sondern ersetzen
teilweise auch Modulattribute wie Reader, Zeitquellen, Logging,
Threading, Socket und Modbus-Verbindungen.

**Auswirkung:** Ein einfacher Re-Export ist nicht immer ausreichend.
Die aufrufende Implementierung muss den historischen Patchpunkt weiterhin
dynamisch auflösen.

**Umsetzung in Phase 03:** Für Collector, Konfiguration, Runtime und
Solakon wurden gezielte Kompatibilitäts-Wrapper beziehungsweise Hooks
beibehalten.

**Status:** gelöst und durch Charakterisierungstests abgesichert.

**Priorität für spätere Arbeiten:** hoch, falls Legacy-Pfade entfernt
oder eine neue öffentliche API eingeführt werden soll.

## Schlussfolgerung

Die verbliebenen offenen Punkte sind keine versehentlich ausgelassenen
Teile der Modularisierung. Sie wurden bewusst nicht verändert, weil sie
beobachtbares Verhalten, Importverhalten oder fachliche Berechnungen
betreffen.

Ihre Bearbeitung sollte in eigenständigen Arbeitspaketen mit eigenen
Charakterisierungstests und klarer Migrationsstrategie erfolgen.
