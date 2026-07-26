# Validation engine

## Purpose

SolarInspector 4.5 validates normalized device measurements before source
selection, calculation, energy integration, and persistence.

```text
DeviceSnapshot
→ CollectorValidationBridge
→ ValidationEngine
→ ValidatedDeviceSnapshot
→ existing source selection and calculations
```

The engine classifies measurements. It does not calibrate them, query devices,
select long-term source priorities, or implement the Phase-09 energy balance.

## Models

- `MeasurementCandidate` accepts values before strict validation.
- `ValidationFinding` carries a stable rule ID, code, severity, message, and
  bounded details.
- `ValidationResult` contains decision, quality, raw value, accepted value, and
  all findings.
- `ValidatedMeasurement` keeps the original measurement beside the result and
  optional usable measurement.
- `ValidatedDeviceSnapshot` keeps the original snapshot beside its filtered
  snapshot.
- `ValidationEvent` contains actionable warnings or rejections.

Decisions:

- `accept`
- `accept_with_warning`
- `reject`

Quality mapping:

- accepted values retain their original quality unless a successful comparison
  upgrades them to `validated`
- warnings become `suspect`
- rejected physical values become `rejected`
- missing values become `unavailable`
- stale values become `stale`

## State and ordering

Rules are stateless. `ValidationStateStore` owns accepted historical values.
The collector bridge performs two passes:

1. local format, unit, range, time, history, counter, and phase checks
2. cross-source checks using locally accepted peers

Only accepted or suspect measurements enter history. Rejected, stale, or
unavailable measurements cannot become references for later delta checks.

The bridge uses a bounded deque with a default maximum of 512 measurements and
a default five-minute history horizon.

## Collector boundary

Validation runs before the existing legacy compatibility conversion and before
power values reach source selection or trapezoidal energy integration.

A rejected metric is removed from the filtered snapshot. Other valid metrics
from the same device remain available. A connected device with warnings or
rejections becomes `degraded`; connection state and measurement quality remain
separate.

Disabling `validation.enabled` is a strict no-op and preserves the prior data
path.

## Events and persistence

Warnings and rejections become `ValidationEvent` instances. Persistence occurs
after the aggregate sample was stored, so an event-storage failure cannot
discard the measurement sample.

Repeated events are aggregated by source, role, metric, rule, finding code, and
decision. Raw values and details are bounded and sanitized before SQLite
storage.

## Public interfaces

- `GET /api/validation/summary`
- `GET /api/validation/events`

The dashboard shows a 24-hour summary and recent deduplicated events. The
configuration page exposes operational limits but no rule DSL or automatic
calibration controls.
