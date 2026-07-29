# API-Referenz für Version 4.5

## Status und Stabilitätszusage

Zrzavy Energy Monitor 4.5 registriert 20 explizite `/api`-Routen. Die
Endpunkte dienen primär der mitgelieferten Weboberfläche und dem lokalen
Betrieb. Sie sind unversioniert und nicht als dauerhaft stabile öffentliche
Integrations-API garantiert. Flask stellt für GET-Routen zusätzlich `HEAD` und
für alle Routen `OPTIONS` bereit; diese automatisch erzeugten Methoden sind
keine eigenständigen fachlichen API-Verträge.

Die Klassen in dieser Referenz bedeuten:

- `integration_read`: lesend und eingeschränkt für lokale Integrationen
  geeignet;
- `ui_internal_read`: lesende, unversionierte Schnittstelle der
  Weboberfläche;
- `operational_write`: Aufruf mit Auswirkung auf Collector oder
  Updatezustand;
- `diagnostic_network`: Diagnose mit Zugriff auf ein konfiguriertes lokales
  Gerät;
- `destructive`: Löschung persistierter Daten;
- `file_export`: Download potenziell sensibler Mess- oder Diagnosedaten.

## Basis-URL, Transport und Zugriffsschutz

Die synthetische Basis-URL dieser Referenz ist
`http://127.0.0.1:8787`. Die Anwendung stellt selbst keine TLS-Terminierung
bereit. Sie sollte nur vom lokalen Rechner, in einem vertrauenswürdigen lokalen
Netz oder über einen abgesicherten VPN-Zugang erreichbar sein. Eine direkte
ungeschützte Veröffentlichung im Internet wird nicht empfohlen.

Die Implementierung der Version 4.5 prüft an den hier dokumentierten
API-Routen weder Anmeldung noch Benutzerberechtigung. Für die POST-Routen ist
keine CSRF-Prüfung implementiert. Der Flask-Session-Schlüssel ist kein
API-Zugriffsschutz. Jeder Client mit Netzwerkzugriff kann daher auch
zustandsändernde, netzwerkaktive und destruktive Routen aufrufen.

## Gemeinsame Datentypen, Zeitstempel, Nullwerte und Einheiten

- JSON ist das Antwortformat, sofern nicht ausdrücklich CSV genannt wird.
  POST-Routen erwarten entweder keinen Body oder ein JSON-Objekt.
- ISO-8601-Zeitstempel können einen UTC-Offset wie `+02:00` oder `+00:00`
  enthalten. Epoch-Felder sind Sekunden seit Unix-Epoch.
- `null` bedeutet „nicht verfügbar“. `0` und `0.0` sind gültige Werte und
  dürfen nicht wie fehlende Werte behandelt werden.
- Leistung wird in Watt (`W`), Energie in Wattstunden (`Wh`) oder
  Kilowattstunden (`kWh`), Spannung in Volt (`V`), Strom in Ampere (`A`),
  Frequenz in Hertz (`Hz`) und Anteile in Prozent (`%`) angegeben.
- Bei signierter Netzleistung bedeutet ein positiver Wert Netzbezug und ein
  negativer Wert Einspeisung. Getrennte Import- und Exportfelder sind
  nichtnegative Beträge.
- UI-interne Antworten können innerhalb der 4.x-Reihe zusätzliche Felder
  erhalten. Clients müssen unbekannte Felder tolerieren.

## Endpunktübersicht

| Methode und Pfad | Klasse | Zielgruppe | Seiteneffekt |
|---|---|---|---|
| `POST /api/start` | `operational_write` | lokaler Betrieb | startet den Collector |
| `POST /api/stop` | `operational_write` | lokaler Betrieb | stoppt den Collector |
| `POST /api/collect-once` | `operational_write` | lokale Diagnose | erfasst und persistiert einen Zyklus |
| `GET /api/status` | `ui_internal_read` | Weboberfläche | keiner |
| `GET /api/health` | `integration_read` | lokales Monitoring | keiner |
| `GET /api/live` | `integration_read` | Weboberfläche, lokale Integration | keiner |
| `GET /api/dashboard` | `ui_internal_read` | Weboberfläche | keiner |
| `GET /api/validation/events` | `ui_internal_read` | Weboberfläche | keiner |
| `GET /api/validation/summary` | `ui_internal_read` | Weboberfläche | keiner |
| `GET /api/phases/live` | `ui_internal_read` | Weboberfläche | keiner |
| `GET /api/phases/dashboard` | `ui_internal_read` | Weboberfläche | keiner |
| `POST /api/test-device/<role>` | `diagnostic_network` | lokale Einrichtung | lokaler Gerätezugriff |
| `POST /api/test-solakon-one` | `diagnostic_network` | lokale Einrichtung | lokaler Modbus-Zugriff |
| `GET /api/export.csv` | `file_export` | lokaler Datenexport | liest potenziell sensible Daten |
| `POST /api/delete-all` | `destructive` | lokaler Betrieb | löscht persistierte Messdaten |
| `GET /api/system/version` | `integration_read` | lokales Monitoring | keiner |
| `GET /api/update/check` | `operational_write` | lokale Updateverwaltung | GitHub-Zugriff, Updateprüfung |
| `GET /api/update/status` | `ui_internal_read` | Weboberfläche | liest lokalen Updatezustand |
| `POST /api/update/download` | `operational_write` | lokale Updateverwaltung | Netzwerk-, Datei- und Statusschreibzugriffe |
| `POST /api/update/install` | `operational_write` | lokale Updateverwaltung | schreibt Installationsanforderung |

## Collector-Steuerung

### `POST /api/start`

- **Klassifikation, Zweck und Stabilität:** `operational_write` für den
  lokalen Betrieb; startet die zyklische Datenerfassung; unversioniert und
  intern.
- **Parameter:** keine Pfad- oder Queryparameter.
- **Request:** kein Content-Type und kein Body erforderlich.
- **Erfolg:** `200`; JSON mit `ok: true`, `started` und `status`. `started`
  ist `false`, wenn der Collector bereits läuft.
- **Fehler:** `400`, wenn der Start fehlschlägt und der Collector nicht
  läuft; JSON mit `ok: false`, `started: false`, `error` und `status`.
- **Einheiten und Vorzeichen:** im eingebetteten Status nicht fest zugesagt;
  Zeitstempel sind ISO 8601 oder `null`.
- **Seiteneffekt und Sicherheit:** startet Hintergrundabfragen lokaler Geräte
  und spätere Persistenz. Es gibt keine API-Authentifizierung,
  Autorisierung oder CSRF-Prüfung.
- **Synthetisches Beispiel:**

```http
POST /api/start HTTP/1.1
Host: 127.0.0.1:8787

HTTP/1.1 200 OK
Content-Type: application/json

{"ok":true,"started":true,"status":{"running":true,"started_at":"2026-07-27T10:00:00+02:00","cycles":0,"last_error":"","last_sample":null}}
```

### `POST /api/stop`

- **Klassifikation, Zweck und Stabilität:** `operational_write`; stoppt die
  zyklische Erfassung; unversioniert und intern.
- **Parameter:** keine Pfad- oder Queryparameter.
- **Request:** kein Content-Type und kein Body erforderlich.
- **Erfolg:** `200`; `{"ok":true,"stopped":<boolean>,"status":{...}}`.
  `stopped` kann `false` sein, wenn nichts lief.
- **Fehler:** kein eigener fachlicher Fehlerstatus implementiert; unerwartete
  Ausnahmen fallen auf Flasks `500`-Fehlerbehandlung zurück.
- **Einheiten und Vorzeichen:** nicht anwendbar.
- **Seiteneffekt und Sicherheit:** beendet Collector-Abfragen; keine
  Authentifizierung, Autorisierung oder CSRF-Prüfung.
- **Synthetisches Beispiel:** `POST /api/stop` liefert
  `{"ok":true,"stopped":true,"status":{"running":false}}`.

### `POST /api/collect-once`

- **Klassifikation, Zweck und Stabilität:** `operational_write`; führt einen
  vollständigen Erfassungszyklus aus; unversioniert und intern.
- **Parameter:** keine Pfad- oder Queryparameter.
- **Request:** kein Content-Type und kein Body erforderlich.
- **Erfolg:** `200`; `{"ok":true,"sample":{...}}`. Das Sample kann
  hersteller- und konfigurationsabhängige Messfelder enthalten.
- **Fehler:** `500`; `{"ok":false,"error":"..."}` bei einem Fehler der
  Erfassung oder Persistenz.
- **Einheiten und Vorzeichen:** Feldsuffixe wie `_w`, `_wh`, `_kwh`, `_v`,
  `_a`, `_hz` und `_pct` geben die Einheit an; signierte Netzleistung ist
  positiv bei Bezug und negativ bei Einspeisung.
- **Seiteneffekt und Sicherheit:** kontaktiert aktivierte Geräte und
  persistiert bei Erfolg Mess- und Diagnosedaten. Keine Authentifizierung,
  Autorisierung oder CSRF-Prüfung.
- **Synthetisches Beispiel:** `POST /api/collect-once` liefert
  `{"ok":true,"sample":{"id":9,"solar_power_w":410.0}}`.

## Status, Healthcheck und Version

### `GET /api/status`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; aktueller
  Collector-Zustand für die Weboberfläche; unversioniert.
- **Parameter und Request:** keine Parameter; kein Request-Body.
- **Erfolg:** `200`; Collector-Status mit mindestens `running`,
  `started_at`, `cycles`, `last_error` und `last_sample`.
- **Fehler:** kein fachlicher Fehlerstatus; unerwartete Ausnahmen ergeben
  `500`.
- **Einheiten und Vorzeichen:** `cycles` ist eine Anzahl; `started_at` ist
  ISO 8601 oder `null`; Einheiten des optionalen `last_sample` folgen den
  Feldsuffixen.
- **Seiteneffekt und Sicherheit:** lesend, kann Betriebs- und Fehlerdetails
  offenlegen; kein Zugriffsschutz.
- **Synthetisches Beispiel:** `GET /api/status` liefert
  `{"running":true,"started_at":"2026-07-27T10:00:00+02:00","cycles":4,"last_error":"","last_sample":null}`.

### `GET /api/health`

- **Klassifikation, Zweck und Stabilität:** `integration_read`; einfacher
  Prozess-, Datenbank- und Web-Healthcheck; unversioniert, aber für lokales
  Monitoring geeignet.
- **Parameter und Request:** keine Parameter; kein Request-Body.
- **Erfolg:** `200`; Felder `status`, `version`, `config_schema`,
  `database`, `web`, `product_name`, `product_id` und
  `product_description`.
- **Fehler:** kein degradierter fachlicher Status implementiert; ein
  unerwarteter Serverfehler ergibt `500`.
- **Einheiten und Vorzeichen:** nicht anwendbar.
- **Seiteneffekt und Sicherheit:** lesend; prüft keine externen Messgeräte
  und legt Versionsinformationen ohne Zugriffsschutz offen.
- **Synthetisches Beispiel:**

```json
{"status":"ok","version":"4.5.2","config_schema":5,"database":"ok","web":"ok","product_name":"Zrzavy Energy Monitor","product_id":"zrzavy-energy-monitor","product_description":"Open-source home energy monitoring and validation"}
```

### `GET /api/system/version`

- **Klassifikation, Zweck und Stabilität:** `integration_read`; Produkt-,
  Versions- und Konfigurationsschemainformation; unversioniert.
- **Parameter und Request:** keine Parameter; kein Request-Body.
- **Erfolg:** `200`; `product`, `product_name`, `product_id`,
  `product_description`, `version` und `config_schema`.
- **Fehler:** kein fachlicher Fehlerstatus; unerwartete Ausnahmen ergeben
  `500`.
- **Einheiten, Seiteneffekte und Sicherheit:** keine Einheiten, lesend;
  Versionsinformationen sind ohne Zugriffsschutz sichtbar.
- **Synthetisches Beispiel:** `GET /api/system/version` liefert
  `{"product":"Zrzavy Energy Monitor","product_name":"Zrzavy Energy Monitor","product_id":"zrzavy-energy-monitor","product_description":"Open-source home energy monitoring and validation","version":"4.5.2","config_schema":5}`.

## Live- und Dashboard-Daten

### `GET /api/live`

- **Klassifikation, Zweck und Stabilität:** `integration_read`; aktuelle
  persistierte Messung, Collector, offizieller Zähler, aktive Quelle und
  Energiebilanz; unversioniert und erweiterbar.
- **Parameter und Request:** keine Parameter; kein Request-Body.
- **Erfolg:** `200`; Top-Level-Felder `latest`, `collector`, `grid_meter`,
  `energy_balance` und `active_sources`.
- **Fehler:** kein fachlicher Fehlerstatus; Daten fehlen als `null`;
  unerwartete Ausnahmen ergeben `500`.
- **Einheiten und Vorzeichen:** `age_seconds` in Sekunden; Leistungsfelder
  in `W`, Summenzähler in `kWh`, SOC und Raten in `%`. `grid_power_w` ist
  positiv bei Bezug und negativ bei Einspeisung. `null` und `0.0` bleiben
  unterscheidbar. `calculated_at`, `measured_at` und `last_update` sind
  ISO-8601-Zeitstempel.
- **Seiteneffekt und Sicherheit:** lesend; Mess-, Fehler-, Quellen- und
  Metadaten können standortbezogen und sensibel sein; kein Zugriffsschutz.
- **Synthetisches Beispiel:**

```json
{
  "latest": null,
  "collector": {"running": true, "cycles": 2},
  "grid_meter": {
    "source_id": "grid_meter_primary",
    "status": "online",
    "power_w": -241.0,
    "import_power_w": 0.0,
    "export_power_w": 241.0,
    "import_total_kwh": 3456.782,
    "export_total_kwh": 512.118,
    "age_seconds": 5
  },
  "active_sources": {"grid_power": "grid_meter_primary", "grid_power_label": "Offizieller Netzstromzähler"},
  "energy_balance": {
    "calculated_at": "2026-07-27T10:00:00+02:00",
    "age_seconds": 4,
    "quality": "calculated",
    "values": {"house_power_w": 1500.0, "grid_power_w": 900.0, "grid_export_power_w": 0.0},
    "sources": {},
    "fallback_used": false,
    "findings": []
  }
}
```

`energy_balance.values` kann außerdem Anlagen-, PV-, Batterie-, SOC-,
Eigenverbrauchs-, Autarkie- und Residualfelder enthalten. Quellen- und
Finding-Strukturen sind erweiterbar.

### `GET /api/dashboard`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; aggregierte
  Dashboard-Zeitreihe; unversioniert.
- **Pfadparameter:** keine.
- **Queryparameter:** `period` mit Default `day` und erlaubten Werten `day`,
  `week`, `year`; andere Werte fallen auf `day` zurück. `anchor` ist ein
  Datum `YYYY-MM-DD`; fehlende oder ungültige Werte fallen auf das aktuelle
  lokale Datum zurück.
- **Request:** kein Body.
- **Erfolg:** `200`; mindestens `period`, `anchor`, `title`, `labels`,
  Zeitreihen und `kpi`. Ein leerer Zeitraum enthält eine Sample-Anzahl von
  `0`.
- **Fehler:** keine fachlichen `4xx` für ungültige Parameter; unerwartete
  Fehler ergeben `500`.
- **Einheiten und Vorzeichen:** Leistung `W`, Energie `Wh` beziehungsweise
  `kWh` gemäß Feldsuffix; lokale Datumsgrenzen und ISO-Datum für `anchor`;
  Netzvorzeichen wie oben.
- **Seiteneffekt und Sicherheit:** lesender Zugriff auf aggregierte
  Messhistorie, ohne Zugriffsschutz.
- **Synthetisches Beispiel:** `GET
  /api/dashboard?period=day&anchor=2026-07-27` liefert unter anderem
  `{"period":"day","anchor":"2026-07-27","labels":["00:00"],"kpi":{"sample_count":0}}`.

## Validierung und Phasen

### `GET /api/validation/events`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; gefilterte
  persistierte Validierungsereignisse; unversioniert.
- **Queryparameter:** `limit` Default `100`, begrenzt auf `1..500`;
  `hours` Default `24`, begrenzt auf `0.25..8760`; `source` optional;
  `decision` wird nur für `accept_with_warning` oder `reject` angewendet;
  `severity` nur für `warning` oder `error`. Ungültige Zahlen verwenden den
  Default, Werte außerhalb des Bereichs werden geklemmt. Unbekannte
  Auswahlwerte entfernen den betreffenden Filter.
- **Request:** kein Body.
- **Erfolg:** `200`; `window_hours`, normalisierte `filters` und `events`.
  Ein Event enthält Zeitpunkte, Dauer, Quelle, Rolle, Metrik, Einheit, Regel,
  Code, Schwere, Entscheidung, Qualität, Begründung, Werte, sichere Details
  und Häufigkeiten.
- **Fehler:** keine fachlichen `4xx` für ungültige Filter; Datenbankfehler
  ergeben `500`.
- **Einheiten und Vorzeichen:** `hours` in Stunden,
  `duration_seconds`/Epoch-Felder in Sekunden; `unit` benennt die Einheit des
  Werts; Vorzeichen folgt der jeweiligen Metrik.
- **Seiteneffekt und Sicherheit:** lesend; enthält Diagnosewerte. Persistierte
  Details werden vorab bereinigt, sind aber dennoch potenziell sensibel.
- **Synthetisches Beispiel:** `GET
  /api/validation/events?hours=24&limit=10&severity=warning` liefert
  `{"window_hours":24.0,"filters":{"source_id":null,"decision":null,"severity":"warning","limit":10},"events":[]}`.

### `GET /api/validation/summary`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; betriebliche
  Zusammenfassung und neueste Ereignisse; unversioniert.
- **Queryparameter:** `hours` wie bei `/api/validation/events`; `limit`
  Default `8`, begrenzt auf `1..50`.
- **Request:** kein Body.
- **Erfolg:** `200`; `enabled`, `status` (`disabled`, `error`, `warning`
  oder `ok`), `window_hours`, aggregierte `summary`, `sources` und
  `recent_events`.
- **Fehler:** keine fachlichen `4xx` für ungültige Parameter;
  Datenbankfehler ergeben `500`.
- **Einheiten:** Zeitfenster in Stunden, Epoch-Felder in Sekunden,
  Häufigkeiten als Anzahlen; neueste lokale Zeit als ISO-8601-Text oder
  `null`.
- **Seiteneffekt und Sicherheit:** lesend; potenziell sensible Diagnose- und
  Quelleninformationen, ohne Zugriffsschutz.
- **Synthetisches Beispiel:** `GET /api/validation/summary` liefert
  `{"enabled":false,"status":"disabled","window_hours":24.0,"summary":{"event_group_count":0,"occurrence_count":0},"sources":[],"recent_events":[]}`.

### `GET /api/phases/live`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; neuester
  persistierter Phasensnapshot einer Quelle; unversioniert.
- **Queryparameter:** `source` Default `house_meter`; Leerwert fällt auf den
  Default zurück, sonst wird der getrimmte Wert auf 120 Zeichen begrenzt.
- **Request:** kein Body.
- **Erfolg:** `200`; `source_id` und `latest`. `latest` ist `null` oder
  enthält Sample-, Quellen-, Rollen-, Status- und Zeitfelder, `phases` für
  `l1`, `l2`, `l3`, `analysis` und `metadata`.
- **Fehler:** kein fachlicher Fehlerstatus; Datenbankfehler ergeben `500`.
- **Einheiten und Vorzeichen:** pro Phase `power_w`, `voltage_v`,
  `current_a`, dimensionsloser `power_factor`; Analyse in `W` und `%`.
  Zeitstempel sind ISO 8601, `ts_epoch` Sekunden. `null` bleibt von `0.0`
  unterscheidbar.
- **Seiteneffekt und Sicherheit:** lesend; Mess- und Gerätemetadaten können
  sensibel sein; kein Zugriffsschutz.
- **Synthetisches Beispiel:** `GET /api/phases/live?source=house_meter`
  liefert `{"source_id":"house_meter","latest":null}`.

### `GET /api/phases/dashboard`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; gebuckette
  Phasenmittelwerte; unversioniert.
- **Queryparameter:** `period` Default `day`, erlaubt `day`, `week`, `year`,
  sonst Fallback `day`; `anchor` wie beim Dashboard; `source` Default
  `house_meter` und Normalisierung wie bei `/api/phases/live`.
- **Request:** kein Body.
- **Erfolg:** `200`; `period`, `anchor`, `title`, `source_id`, `labels`,
  `series` mit `l1_power_w` bis `l3_power_w` sowie `summary` mit Sample- und
  Verdachtsanzahl, Phasenmitteln, maximalem Spread und letztem Sample.
- **Fehler:** keine fachlichen `4xx` für ungültige Parameter;
  Datenbankfehler ergeben `500`.
- **Einheiten und Vorzeichen:** Leistung und Spread in `W`; fehlende
  Bucketwerte `null`; `anchor` als ISO-Datum.
- **Seiteneffekt und Sicherheit:** lesender Historienzugriff ohne
  Zugriffsschutz.
- **Synthetisches Beispiel:** `GET
  /api/phases/dashboard?period=day&anchor=2026-07-27` liefert
  `{"period":"day","anchor":"2026-07-27","source_id":"house_meter","labels":[],"series":{"l1_power_w":[]},"summary":{"sample_count":0}}`.

## Gerätediagnose

Diese Endpunkte führen reale lokale Netzwerkzugriffe aus, sofern keine
Simulation konfiguriert ist. Request-Daten können Geräteadressen und
Zugangsdaten enthalten. Solche Daten dürfen nicht protokolliert, in Tickets
kopiert oder in Beispiele übernommen werden. Die Tests lesen Geräte nur; die
API selbst besitzt jedoch keinen Zugriffsschutz.

### `POST /api/test-device/<role>`

- **Klassifikation, Zweck und Stabilität:** `diagnostic_network`; testet
  `house_meter`, `solakon_meter` oder `grid_meter`; unversioniert und intern.
- **Pfadparameter:** `role` mit genau diesen drei unterstützten Werten.
- **Queryparameter:** keine.
- **Request:** optionales JSON-Objekt. Für Shelly-Rollen: `enabled` Default
  `true`, `type` aus Konfiguration, `host` Default leer, `username` und
  `password` Default leer, `timeout_seconds` Default `3`,
  `direction_factor` Default `1`; beim `house_meter` außerdem
  `measurement_role` und `phase_direction` aus Konfiguration. Für
  `grid_meter`: zusätzlich `adapter`, `source_id`, `name`, `port` Default
  `80`, `scheme` Default `http`, `poll_interval_seconds` Default `5`,
  `shrdzm_rest` und `mapping`. Ein leeres Objekt verwendet die aktuelle
  Rollenkonfiguration.
- **Erfolg:** `200`; Shelly-Rollen liefern
  `{"ok":true,"reading":{...}}`; der Grid-Meter-Test liefert
  `{"ok":true,"diagnostic":{...}}` mit begrenzten Feldpfaden,
  Mappingstatus, Einheiten und bereinigten Werten.
- **Fehler:** `404` bei unbekannter Rolle; `400` bei deaktivierter oder
  ungültiger Konfiguration; `502` bei Geräte-, Transport- oder unbrauchbarer
  Snapshot-Antwort. Form: `{"ok":false,"error":"..."}`, beim Grid-Meter
  gegebenenfalls zusätzlich `diagnostic`.
- **Einheiten und Vorzeichen:** Reading-Felder nach Suffix; Grid-Diagnose
  nennt `W` und `kWh` explizit. Signierte Netzleistung positiv bei Bezug,
  negativ bei Einspeisung.
- **Seiteneffekt und Sicherheit:** die übergebene Konfiguration wird nur in
  der Request-Verarbeitung verwendet und nicht gespeichert; es erfolgt ein
  lokaler Netzwerkzugriff. Ein nichtleeres Grid-Meter-Passwort ersetzt das
  Laufzeitpasswort für den Test, wird aber nicht in der Antwort ausgegeben.
- **Synthetisches Beispiel:**

```http
POST /api/test-device/house_meter HTTP/1.1
Host: 127.0.0.1:8787
Content-Type: application/json

{"enabled":true,"type":"simulation","direction_factor":1}
```

Eine synthetische Erfolgsantwort ist
`{"ok":true,"reading":{"power_w":123.0,"voltage_v":230.0,"source":"Simulation"}}`.

### `POST /api/test-solakon-one`

- **Klassifikation, Zweck und Stabilität:** `diagnostic_network`; testet die
  read-only Modbus-TCP-Verbindung zur Solakon ONE; unversioniert und intern.
- **Parameter:** keine Pfad- oder Queryparameter.
- **Request:** optionales JSON-Objekt mit `enabled` Default `true`, `host`
  Default leer, `port` Default `502`, `device_id` Default `1`,
  `timeout_seconds` Default `5` und `simulation` Default `false`.
- **Erfolg:** `200`; `{"ok":true,"reading":{...}}`.
- **Fehler:** `400` bei deaktiviertem Gerät; `502` für Validierungs-,
  Verbindungs- oder Lesefehler; Form `{"ok":false,"error":"..."}`.
- **Einheiten und Vorzeichen:** Reading-Felder nach Suffix, darunter `W`,
  `%` und `Hz`; `meter_power_w` folgt der Netzvorzeichenkonvention.
- **Seiteneffekt und Sicherheit:** read-only Geräteabfrage, keine
  Konfigurationspersistenz. Der Aufruf kann eine Verbindung zu einem lokalen
  Host auslösen und besitzt keine API-Zugriffskontrolle.
- **Synthetisches Beispiel:** `POST /api/test-solakon-one` mit
  `{"enabled":true,"simulation":true}` liefert beispielsweise
  `{"ok":true,"reading":{"status":"Betrieb","total_pv_power_w":500.0}}`.

## CSV-Export

### `GET /api/export.csv`

- **Klassifikation, Zweck und Stabilität:** `file_export`; lädt historische
  Mess- oder Diagnosedaten als semikolongetrennte UTF-8-CSV; unversioniert.
- **Queryparameter:** `from` und `to` sind inklusive lokale Datumswerte
  `YYYY-MM-DD`; fehlende oder ungültige Werte fallen jeweils auf das aktuelle
  lokale Datum zurück. `dataset` Default `legacy`. Weitere Werte:
  `measurements`, `phases`, `grid`, `energy_balance`,
  `validation_events`, `source_selection_events`. `maximum_rows` Default
  `50000`, erlaubt `1..50000`. `metric` ist für `measurements` Pflicht und
  für Diagnose-/Auswahldatasets optional; `source_id` ist für Messungen und
  Validierungsereignisse optional.
- **Request:** kein Body.
- **Erfolg:** `200`; `Content-Type` beginnt mit
  `text/csv; charset=utf-8`; `Content-Disposition` enthält einen
  `zrzavy-energy-monitor_...csv`-Dateinamen. `legacy` exportiert das
  historische breite Schema. Die anderen Datasets verwenden explizite
  Einheiten in Spaltennamen und ein hartes Zeilenlimit.
- **Fehler:** `400` als JSON `{"error":"..."}` bei unbekanntem Dataset,
  fehlender Pflichtmetrik, ungültigem Limit oder ungültigem Bereich.
  Unerwartete Datenbankfehler ergeben `500`.
- **Einheiten, Zeit und Nullwerte:** Spaltensuffixe benennen die Einheit.
  Additive Datasets verwenden UTC-Zeitspalten; Legacy-Zeit ist lokal.
  Fehlende Werte werden leere CSV-Felder, echte Nullen bleiben `0.0`.
- **Seiteneffekt und Sicherheit:** ausschließlich lesend, aber Exportdateien
  können Messhistorie, Quellen, Betriebszustände und Diagnosen enthalten.
  Additive Exporte schließen unter anderem Rohantworten, Metadaten-JSON,
  verworfene Kandidaten, Seriennummern, Adressen und Zugangsdaten aus und
  entschärfen Tabellenformel-Präfixe. Der Legacy-Export kann hingegen
  historische Gerätefelder wie `solakon_serial` enthalten. Dateien müssen
  daher als potenziell sensibel geschützt werden.
- **Synthetisches Beispiel:**

```http
GET /api/export.csv?from=2026-07-27&to=2026-07-27&dataset=measurements&metric=grid_power&maximum_rows=100 HTTP/1.1
Host: 127.0.0.1:8787
```

Eine synthetische Antwort beginnt mit
`measured_at_utc;received_at_utc;source_id;role;metric;value;unit;quality;device_status`.

## Datenlöschung

### `POST /api/delete-all`

- **Klassifikation, Zweck und Stabilität:** `destructive`; löscht die von der
  Datenbankwartung erfassten persistierten Mess- und zugehörigen
  Detail-/Diagnosedaten; unversioniert und intern.
- **Parameter und Request:** keine Parameter; kein Body erforderlich.
- **Erfolg:** `200`; `{"ok":true}`.
- **Fehler:** kein fachlicher Fehlerstatus; eine Ausnahme beim Stoppen,
  Löschen oder Zurücksetzen ergibt `500` und kann einen teilweise
  ausgeführten Ablauf hinterlassen.
- **Einheiten und Vorzeichen:** nicht anwendbar.
- **Seiteneffekt und Sicherheit:** Reihenfolge ist Collector stoppen,
  Datenbank `delete_all` ausführen, Collector-Laufzeitstatus zurücksetzen.
  Die API bietet weder Vorschau, Bestätigungsparameter noch
  Wiederherstellung. Vorhandene externe Backups werden von diesem Endpunkt
  nicht verwaltet. Ohne Authentifizierung, Autorisierung und CSRF-Prüfung
  darf der Endpunkt nur innerhalb einer anderweitig geschützten
  Betriebsgrenze erreichbar sein.
- **Synthetisches Beispiel:** Aus Sicherheitsgründen wird kein direkt
  ausführbarer Schnellstartbefehl gezeigt. Ein autorisierter lokaler
  Betriebsablauf sendet `POST /api/delete-all` und erwartet ausschließlich
  `{"ok":true}`.

## Update-Schnittstellen

Updateprüfung und Download kommunizieren mit dem öffentlichen GitHub-Release-
Dienst. Der Download schreibt Updatezustand und einen verifizierten
Release-Cache. Die Installationsroute schreibt nur eine lokale
Anforderungsdatei; der privilegierte systemd-Updater läuft außerhalb des
Webprozesses. Diese Prozessgrenze ist kein Schutz vor unberechtigten
API-Aufrufen.

### `GET /api/update/check`

- **Klassifikation, Zweck und Stabilität:** `operational_write`; prüft das
  konfigurierte GitHub-Repository; unversioniert und intern.
- **Parameter und Request:** keine Parameter; kein Body.
- **Erfolg:** `200`; `status`, installierte und verfügbare Version,
  `update_available`, Release-Name, -Notizen, Veröffentlichungszeit,
  Release-URL sowie Namen und URLs von Archiv und Prüfsumme. Assetfelder
  können `null` sein.
- **Fehler:** `502`; `{"status":"error","installed_version":"...","message":"..."}`.
- **Einheiten und Zeit:** `published_at` ist der von GitHub gelieferte
  ISO-8601-Zeitstempel oder `null`.
- **Seiteneffekt und Sicherheit:** externer HTTPS-Zugriff auf GitHub; keine
  lokale Installation, aber aktiver Netzwerkaufruf ohne API-Zugriffsschutz.
- **Synthetisches Beispiel:** `GET /api/update/check` liefert
  `{"status":"ok","installed_version":"4.5.2","available_version":"4.5.2","update_available":false,"asset_name":"zrzavy-energy-monitor-4.5.2.tar.gz"}`.

### `GET /api/update/status`

- **Klassifikation, Zweck und Stabilität:** `ui_internal_read`; liest den
  persistenten Updatefortschritt; unversioniert.
- **Parameter und Request:** keine Parameter; kein Body.
- **Erfolg:** `200`; mindestens `state`, `progress`, `message`,
  `installed_version`, `available_version`, `archive_path` und `updated_at`.
  Ohne gültige Statusdatei werden Idle-Defaults geliefert; unbekannte
  persistierte Felder bleiben erhalten.
- **Fehler:** kein fachlicher Fehlerstatus; eine fehlende oder beschädigte
  Statusdatei ist kein Fehler.
- **Einheiten und Zeit:** `progress` ist Prozent; `updated_at` ist UTC als
  ISO 8601 oder `null`.
- **Seiteneffekt und Sicherheit:** lesend, kann lokale Cachepfade und
  Betriebsfehler ohne Zugriffsschutz offenlegen.
- **Synthetisches Beispiel:** `GET /api/update/status` liefert
  `{"state":"idle","progress":0,"message":"","installed_version":null,"available_version":null,"archive_path":null,"updated_at":null}`.

### `POST /api/update/download`

- **Klassifikation, Zweck und Stabilität:** `operational_write`; prüft,
  lädt und verifiziert ein neueres Release; unversioniert und intern.
- **Parameter und Request:** keine Parameter; kein Body erforderlich.
- **Erfolg:** `200`; persistierter Status mit `state: "verified"`,
  `progress: 100`, Nachricht, verfügbarer Version, lokalem `archive_path`
  und `updated_at`.
- **Fehler:** `409`, wenn keine neuere Version verfügbar ist, mit
  `state: "idle"`; `502` bei GitHub-, Download- oder
  Verifikationsfehlern, mit `state: "failed"`.
- **Einheiten und Zeit:** Fortschritt in Prozent; `updated_at` UTC ISO 8601.
- **Seiteneffekt und Sicherheit:** externer GitHub-Zugriff, Download von
  Archiv und Prüfsumme, Größenbegrenzung, SHA-256- und
  Dateinamenverifikation, Schreibzugriff auf Updatecache und Statusdatei.
  Keine Authentifizierung, Autorisierung oder CSRF-Prüfung.
- **Synthetisches Beispiel:** `POST /api/update/download` kann
  `{"state":"verified","progress":100,"message":"Release-Paket wurde erfolgreich heruntergeladen und geprüft.","available_version":"4.6.0","archive_path":"<UPDATE-CACHE>/4.6.0/zrzavy-energy-monitor-4.6.0.tar.gz","updated_at":"2026-07-27T08:00:00+00:00"}` liefern.

### `POST /api/update/install`

- **Klassifikation, Zweck und Stabilität:** `operational_write`; stellt ein
  bereits verifiziertes Paket zur Installation bereit; unversioniert und
  intern.
- **Parameter und Request:** keine Parameter; kein Body erforderlich.
- **Erfolg:** `202`; `{"status":"queued","version":"..."}`.
- **Fehler:** `409` mit `{"status":"error","message":"..."}`, wenn der
  Status nicht `verified` ist oder Version beziehungsweise Archivpfad
  fehlen.
- **Einheiten und Vorzeichen:** nicht anwendbar.
- **Seiteneffekt und Sicherheit:** schreibt atomar eine lokale JSON-
  Anforderungsdatei mit Version und serverseitigem Archivpfad und setzt den
  Status auf `queued`. Der getrennte privilegierte Updater verarbeitet die
  Datei. Der Client kann keinen beliebigen Befehl oder Pfad im Request-Body
  übergeben; die Route hat dennoch keine API-Zugriffskontrolle.
- **Synthetisches Beispiel:** `POST /api/update/install` liefert
  `HTTP 202` und `{"status":"queued","version":"4.6.0"}`.

## Fehlerantworten

Es gibt kein einheitliches Fehlerobjekt. Je nach Route erscheinen `error`,
`message` oder ein kompletter Update-Status. Flask liefert außerdem `404` für
unbekannte Pfade und `405` für eine nicht erlaubte Methode. Relevante
fachliche Statuscodes sind:

| Status | Verwendung |
|---:|---|
| `200` | erfolgreicher Lese- oder Betriebsaufruf |
| `202` | Updateinstallation wurde vorgemerkt |
| `400` | ungültiger Betriebszustand, Diagnosekonfiguration oder Export |
| `404` | unbekannte Geräterolle oder unbekannter Pfad |
| `405` | Methode ist für die Route nicht registriert |
| `409` | kein Update oder Updatezustand erlaubt Aktion nicht |
| `500` | Erfassungs- oder unerwarteter Serverfehler |
| `502` | Geräte-, GitHub-, Download- oder Verifikationsfehler |

## Stabilitätsregeln für lokale Integrationen

Lokale Integrationen sollten die Version über `/api/system/version` prüfen,
unbekannte JSON-Felder tolerieren, optionale und `null`-Felder behandeln,
Einheiten aus Feldnamen oder `unit` lesen und Zeitstempel mit Zeitzone
verarbeiten. Abfrageintervalle, Timeouts und Wiederholungen müssen begrenzt
sein. Zustandsändernde, diagnostische und destruktive Endpunkte sind keine
normalen Polling-Schnittstellen. Änderungen innerhalb der 4.x-Reihe müssen vor
produktiver Nutzung erneut geprüft werden.

## Sicherheit und bekannte Einschränkungen

- Version 4.5 implementiert an diesen API-Routen keine Authentifizierung,
  Autorisierung, Rollenprüfung, CSRF-Prüfung oder Rate Limits.
- HTTP bietet ohne vorgeschaltete, korrekt konfigurierte Absicherung keine
  Transportverschlüsselung.
- Collector-, Diagnose-, Lösch- und Updateaufrufe können durch jeden
  erreichbaren Client ausgelöst werden.
- Live-, Diagnose-, Status- und CSV-Antworten können Betriebs-,
  Netzwerk-, Geräte- oder Messinformationen offenlegen.
- Gerätetests verwenden die im Request oder in der lokalen Konfiguration
  enthaltenen Verbindungsdaten für lokale Netzwerkzugriffe.
- `/api/delete-all` hat keine eingebaute Bestätigung oder Wiederherstellung.
- Eine geplante versionierte und authentifizierte Integrations-API ist nicht
  Bestandteil des Verhaltens von Version 4.5.
