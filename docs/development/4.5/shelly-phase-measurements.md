# Shelly phase measurements

## Purpose

SolarInspector 4.5 Phase 05 adds stable per-phase acquisition for Shelly 3EM
Gen 1 and Shelly Pro 3EM devices. The implementation keeps the existing signed
aggregate grid-power value authoritative while retaining L1, L2, and L3 for
diagnostics, plausibility checks, persistence, APIs, and the dashboard.

The feature is additive. Existing aggregate sample fields, energy integration,
source selection, household balance, CSV export, and existing API payloads
remain compatible.

## Supported devices

### Shelly 3EM Gen 1

Source endpoint:

```text
/status
```

The `emeters` array is mapped deterministically:

| Device index | SolarInspector phase |
| --- | --- |
| `emeters[0]` | `L1` |
| `emeters[1]` | `L2` |
| `emeters[2]` | `L3` |

Available fields include active power, voltage, forward energy, and returned
energy. Fields not reported by the device response remain unavailable rather
than being invented.

### Shelly Pro 3EM

Source endpoint:

```text
/rpc/EM.GetStatus?id=0
```

Device prefixes are mapped deterministically:

| Device prefix | SolarInspector phase |
| --- | --- |
| `a_` | `L1` |
| `b_` | `L2` |
| `c_` | `L3` |

Available values include active power, voltage, current, power factor,
frequency, diagnostic errors, and phase flags. The legacy
`c_active_power` alias is accepted when `c_act_power` is absent.

## Configuration

Three-phase Shelly sources support:

- A device-wide `direction_factor`.
- A functional role for each physical phase.
- Optional per-phase direction overrides.
- Stable phase names `L1`, `L2`, and `L3`.

The device-wide direction applies unless a phase override is configured. A
phase override changes the normalized phase sign but does not replace the
device-reported aggregate total.

When phase-specific directions differ, aggregate-to-phase comparison is skipped
because the values are intentionally no longer directly comparable.

## Aggregate and phase semantics

The device-reported total remains authoritative when available.

```text
aggregate grid power
    = signed device total
```

A phase sum is used only as an explicit fallback when the aggregate total is
missing. The fallback is identified in snapshot metadata and is not
misrepresented as a device-reported total.

Phase measurements are emitted under the `HOUSE_METER` role:

- `PHASE_POWER_L1`, `PHASE_POWER_L2`, `PHASE_POWER_L3`
- `PHASE_VOLTAGE_L1`, `PHASE_VOLTAGE_L2`, `PHASE_VOLTAGE_L3`
- `PHASE_CURRENT_L1`, `PHASE_CURRENT_L2`, `PHASE_CURRENT_L3`
- `PHASE_POWER_FACTOR_L1`, `PHASE_POWER_FACTOR_L2`,
  `PHASE_POWER_FACTOR_L3`

The signed aggregate value continues to use `GRID_METER` and `GRID_POWER`.

## Quality and device status

Valid production values use `MeasurementQuality.REPORTED`.

A phase is marked `SUSPECT` when device diagnostics or phase validity indicate
a problem. Partial values are retained for diagnosis instead of discarding the
complete snapshot.

The snapshot becomes `DEGRADED` when:

- Required aggregate power is unavailable.
- A phase reports errors or invalid status.
- Comparable aggregate and phase totals differ beyond the configured analysis
  tolerance.
- Only a fallback phase sum is available.

Transport failures produce an `OFFLINE` snapshot without numeric
measurements.

## Phase power analysis

The pure phase-analysis service calculates:

- Sum of available phase powers.
- Difference between phase sum and aggregate total.
- Percentage difference where the reference magnitude is sufficient.
- Absolute load contribution by phase.
- Percentage load distribution across L1, L2, and L3.
- Spread between the strongest and weakest available phase.
- Phase-sum comparability status.

The comparison does not replace the aggregate total and does not modify energy
integration.

## Persistence

The existing `samples` table remains unchanged.

Phase data is stored additively in `phase_samples`, linked to the aggregate
sample. Aggregate and phase rows are written in one SQLite transaction so they
cannot diverge after a partial insert.

Persisted information includes:

- Source identity and timestamp.
- Connection status and diagnostic text.
- L1, L2, and L3 power, voltage, current, power factor, and quality.
- Device total and phase sum.
- Difference and percentage difference.
- Per-phase load distribution.
- Load spread and comparison status.

Offline and degraded multi-phase snapshots are retained as status records.
Single-phase meters do not create phase rows.

Deleting SolarInspector data removes aggregate and phase rows together.

## Public API

Phase data uses additive endpoints:

```text
GET /api/phases/live
GET /api/phases/dashboard?period=day|week|year&anchor=YYYY-MM-DD
```

`/api/phases/live` returns the latest persisted phase snapshot with nested
`l1`, `l2`, and `l3` values, quality classifications, status, diagnostics, and
analysis.

`/api/phases/dashboard` returns period metadata, bucket labels, phase-power
series, and period statistics. Unknown periods fall back to `day`, matching the
existing dashboard convention.

The existing `/api/live` and `/api/dashboard` payloads are not changed.

## Dashboard

The dashboard displays:

- Current L1, L2, and L3 power.
- Voltage, current, power factor, and quality for each phase where available.
- Current device status and diagnostics.
- Device total, phase sum, difference, spread, and load distribution.
- Historical L1, L2, and L3 power for day, week, and year.

Phase API failures are isolated from the established aggregate dashboard
updates.

## Deliberate limitations

Phase 05 does not introduce:

- Official utility-meter communication.
- Cross-device validation against a legally calibrated meter.
- Device-specific configurable voltage, current, or power limits.
- Long-term phase-energy aggregation.
- Phase-aware household or self-consumption formulas.
- Phase-aware CSV export.
- Automatic correction of wiring or current-transformer orientation.
- Replacement of the aggregate grid-power source by a calculated phase sum.

Those concerns remain separate follow-up work.
