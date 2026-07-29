# Konfigurationsreferenz

Zrzavy Energy Monitor verwendet eine JSON-Konfiguration. Die Vorlage befindet sich unter:

```text
app/config.example.json
```

In einer 4.5-Referenzinstallation liegt die persistente Konfiguration unter:

```text
/etc/zrzavy-energy-monitor/config.json
```

## Grundregeln

- JSON erlaubt keine Kommentare.
- Zeichenketten stehen in doppelten Anführungszeichen.
- `true` und `false` werden kleingeschrieben.
- Nach dem letzten Element eines Objekts steht kein Komma.
- Vor jeder manuellen Änderung sollte eine Sicherung erstellt werden.
- Kennwörter dürfen nicht in GitHub, Issues oder Diagnoseausgaben veröffentlicht werden.

Konfiguration prüfen:

```bash
python3 -m json.tool /etc/zrzavy-energy-monitor/config.json >/dev/null
```

## Vollständiges Beispiel

```json
{
  "general": {
    "project_name": "Zrzavy Energy Monitor",
    "site_name": "Standort",
    "poll_interval_seconds": 10,
    "auto_start_collection": false,
    "bind_host": "127.0.0.1",
    "port": 8787,
    "open_browser": true,
    "solar_power_source": "auto",
    "grid_power_source": "auto"
  },
  "solakon_one": {
    "enabled": false,
    "host": "",
    "port": 502,
    "device_id": 1,
    "timeout_seconds": 5,
    "simulation": false
  },
  "house_meter": {
    "enabled": false,
    "type": "shelly_3em_gen1",
    "host": "",
    "username": "",
    "password": "",
    "timeout_seconds": 3,
    "direction_factor": 1
  },
  "solakon_meter": {
    "enabled": false,
    "type": "shelly_pm_mini_gen3",
    "host": "",
    "username": "",
    "password": "",
    "timeout_seconds": 3,
    "direction_factor": 1
  }
}
```

## Abschnitt `general`

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `project_name` | String | `Zrzavy Energy Monitor` | Name der Installation |
| `site_name` | String | `Standort` | Bezeichnung des Anlagenstandorts |
| `poll_interval_seconds` | Integer | `10` | Abstand zwischen Geräteabfragen |
| `auto_start_collection` | Boolean | `false` | Datenerfassung beim Anwendungsstart aktivieren |
| `bind_host` | String | `127.0.0.1` | Netzwerkschnittstelle des Webservers |
| `port` | Integer | `8787` | TCP-Port der Weboberfläche |
| `open_browser` | Boolean | `true` | Browser beim interaktiven Start öffnen |
| `solar_power_source` | String | `auto` | Quelle für Solarleistung |
| `grid_power_source` | String | `auto` | Quelle für Netzbezug und Einspeisung |

### `bind_host`

| Wert | Verhalten |
|---|---|
| `127.0.0.1` | Nur auf dem lokalen Rechner erreichbar |
| `0.0.0.0` | Auf allen lokalen Netzwerkschnittstellen erreichbar |
| konkrete IP | Nur an diese lokale Adresse binden |

`0.0.0.0` ist für einen Raspberry Pi im Heimnetz praktisch, erhöht aber die erreichbare Angriffsfläche. Die Anwendung nicht direkt ins Internet veröffentlichen.

### `solar_power_source`

Unterstützte Auswahlwerte:

| Wert | Bedeutung |
|---|---|
| `auto` | Zrzavy Energy Monitor wählt eine verfügbare Quelle |
| `shelly_ac` | unabhängige AC-Messung am Solakon-Ausgang |
| `solakon_ac` | AC-Leistung aus der Solakon ONE |
| `solakon_pv` | PV-Eingangsleistung aus der Solakon ONE |

AC- und PV-Leistung sind nicht identisch. Für Wirkungsgrad- oder Verlustvergleiche müssen Quelle und Bedeutung eindeutig angegeben werden.

### `grid_power_source`

| Wert | Bedeutung |
|---|---|
| `auto` | Zrzavy Energy Monitor wählt eine verfügbare Quelle |
| `house_meter` | separate Shelly-Hausanschlussmessung |
| `solakon_one` | mit Solakon ONE verbundenes Meter beziehungsweise CT |

Ohne kompatibles Solakon-Meter sollte `house_meter` verwendet werden.

## Abschnitt `energy_balance`

Dieser additive Abschnitt steuert die validierte aktuelle Energiebilanz.
Fehlt er in einer bestehenden Konfiguration, werden rückwärtskompatible
Standardwerte ergänzt.

| Feld | Standard | Bedeutung |
|---|---:|---|
| `enabled` | `true` | neue aktuelle Bilanz berechnen |
| `maximum_measurement_age_seconds` | `30` | maximales Messwertalter |
| `maximum_source_skew_seconds` | `10` | maximaler Zeitversatz der Bilanzquellen |
| `allow_suspect_measurements` | `true` | warnungsbehaftete, nutzbare Werte zulassen |
| `allow_grid_fallback` | `true` | expliziten Hauszähler-Fallback zulassen |
| `allow_plant_fallback` | `true` | Solakon-AC als Anlagen-Fallback zulassen |
| `negative_house_power_tolerance_w` | `30` | Toleranz kleiner negativer Residuen |
| `short_window_average_seconds` | `0` | optionale kurze Mittelung; `0` deaktiviert |
| `persist_source_decisions` | `true` | sichere Auswahlmetadaten speichern |
| `source_priorities` | siehe unten | geordnete stabile Quellen-IDs je Metrik |

Standardprioritäten:

```json
{
  "grid_power": ["grid_meter_primary", "house_meter"],
  "plant_ac_power": ["solakon_meter", "solakon_one"],
  "pv_power": ["solakon_one"],
  "battery_charge_power": ["solakon_one"],
  "battery_discharge_power": ["solakon_one"],
  "battery_soc": ["solakon_one"]
}
```

Der `house_meter` ist für Netzleistung nur mit
`measurement_role: "grid_fallback"` berechtigt. Eine Unterverteilung wird
nicht als Hausanschlusspunkt verwendet. Ein Wert mit `0 W` ist gültig und
löst keinen Fallback aus. Abgelehnte, veraltete oder zeitlich nicht
vergleichbare Werte werden nicht zur Bilanz verrechnet.

## Abschnitt `grid_meter`

Dieser Abschnitt konfiguriert die führende, offizielle Referenz für
Netzbezug und Einspeisung. Unterstützte Adapter sind:

| Adapter | Lokaler Zugriff |
|---|---|
| `tasmota_http` | Tasmota `Status 10`, beispielsweise mit Hichi-Lesekopf |
| `shrdzm_rest` | SHRDZM REST über `/getLastData` |

Gemeinsame Felder:

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `enabled` | Boolean | `false` | offizielle Netzreferenz aktivieren |
| `adapter` | String | `tasmota_http` | konkreten read-only Adapter auswählen |
| `source_id` | String | `grid_meter_primary` | dauerhaft stabile Quellen-ID |
| `name` | String | `Offizieller Netzstromzähler` | sichtbare Bezeichnung |
| `host` | String | leer | lokale IP-Adresse oder Hostname |
| `port` | Integer | `80` | HTTP- beziehungsweise HTTPS-Port |
| `scheme` | String | `http` | `http` oder `https` |
| `timeout_seconds` | Integer | `3` | Timeout eines einzelnen Abrufs |
| `poll_interval_seconds` | Integer | `5` | separates Pollingintervall |
| `username` | String | leer | lokale Geräteauthentifizierung |
| `password` | String | leer | lokales Gerätekennwort |
| `direction_factor` | Integer | `1` | globale Vorzeichenkorrektur |
| `mapping` | Objekt | adapterabhängig | Zuordnung zu Tasmota-Pfaden oder OBIS-Schlüsseln |

SHRDZM-spezifische Felder unter `shrdzm_rest`:

| Feld | Standard | Bedeutung |
|---|---|---|
| `endpoint` | `/getLastData` | lokaler, ausschließlich lesender REST-Endpunkt |
| `authentication_mode` | `query` | `query`, `basic` oder `none` |
| `username_parameter` | `user` | Name des Query-Parameters für den Benutzer |
| `password_parameter` | `password` | Name des Query-Parameters für das Kennwort |
| `energy_total_unit` | `auto` | `auto`, `wh`, `kwh` oder `mwh` |

Beim Wechsel von einem unveränderten Tasmota-Standardmapping auf
`shrdzm_rest` setzt die Validierung automatisch das SHRDZM-OBIS-Profil.
Eigene Mappings und unbekannte Herstellerfelder bleiben erhalten.

Die vollständige Einrichtung und spätere Hardwareprüfung beschreibt
[SHRDZM als offizieller Netzstromzähler](shrdzm-grid-meter.md).

## Abschnitt `solakon_one`

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `enabled` | Boolean | `false` | Solakon-Abfrage aktivieren |
| `host` | String | leer | IP-Adresse oder lokaler Hostname |
| `port` | Integer | `502` | Modbus-TCP-Port |
| `device_id` | Integer | `1` | Modbus Unit-ID |
| `timeout_seconds` | Zahl | `5` | Netzwerk-Timeout in Sekunden |
| `simulation` | Boolean | `false` | simulierte Solakon-Werte verwenden |

Beispiel:

```json
"solakon_one": {
  "enabled": true,
  "host": "192.168.1.50",
  "port": 502,
  "device_id": 1,
  "timeout_seconds": 5,
  "simulation": false
}
```

## Abschnitt `house_meter`

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `enabled` | Boolean | `false` | Hausanschlussmessung aktivieren |
| `type` | String | `shelly_3em_gen1` | Gerätetyp |
| `host` | String | leer | IP-Adresse oder lokaler Hostname |
| `username` | String | leer | optionale lokale Authentifizierung |
| `password` | String | leer | optionales Kennwort |
| `timeout_seconds` | Zahl | `3` | HTTP-Timeout in Sekunden |
| `direction_factor` | Integer | `1` | Vorzeichen normalisieren |

Unterstützte Typen:

```text
shelly_3em_gen1
shelly_pro_3em
simulation
```

### Messrichtung

Zrzavy Energy Monitor erwartet:

- positiv = Netzbezug
- negativ = Einspeisung

Bei umgekehrter Anzeige:

```json
"direction_factor": -1
```

Die Korrektur erst nach einem nachvollziehbaren Test vornehmen, beispielsweise bei bekanntem Verbrauch ohne PV-Erzeugung und anschließend bei deutlicher Einspeisung.

### Netzleistungsvergleich mit dem offiziellen Zähler

Der Vergleich zwischen `grid_meter_primary` und `house_meter` darf nur
aktiviert werden, wenn beide Geräte dieselbe elektrische Position am gesamten
Hausanschluss messen. Zrzavy Energy Monitor vergleicht dann die Mittelwerte der
akzeptierten Messungen beider Quellen innerhalb des konfigurierten
Vergleichsfensters. Der offizielle Netzstromzähler bleibt auch bei einer
anhaltend großen Abweichung die führende Referenz.

`minimum_duration_seconds` bezeichnet die tatsächlich beobachtete Zeitspanne
zwischen dem ältesten und neuesten Messwert jeder Quelle. Das
`window_seconds`-Fenster sollte deshalb größer als die Mindestdauer sein.
Sind beide Werte gleich, kann bereits geringer Polling- oder Netzwerk-Jitter
den ältesten Messwert aus dem Fenster schieben und den Vergleich verzögern.

Für einen Tasmota-Zähler, der ungefähr alle zehn Sekunden einen neuen Messwert
liefert, ist folgende Pilotkonfiguration robust:

| Einstellung | Wert |
|---|---:|
| Vergleichsfenster | `60 s` |
| Mindestdauer | `30 s` |
| Mindestanzahl Messwerte | `4` |
| Mindestreferenz | `200 W` |
| Warnung absolut | `50 W` |
| Ablehnungsschwelle absolut | `250 W` |
| Warnung relativ | `10 %` |
| Ablehnungsschwelle relativ | `30 %` |

Vier Messwerte bei etwa zehn Sekunden Abstand decken die Zeitpunkte 0, 10, 20
und 30 Sekunden ab. Das 60-Sekunden-Fenster lässt zusätzlich Reserve für
Jitter oder einen verzögerten Abruf. Allgemein sollte die Mindestanzahl
mindestens
`ceil(Mindestdauer / effektives Messintervall) + 1` betragen.

## Abschnitt `solakon_meter`

Dieser Abschnitt beschreibt die unabhängige AC-Messung am Ausgang der Solakon-Anlage.

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `enabled` | Boolean | `false` | Messung aktivieren |
| `type` | String | `shelly_pm_mini_gen3` | Gerätetyp |
| `host` | String | leer | IP-Adresse oder lokaler Hostname |
| `username` | String | leer | optionale lokale Authentifizierung |
| `password` | String | leer | optionales Kennwort |
| `timeout_seconds` | Zahl | `3` | HTTP-Timeout |
| `direction_factor` | Integer | `1` | Vorzeichen normalisieren |

Unterstützte Typen:

```text
shelly_pm_mini_gen3
simulation
```

## Abschnitt `plant_meter`

Der optionale `plant_meter` unterstützt den Shelly Plug M Gen3 als lokale,
read-only Messquelle zwischen Solakon-AC-Ausgang und Steckdose beziehungsweise
Hausnetz. Er ist standardmäßig deaktiviert und fällt bei fehlenden oder
abgelehnten Werten auf Solakon ONE AC zurück.

| Feld | Typ | Standard | Bedeutung |
|---|---|---:|---|
| `enabled` | Boolean | `false` | Quelle aktivieren |
| `type` | String | `shelly_plug_m_gen3` | Gerätetyp |
| `host` | String | leer | lokale IP oder Hostname |
| `component_id` | Integer | `0` | RPC-Komponente, normalerweise `switch:0` |
| `timeout_seconds` | Zahl | `3` | begrenzter Read-only-Timeout |
| `direction_factor` | Integer | `1` | Vorzeichenkorrektur nach Hardwaretest |

Gelesen wird ausschließlich `Switch.GetStatus?id=<component_id>`. Das Relais,
die Zähler und die Gerätekonfiguration werden niemals verändert. Ein explizites
`apower: 0` ist gültig; fehlendes oder ungültiges `apower` ist unavailable.

## Abschnitt `persistence.retention`

Die Aufbewahrung ist standardmäßig deaktiviert und arbeitet bei Aktivierung
begrenzt. Die Werte werden beim Start aus diesem Abschnitt gelesen:

| Feld | Bedeutung |
|---|---|
| `enabled` | Aufbewahrung aktivieren |
| `raw_high_resolution_days` | Aufbewahrungsdauer roher hochauflösender Werte |
| `validation_events_days` | Aufbewahrungsdauer von Validierungsereignissen |
| `source_selection_events_days` | Aufbewahrungsdauer von Quellenentscheidungen |
| `batch_rows` | Maximale Zeilen je begrenztem Bereinigungslauf |

Die Konfigurationsvorlage enthält außerdem die folgenden Blatt-Schlüssel; sie
werden hier bewusst als Referenzschlüssel und nicht als Wertprüfung aufgeführt:

`project_name`, `site_name`, `poll_interval_seconds`, `auto_start_collection`,
`bind_host`, `port`, `open_browser`, `solar_power_source`, `grid_power_source`,
`enabled`, `host`, `port`, `device_id`, `timeout_seconds`, `simulation`, `type`,
`username`, `password`, `direction_factor`, `measurement_role`, `adapter`,
`source_id`, `name`, `scheme`, `mapping`, `grid_power_w`, `grid_import_power_w`,
`grid_export_power_w`, `grid_import_total_kwh`, `grid_export_total_kwh`,
`frequency_hz`, `phase_voltage_l1_v`, `phase_voltage_l2_v`,
`phase_voltage_l3_v`, `phase_current_l1_a`, `phase_current_l2_a`,
`phase_current_l3_a`, `phase_power_l1_w`, `phase_power_l2_w`,
`phase_power_l3_w`, `shrdzm_rest`, `endpoint`, `authentication_mode`,
`username_parameter`, `password_parameter`, `energy_total_unit`,
`raw_high_resolution_days`, `validation_events_days`,
`source_selection_events_days`, `batch_rows`, `maximum_measurement_age_seconds`,
`maximum_source_skew_seconds`, `allow_suspect_measurements`,
`allow_grid_fallback`, `allow_plant_fallback`,
`negative_house_power_tolerance_w`, `short_window_average_seconds`,
`persist_source_decisions`, `source_priorities`, `grid_power`, `plant_ac_power`,
`pv_power`, `battery_power`, `battery_charge_power`, `battery_discharge_power`,
`battery_soc`.

## Konfiguration aktivieren

Nach einer manuellen Änderung:

```bash
sudo systemctl restart zrzavy-energy-monitor.service
sudo systemctl status zrzavy-energy-monitor.service
```

Danach:

```bash
curl --fail http://127.0.0.1:8787/api/health
```

## Sichere Weitergabe einer Konfiguration

Vor dem Teilen mindestens entfernen oder ersetzen:

- `username`
- `password`
- öffentliche Hostnamen
- interne IP-Adressen, sofern nicht für die Analyse erforderlich
- Seriennummern
- Standortnamen

Beispiel für Platzhalter:

```json
"host": "<SOLAKON-IP>",
"username": "<BENUTZER>",
"password": "<ENTFERNT>"
```
