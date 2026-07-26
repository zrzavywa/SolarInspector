# SolarInspector 4.5 database migration

## Current operational status

Blocks 10.4–10.11 provide transactional transformations plus an independent
database-maintenance CLI with read-only inspection, consistent SQLite backup,
dry-run migration, backup-gated real migration, and application startup
integration.

The maintenance entry point imports neither `solarinspector.py` nor Flask,
Collector, or device adapters:

```bash
python app/database_cli.py --help
```

## Application startup

`solarinspector.py` validates the required application secret and then calls
`prepare_database_for_startup` before constructing `Database`, `Collector`, or
Flask. Consequently, no collection thread, HTTP listener, or device adapter
can start against an unchecked schema.

The startup state machine is:

1. Missing or zero-byte path: create the established empty Phase-09 baseline.
2. Open the file read-only and run integrity, version, plan, and central-table
   readability checks.
3. Older/unversioned schema: create and verify a private backup, then migrate
   transactionally to schema 2.
4. Schema 2: verify the complete target schema without writing or creating a
   redundant backup.
5. Unknown newer, corrupt, incomplete, or failed migration: raise
   `DatabaseStartupError` and abort process initialization.
6. Only after success, construct the normal `Database` and `Collector`.

There is no retry loop. One process start attempts preparation once. When a
migration fails after backup creation, the error includes the verified backup
path; SQLite rolls back the migration transaction and the process exits
nonzero. An operator must diagnose the cause before restarting.

The optional `SOLARINSPECTOR_DATABASE_PATH` environment variable selects an
alternative database file before module import. Its default remains
`app/data/solarinspector.db`. Tests use it to keep import-time startup isolated
from local or productive data. Production services should set it only to an
absolute path owned by the SolarInspector service account.

Startup compatibility is tested for a missing database, the characterized
synthetic 4.1.3 shape, the Phase-09 intermediate schema, and current schema 2.
An unknown schema 3 is rejected without backup or mutation. A forced migration
failure is attempted exactly once and produces a chained, actionable error.

## Supported version 1 sources

The migration accepts the unversioned 48-column `samples` table characterized
for SolarInspector 4.1.3. It also accepts the older 21-column “v3-style” base
and the characterized Phase 05, Phase 06/07, Phase 08, and Phase 09
intermediate shapes. Unknown columns are tolerated, preserved, and recorded
as findings.

The synthetic input fixture is documented in
[`tests/fixtures/database/README.md`](../../../tests/fixtures/database/README.md).
No real 4.1.x backup was available, so 4.1.x support is limited to the
repository-characterized 4.1.3 shape. Missing base columns cause a safe
rollback.

## Transformation

1. Start `BEGIN IMMEDIATE`.
2. Verify the 21 invariant base columns; recognize the remaining characterized
   4.1.3 columns when present.
3. Create `schema_migrations`, `migration_findings`, and the finding index.
4. Record unknown `samples` columns without reading their values.
5. Add missing Phase 05–09 compatibility columns.
6. Create missing phase, official-grid, validation, and balance tables.
7. Create the characterized indexes.
8. Record local timestamps that are not timezone-aware ISO-8601 text.
9. Insert the version 1 ledger row.
10. Verify all target columns, indexes, checksums, and cascade foreign keys.
11. Commit.

Every step uses the caller-owned SQLite connection and one transaction.
Failure at any step triggers `rollback()`; version 1 is not recorded.

## Value preservation

- Existing rows and primary keys remain unchanged.
- Existing power values remain in watts with their original signs.
- Existing per-cycle energy values remain in Wh; they are not reclassified as
  physical cumulative counters.
- Missing later fields are added as nullable and contain `NULL`.
- Physical grid import/export totals are not reconstructed.
- Phase values, validation quality, energy balances, and source decisions are
  not backfilled.
- A real zero remains numeric zero.
- Unknown columns and uninterpretable timestamps are preserved as-is.

The migration never guesses a unit, timezone, source, quality, or historical
measurement.

## Findings

Version 1 currently emits:

| Code | Condition | Action |
| --- | --- | --- |
| `unknown_legacy_column` | Additional column outside the known 4.1.x and Phase 05–09 sets | Preserve column and record its name |
| `uninterpretable_legacy_timestamp` | `ts_local` is invalid, naive, or lacks a UTC offset | Preserve text and reference the source row |

Finding JSON contains only the migration action. It does not contain the
unknown value, device response, serial number, address, or credential.

## Programmatic use

The transformation API remains intentionally low-level:

```python
with sqlite3.connect(database_copy) as connection:
    apply_migrations(
        connection,
        application_version="4.5.0",
    )
```

The caller must supply a database copy and must not have an open transaction.
`apply_migrations` commits on success and raises a specific schema exception
or `sqlite3.DatabaseError` on failure. Operational callers should instead use
`inspect_database`, `create_database_backup`, `dry_run_database_migration`, or
`migrate_database_with_backup`, which enforce the file-level safety sequence.

## Maintenance CLI

Common options:

- `--database PATH`: database file; defaults to the application data path;
- `--backup-directory PATH`: defaults to a `backups` directory beside the
  selected database;
- `--application-version VERSION`: migration-ledger value; defaults to the
  repository `VERSION`.

Exactly one action is required:

```bash
python app/database_cli.py --check-database --database app/data/solarinspector.db
python app/database_cli.py --database-info --database app/data/solarinspector.db
python app/database_cli.py --backup-database --database app/data/solarinspector.db
python app/database_cli.py --migrate-database --dry-run --database app/data/solarinspector.db
python app/database_cli.py --migrate-database --database app/data/solarinspector.db
```

`--check-database` verifies SQLite integrity, version metadata, known central
tables, and prints the pending migration plan. `--database-info` additionally
prints only safe table counts—never rows, JSON details, device identities, or
configuration secrets. Both open SQLite with `mode=ro` and `query_only`.

`--backup-database` creates a standalone verified backup without migration.
`--migrate-database --dry-run` copies through SQLite's online backup API,
applies all pending migrations to the temporary copy, verifies target schema,
integrity, and preserved domain row counts, then removes the copy. It does not
write the source, create a persistent backup, start WAL, or update file
timestamps.

Real `--migrate-database` performs the same source checks, creates and verifies
a persistent backup, prints its path, and only then opens the source writable.
Migration and ledger changes use the existing single transaction. A failure
rolls back the database while retaining the backup for recovery.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Requested operation completed and verified |
| `2` | Invalid or contradictory CLI syntax |
| `3` | Path, SQLite, integrity, schema, backup, or migration failure |

The CLI requires filesystem read permission for checks/dry-run and write
permission for the backup directory. A real migration additionally requires
write permission for the database and its directory. It must be run while no
older SolarInspector process is writing the database.

## Backup contract

Backups use SQLite's online backup API rather than copying only the main file,
so committed WAL content is included consistently. The source first passes
`PRAGMA integrity_check`; the backup then passes the same check and must match
the source schema version and all readable domain-table row counts.

The filename includes target schema, UTC date/time, and source schema:

```text
solarinspector-before-schema-2-20260726T201530Z-from-0.db
```

New backup directories are mode `0700`; backup files are mode `0600`.
Existing destinations are never overwritten. A temporary private file is
atomically renamed only after verification. Backups and temporary databases
must remain outside Git.

## Restore procedure

Restore is deliberately an operator procedure, not a CLI command: replacing
the active database is destructive and requires coordination with the running
service.

1. Stop SolarInspector and confirm no Collector, web process, export, or
   migration still has the database open.
2. Run `--check-database` against the selected backup.
3. Preserve the failed/current database under a new diagnostic filename;
   never overwrite the verified backup.
4. Remove or preserve the current database's `-wal` and `-shm` files together
   with that failed database. Never combine sidecars from different copies.
5. Copy the verified backup to a new temporary file in the active database
   directory, set mode `0600`, then atomically rename it to
   `solarinspector.db`.
6. Run `--check-database` against the restored active path.
7. Start SolarInspector and check `/api/health`, current schema, sample count,
   latest sample, and logs before re-enabling automatic collection.

If backup integrity fails, schema is newer than the installed application,
row counts are implausible, disk space is insufficient, permissions prevent
an atomic rename, or the old process cannot be stopped, abort restore and keep
all copies unchanged. Restoring an unversioned pre-migration backup is
supported as rollback data, but the current application may subsequently
require a fresh dry-run and migration before startup.

## Verification

Automated tests build temporary databases from the reviewed layered 4.1.3 and
Phase 05–09 fixtures, preserve every existing domain row, exercise
unknown-column and timestamp findings, run `PRAGMA integrity_check`, and
confirm the target schema version. Every intermediate migration is executed a
second time to prove that rows and schema objects are not duplicated. The
older v3-style path separately verifies that later fields are not invented.

Tests verify read-only inspection, private permissions, collision refusal,
source immutability, backup-before-write notification, dry-run isolation,
integrity and row-count comparison, retained backup after migration failure,
CLI output, and nonzero failure exit status.

The user-authorized local `app/data/solarinspector.db` was additionally checked
with `--database-info` and `--migrate-database --dry-run`. It was an empty
unversioned Phase-09-shaped database, passed integrity checking, and reached
target schema 2 on the temporary copy. Its SHA-256 digest remained
`c6862767d5b3783b4af8f1d74f84b55beafb20a6b493b5a762a2e6af400dc6dd`
before and after. This is a local empty database check, not evidence from a
productive or historical 4.1.x installation.
