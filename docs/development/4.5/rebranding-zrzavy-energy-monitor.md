# Zrzavy Energy Monitor rebranding

## Block R.2 decision

Zrzavy Energy Monitor is the canonical product identity for version 4.5.0.
Product metadata and environment-variable compatibility are centralized before
the entry point and the remaining core package move in later blocks. Importing
the new modules performs no network or filesystem operations.

The complete public name is **Zrzavy Energy Monitor**. `ZEM` is supplementary
only and must not be used as the sole public product, repository, page, or
release name.

## Canonical metadata

`app/zrzavy_energy_monitor_core/branding.py` owns the approved values:

| Metadata | Canonical value |
| --- | --- |
| Product name | `Zrzavy Energy Monitor` |
| Product ID | `zrzavy-energy-monitor` |
| Description | `Open-source home energy monitoring and validation` |
| Supplementary abbreviation | `ZEM` |
| GitHub owner | `zrzavywa` |
| GitHub repository | `zrzavy-energy-monitor` |
| User-agent product token | `ZrzavyEnergyMonitor` |

`SolarInspector` remains available as explicit legacy product and repository
metadata. Updater, UI, API, release, and documentation consumers switch to the
central values in their assigned later blocks; R.2 does not rename the live
repository or release artifacts.

## Environment compatibility

The canonical variables and temporary legacy aliases are:

| Canonical variable | Legacy alias |
| --- | --- |
| `ZRZAVY_ENERGY_MONITOR_SECRET` | `SOLARINSPECTOR_SECRET` |
| `ZRZAVY_ENERGY_MONITOR_CONFIG_PATH` | `SOLARINSPECTOR_CONFIG_PATH` |
| `ZRZAVY_ENERGY_MONITOR_DATABASE_PATH` | `SOLARINSPECTOR_DATABASE_PATH` |
| `ZRZAVY_ENERGY_MONITOR_UPDATE_STATUS_PATH` | `SOLARINSPECTOR_UPDATE_STATUS_PATH` |
| `ZRZAVY_ENERGY_MONITOR_UPDATE_REQUEST_PATH` | `SOLARINSPECTOR_UPDATE_REQUEST_PATH` |
| `ZRZAVY_ENERGY_MONITOR_UPDATE_CACHE_DIR` | `SOLARINSPECTOR_UPDATE_CACHE_DIR` |

Resolution is deterministic:

1. Use the canonical variable when it is set.
2. If only the legacy alias is set, use it and log one deprecation warning.
3. If both values are identical, use the canonical variable without warning.
4. If both values differ, use the canonical variable and log one conflict
   warning.
5. If neither is set, use the caller-provided documented default.

Warnings name variables but never values. This is mandatory for secret
redaction and applies equally to non-secret values to avoid exposing private
paths. Legacy aliases remain supported during the 4.5 stabilization period;
their eventual removal requires a separately documented compatibility
decision.

R.2 connects the application secret to this resolver. Runtime path consumers
remain unchanged until R.4 so importing or deploying R.2 cannot select,
create, copy, or migrate a database.

## Deferred work

- R.4 connects configuration, database, update, log, and PID paths.
- R.5/R.6 implement backup, direct migration, release, and service changes.
- R.7 switches web and API product metadata.
- R.8 completes current user and operator documentation.
- R.9 performs gated end-to-end verification before repository rename.

No productive installation, repository name, systemd unit, data file, metric,
validation rule, source-selection rule, persistence schema, or energy-balance
semantic is changed by R.2.

## Block R.3 entry point and namespace

The canonical application entry point is
`app/zrzavy_energy_monitor.py`. The former `app/solarinspector.py` contains no
application logic: it imports `main` from the canonical module, emits a
`DeprecationWarning`, and delegates execution. The wrapper is retained for the
4.5 series; new commands and integrations must use the canonical entry point.

The complete core implementation was moved with `git mv` to
`app/zrzavy_energy_monitor_core`. All application, tool, benchmark, and test
imports now use that namespace. There is no copied implementation.

`app/solarinspector_core/__init__.py` is the only retained package
compatibility module. It warns on import and documents the canonical
replacement. Concrete legacy submodule paths are not retained: they were
internal implementation paths, all repository consumers now use canonical
imports, and recreating the entire old module tree would risk duplicate module
instances and class identities. The package-root bridge remains through the
4.5 series and its later removal requires a documented compatibility decision.

R.3 does not change runtime data paths, database names, environment precedence,
service units, release artifacts, updater repository selection, web/API
branding, or the GitHub repository name.

## Block R.4 runtime paths and data filenames

Runtime paths are resolved by the immutable `RuntimePaths` model in
`zrzavy_energy_monitor_core.paths`. Importing the module never creates, moves,
copies, opens, or deletes runtime data. Resolution order is:

1. explicit `ZRZAVY_ENERGY_MONITOR_*` path variable;
2. documented `SOLARINSPECTOR_*` compatibility alias;
3. for updater paths only, the actually used historical aliases without
   `_PATH` or `_DIR`;
4. detected installation default.

An explicit canonical path selects canonical mode even if an old local
database remains present. An explicit legacy path or a source-tree
`data/solarinspector.db` selects legacy mode. A release below
`/opt/zrzavy-energy-monitor` uses the canonical Linux paths; a release below
`/opt/solarinspector` uses the old paths until the controlled R.5 migration.

Clean source-tree execution uses:

| Purpose | Local canonical default |
| --- | --- |
| Configuration | `app/config.json` |
| Database | `app/data/zrzavy-energy-monitor.db` |
| Log | `app/data/zrzavy-energy-monitor.log` |
| PID | `app/data/zrzavy-energy-monitor.pid` |
| Update status | `app/data/update-status.json` |
| Update request | `app/data/update-request.json` |
| Update cache | `app/data/updates` |

Installed canonical execution uses `/etc/zrzavy-energy-monitor`,
`/var/lib/zrzavy-energy-monitor`, `/var/cache/zrzavy-energy-monitor`, and
`/var/log/zrzavy-energy-monitor` as specified by the work order.

R.4 performs no automatic file migration. Tests prove that selecting canonical
paths and selecting the legacy path again as rollback leave a synthetic SQLite
database byte-identical, integral, and semantically unchanged, including a
real zero, `NULL`, and historical timestamps. Backup, stopped-service file
movement, ownership preservation, fsync, healthcheck, and operational rollback
belong to R.5.

## Block R.5 direct 4.1.3 migration

The one-time migration command is
`scripts/migrate-to-zrzavy-energy-monitor.sh`. Its data layer provides three
mutually exclusive modes:

- `--dry-run` validates all legacy inputs, confirms that no canonical data or
  earlier migration backup exists, and reports SQLite integrity and table row
  counts without writing.
- `--apply --services-stopped` creates a private, deterministic backup and
  copies the configuration and SQLite database to canonical paths. Existing
  targets are never overwritten.
- `--rollback --services-stopped` verifies the backup, preserves canonical
  diagnostic copies, and atomically restores the legacy configuration and
  database.

The backup contains the complete `/opt/solarinspector` installation tree, the
legacy configuration, a consistent SQLite backup, the old log when present,
the three SolarInspector systemd unit files, and a redacted migration manifest.
File modes are copied, ownership is preserved when the command has permission,
and files plus containing directories are synchronized before activation.
SQLite uses the backup API rather than a byte copy and must pass
`PRAGMA integrity_check`; table row counts must match before a target is
accepted. Measurement tables, metric names, source identifiers, schemas, real
zero values, `NULL` values, and historical timestamps are not rewritten.

Mutating modes deliberately require the explicit `--services-stopped`
precondition. R.5 does not invoke `systemctl`, install new units, activate a
release, perform an HTTP healthcheck, remove legacy paths, or touch a productive
installation. R.6 will provide the privileged Linux orchestration around this
tested data layer, including service-conflict prevention, new units,
healthcheck, and automatic operational rollback.

R.5 is tested only against isolated synthetic copies in temporary directories.
The repository rename gate therefore remains closed until R.6 and R.9 verify a
copy of the actual installation and the complete service/healthcheck sequence.

## Block R.6 release, Linux, and systemd

Release 4.5.0 uses the archive contract
`zrzavy-energy-monitor-4.5.0.tar.gz` plus the corresponding `.sha256` file.
The release manifest, build script, GitHub workflow, download lookup, archive
validator, smoke test, and updater user agent use the same canonical
identifiers. Legacy Raspberry Pi installer scripts remain in the repository
for historical rollback context but are excluded from new release archives.

The canonical units are `zrzavy-energy-monitor.service`,
`zrzavy-energy-monitor-updater.service`, and
`zrzavy-energy-monitor-updater.path`. The application unit declares
`Conflicts=solarinspector.service`; the migration script also checks both
collectors before and after stopping the old service. An upgraded host retains
the existing `solarinspector` Unix user by design. This avoids an untested UID
and ownership migration while visible service, path, executable, environment,
and description identifiers become canonical.

`scripts/migrate-to-zrzavy-energy-monitor.sh --orchestrate-systemd` layers
privileged service control around the R.5 data migration. It requires root and
an already prepared canonical 4.5.0 release, stops the old updater path and
collector, verifies that neither collector remains active, installs the three
new units, reloads systemd, starts exactly one collector, and checks
`/api/health` for version 4.5.0. Only after success does it enable the new
updater path and disable the old units. An error trap stops the new service,
rolls the data migration back, reloads systemd, and restarts the legacy units.

Old installation files and units are not deleted even without
`--keep-legacy-paths`; deletion remains prohibited before the final migration
gate. Repository tests validate scripts, paths, conflict declarations,
artifact metadata, archive structure, checksum, healthcheck behavior, and
rollback behavior. No command was run against systemd or a productive
installation in R.6, and no Debian/Raspberry Pi hardware result is claimed.

## Block R.7 web and API branding

All current browser-visible product text uses the full name
Zrzavy Energy Monitor. The header, document titles, footer, update states,
runtime help and log messages, configuration safety notice, and CSV download
filenames use canonical branding. `ZEM` appears only as the supplementary
header mark immediately beside the full name; it is never the sole page title
or wordmark.

The configurable `general.project_name` remains an installation label. The
former untouched default value `SolarInspector` is normalized to
`Zrzavy Energy Monitor` on load, while every custom label is preserved. The
update page includes the allowed historical notice that Zrzavy Energy Monitor
was named SolarInspector through version 4.1.3 and that the direct upgrade
retains data and configuration.

The existing `/api/health` and `/api/system/version` paths, status codes, and
domain fields remain stable. Both responses now add:

- `product_name`: `Zrzavy Energy Monitor`
- `product_id`: `zrzavy-energy-monitor`
- `product_description`: `Open-source home energy monitoring and validation`

The pre-existing `product` field of the version response now carries the
canonical full name. Measurement, source, energy, validation, persistence, and
update payload structures are otherwise unchanged. Tests cover every rendered
page, the historical upgrade notice, API metadata, legacy-default
normalization, custom-label preservation, and canonical CSV filenames.

## Block R.8 documentation and naming policy

The active README, documentation index, installation, configuration,
operation, update, troubleshooting, architecture, API, security, device, and
SHRDZM documents now describe Zrzavy Energy Monitor 4.5.0 with canonical
repository, release, service, environment, and filesystem identifiers. The
English short description is kept verbatim in the primary README files.

SolarInspector remains only where the reader must understand the former
4.1.3 product, an old path or unit used as a migration source, a compatibility
alias, or a historical development result. The old Raspberry Pi 3.x/4.0.x text
is explicitly marked historical and unsuitable for new installations.
Historical changelog sections and completed phase reports are not rewritten.

### Removal plan

- Keep `SOLARINSPECTOR_*`, the legacy entry point, and the package-root bridge
  through the 4.5 stabilization period.
- Keep old paths and unit backups until the productive migration and rollback
  rehearsal pass the R.9 gate.
- Remove compatibility only in a separately announced release after usage and
  rollback requirements have been reviewed.
- Never reinterpret old database metrics, sources, schemas, or history as
  branding that should be rewritten.

### Remaining technical debt

- The repository and local checkout still have the old repository name until
  R.9.
- Historical development reports contain the former name by design and need
  contextual interpretation.
- The upgrade service user may remain `solarinspector` to preserve UID and
  ownership, while new installations use `zemonitor`.
- Real Debian/Raspberry Pi rendering, service, device, migration, healthcheck,
  and rollback verification remains part of the final gate.
