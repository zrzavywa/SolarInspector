# Konfigurationsreferenz

SolarInspector verwendet eine JSON-Konfiguration. Die Vorlage befindet sich unter:

```text
app/config.example.json
```

In einer 4.1-Referenzinstallation liegt die persistente Konfiguration unter:

```text
/etc/solarinspector/config.json
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
python3 -m json.tool /etc/solarinspector/config.json >/dev/null
```

## Vollständiges Beispiel

```json
{
  "general": {
    "project_name": "SolarInspector",
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
    "timeout": 5,
    "simulation": false
  },
  "house_meter": {
    "enabled": false,
    "type": "shelly_3em_gen1",
    "host": "",
    "username": "",
    "password": "",
    "timeout": 3,
    "direction_factor": 1
  },
  "solakon_meter": {
    "enabled": false,
    "type": "shelly_pm_mini_gen3",
    "host": "",
    "username": "",
    "password": "",
    "timeout": 3,
    "direction_factor": 1
  }
}
```

## Abschnitt `general`

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `project_name` | String | `SolarInspector` | Name der Installation |
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
| `auto` | SolarInspector wählt eine verfügbare Quelle |
| `shelly_ac` | unabhängige AC-Messung am Solakon-Ausgang |
| `solakon_ac` | AC-Leistung aus der Solakon ONE |
| `solakon_pv` | PV-Eingangsleistung aus der Solakon ONE |

AC- und PV-Leistung sind nicht identisch. Für Wirkungsgrad- oder Verlustvergleiche müssen Quelle und Bedeutung eindeutig angegeben werden.

### `grid_power_source`

| Wert | Bedeutung |
|---|---|
| `auto` | SolarInspector wählt eine verfügbare Quelle |
| `house_meter` | separate Shelly-Hausanschlussmessung |
| `solakon_one` | mit Solakon ONE verbundenes Meter beziehungsweise CT |

Ohne kompatibles Solakon-Meter sollte `house_meter` verwendet werden.

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
| `timeout` | Zahl | `5` | Netzwerk-Timeout in Sekunden |
| `simulation` | Boolean | `false` | simulierte Solakon-Werte verwenden |

Beispiel:

```json
"solakon_one": {
  "enabled": true,
  "host": "192.168.1.50",
  "port": 502,
  "device_id": 1,
  "timeout": 5,
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
| `timeout` | Zahl | `3` | HTTP-Timeout in Sekunden |
| `direction_factor` | Integer | `1` | Vorzeichen normalisieren |

Unterstützte Typen:

```text
shelly_3em_gen1
shelly_pro_3em
simulation
```

### Messrichtung

SolarInspector erwartet:

- positiv = Netzbezug
- negativ = Einspeisung

Bei umgekehrter Anzeige:

```json
"direction_factor": -1
```

Die Korrektur erst nach einem nachvollziehbaren Test vornehmen, beispielsweise bei bekanntem Verbrauch ohne PV-Erzeugung und anschließend bei deutlicher Einspeisung.

## Abschnitt `solakon_meter`

Dieser Abschnitt beschreibt die unabhängige AC-Messung am Ausgang der Solakon-Anlage.

| Feld | Typ | Standard | Bedeutung |
|---|---:|---:|---|
| `enabled` | Boolean | `false` | Messung aktivieren |
| `type` | String | `shelly_pm_mini_gen3` | Gerätetyp |
| `host` | String | leer | IP-Adresse oder lokaler Hostname |
| `username` | String | leer | optionale lokale Authentifizierung |
| `password` | String | leer | optionales Kennwort |
| `timeout` | Zahl | `3` | HTTP-Timeout |
| `direction_factor` | Integer | `1` | Vorzeichen normalisieren |

Unterstützte Typen:

```text
shelly_pm_mini_gen3
simulation
```

## Konfiguration aktivieren

Nach einer manuellen Änderung:

```bash
sudo systemctl restart solarinspector.service
sudo systemctl status solarinspector.service
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
