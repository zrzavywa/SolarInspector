# Normalized measurement model

## Design goal

Device-dependent response formats end inside their adapter. Adapter output is a
small, immutable, device-independent model that can later support validation,
source selection, persistence, and energy-flow calculations without embedding
those decisions in the model itself.

```text
Device response
    -> device-specific parser and scaling
    -> DeviceSnapshot with Measurement values
    -> temporary legacy mapping
    -> existing collector, database, API, dashboard, and CSV behavior
```

## Model elements

### `MeasurementRole`

Describes the functional measurement location independently of a concrete
vendor or model:

- `GRID_METER`
- `HOUSE_METER`
- `PLANT_METER`
- `SOLAR_SYSTEM`
- `BATTERY_SYSTEM`

### `Metric`

Provides stable semantic identifiers. The initial list is limited to values
that are already read or required to represent existing legacy results. Grid
import and export power are defined as calculated metrics, but device adapters
emit signed `GRID_POWER` rather than choosing a direction.

### `Unit`

Defines controlled physical units. `METRIC_UNITS` maps every metric to exactly
one canonical unit and is used as a structural model invariant.

### `MeasurementQuality`

Separates the origin or later assessment of a value from the device connection
status. Phase 04 primarily uses `MEASURED`, `REPORTED`, and `CALCULATED`.

### `Measurement`

An immutable, slotted data class containing:

- Metric and canonical unit.
- Finite numeric value; zero remains valid.
- Stable `source_id`.
- Functional role.
- Timezone-aware measured and received timestamps.
- Quality classification.
- Optional raw value for focused diagnostics.

The class validates only structural invariants. It contains no range checks,
source priority, fallback behavior, or energy formulas.

### `MeasurementSource`

Represents stable configured identity, display name, device type, and one or
more supported functional roles. It does not contain network credentials or
perform device discovery.

### `DeviceSnapshot`

Represents one device read operation with:

- Source identity.
- Connection status.
- Zero or more measurements.
- Receipt timestamp.
- Optional technical diagnostic message.
- Immutable textual device metadata for identity and operating details.

A snapshot may be online with complete values, degraded with partial values, or
zero-value offline/disabled. Duplicate values for the same role and metric are
rejected because Phase 04 has no hidden rule for choosing between them.

## Deliberate exclusions

The model does not implement:

- Device-specific limits or plausibility rules.
- Cross-source comparison.
- Validation, suspect, rejected, stale, or fallback decisions.
- Source priority.
- Historical-data migration.
- New persistence or public API schema.
- Automatic unit conversion outside device adapters and explicit legacy
  mapping.
- A plugin framework, event bus, dependency-injection framework, or abstract
  factory hierarchy.

## Implemented Phase 04 integration

Both production device families now implement the common adapter protocol:

- `ShellyMeasurementAdapter` normalizes configured grid and plant meters.
- `SolakonMeasurementAdapter` normalizes grid, solar-system, and battery values.
- The collector reads both device families through `DeviceSnapshot`.
- Explicit compatibility functions restore the existing `MeterReading` and
  `SolakonOneReading` structures before the established source-selection,
  balance, energy-integration, persistence, API, dashboard, and CSV logic runs.

The compatibility boundary is temporary and intentional. It allows Phase 04 to
replace device-dependent acquisition without changing the public schema or
historical calculation behavior. A later phase may migrate the remaining
consumers to normalized measurements and then remove the legacy mappings.

## Completion boundary

Phase 04 is complete when adapter and collector contract tests, characterization
tests, Ruff, mypy, compilation, imports, and the full regression suite pass.
Device-specific plausibility limits, cross-source validation, stale detection,
new source-priority rules, and public-schema changes remain outside this phase.
