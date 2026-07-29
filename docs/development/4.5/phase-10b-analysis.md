# Phase 10B – Analysebericht und vorbereitender Implementierungsauftrag

**Stand:** 2026-07-29
**Ausgangsversion laut `VERSION`:** 4.5.3
**Ziel:** ZEM 4.5.4
**Evidenzbasis:** `phase-10b-zem-4.5.4-planning-input.json` und
`phase_10b_zem_4.5.4_chat_auftrag.md`

## 1. Ergebnis von Block 10B.1

Die lokale Arbeitskopie ist bereits auf `4.5.3`. Der aktuelle Branch ist
`codex/zem-wp-05-prepare-release-4.5.1`, nicht der im Auftrag vorgesehene
Feature-Branch. Der Worktree war beim Preflight sauber. Der letzte lokale
Commit ist `a397e09 Add Shelly Plug M Gen3 plant AC source`.

Der SHRDZM-Pfad ist im Repository nicht nur dokumentiert, sondern bereits
teilimplementiert. Daher ist Phase 10B im vorhandenen Stand eine
Vertrags-, Sicherheits-, Qualitäts- und Hardwarevalidierungsphase mit gezielten
Korrekturen; sie ist keine freie Neuentwicklung eines Adapters.

## 2. Verbindlicher Vertrag und Evidenzgrenzen

### Bestätigt und für die Implementierung verwendbar

- Lokaler HTTP-Transport, `GET /getLastData`, JSON-Objekt, Standardport 80.
- Query-Authentifizierung über `user` und `password`; Konfiguration mit Host,
  Benutzername, Passwort und Timeout.
- HTTP 200 mit einem JSON-Feld `error` ist ein fehlgeschlagener Abruf.
- Numerische Messwerte und Zeitwerte kommen als Strings.
- Fehlende Schlüssel bleiben fehlend/null; der String `"0"` ist ein echter
  Nullwert.
- `1.7.0` und `2.7.0` sind getrennte positive Leistungswerte in Watt.
  ZEM-Nettoleistung bleibt `Import - Export`.
- `32.7.0`, `52.7.0`, `72.7.0` sind optionale Spannungen in Volt und
  `31.7.0`, `51.7.0`, `71.7.0` optionale Ströme in Ampere.
- `UTC` ist die bevorzugte Messzeit; `timestamp` ist ergänzende lokale
  Gerätezeit.

### Nicht als Produktvertrag verwenden

- `1.8.0` und `2.8.0`: Einheit und kWh-Skalierung sind nur angenommen.
  Keine produktive Umrechnung ohne externe Anzeige-/Hardwareevidenz.
- `16.7.0`: Importfall bestätigt; die nachgereichten Einspeiseantworten zeigen
  bei positivem `2.7.0` den entsprechenden negativen Nettowert.
- `13.7.0`: für die Anlage nicht relevant und außerhalb des produktiven
  ZEM-4.5.4-Scopes; keine Interpretation oder Skalierung.
- `id`, `uptime` und lokale Gerätezeit sind optionale Metadaten, keine
  belastbare Grundlage für Messzeit oder Identität.
- Modbus TCP, MQTT und HTTPS sind nicht Scope dieser Phase.
- Der bestehende lokale Modbus-Test wird bewusst für eine spätere 4.6-Phase
  zurückgestellt. Er ist kein Abnahmekriterium für ZEM 4.5.4.

Credentials, authentifizierte URLs und reale Gerätekennungen dürfen weder in
Bericht, Fixtures, Logs, Exceptions, API-Ausgaben noch Dokumentation stehen.

## 3. Tatsächliche Repository-Zuordnung

| Arbeitsteil | Tatsächliche Dateien | Befund für 10B |
|---|---|---|
| Einstieg/Runtime | `app/zrzavy_energy_monitor.py`, `app/zrzavy_energy_monitor_core/runtime.py` | Kanonischer ZEM-Einstieg vorhanden. |
| Adapter/Transport | `app/zrzavy_energy_monitor_core/adapters/shrdzm_grid_meter.py`, `grid_meter_factory.py` | SHRDZM-Adapter und Factory vorhanden; Vertrag und Redaction prüfen. |
| Konfiguration | `app/zrzavy_energy_monitor_core/config/grid_meter.py`, `config/manager.py`, `validation/config.py` | `shrdzm_rest`, Mapping und Defaults vorhanden; bestehende Tasmota-Defaults schützen. |
| Messmodell | `models/device.py`, `models/measurement.py`, `models/metrics.py`, `models/quality.py`, `models/roles.py`, `models/units.py` | `GRID_METER`, Import/Export, Phasen und Quality-Verträge vorhanden. |
| Collector/Quellenwahl | `services/collector.py`, `services/source_selector.py`, `validation/collector.py` | Führende Rolle und Fallback bereits angebunden; Regression absichern. |
| Persistenz | `persistence/database.py`, `persistence/queries.py`, `persistence/migrations.py` | `grid_meter_samples` und Phasenpersistenz vorhanden; keine Schemaänderung ohne explizite Notwendigkeit. |
| API/Web | `web/api.py`, `web/configuration.py`, `web/pages.py`, `templates/configuration.html`, `templates/dashboard.html`, `static/dashboard.js` | Konfiguration, Diagnose, API und Dashboard lokalisierbar. |
| SHRDZM-Doku | `docs/shrdzm-grid-meter.md`, `docs/devices.md`, `docs/configuration.md`, `docs/api.md` | Vorhandene Aussagen gegen bestätigte Evidenz bereinigen. |
| Charakterisierung/Adapter | `tests/test_shrdzm_grid_meter_adapter.py`, `tests/test_grid_meter_adapter_factory.py`, `tests/test_shrdzm_grid_meter_end_to_end.py`, `tests/test_grid_meter_configuration.py` | Vorhandene Testbasis; auf Vertrag und Negativfälle ausrichten. |
| Fixtures | `tests/fixtures/shrdzm/rest/README.md` und die fünf JSON-Fixtures darunter | Import/Export/Null/Teilantwort/invalid vorhanden; Credentials und reale IDs prüfen. |
| Integration/Regression | `tests/test_collector_grid_meter.py`, `tests/test_grid_meter_persistence_api.py`, `tests/test_grid_meter_web.py`, `tests/test_collector_phase_persistence.py`, Tasmota/Shelly-Tests | Für spätere WP-10B-05-Regression vorgesehen. |

## 4. Analyse des bestehenden SHRDZM-Pfads

Der Adapter baut eine `MeasurementSource` mit Rolle `GRID_METER`, liest den
konfigurierten Endpoint über eine injizierbare HTTP-Session und normalisiert
Mappingwerte in `DeviceSnapshot`/`Measurement`. Der Collector cached den
Snapshot bis zum Poll-Intervall und behandelt Adapterfehler kontrolliert. Die
Factory wählt zwischen Tasmota HTTP und `shrdzm_rest`; dadurch bleibt der
bestehende alternative Netzstromzählerpfad grundsätzlich erhalten.

Die Konfiguration enthält zusätzlich allgemeine Felder wie Scheme, Port,
Direction-Factor, Poll-Intervall und Mapping. Diese sind vorhandene
Kompatibilitätsmechanismen, aber nicht automatisch Teil des bestätigten
SHRDZM-API-Vertrags. Besonders `energy_total_unit=auto`, ein optionales
`16.7.0`-Mapping und generische Auth-Modi müssen in der Implementierung so
begrenzt werden, dass keine unbestätigte Semantik produktiv behauptet wird.

Die vorhandene Testlandschaft enthält bereits synthetische Export-, Null-,
Teil- und ungültige-Werte-Fixtures sowie End-to-End-Tests. Die Analyse ergab
außerdem, dass mindestens ein End-to-End-Test einen als Secret bezeichneten
Passwortwert im Testinput verwendet. Das ist für den Evidenzvertrag zu
bereinigen; der konkrete Wert wird hier absichtlich nicht wiedergegeben.

## 5. Offene Punkte und Entscheidungstore

### Nachgereichte Hardwareevidenz

Die nachgereichten, anonymisierten realen Antworten bestätigen Import, Nullpunkt
und Einspeisung. Im Einspeisefall ist `1.7.0` null, `2.7.0` positiv und
`16.7.0` der negative entsprechende Netto-Wert. Damit ist die bestehende
ZEM-Vorzeichenkonvention für diese beobachteten Fälle belegt; die Priorität
von `UTC` für `measured_at` wird ebenfalls bestätigt.

Die Rohantwort enthielt außerdem eine Geräte-/Telegrammkennung und wurde nicht
in das Repository übernommen. Zugangsdaten, Hostadresse und Kennung bleiben
aus Sicherheitsgründen vollständig ausgeschlossen.

Die Evidenz schließt keine weiteren für den ZEM-4.5.4-Scope erforderlichen
Hardware-Entscheidungstore. `13.7.0` bleibt bewusst außerhalb des Scopes.

### Benötigtes Evidenzformat für die nächste Hardwareabfrage

Für jeden Fall genügt eine bereinigte JSON-Antwort plus ein kurzer Kontext;
Hostadresse, Benutzername, Passwort, `id` und vollständige URLs sind vor der
Weitergabe zu entfernen.

| Fall | Erforderliche Beobachtung | Zusätzlicher Nachweis |
|---|---|---|
| Einspeisung | `1.7.0 = 0`, `2.7.0 > 0`, `16.7.0` vorhanden | Anzeige/Exportstatus und beobachtetes Vorzeichen von `16.7.0` |
| Nullpunkt | `1.7.0 = 0`, `2.7.0 = 0`, `16.7.0 = 0` | stabile Wiederholung oder Zähleranzeige „0“ |
| Energieeinheit | Werte von `1.8.0` und `2.8.0` | zeitgleicher Vergleich mit offizieller Anzeige in Wh/kWh |

Eine einzelne Importantwort schließt diese Fälle nicht stellvertretend.

1. Der Modbus-Testpfad wird nach den ersten Echtbetriebswochen von ZEM 4.5
   separat für 4.6 geplant.
2. Hardwaretests gegen das echte Gerät, Zeitreihenvergleich und
   Energieabgleich sind nicht durch lokale Tests ersetzbar.

Diese Punkte werden nicht durch Annahmen geschlossen. Die kumulierten Werte
sind inzwischen als Wh bestätigt. `13.7.0` wird nicht produktiv verwendet;
Wirk- und Blindleistung bleiben getrennte, anlagenrelevante Messgrößen.

## 6. Credit-effizienter Folgeauftrag: erster Implementierungsblock

**Block 10B.2 – SHRDZM-Vertrags-Härtung auf Adapterebene**

Arbeite ausschließlich in den vorhandenen SHRDZM-Adapter-, Konfigurations-,
Fixture- und fokussierten Testdateien. Verwende die bestätigten Regeln dieses
Berichts und der beiden Planungsdateien. Führe keine Collector-, Persistenz-,
Dashboard-, Schema- oder Releaseänderung durch.

Aufgaben:

1. Prüfe den vorhandenen Adapter gegen `GET /getLastData`, Query-Auth,
   HTTP-200-`error`, numerische Strings, fehlende Felder, echten Nullwert und
   Secret-Redaction.
2. Ergänze oder korrigiere ausschließlich bereinigte Charakterisierungs- und
   Adaptertests für Import, Export, Null, Teilantwort, ungültige Werte,
   Timeout/HTTP-Fehler, ungültiges JSON und HTTP-200-Auth-Fehler.
3. Stelle sicher, dass `UTC` als timezone-aware Messzeit priorisiert wird.
4. Sperre produktive Interpretation von `13.7.0`; der Wert bleibt außerhalb
   des ZEM-4.5.4-Scopes.
5. Entferne Secret- und Geräteidentitätsleaks aus Fixtures und Testartefakten,
   ohne echte Zugangsdaten zu übernehmen.
6. Bewahre Tasmota-, Shelly- und sonstige bestehende Adapterpfade unverändert.

Abschlussnachweise für diesen Block: fokussierte Tests, `git diff --check`,
kein Secret in den geänderten Dateien, und ein kurzer Ergebnisvermerk mit
getrennten Listen für bestätigt, angenommen und offen. Die vollständige
`./scripts/verify.sh`-Prüfung erfolgt nach dem Block und vor jeder
Abnahmefreigabe.

Nicht Bestandteil dieses Auftrags sind reale Hardwareabfragen, die Schließung
offener Energie-/Einspeisepunkte, Collector-/Persistenz-/Dashboard-Integration,
Migrationen, Releaseerstellung, Commit, Push oder Pull Request.

## 7. Abschlussstatus Phase 10B

### Erreicht

- Lokaler HTTP-Transport und Query-Authentifizierung sind gegen bereinigte
  reale Antworten abgesichert.
- Import, Nullpunkt und Einspeisung sind mit realen Antworten belegt.
- `1.7.0` und `2.7.0` werden getrennt übernommen; die Nettoleistung folgt
  `Import - Export`.
- `16.7.0` zeigt in den gelieferten Einspeisefällen den passenden negativen
  Nettowert.
- `UTC` wird als timezone-aware `measured_at` verwendet.
- `1.8.0` und `2.8.0` sind als JSON-Wh bestätigt und werden intern in Wh
  normalisiert.
- Keine Credentials, Hostadressen oder Gerätekennungen wurden in Artefakte
  übernommen.

### Noch aus dem Echtbetrieb zu beobachten

- Betriebsstabilität, Zeitreihenqualität und Fallback-Verhalten während der
  ersten ZEM-4.5-Wocheninstallation.
- Keine produktive Interpretation von `13.7.0`; Wirk- und Blindleistung sind
  davon unabhängig.
- Modbus-Tests und Modbus-Erweiterungen sind für 4.6 vorgemerkt.

Die lokalen fokussierten SHRDZM-/Dokumentationsprüfungen sowie Lint, Typ- und
Compile-Prüfungen sind erfolgreich. Der einzige nicht ausführbare Vollsuite-
Test ist der lokale Modbus-Socket-Test, der in der Sandbox keine TCP-Bindung
erlaubt und für 4.6 zurückgestellt ist.
