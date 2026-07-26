# Phase 08 findings and open verification

## Automated findings

The deterministic replay catalog covers:

- normal plant operation including a real 0 W value
- an official grid-meter spike against a comparable Shelly value
- an impossible Solakon AC power value
- one missing Shelly phase
- a cumulative counter rollback
- network failure followed by recovery

The replay layer uses normalized snapshots and controlled timestamps. It never
waits or performs network communication.

## Hardware status

No real Phase-08 hardware observation is claimed by this commit.

The optional observer `scripts/validation_hardware_soak.py` reads the running
local APIs for 15–60 minutes. It records collector state, validation status,
warning and rejection counts, response time, and recent events. It never edits
thresholds or device configuration.

A hardware observation is complete only after its generated JSON report and the
physical installation have been reviewed together. In particular, the reviewer
must identify false alarms caused by:

- different electrical measurement positions
- device timestamp skew
- sign configuration
- standby consumption
- normal inverter clipping
- counter resets after device replacement
- incomplete phases during communication recovery

## Performance boundary

The deterministic benchmark validates thousands of cycles without wall-clock
sleep, records average cycle time, Python allocation peak, event count, and
bounded history size.

The automated limit is intentionally generous:

- average validation cycle no more than 5 ms
- Python allocation peak no more than 64 MiB
- history no more than 512 measurements
- no events for the generated normal values

This is a regression guard, not a Raspberry Pi capacity certification.

## Technical debt

- Adapter parsers can still reject malformed payload fields before a
  `MeasurementCandidate` exists; not every raw transport error therefore
  becomes a metric-level validation event.
- Validation history is process-local and intentionally resets on restart.
- Event acknowledgment and external alerting are not implemented.
- Historic samples are not retroactively revalidated.
- The dashboard provides an operational summary, not a full rule-analysis UI.
- Whole-site balance equations and final source priority remain Phase 09.
- Real hardware false-positive rates still require observation at Walter's and
  his father's actual installations.

## Explicitly not implemented

- automatic calibration
- automatic threshold tuning
- correction or scaling of accepted measurements
- replacement of official meter readings
- machine-learning anomaly detection
- email, MQTT, or Home Assistant alerting
- a complex browser rule editor

## Behoben: SQLite-ResourceWarnings unter Python 3.14

Direkte `sqlite3.connect(...)`-Verwendungen in Tests wurden zuvor mit dem
Connection-Kontextmanager verwendet. Dieser führt Commit oder Rollback aus,
schließt die Verbindung jedoch nicht. Unter Python 3.14 wurde dies als
`ResourceWarning` sichtbar.

Die direkten Testverbindungen verwenden nun zusätzlich
`contextlib.closing`. Ein Regressionstest verhindert neue ungeschlossene
direkte SQLite-Testverbindungen. Die vollständige Testsuite wird bei der
finalen Abnahme mit `ResourceWarning` als Fehler ausgeführt.
