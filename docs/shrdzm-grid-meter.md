# SHRDZM als offizieller Netzstromzähler

Diese Anleitung beschreibt die in SolarInspector 4.5 implementierte,
ausschließlich lesende Anbindung eines SHRDZM-Kundenschnittstellen-Moduls
an den offiziellen Netzstromzähler.

## Status und Geltungsbereich

Implementiert und automatisiert getestet sind:

- lokaler HTTP- beziehungsweise HTTPS-Abruf über `/getLastData`,
- Query-Authentifizierung, HTTP Basic oder explizit keine Authentifizierung,
- direkte OBIS-Schlüssel und konfigurierbare verschachtelte JSON-Pfade,
- Netzbezug, Einspeisung, saldierte Netzleistung und echte Nullwerte,
- Energiezähler in der internen SolarInspector-Einheit Wh,
- optionale Phasenspannungen und Phasenströme,
- kontrollierte Zustände `ONLINE`, `DEGRADED`, `OFFLINE` und `DISABLED`,
- priorisierte Nutzung als offizielle Netzreferenz mit bestehenden Quellen
  als gekennzeichnetem Fallback.

Die automatisierten Tests verwenden bereinigte Fixture-Daten. Eine reale
**Hardwarevalidierung** des konkreten Moduls, Zählers und Netzbetreibers ist
weiterhin erforderlich, sobald das Gerät verfügbar ist.

## Messkonzept

Der offizielle Netzstromzähler ist die führende Referenz für Netzbezug und
Einspeisung. SolarInspector verwendet folgende Vorzeichenkonvention:

- positiver Wert: Netzbezug,
- negativer Wert: Einspeisung.

Wenn getrennte Leistungswerte vorhanden sind, wird die saldierte
Netzleistung berechnet als:

```text
Netzleistung = Bezug - Einspeisung
```

Ein gemeldeter Wert von `0` bleibt ein echter Messwert und wird nicht als
fehlend interpretiert.

## Standard-OBIS-Zuordnung

| SolarInspector-Feld | OBIS | Bedeutung |
|---|---|---|
| `grid_power_w` | `16.7.0` | saldierte Wirkleistung, falls verfügbar |
| `grid_import_power_w` | `1.7.0` | aktueller Netzbezug |
| `grid_export_power_w` | `2.7.0` | aktuelle Einspeisung |
| `grid_import_total_kwh` | `1.8.0` | kumulierter Netzbezug |
| `grid_export_total_kwh` | `2.8.0` | kumulierte Einspeisung |
| `phase_voltage_l1_v` | `32.7.0` | Spannung L1 |
| `phase_voltage_l2_v` | `52.7.0` | Spannung L2 |
| `phase_voltage_l3_v` | `72.7.0` | Spannung L3 |
| `phase_current_l1_a` | `31.7.0` | Strom L1 |
| `phase_current_l2_a` | `51.7.0` | Strom L2 |
| `phase_current_l3_a` | `71.7.0` | Strom L3 |

Die tatsächlich verfügbaren OBIS-Werte werden vom offiziellen Zähler und
dessen Freigabe durch den Netzbetreiber bestimmt. Fehlende optionale Werte
dürfen nicht durch erfundene Nullwerte ersetzt werden.

## Konfigurationsbeispiel

```json
"grid_meter": {
  "enabled": true,
  "adapter": "shrdzm_rest",
  "source_id": "grid_meter_primary",
  "name": "Offizieller Netzstromzähler",
  "host": "<SHRDZM-IP>",
  "port": 80,
  "scheme": "http",
  "timeout_seconds": 3,
  "poll_interval_seconds": 5,
  "username": "<BENUTZER>",
  "password": "<LOKALES-KENNWORT>",
  "direction_factor": 1,
  "shrdzm_rest": {
    "endpoint": "/getLastData",
    "authentication_mode": "query",
    "username_parameter": "user",
    "password_parameter": "password",
    "energy_total_unit": "auto"
  },
  "mapping": {
    "grid_power_w": "16.7.0",
    "grid_import_power_w": "1.7.0",
    "grid_export_power_w": "2.7.0",
    "grid_import_total_kwh": "1.8.0",
    "grid_export_total_kwh": "2.8.0",
    "phase_voltage_l1_v": "32.7.0",
    "phase_voltage_l2_v": "52.7.0",
    "phase_voltage_l3_v": "72.7.0",
    "phase_current_l1_a": "31.7.0",
    "phase_current_l2_a": "51.7.0",
    "phase_current_l3_a": "71.7.0"
  }
}
```

Die Feldnamen der historischen Konfiguration enden bei den Energiezählern
weiterhin auf `_kwh`. Intern werden die Messwerte unabhängig davon in Wh
normalisiert. Bei `energy_total_unit: "auto"` verwendet SolarInspector für
die Standard-OBIS-Zähler `1.8.0` und `2.8.0` die bestätigte Rohdateneinheit
Wh. Für eigene Pfade muss die Einheit ausdrücklich als `wh`, `kwh` oder
`mwh` konfiguriert werden.

## Authentifizierungsmodi

| Modus | Verhalten |
|---|---|
| `query` | Benutzername und Kennwort werden als konfigurierbare Query-Parameter übertragen |
| `basic` | HTTP-Basic-Authentifizierung; ohne Benutzername wird `admin` verwendet |
| `none` | gespeicherte Zugangsdaten werden nicht übertragen |

Zugangsdaten sind niemals Bestandteil der protokollierten URL oder der
Diagnoseantwort. Die lokale `config.json` muss trotzdem mit restriktiven
Dateirechten geschützt werden.

## Verbindungstest in SolarInspector

1. Unter **Konfiguration** den Adapter `SHRDZM REST / getLastData` wählen.
2. IP-Adresse beziehungsweise Hostname eintragen.
3. Authentifizierungsmodus und lokale Zugangsdaten konfigurieren.
4. **Verbindung und Mapping testen** ausführen.
5. Prüfen, ob Adapter, REST-Endpunkt, Netzleistung, Bezug, Einspeisung und
   erkannte OBIS-Felder plausibel angezeigt werden.
6. Erst nach erfolgreicher Prüfung die automatische Datenerfassung starten.

Ein erfolgreicher Fixture-Test bestätigt die Softwarelogik, aber nicht die
Erreichbarkeit oder konkrete Datenfreigabe eines realen Zählers.

## Status und Fallback

| Status | Bedeutung |
|---|---|
| `ONLINE` | verwertbare Messwerte ohne Diagnosehinweis |
| `DEGRADED` | Kernwert nutzbar, optionale oder konfigurierte Werte fehlen |
| `OFFLINE` | Netzwerk-, HTTP- oder JSON-Fehler; keine verwertbaren Werte |
| `DISABLED` | Messstelle ist deaktiviert und wird nicht abgefragt |

Liefert der offizielle Zähler keine nutzbare Netzleistung, kann
SolarInspector auf die bestehende Shelly-Hausanschlussmessung oder das
Solakon-Meter zurückfallen. Der Fallback wird im Quellenlabel ausdrücklich
gekennzeichnet.

## Checkliste für die spätere Hardwarevalidierung

- Modul und offizieller Zähler sind elektrisch und optisch korrekt verbunden.
- Die Kundenschnittstelle des Zählers ist beim Netzbetreiber freigeschaltet.
- `/getLastData` liefert im lokalen Netz ein JSON-Objekt.
- Bezug ohne PV-Erzeugung erzeugt einen positiven SolarInspector-Netzwert.
- Deutliche Einspeisung erzeugt einen negativen SolarInspector-Netzwert.
- Stillstand beziehungsweise Bilanznull bleibt exakt `0 W`.
- `1.8.0` und `2.8.0` steigen nur in der fachlich richtigen Richtung.
- Einheiten werden mit dem Zählerdisplay oder Netzbetreiberportal verglichen.
- Neustart, Timeout, falsches Kennwort und Geräteausfall werden geprüft.
- Diagnoseausgaben werden vor Weitergabe auf sensible Daten kontrolliert.
