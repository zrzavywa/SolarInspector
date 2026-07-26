# Phase 08 – externe Hardwareverifikation

## Status

Die automatisierte und simulierte Abnahme von Phase 08 ist vollständig. Am
lokalen Entwicklungsstandort steht keine Solakon-ONE-Hardware zur Verfügung.
Deshalb wird kein realer Solakon-Hardwaretest behauptet.

Die verbleibende Hardwareprüfung ist ein externer Zielsystem-Check am Standort
mit Solakon ONE, Shelly PM Mini Gen3 und – sofern vorhanden – Shelly 3EM oder
offiziellem Netzstromzähler.

Dieser Check verändert keine Konfiguration der Geräte. SolarInspector greift
ausschließlich lesend zu.

## Voraussetzungen

- aktueller Phase-08-Branch oder daraus erzeugtes Testpaket
- gesicherte bestehende `config.json`
- gesicherte SQLite-Datenbank
- lokale IP-Adressen der verwendeten Geräte
- aktivierter read-only Modbus-TCP-Zugriff der Solakon ONE
- bekannte elektrische Positionen der Vergleichsmessgeräte
- synchronisierte Systemzeit

## Empfohlener Ablauf

1. SolarInspector mit aktivierter Plausibilitätsprüfung starten.
2. Verbindungstests für Solakon ONE und die Shelly-Messgeräte ausführen.
3. Prüfen, dass die angezeigten Quellennamen und Messrollen stimmen.
4. Den Beobachter 30 Minuten laufen lassen:

   ```bash
   python scripts/validation_hardware_soak.py --duration-minutes 30
   ```

5. Währenddessen mindestens folgende Situationen beobachten:
   - normale PV-Erzeugung
   - Lastwechsel im Haushalt
   - geringe oder keine PV-Erzeugung
   - kurze Kommunikationsunterbrechung eines Geräts, sofern gefahrlos möglich
6. Dashboard und Validierungs-API vergleichen:

   ```text
   GET /api/validation/summary
   GET /api/validation/events
   ```

## Abnahmekriterien

- gültige Messwerte werden weiterverarbeitet
- fehlende oder ungültige Werte werden nicht für Energieintegration verwendet
- Warnungen verursachen keine Ereignisflut, sondern werden dedupliziert
- abgelehnte Werte besitzen keinen `accepted_value`
- der offizielle Netzstromzähler bleibt die führende Netzreferenz
- ein Geräteausfall stoppt den Collector nicht
- nach Wiederverbindung wird die Erfassung fortgesetzt
- keine Passwörter, Tokens oder vollständigen Rohantworten erscheinen in Events
- Dashboard und API zeigen denselben Qualitätsstatus

## Ergebnisprotokoll

Für den externen Test sind festzuhalten:

- Datum und Dauer
- eingesetzte Geräte und Firmwarestände
- verwendete Source-IDs und Messrollen
- Anzahl Warnungen und Ablehnungen
- auffällige Rule-IDs
- Screenshots der Qualitätsübersicht
- exportierte, bereinigte Ereigniszusammenfassung
- Ergebnis: bestanden, bestanden mit Findings oder nicht bestanden

## Einordnung

Die externe Hardwareverifikation ist keine Voraussetzung dafür, die
Implementierung, Tests und Dokumentation von Phase 08 abzuschließen. Sie bleibt
jedoch Voraussetzung für die Freigabe einer konkreten Solakon-Installation.
