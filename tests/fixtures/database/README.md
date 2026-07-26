# Phase 10 database fixtures

## Format

The fixtures are SQL source files rather than committed SQLite binaries. Tests
execute each script against a new temporary database. This keeps schema and
values reviewable, produces a real SQLite database for every test, and avoids
binary drift between SQLite versions.

`expected.json` is the machine-readable pre-migration contract. Later
migration blocks extend it with post-migration expectations instead of hiding
expected transformations inside test code.

## `legacy_v3.sql`

- Classification: synthetic pre-4.1 legacy shape, not extracted from a
  production database.
- Origin: the 21-column base `samples` DDL and the test explicitly named
  `test_v3_style_schema_migration_preserves_existing_row`.
- Anonymization: all timestamps and measurements are invented; it contains no
  serial number, address, credential, hostname, or personal data.
- Starting schema: unversioned `samples` plus its timestamp index.
- Special cases: positive grid import, negative signed grid export, real zero,
  nullable electrical details, aware timestamps, nonzero per-cycle Wh values,
  status flags, and diagnostic text.
- Expected migration result: both rows and all original values remain;
  missing later measurements remain absent/`NULL`; no historical quality,
  source decision, physical counter, or phase value is invented.

This fixture is retained to verify the older additive migration entry point.
It must not be described as SolarInspector 4.1.x.

## `legacy_4_1.sql`

- Classification: synthetic SolarInspector 4.1.3 schema delta.
- Origin: the 48-column schema fixed by Phase 02 characterization tests.
- Construction: tests apply `legacy_v3.sql` and then this reviewed 27-column
  additive delta to a new temporary database.
- Anonymization: it reuses only the invented rows from `legacy_v3.sql`.
- Starting schema: one unversioned 48-column `samples` table and timestamp
  index, with no Phase 05–09 detail tables.
- Special cases: nullable device values and the characterized `NOT NULL
  DEFAULT 0` compatibility energy/status fields.
- Expected migration result: preserve all 48 columns and both rows, then add
  only versioning, finding, and Phase 05–09 detail structures.

Because no unmodified real 4.1.x backup is available, this fixture covers the
repository-characterized 4.1.3 shape only. Unknown field variants must produce
a finding or a safe migration failure.

## `phase_09.sql`

- Classification: synthetic Phase 09 intermediate-state fixture.
- Origin: the complete schema from the Phase 09 application baseline and its
  persistence characterization tests.
- Anonymization: every measurement, name, timestamp, source detail, and JSON
  value is invented. No productive device identity or connection data is
  present.
- Starting schema: all five Phase 09 tables and six explicit indexes, without
  `schema_migrations`.
- Special cases: complete phases, physical cumulative grid counters in kWh,
  selected energy-balance inputs, one warning-classified validation event,
  real zero export, source metadata, and per-cycle integrated energy.
- Expected migration result: versions 1 and 2 are applied without changing the
  five existing domain tables or any contained value.

## Intermediate deltas

The intermediate fixtures are layered after the synthetic 4.1.3 state:

| Fixture | Adds | Preserved special case |
| --- | --- | --- |
| `phase_05.sql` | `phase_samples` and its source index | One complete three-phase snapshot |
| `phase_06_07.sql` | `grid_meter_samples` and its source index | Physical import/export counters in kWh and real zero export |
| `phase_08.sql` | `validation_events` and both event indexes | One deduplicated warning with accepted value |

Each delta uses the exact characterized table shape for its phase. Tests
create the cumulative state, migrate it twice, and verify that existing row
counts and values do not change. Tables from later phases are created empty;
no historical detail row is synthesized.

## Empty database

An empty-database fixture is created by opening a new path in the test
temporary directory. A committed empty file would provide no additional
schema evidence.

## Maintenance

Changes to fixture SQL require synchronized changes to `expected.json`, this
README, the relevant migration documentation, and the fixture contract tests.
Tests must continue to use temporary database paths and must never execute
against `app/data/solarinspector.db`.
