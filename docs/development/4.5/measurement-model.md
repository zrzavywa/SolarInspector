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

A snapshot may be online with complete values, degraded with partial values, or
o-value offline/disabled. Duplicate values for the same role and metric are
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

## Initial integration strategy

Existing public reader behavior remains temporarily available. Normalized read
methods return `DeviceSnapshot`; explicit compatibility functions convert
snapshots to the existing `MeterReading`, `SolakonOneReading`, and collector
sample structures.

The first implementation commit introduces only the central model and unit
tests. It does not modify Shelly, Solakon, collector, persistence, API,
dashboard, or CSV behavior.
