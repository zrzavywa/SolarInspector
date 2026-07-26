# Phase 10 schema inventory

## Scope and evidence

This inventory describes the schema created by `Database.initialize()` on the
Phase 09 baseline (`40e1cdd`). It is the analysis deliverable for block 10.1
and does not define the Phase 10 target schema.

The inventory was derived from:

- `app/solarinspector_core/persistence/database.py`;
- all SQL statements below `app/`;
- persistence characterization and Phase 05–09 persistence tests;
- a newly initialized temporary SQLite database;
- a read-only analysis copy of the user-authorized local database.

The baseline test suite passes with 713 tests and one skipped hardware test.
The original local database was not changed. Its working copy was stored in a
new temporary directory with mode `0600`; no device identity or measurement
content was printed or copied into the repository.

## User-authorized local database inspection

The database at `app/data/solarinspector.db` was copied before inspection. The
copy passed `PRAGMA integrity_check` with `ok` and contained:

- the complete Phase 09 schema documented below;
- five application tables, six explicit application indexes, no views, and no
  triggers;
- 48 `samples` columns, including every additive Phase 05–09 column;
- no schema-version or migration-log table;
- zero `samples` rows and therefore no timestamp or NULL-distribution evidence.

This file confirms that the checked-in application opens and initializes the
current Phase 09 schema. It does **not** qualify as the required real 4.1.x
input fixture: its schema has already been extended by the current
presence-based `initialize()` path, it contains no rows, and the pre-extension
DDL cannot be recovered from SQLite metadata. The internal SQLite schema
cookie is not a SolarInspector application schema version.

No unmodified 4.1.x backup is available. The user therefore approved using a
documented synthetic 4.1.3 fixture derived from the Phase 02 characterization
of the complete 48-column `samples` schema. The 21-column base DDL is retained
separately as an older “v3-style” fixture and is not labeled 4.1.x.

This decision provides a reproducible test for the known 4.1.3 schema and its
documented values. It is not evidence that unknown field deployments or
unrecorded 4.1.x schema variants are supported. Such variants must fail safely
or produce migration findings rather than be guessed.

## Database-wide properties

| Property | Current behavior |
| --- | --- |
| Engine | SQLite through Python `sqlite3` |
| Connection | Short-lived connection, 30-second timeout, `sqlite3.Row` rows |
| Foreign keys | Enabled on every application connection |
| Journal | WAL requested during every initialization |
| Transaction model | Explicit commit after initialization and aggregate inserts |
| Schema version | None |
| Migration log | None |
| Views | None |
| Triggers | None |
| Application ID / user version | Not set |
| Timestamp strategy | Mixed: epoch seconds plus local ISO text in `samples` and validation events; aware ISO text in normalized detail tables |
| Retention | Validation events only, controlled by validation configuration |
| Aggregation | Dashboard performs in-memory bucket aggregation; no aggregate tables |

`initialize()` is also the only migration entry point. It creates missing
tables and indexes and adds missing legacy `samples` columns individually.
There is no ordered migration plan, schema verification, transaction spanning
the complete migration, backup, checksum, dry run, or rejection of a newer
unknown schema.

## Tables

### `samples`

This is the SolarInspector 4.1-compatible wide aggregate table and the parent
of all per-cycle Phase 05–09 details.

- Primary key: `id INTEGER PRIMARY KEY AUTOINCREMENT`
- Foreign keys: none
- Index: `idx_samples_ts_epoch(ts_epoch)`
- Unique constraints: none
- Required timestamp fields: `ts_epoch REAL`, `ts_local TEXT`

| Column group | Columns and current meaning |
| --- | --- |
| Current aggregate power | `grid_power_w`, `solar_power_w`, `house_power_w`, `grid_import_w`, `feed_in_w`, `self_consumption_w` |
| Electrical detail | `voltage_v`, `current_a`, `power_factor`, `frequency_hz` |
| Per-cycle integrated energy | `grid_import_wh`, `feed_in_wh`, `solar_wh`, `house_wh`, `self_consumption_wh` |
| Legacy status | `house_ok`, `solar_ok`, `error_text` |
| Added source power | `shelly_solar_power_w`, `solakon_pv_power_w`, `solakon_ac_power_w`, `solakon_battery_power_w`, `solakon_load_power_w`, `solakon_meter_power_w` |
| Added Solakon detail | `solakon_battery_soc_pct`, `solakon_temperature_c`, `solakon_daily_pv_kwh`, `solakon_total_pv_kwh`, `solakon_pv1_power_w` through `solakon_pv4_power_w` |
| Comparison and selection | `solar_difference_w`, `solar_difference_pct`, `solar_source`, `grid_source` |
| Device identity/status | `solakon_model`, `solakon_serial`, `solakon_status`, `solakon_ok` |
| Added per-cycle energy | `shelly_solar_wh`, `solakon_pv_wh`, `solakon_ac_wh`, `battery_charge_wh`, `battery_discharge_wh` |

There are 48 columns. Power and device-detail fields are nullable. Ten
per-cycle energy fields and three status flags are `NOT NULL DEFAULT 0`.
These energy values are interval contributions in Wh, not cumulative physical
meter readings. A zero default therefore currently means both “no integrated
energy in this cycle” and, for a minimal legacy insert, “not supplied”. Phase
10 must preserve legacy rows while avoiding this ambiguity in the new
time-series representation.

Legacy findings:

- `grid_import_w` and `feed_in_w` are power despite lacking `_power_` in their
  names.
- `*_wh` columns contain per-cycle integrated energy, not device counters.
- `solar_power_w` is a selected compatibility value and can represent
  different physical sources.
- `solar_source` and `grid_source` are display labels, not stable source IDs.
- `voltage_v`, `current_a`, `power_factor`, and `frequency_hz` are flattened
  aggregate details; the originating source is implicit in the collector path.
- `house_ok`, `solar_ok`, and `solakon_ok` are legacy availability flags and
  do not encode normalized measurement quality.
- `ts_local` is produced as an aware ISO-8601 string by the current collector,
  but SQLite does not enforce its format and older rows are not characterized
  beyond being text.
- Solakon model and serial are stored in the measurement table. They are
  diagnostic identity data and must not be copied into generic measurements
  without an explicit target mapping.

No listed legacy column is unexplained; columns with overloaded or ambiguous
semantics are explicitly identified above and require a migration finding
when their source, timestamp, or unit cannot be established.

### `phase_samples`

One flattened three-phase snapshot per aggregate sample and source.

- Primary key: `(sample_id, source_id)`
- Foreign key: `sample_id -> samples(id) ON DELETE CASCADE`
- Index: `idx_phase_samples_source_sample(source_id, sample_id)`; this repeats
  the primary-key order with `source_id` first for source-range reads
- Status/context: `measurement_role`, `device_status`, `error_text`,
  `measured_at`, `received_at`, `metadata_json`
- Per-phase values: `l1_`, `l2_`, and `l3_` variants of `power_w`,
  `voltage_v`, `current_a`, `power_factor`, and `quality`
- Analysis: `phase_power_available_count`, `phase_power_complete`,
  `phase_power_total_source`, `phase_power_sum_w`, `phase_power_spread_w`,
  phase shares, total deltas, and `phase_power_total_consistent`

Missing measurements are `NULL`; valid zeroes remain `0.0`. Quality is stored
per phase power value only. Voltage, current, and power-factor quality are not
persisted separately. Metadata is bounded by the normalized model but stored
as JSON text without a database JSON constraint.

### `grid_meter_samples`

One official grid-meter snapshot per aggregate sample.

- Primary key: `sample_id`
- Foreign key: `sample_id -> samples(id) ON DELETE CASCADE`
- Index: `idx_grid_meter_samples_source_sample(source_id, sample_id)`
- Context: `source_id`, `source_name`, `adapter`, `active_source_id`,
  `device_status`, `quality`, `error_text`, `measured_at`, `received_at`,
  `metadata_json`
- Values and qualities: `grid_power_w`, `grid_import_power_w`,
  `grid_export_power_w`, `grid_import_total_kwh`,
  `grid_export_total_kwh`, each paired with a quality column

This is the only current structure that stores physical cumulative grid
counters. Missing counters remain `NULL` and are not reconstructed from power.
The one-row-per-sample primary key prevents storing two official grid-meter
sources in the same collector cycle.

### `validation_events`

Deduplicated validation findings rather than a row for every rejected sample.

- Primary key: `id INTEGER PRIMARY KEY AUTOINCREMENT`
- Foreign keys: none; `first_sample_id` and `last_sample_id` are intentionally
  unenforced references
- Indexes:
  `idx_validation_events_last_seen(last_seen_epoch DESC)` and
  `idx_validation_events_identity(source_id, role, metric, rule_id,
  finding_code, decision, last_seen_epoch)`
- Time: first/last epoch plus first/last local ISO text
- Identity: source, role, metric, unit, rule, finding, severity, decision,
  quality
- Values: bounded `raw_value_json`, nullable `accepted_value`, observed
  minimum and maximum
- Diagnosis: bounded `reason`, bounded `details_json`, occurrence count

Events inside the configured deduplication window update the existing row.
Rejected values use `accepted_value = NULL`. Raw values and details are
sanitized and size-limited before storage. Optional automatic pruning deletes
rows by `last_seen_epoch`; no aggregation precedes deletion.

### `energy_balance_samples`

One Phase 09 calculated balance per aggregate sample.

- Primary key: `sample_id`
- Foreign key: `sample_id -> samples(id) ON DELETE CASCADE`
- Index:
  `idx_energy_balance_samples_quality_sample(quality, sample_id)`
- Time/status: `calculated_at`, `quality`
- Power/rate values: house, signed grid, separated grid directions, plant AC,
  PV, battery directions, battery SOC, self-consumed power, self-consumption
  rate, autonomy rate, and residual power
- Selection/diagnosis: `fallback_used`, bounded `source_metadata_json`,
  bounded `findings_json`

Source selections are embedded in `source_metadata_json`; there is no
independent `source_selection_events` table. Disabling source-decision
persistence writes `{}` and clears `fallback_used`. Missing calculated values
remain `NULL`; valid zeroes remain `0.0`.

## Objects that do not exist

The current database has no generic normalized `measurements` table, schema
version table, migration-finding table, source-selection event table,
retention-run log, aggregate table, view, or trigger. Adding any of these is a
target-schema decision for block 10.2, not an assumption from the suggested
task schema.

## Current indexes and access fit

| Access pattern | Available index | Finding |
| --- | --- | --- |
| Aggregate range/latest by `ts_epoch` | `idx_samples_ts_epoch` | Suitable |
| Phase latest/range for source | phase source/sample index plus parent lookup | Filtering uses source index; time ordering still joins and sorts on parent |
| Grid latest for source | grid source/sample index plus parent lookup | Filtering is supported; ordering is by parent timestamp |
| Latest energy balance | quality/sample index | Query does not filter quality; index is not aligned with timestamp ordering |
| Validation recent window | last-seen index | Suitable |
| Validation dedup identity/window | composite identity index | Suitable |
| Generic metric/source time series | none | No generic table or query exists |

No `EXPLAIN QUERY PLAN` evidence is currently recorded. Block 10.7 must measure
the actual queries before changing indexes.

## Migration entry points and supported starting shapes

1. `Database.__init__()` calls `initialize()` for every application start and
   every test-created database.
2. `initialize()` creates `samples` if absent.
3. It detects missing `samples` columns using `PRAGMA table_info(samples)` and
   applies one `ALTER TABLE ... ADD COLUMN` per missing additive column.
4. It creates Phase 05–09 tables and all indexes with `IF NOT EXISTS`.

Characterization tests cover an empty database, repeated initialization, and
a minimal older `samples` table (“v3-style”). They demonstrate additive
preservation of existing rows. They do not prove the exact SolarInspector
4.1.x production schema, all Phase 05–09 intermediate shapes, transactional
rollback of multi-step initialization, or handling of conflicting column
definitions.

## Reproduction commands

Use only a copy of an installation database:

```bash
cp --preserve=mode,timestamps solarinspector.db solarinspector-analysis.db
sqlite3 solarinspector-analysis.db '.schema'
sqlite3 solarinspector-analysis.db 'PRAGMA table_list;'
sqlite3 solarinspector-analysis.db 'PRAGMA integrity_check;'
sqlite3 solarinspector-analysis.db \
  "SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name;"
```

For every returned table, also run `PRAGMA table_info`, `foreign_key_list`,
and `index_list`. The Phase 10 migration fixture work must capture the exact
4.1.x shape without committing production data, credentials, addresses,
serial numbers, or personal data.

## Block 10.2 decisions exposed by the inventory

- Define an explicit versioned target schema and a safe legacy classification
  strategy before replacing presence-based initialization.
- Decide whether the wide `samples` table remains the compatibility parent
  while accepted normalized measurements are added, or whether all reads can
  be migrated without parallel indefinite storage.
- Preserve physical grid counters as reported kWh; never derive them from
  `*_wh` interval energy.
- Make a single UTC/aware-ISO timestamp policy enforceable at application
  boundaries.
- Represent missing accepted measurements as absent/`NULL`, while preserving
  legacy interval-energy zeroes without claiming historical availability.
- Decide whether embedded Phase 09 source metadata satisfies traceability or
  requires normalized source-selection events.
- Add backup, integrity verification, migration findings, and newer-schema
  rejection before any automatic destructive or data-copying migration.
