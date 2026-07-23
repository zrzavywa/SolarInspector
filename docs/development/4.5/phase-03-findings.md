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
