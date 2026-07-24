# Hichi/Tasmota als offizieller Netzstromzähler

## Zweck

SolarInspector 4.5 Phase 06 unterstützt einen optischen Hichi-Lesekopf mit
Tasmota-Firmware als offizielle Messstelle am öffentlichen Netzanschlusspunkt.

Die Quelle besitzt die fachliche Rolle `GRID_METER` und ist bei aktivierter,
verwertbarer Messung die bevorzugte Referenz für Netzbezug und Einspeisung.
Bestehende Shelly- oder Solakon-Netzwerte bleiben als deutlich gekennzeichneter
Kompatibilitätsfallback erhalten.

## Unterstützter Transport

Phase 06 implementiert ausschließlich lokales HTTP- beziehungsweise
HTTPS-Polling:

```text
GET /cm?cmnd=Status%2010
```

Der Adapter verwendet einen konfigurierbaren Host, Port, Timeout und ein eigenes
Pollingintervall. MQTT, Cloudzugriff und öffentliche Internetendpunkte sind
nicht Bestandteil dieser Phase.

## Konfiguration

```json
{
  "grid_meter": {
    "enabled": true,
    "adapter": "tasmota_http",
    "source_id": "grid_meter_primary",
    "name": "Offizieller Netzstromzähler",
    "host": "192.0.2.50",
    "port": 80,
    "scheme": "http",
    "timeout_seconds": 3,
    "poll_interval_seconds": 5,
    "username": "",
    "password": "",
    "direction_factor": 1,
    "mapping": {
      "grid_power_w": "StatusSNS.strom.Pges",
      "grid_import_power_w": "",
      "grid_export_power_w": "",
      "grid_import_total_kwh": "StatusSNS.strom.VerbrauchT0",
      "grid_export_total_kwh": "StatusSNS.strom.RetourT0"
    }
  }
}
```

`source_id` ist die stabile technische Identität und bleibt bei einer Änderung
der IP-Adresse unverändert. Unbekannte Konfigurations- und Mappingfelder bleiben
bei Migrationen erhalten.

## Authentifizierung und Sicherheit

Tasmota-Benutzername und Passwort werden nur als HTTP-Parameter an das lokale
Gerät übergeben. Die Konfigurationsseite zeigt das gespeicherte Passwort nicht
an. Ein leeres Passwortfeld behält den vorhandenen Wert.

Fehler, API-Antworten, Diagnoseausgaben und Hardwareberichte enthalten weder
Passwörter noch URLs mit eingebetteten Zugangsdaten. Rohantworten werden nicht
im Dashboard oder in der Datenbank gespeichert.

## Verbindung und Diagnose

Die Konfigurationsseite bietet „Verbindung und Mapping testen“. Der Test:

- schreibt keine Daten in die Datenbank,
- zeigt Status und normalisierte Kernwerte,
- prüft konfigurierte Feldpfade,
- listet kontrolliert bis zu 100 erkannte skalare Felder,
- zeigt keine vollständige Rohantwort,
- gibt keine Zugangsdaten zurück.

## Unterstützte Kernmetriken

| Metrik | Bedeutung | kanonische Einheit |
|---|---|---|
| `GRID_POWER` | vorzeichenbehaftete Netto-Netzleistung | W |
| `GRID_IMPORT_POWER` | aktueller Bezug, immer nicht negativ | W |
| `GRID_EXPORT_POWER` | aktuelle Einspeisung, immer nicht negativ | W |
| `GRID_IMPORT_TOTAL` | kumulierter Netzbezug | Wh im Messwertmodell |
| `GRID_EXPORT_TOTAL` | kumulierte Netzeinspeisung | Wh im Messwertmodell |

Das reale Gerät liefert die Zählerstände in kWh. Der Adapter wandelt sie für
das bestehende kanonische Messwertmodell in Wh um. Die Grid-Meter-Persistenz und
die öffentliche API stellen sie wieder in kWh dar.

Direkte Import- und Exportleistungen sind optional. Fehlen sie, werden beide
nicht negativen Richtungswerte aus `GRID_POWER` abgeleitet.

## Vorzeichen

```text
GRID_POWER > 0  = Netzbezug
GRID_POWER < 0  = Netzeinspeisung
GRID_POWER = 0  = gültiger Nullwert
```

`direction_factor` darf `1` oder `-1` sein und wird vor der Aufteilung in Bezug
und Einspeisung angewendet.

## Gerätestatus

| Status | Verhalten |
|---|---|
| `ONLINE` | Kernwert vorhanden und keine Diagnose |
| `DEGRADED` | Antwort verwertbar, aber Werte fehlen oder Mapping ist auffällig |
| `OFFLINE` | Timeout, HTTP-/Verbindungsfehler oder unbrauchbare Antwort |
| `DISABLED` | Quelle deaktiviert |

Ein Offline- oder degradiertes Gerät stoppt den Collector nicht. Ein
degradiertes Snapshot mit gültiger `GRID_POWER` bleibt als primäre Quelle
verwendbar. Fehlt die Kernleistung, kann die bestehende Netzquelle als
gekennzeichneter Fallback verwendet werden.

## Persistenz und API

Die bestehende Tabelle `samples` bleibt kompatibel. Normalisierte offizielle
Zählerdetails werden atomar in `grid_meter_samples` gespeichert.

`/api/live` ergänzt additiv:

- `grid_meter`
- `active_sources.grid_power`
- `active_sources.grid_power_label`

Bestehende API-Felder werden weder entfernt noch umbenannt.

## Hardwaretest

Der optionale pytest-Hardwaretest ist standardmäßig übersprungen:

```bash
export SOLARINSPECTOR_TEST_TASMOTA_HOST="tasmota.local"
export SOLARINSPECTOR_TEST_TASMOTA_PORT="80"
export SOLARINSPECTOR_TEST_TASMOTA_USERNAME=""
export SOLARINSPECTOR_TEST_TASMOTA_PASSWORD=""

pytest -v -m hardware \
  tests/test_tasmota_grid_meter_hardware.py
```

Der Test ruft das Gerät mehrfach ab, verlangt mindestens eine Kernmetrik,
prüft Status und Zeitzonen und kontrolliert, dass Zugangsdaten nicht in der
Snapshot-Repräsentation erscheinen.

## Dauerprüfung

Ein begrenzter Lauf wird separat gestartet:

```bash
python scripts/tasmota_grid_meter_soak.py \
  --duration-minutes 120 \
  --interval-seconds 5
```

Der Bericht wird standardmäßig unter `.phase06-capture/` gespeichert und darf
nicht committed werden. Er enthält keine Adresse und keine Zugangsdaten.
