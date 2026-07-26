# SolarInspector 4.5 time-series persistence

## Write contract

After schema migration to version 2, each collector cycle persists the
following in one transaction:

1. the wide compatibility sample;
2. optional phase and official-grid detail rows;
3. the energy-balance row;
4. every usable normalized measurement from the validated cycle;
5. calculated balance metrics whose values are available;
6. source-selection events when decision persistence is enabled.

Any failure rolls back the complete cycle. Validation events retain their
existing separate diagnostic transaction boundary.

## Accepted values

`measurements` accepts qualities `measured`, `reported`, `calculated`,
`validated`, `suspect`, and `fallback`. Qualities `rejected`, `stale`, and
`unavailable` are never written as fachliche Zeitreihenwerte.

- Missing value: no row.
- Rejected value: no measurement row; optional validation event only.
- Real zero: row with `value = 0.0`.
- Non-finite value: rejected earlier by the normalized model.
- SUSPECT value: stored with `quality = suspect`.

The source ID, role, measurement time, receipt time, quality, and device
status remain attached to each value.

## Units

| Metric family | Stored unit |
| --- | --- |
| Instantaneous power and calculated residual | `W` |
| Physical cumulative energy counters | `kWh` |
| Voltage | `V` |
| Current | `A` |
| State of charge and rates | `%` |
| Frequency | `Hz` |
| Power factor | `ratio` |
| Temperature | `°C` |

The normalized in-memory model represents energy counters in Wh. Persistence
divides those reported counter values by 1000 exactly once. It never derives a
counter from instantaneous power or from the compatibility `*_wh` interval
fields.

## Calculated metrics

The balance writer stores non-missing values for:

- `house_power`;
- `self_consumed_power`;
- `self_consumption_rate`;
- `autonomy_rate`;
- `energy_balance_residual_power`.

Their source is `energy_balance`, role and device status are `calculated`, and
their measurement and receipt timestamp is the balance calculation time.
Unavailable calculated terms have no row.

## Source decisions

Each source-selection result is stored even when no source is eligible. An
unavailable decision therefore has nullable selected source and role,
`selected_quality = unavailable`, and an explicit reason.

Rejected candidates contain only source ID, role, quality, reason, and
measurement timestamp. JSON is capped at 16,384 characters by removing whole
trailing candidates. No raw measurement value, device response, address,
credential, token, or secret is included.

The existing `energy_balance_samples.source_metadata_json` remains for live
API compatibility. `source_selection_events` is the normalized historical
representation and is controlled by the existing
`energy_balance.persist_source_decisions` setting.

## Compatibility and activation

The writer checks for version-2 tables before adding normalized rows. This
preserves Phase 09 operation until the later backup and startup blocks safely
activate schema migration. Once version 2 exists, normalized writes are
automatic and atomic.

## Timestamp and range contract

New normalized measurements and source-selection events are stored as
timezone-aware ISO 8601 text normalized to UTC. Normalization is required
because SQLite compares these indexed text timestamps lexically. Legacy
detail tables remain joined to `samples.ts_epoch`; this avoids interpreting
historical local timestamp strings whose timezone quality cannot be assumed.

All public range functions require timezone-aware `datetime` values and use
the half-open interval `start <= timestamp < end`. Empty and reversed ranges
raise `ValueError`. Different caller timezones are accepted and normalized.

## Query interface

`solarinspector_core.persistence.queries` separates database reads from API,
dashboard, and export formatting. It provides:

- `get_latest_measurement(connection, source_id, metric)`;
- `get_measurement_series(connection, metric, start, end, source_id=None)`;
- `get_phase_series(connection, start, end)`;
- `get_grid_series(connection, start, end)`;
- `get_energy_balance_series(connection, start, end)`;
- `get_validation_events(connection, start, end, source_id=None, metric=None)`;
- `get_source_selection_events(connection, start, end, metric=None)`.

Results are dictionaries containing explicit stable columns, including source
and quality where the underlying table provides them. No interface uses
`SELECT *`. Empty matches return `[]`; the latest-value function returns
`None`. Callers pass a connection configured with `sqlite3.Row`, as
`Database.connect()` does.

Every filter value and row limit uses SQLite parameter binding. Range queries
default to at most 5,000 rows and accept an explicit limit up to the hard
maximum of 50,000 rows. Larger history windows must therefore be paged or,
once justified by measured growth, served from aggregates. Block 10.8
evaluates retention and aggregation; no lossy aggregation is active yet.

## Index validation

Representative automated `EXPLAIN QUERY PLAN` checks establish these access
paths:

| Access pattern | Index used |
| --- | --- |
| latest value for source and metric | `idx_measurements_source_metric_measured_at` |
| metric/source decision over time | `idx_source_selection_events_metric_selected_at` |
| phase, grid, and balance range through parent sample | `idx_samples_ts_epoch` plus child primary key |

Metric-only measurement history uses
`idx_measurements_metric_measured_at`. Validation history uses
`idx_validation_events_last_seen` unless its optional identity filters allow
the more selective existing `idx_validation_events_identity`. No separate
`energy_balance_samples(calculated_at)` index was added: the stable range
contract uses the authoritative parent sample time, and its existing index
already supplies the ordered range before the primary-key lookup. This avoids
an additional index update on every five-second collector cycle.

## Retention

Retention is opt-in under `persistence.retention`. Existing configurations
receive the documented policy with `enabled: false`; loading or saving such a
configuration therefore never starts deleting history.

```json
{
  "persistence": {
    "retention": {
      "enabled": false,
      "raw_high_resolution_days": 30,
      "validation_events_days": 365,
      "source_selection_events_days": 90,
      "batch_rows": 1000
    }
  }
}
```

| Setting | Type/default | Meaning |
| --- | --- | --- |
| `enabled` | boolean, `false` | Master opt-in; false is a strict no-op |
| `raw_high_resolution_days` | number/null, `30` | Age of `samples` and cascading detail/time-series rows |
| `validation_events_days` | number/null, `365` | Age based on the event's last occurrence |
| `source_selection_events_days` | number/null, `90` | Age of normalized source decisions |
| `batch_rows` | integer, `1000` | Per-category limit per run; allowed range 1–10,000 |

Setting an age to `null` retains that category indefinitely. Ages must be
positive. `apply_retention()` also requires an explicit timezone-aware
reference clock, making maintenance runs reproducible and testable.

An enabled run uses one `BEGIN IMMEDIATE` transaction. It deletes oldest rows
strictly before each cutoff, up to one batch per configured category. Failure
in any category rolls back all categories. The exact cutoff and all newer
data—including the current measurement period—survive. Raw sample deletion
uses existing foreign-key cascades for normalized measurements, phase/grid
details, balances, and source decisions. The committed parent/event counts
are returned and logged. Cascaded child counts are not guessed. No retention
run performs `VACUUM`.

The callable is intentionally separate from the collector cycle: cleanup must
not add a write transaction every five seconds. After schema preparation, the
application executes exactly one bounded retention run during process startup
and before Collector construction. With `enabled: false` this remains a strict
no-op. Large expired histories are drained across successive controlled
starts or explicit maintenance calls rather than one unbounded transaction.

## Growth measurement and aggregation decision

On 2026-07-26, a temporary target-schema SQLite database was populated with a
representative high-cardinality day:

- 17,280 five-second cycles;
- 25 normalized measurements per cycle (432,000 rows);
- six source decisions per cycle (103,680 rows);
- one parent sample and one balance per cycle.

After checkpointing WAL, the database occupied 140,361,728 bytes, or about
8,123 bytes per cycle. Linear projection of this synthetic workload is about
4.21 GB for 30 days and 51.23 GB for 365 days. A bounded indexed query for one
metric returned its maximum 5,000 rows in 91.6 ms on the development machine.
These numbers are measurements of the stated synthetic workload—not Raspberry
Pi guarantees or claims about a particular installation.

Aggregation is not introduced in this block. The query remains responsive,
the actual number of metrics per installation is not yet measured, and a
correct aggregate format must distinguish gauges from cumulative counters.
In particular, counters require first/last/delta plus explicit reset handling;
averaging them would corrupt their semantics. The measured growth does justify
the opt-in raw retention mechanism and a later aggregate design if real
Phase-10 duration tests confirm long-history demand. Until that evidence
exists, row-limited indexed reads and explicit retention avoid irreversible
or semantically ambiguous aggregation.

## CSV exports

The existing `/api/export.csv?from=YYYY-MM-DD&to=YYYY-MM-DD` contract remains
the default and keeps its field order, delimiter, inclusive calendar-date
interpretation, filename, and values.

New datasets are selected additively with `dataset`:

| Dataset | Content and optional filters |
| --- | --- |
| `measurements` | One normalized metric; mandatory `metric`, optional `source_id` |
| `phases` | Partial or complete L1/L2/L3 values, qualities, and phase analysis |
| `grid` | Official meter power, cumulative kWh counters, status, and quality |
| `energy_balance` | Calculated flows, rates, residual, quality, and fallback flag |
| `validation_events` | Safe event summary; optional `metric` and `source_id` |
| `source_selection_events` | Selected source and reason; optional `metric` |

All new exports use semicolons, explicit headers, a half-open internal time
range, and at most 50,000 rows. `maximum_rows` may request a smaller bound.
CSV `NULL` is empty; a real `0.0` is emitted as `0.0`. Unit-bearing fields
use unit suffixes or, for normalized measurements, a separate `unit` column.

Diagnostic CSVs deliberately omit raw-value JSON, details JSON, source
metadata, rejected-candidate JSON, serial numbers, addresses, and credentials.
Strings beginning with `=`, `+`, `-`, or `@` are apostrophe-prefixed to prevent
spreadsheet formula execution. The legacy export still contains its historical
serial field solely for backward compatibility.
