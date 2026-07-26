# Direct migration from SolarInspector 4.1.3

This document describes the prepared direct upgrade to Zrzavy Energy Monitor
4.5.0. It does not authorize running it on the productive installation. A
production-copy rehearsal and final approval remain mandatory.

## Preconditions

- The source must be SolarInspector 4.1.3.
- The legacy configuration, SQLite database, installation root, and three
  systemd unit files must be regular, readable inputs.
- Neither the old nor the new collector may write during `--apply` or
  `--rollback`.
- Canonical configuration and database targets must not already exist.
- The deterministic migration backup must not already exist.
- Sufficient free space is required for the full installation, configuration,
  database, optional log, unit files, and temporary atomic copies.

The data-only mutating commands enforce an explicit `--services-stopped` flag.
The R.6 systemd orchestrator adds the root check and independently verifies and
controls service state.

## Default paths

| Purpose | Legacy source | Canonical target |
| --- | --- | --- |
| Installation | `/opt/solarinspector` | prepared in R.6 |
| Configuration | `/etc/solarinspector/config.json` | `/etc/zrzavy-energy-monitor/config.json` |
| Database | `/var/lib/solarinspector/data/solarinspector.db` | `/var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db` |
| Log | `/var/log/solarinspector/solarinspector.log` | `/var/log/zrzavy-energy-monitor/zrzavy-energy-monitor.log` |
| Backup | — | `/var/lib/zrzavy-energy-monitor/backups/solarinspector-4.1.3-to-zrzavy-energy-monitor-4.5.0` |

The default unit inputs are `solarinspector.service`,
`solarinspector-updater.service`, and `solarinspector-updater.path` below
`/etc/systemd/system`. Every path can be overridden for an isolated rehearsal;
`--source-systemd-unit` is repeatable and replaces the default list when used.

## Dry run

Run the read-only validation before any migration:

```console
sudo scripts/migrate-to-zrzavy-energy-monitor.sh --dry-run
```

The JSON result has status `ready` only when all source inputs are present, the
SQLite integrity check succeeds, table row counts can be read, and neither the
target data nor a previous backup exists. The dry run creates no directory or
file.

## Backup and apply

Only the R.6 service orchestrator or an operator who independently proved that
both collectors are stopped may run:

```console
sudo scripts/migrate-to-zrzavy-energy-monitor.sh \
  --apply \
  --services-stopped
```

Before creating canonical data, the command creates a mode-`0700` backup with:

- a complete copy of `/opt/solarinspector`;
- `config.json`, retaining its mode and, when permitted, ownership;
- a consistent `solarinspector.db` made with the SQLite backup API;
- `solarinspector.log` when the old log exists;
- the three legacy systemd unit files;
- a mode-`0600` manifest containing paths, fingerprints, integrity results, row
  counts, timestamps, and status, but no configuration values or exception
  messages.

Configuration and database are copied through temporary files, synchronized,
verified, and atomically renamed. Existing canonical targets are never
overwritten. The database schema and contents are not transformed: in
particular, measurement history, metrics, source IDs, timestamps, real zeroes,
and `NULL` values remain unchanged. The old log is retained; new logging starts
at the canonical path after R.6 activates the new service.

Exit code `0` means the requested mode completed. Exit code `2` means a
controlled safety refusal or migration failure. A failed apply records only the
exception type in the private manifest and leaves the legacy source in place.

## Rollback

With both collectors independently confirmed stopped:

```console
sudo scripts/migrate-to-zrzavy-energy-monitor.sh \
  --rollback \
  --services-stopped
```

Rollback verifies the backed-up database and its original row counts, stores
diagnostic copies of canonical configuration and database below
`failed-target`, and atomically restores the legacy configuration and database.
It does not delete canonical files. The R.6 operational wrapper reloads
systemd and starts only the legacy collector after a failed switch. The
backed-up installation and units remain available for manual recovery.

## Automated systemd migration

The canonical release must already be prepared below
`/opt/zrzavy-energy-monitor/current`. Start with:

```console
sudo scripts/migrate-to-zrzavy-energy-monitor.sh \
  --orchestrate-systemd \
  --dry-run \
  --keep-legacy-paths
```

After reviewing the JSON plan, the approved cutover command is:

```console
sudo scripts/migrate-to-zrzavy-energy-monitor.sh \
  --orchestrate-systemd \
  --apply \
  --keep-legacy-paths
```

The script refuses an already active new collector, stops the old updater path
and collector, verifies that both collectors are inactive, runs the R.5 data
migration, installs the three canonical units, reloads systemd, and starts the
new collector. It accepts the switch only when `/api/health` reports `ok` and
version `4.5.0`. It then enables the new updater path and disables the old
units. On any later error, the error trap stops the new service, restores the
R.5 data backup, reloads systemd, and starts the old collector and updater path.

The canonical application unit explicitly conflicts with
`solarinspector.service`. Existing upgrades continue to use the Unix user
`solarinspector`, preserving its UID and file ownership.

## New interfaces

New service definitions and operator configuration use
`ZRZAVY_ENERGY_MONITOR_*` variables. The corresponding
`SOLARINSPECTOR_*` variables remain temporary compatibility aliases for the
4.5 stabilization period, with canonical values taking precedence.

The repository remains named `SolarInspector` until the final gate. Release
artifact naming, new service files, installer changes, service healthcheck, and
repository rename are not part of R.5.

## Manual migration and healthcheck

If automatic orchestration cannot be used, do not improvise destructive moves.
Stop and disable the old collector and updater path, verify that neither old
nor new collector is active, run the documented data-only `--apply` command,
install the three canonical unit files, and run `systemctl daemon-reload`.
Start only `zrzavy-energy-monitor.service`, then require:

```console
curl --fail http://127.0.0.1:8787/api/health
```

The response must contain status `ok`, version `4.5.0`, product ID
`zrzavy-energy-monitor`, and healthy database/web fields. Only then enable
`zrzavy-energy-monitor-updater.path` and disable the old units. If any check
fails, stop the new service and follow the rollback procedure before restarting
the old collector.

## Repository rename

The GitHub repository is renamed only in R.9 after the mandatory migration
gate. Until then, source checkout and remote settings may still show the former
repository name even though application, release, service, and documentation
identifiers are prepared for `zrzavywa/zrzavy-energy-monitor`. The rename must
not be used as evidence that the productive migration has passed.

## Known limitations

- R.5 has been verified with synthetic temporary installations only, not the
  productive host or real devices.
- Data-only mode does not call `systemctl`; service operations require the
  explicit `--orchestrate-systemd` option and root.
- The orchestrator requires a separately prepared canonical 4.5.0 release. It
  does not download artifacts or create the release virtual environment.
- Neither mode removes old paths, units, PID files, or user accounts.
- The repository rename gate remains closed until migration against a copy of
  the single installation, service conflict checks, healthcheck, device access,
  and rollback have all succeeded.
