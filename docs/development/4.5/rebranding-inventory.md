# Block R.1: SolarInspector rebranding inventory

## Scope and baseline

This inventory implements block R.1 / WR-01 of
`rebranding-work-order.yaml`. It records the state at commit `f403a63` on
branch `feature/4.5-rebrand-zrzavy-energy-monitor`. R.1 changes no product
code, runtime configuration, repository metadata, release artifact, service,
database, or productive installation.

The canonical target is:

| Concern | Legacy identifier | Planned canonical identifier | R.1 classification and action |
| --- | --- | --- | --- |
| Public product name | `SolarInspector` | `Zrzavy Energy Monitor` | Current public brand; replace in R.7/R.8. Retain only in explicit history and migration text. |
| Product ID | `solarinspector` | `zrzavy-energy-monitor` | Canonical technical identifier; replace through the responsible later blocks. |
| Abbreviation | none | `ZEM` | Supplementary internal abbreviation only; never use as the sole public name. |
| Description | existing descriptions | `Open-source home energy monitoring and validation` | Centralize in R.2 and publish in R.7/R.8. |
| Repository | `zrzavywa/SolarInspector` | `zrzavywa/zrzavy-energy-monitor` | Prepare in R.6/R.8; rename only after the R.9 gate. |
| Executable | `solarinspector` | `zrzavy-energy-monitor` | Migrate in R.3/R.6 with a documented compatibility path. |
| Python entry point | `app/solarinspector.py` | `app/zrzavy_energy_monitor.py` | Move canonical logic in R.3; retain the old file only as a thin wrapper. |
| Python package | `solarinspector_core` | `zrzavy_energy_monitor_core` | Move with `git mv` in R.3; add only required legacy import wrappers. |
| Environment prefix | `SOLARINSPECTOR_*` | `ZRZAVY_ENERGY_MONITOR_*` | Add new-first resolution and redacted warnings in R.2; retain documented fallbacks for 4.5 stabilization. |
| Release prefix | `SolarInspector-` | `zrzavy-energy-monitor-` | Change archive, checksum, manifest, and updater references in R.6. |
| User agent | `SolarInspector/<VERSION>` | `ZrzavyEnergyMonitor/<VERSION>` | Centralize in R.2 and use in updater code in R.6. |
| Application service | `solarinspector.service` | `zrzavy-energy-monitor.service` | Migrate in R.5/R.6; old and new collectors must never run together. |
| Updater service | `solarinspector-updater.service` | `zrzavy-energy-monitor-updater.service` | Migrate in R.6 with rollback. |
| Updater path unit | `solarinspector-updater.path` | `zrzavy-energy-monitor-updater.path` | Migrate in R.6 in the same sequence as the updater service. |
| Installation root | `/opt/solarinspector` | `/opt/zrzavy-energy-monitor` | Migrate only from a stopped service in R.5/R.6. |
| Configuration directory | `/etc/solarinspector` | `/etc/zrzavy-energy-monitor` | Preserve content and permissions in R.5/R.6. |
| State directory | `/var/lib/solarinspector` | `/var/lib/zrzavy-energy-monitor` | Back up and migrate atomically where possible in R.5. |
| Cache directory | `/var/cache/solarinspector` | `/var/cache/zrzavy-energy-monitor/updates` | Migrate updater state in R.5/R.6. |
| Log directory | `/var/log/solarinspector` | `/var/log/zrzavy-energy-monitor` | Preserve logs for audit and rollback in R.5/R.6. |
| Database basename | `solarinspector.db` | `zrzavy-energy-monitor.db` | Preserve bytes, rows, schema, `NULL`, zero values, and timestamps in R.4/R.5. |
| Log basename | `solarinspector.log` | `zrzavy-energy-monitor.log` | Resolve compatibly in R.4; do not rewrite existing logs. |
| PID basename | `solarinspector.pid` | `zrzavy-energy-monitor.pid` | Resolve compatibly in R.4; avoid concurrent collectors. |
| Service user | `solarinspector` | `zemonitor` for new installs | Existing installations initially retain the legacy UID/user unless ownership and rollback are verified. |

`ZEM` is not an alternative value in the matrix: it may appear only after the
full name or as a documented internal compatibility abbreviation.

## Search method and results

The required case-sensitive spellings were searched in all work-order file
types, including hidden repository files but excluding `.git` and `.venv`.
The inventory found 1,455 matching lines in 229 text files. Since a line can
contain multiple occurrences, occurrence counts are separate:

| Exact spelling | Occurrences |
| --- | ---: |
| `SolarInspector` | 368 |
| `SOLARINSPECTOR` | 73 |
| `solarinspector` | 1,056 |
| `Solarinspector` | 4 |

The explicitly required identifiers were all found:

| Identifier | Occurrences | Planned treatment |
| --- | ---: | --- |
| `solarinspector.py` | 32 | New canonical entry point plus legacy wrapper in R.3. |
| `solarinspector_core` | 673 | New canonical package plus targeted compatibility imports in R.3. |
| `solarinspector.db` | 45 | Compatible path resolution in R.4; integrity-preserving migration in R.5. |
| `solarinspector.log` | 4 | Compatible path resolution in R.4 and operational migration in R.6. |
| `solarinspector.pid` | 4 | Compatible path resolution in R.4 and collision prevention in R.6. |
| `solarinspector.service` | 44 | Controlled service transition in R.5/R.6. |
| `solarinspector-updater.service` | 10 | Controlled updater transition in R.6. |
| `solarinspector-updater.path` | 11 | Controlled path-unit transition in R.6. |
| `/opt/solarinspector` | 48 | Backup and controlled migration in R.5/R.6. |
| `/etc/solarinspector` | 24 | Preserve configuration and permissions in R.5/R.6. |
| `/var/lib/solarinspector` | 41 | Preserve database and state in R.4/R.5. |
| `/var/cache/solarinspector` | 10 | Migrate updater cache handling in R.4/R.6. |
| `/var/log/solarinspector` | 8 | Preserve old logs and use the new path after migration. |
| `SolarInspector-` | 93 | Change current release naming in R.6; retain historical 4.1.3 references. |
| `zrzavywa/SolarInspector` | 11 | Retain as migration source; switch current links after the repository gate. |
| `SOLARINSPECTOR_SECRET` | 20 | Legacy fallback with warning; new variable wins and values remain redacted. |

The counts intentionally include the work order itself. This makes the search
reproducible but does not turn its explicit legacy examples into product
usage.

## Complete affected-path list

Every matching line inherits the category and action of its group below.
Counts in parentheses are matching lines, not occurrence counts.

### Current public brand, configuration, release, and operational interfaces

Category: **current public brand** or **canonical technical identifier**.
Action: update in R.2 and R.4–R.8 while retaining compatibility where the
matrix requires it.

```text
.github/workflows/release.yml (3)
.github/workflows/test.yml (1)
CHANGELOG.md (1)
CONTRIBUTING.md (4)
README.md (9)
TRADEMARKS.md (2)
app/config.example.json (1)
app/config.json (1; ignored local configuration, inspect only and never commit)
app/database_cli.py (6)
app/github_updater.py (5)
app/modbus_solakon.py (3)
app/release_installer.py (8)
app/solarinspector.py (38)
app/static/app.css (2)
app/static/update.js (4)
app/templates/base.html (2)
app/templates/configuration.html (1)
app/templates/update.html (1)
app/updater_service.py (11)
release-manifest.json (3)
scripts/Diagnose-SolarInspector-RaspberryPi.sh (2)
scripts/Rollback-SolarInspector-RaspberryPi.sh (3)
scripts/Upgrade-SolarInspector-RaspberryPi.sh (25)
scripts/build-release.sh (1)
scripts/install-updater-bootstrap.sh (17)
systemd/solarinspector-updater.path (3)
systemd/solarinspector-updater.service (8)
tools/capture_tasmota_grid_meter.py (3)
tools/migrate_config.py (2)
updater/release_installer.py (8)
updater/updater_service.py (11)
```

The local `app/config.json` is ignored and may contain private settings. Later
blocks must validate behavior using fixtures or temporary files, never copy
this file into a patch or test output.

### Canonical Python implementation

Category: **canonical technical identifier**. Most matches are import paths,
module names, logger names, defaults, or type/module representations rather
than user-facing branding. Action: move the implementation with `git mv` in
R.3, update imports mechanically but review semantic strings individually,
and add no duplicate product logic.

```text
app/solarinspector_core/__init__.py (1)
app/solarinspector_core/adapters/__init__.py (4)
app/solarinspector_core/adapters/base.py (1)
app/solarinspector_core/adapters/compatibility.py (6)
app/solarinspector_core/adapters/grid_meter_factory.py (4)
app/solarinspector_core/adapters/shelly.py (10)
app/solarinspector_core/adapters/shrdzm_grid_meter.py (7)
app/solarinspector_core/adapters/solakon_measurement.py (7)
app/solarinspector_core/adapters/tasmota_grid_meter.py (7)
app/solarinspector_core/config/defaults.py (8)
app/solarinspector_core/config/energy_balance.py (1)
app/solarinspector_core/config/grid_meter.py (1)
app/solarinspector_core/config/manager.py (12)
app/solarinspector_core/logging.py (2)
app/solarinspector_core/models/__init__.py (2)
app/solarinspector_core/models/device.py (3)
app/solarinspector_core/models/energy_balance.py (1)
app/solarinspector_core/models/legacy.py (3)
app/solarinspector_core/models/measurement.py (5)
app/solarinspector_core/models/metrics.py (1)
app/solarinspector_core/models/source_selection.py (4)
app/solarinspector_core/models/units.py (2)
app/solarinspector_core/paths.py (8)
app/solarinspector_core/persistence/__init__.py (1)
app/solarinspector_core/persistence/database.py (8)
app/solarinspector_core/persistence/maintenance.py (3)
app/solarinspector_core/persistence/queries.py (2)
app/solarinspector_core/persistence/retention.py (1)
app/solarinspector_core/persistence/startup.py (3)
app/solarinspector_core/runtime.py (4)
app/solarinspector_core/services/collector.py (21)
app/solarinspector_core/services/dashboard.py (4)
app/solarinspector_core/services/demo.py (1)
app/solarinspector_core/services/energy_balance.py (4)
app/solarinspector_core/services/energy_balance_collector.py (7)
app/solarinspector_core/services/periods.py (2)
app/solarinspector_core/services/source_selector.py (7)
app/solarinspector_core/services/update.py (1)
app/solarinspector_core/services/version.py (1)
app/solarinspector_core/validation/__init__.py (11)
app/solarinspector_core/validation/base.py (2)
app/solarinspector_core/validation/collector.py (11)
app/solarinspector_core/validation/config.py (2)
app/solarinspector_core/validation/context.py (5)
app/solarinspector_core/validation/engine.py (9)
app/solarinspector_core/validation/persistence.py (3)
app/solarinspector_core/validation/profiles.py (2)
app/solarinspector_core/validation/replay.py (8)
app/solarinspector_core/validation/result.py (2)
app/solarinspector_core/validation/rules/__init__.py (6)
app/solarinspector_core/validation/rules/cross_source.py (7)
app/solarinspector_core/validation/rules/device.py (2)
app/solarinspector_core/validation/rules/historical.py (4)
app/solarinspector_core/validation/rules/numeric.py (4)
app/solarinspector_core/validation/rules/phase.py (6)
app/solarinspector_core/validation/rules/time.py (3)
app/solarinspector_core/validation/state.py (3)
app/solarinspector_core/web/__init__.py (1)
app/solarinspector_core/web/api.py (9)
app/solarinspector_core/web/configuration.py (2)
app/solarinspector_core/web/context.py (1)
app/solarinspector_core/web/export.py (4)
app/solarinspector_core/web/pages.py (1)
```

### Tests, fixtures, benchmarks, and development tooling

Category: **test fixture** where a legacy name is asserted; otherwise
**canonical technical identifier** in test imports and paths. Action: update
canonical expectations alongside their responsible block and preserve
explicit compatibility cases. Tests must continue to cover measurement,
validation, source-selection, persistence, and energy-integration semantics.

```text
pyproject.toml (51)
scripts/persistence_timeseries_benchmark.py (4)
scripts/tasmota_grid_meter_soak.py (13)
scripts/validation_hardware_soak.py (1)
scripts/validation_replay_benchmark.py (7)
scripts/verify.sh (1)
tests/conftest.py (5)
tests/fakes/__init__.py (1)
tests/fakes/measurement_adapter.py (1)
tests/fixtures/database/README.md (3)
tests/fixtures/shelly/README.md (1)
tests/fixtures/shrdzm/rest/README.md (1)
tests/fixtures/solarkon/README.md (1)
tests/fixtures/tasmota/README.md (6)
tests/test_collector_characterization.py (2)
tests/test_collector_grid_meter.py (10)
tests/test_collector_phase_persistence.py (4)
tests/test_collector_shelly_snapshot.py (3)
tests/test_collector_solakon_snapshot.py (2)
tests/test_collector_validation.py (11)
tests/test_config_characterization.py (2)
tests/test_core.py (2)
tests/test_database_characterization.py (2)
tests/test_database_maintenance.py (5)
tests/test_database_migration_fixtures.py (1)
tests/test_database_migrations.py (2)
tests/test_database_startup.py (8)
tests/test_device_snapshot_metadata.py (3)
tests/test_energy_balance.py (8)
tests/test_energy_balance_api.py (1)
tests/test_energy_balance_collector.py (10)
tests/test_energy_balance_configuration.py (2)
tests/test_energy_balance_persistence.py (10)
tests/test_energy_balance_replay.py (9)
tests/test_energy_characterization.py (2)
tests/test_error_fallback_characterization.py (9)
tests/test_github_updater.py (6)
tests/test_grid_meter_adapter_factory.py (6)
tests/test_grid_meter_configuration.py (3)
tests/test_grid_meter_persistence_api.py (10)
tests/test_grid_meter_web.py (4)
tests/test_measurement_adapter_contract.py (3)
tests/test_measurement_compatibility.py (7)
tests/test_measurement_model.py (7)
tests/test_measurement_timeseries_persistence.py (11)
tests/test_phase_persistence.py (7)
tests/test_phase_power_analysis.py (1)
tests/test_phase_web_api.py (2)
tests/test_production_measurement_adapter_contract.py (9)
tests/test_release_installer.py (12)
tests/test_release_verification.py (5)
tests/test_shelly_aggregate_compatibility.py (5)
tests/test_shelly_characterization.py (2)
tests/test_shelly_gen1_phases.py (1)
tests/test_shelly_measurement_adapter.py (8)
tests/test_shelly_phase_configuration.py (6)
tests/test_shelly_phase_snapshot.py (5)
tests/test_shelly_pro3em_phases.py (1)
tests/test_shrdzm_grid_meter_adapter.py (9)
tests/test_shrdzm_grid_meter_end_to_end.py (8)
tests/test_solakon_measurement_adapter.py (6)
tests/test_solarkon_modbus_characterization.py (1)
tests/test_source_priority_characterization.py (2)
tests/test_source_selection_models.py (6)
tests/test_source_selector.py (8)
tests/test_source_time_alignment.py (8)
tests/test_tasmota_grid_meter_adapter.py (7)
tests/test_tasmota_grid_meter_hardware.py (13)
tests/test_tasmota_grid_meter_normalization.py (6)
tests/test_time_series_csv_export.py (6)
tests/test_time_series_queries.py (3)
tests/test_time_series_retention.py (4)
tests/test_update_api.py (6)
tests/test_update_download_api.py (8)
tests/test_updater_service.py (6)
tests/test_upgrade_script.py (6)
tests/test_validation_basic_rules.py (5)
tests/test_validation_configuration.py (2)
tests/test_validation_configuration_ui.py (4)
tests/test_validation_cross_source.py (6)
tests/test_validation_device_profiles.py (5)
tests/test_validation_engine.py (6)
tests/test_validation_event_persistence.py (20)
tests/test_validation_historical_rules.py (6)
tests/test_validation_models.py (5)
tests/test_validation_phase_rules.py (7)
tests/test_validation_replay.py (1)
tests/test_validation_replay_performance.py (7)
tests/test_validation_state.py (6)
tests/test_validation_web_api.py (6)
tests/test_version_consistency.py (4)
tests/test_web_api_characterization.py (3)
```

### Current user and operator documentation

Category: **current public brand** except where a passage explicitly describes
the old installation. Action: update current instructions in R.8; put retained
old names in clearly labelled migration/rollback context.

```text
docs/README-RaspberryPi.txt (25)
docs/README.md (5)
docs/api.md (3)
docs/architecture.md (8)
docs/configuration.md (11)
docs/development.md (3)
docs/devices.md (11)
docs/installation-raspberry-pi.md (52)
docs/operation.md (37)
docs/security.md (5)
docs/shrdzm-grid-meter.md (9)
docs/troubleshooting.md (26)
docs/updates.md (23)
```

### Historical development documentation

Category: **historical documentation**. Action: do not rewrite completed-phase
history merely to erase the former name. Update only statements that remain
normative for 4.5, and add explicit migration context if ambiguity would make
an old command look current.

```text
docs/development/4.5/database-migration.md (18)
docs/development/4.5/database-schema.md (2)
docs/development/4.5/grid-meter-mapping.md (2)
docs/development/4.5/measurement-conventions.md (3)
docs/development/4.5/phase-02-completion-report.md (5)
docs/development/4.5/phase-02-coverage-assessment.md (9)
docs/development/4.5/phase-02-test-inventory.md (5)
docs/development/4.5/phase-03-findings.md (6)
docs/development/4.5/phase-03-modularization.md (19)
docs/development/4.5/phase-04-completion.md (1)
docs/development/4.5/phase-04-measurement-inventory.md (2)
docs/development/4.5/phase-05-completion.md (3)
docs/development/4.5/phase-06-current-grid-flow.md (3)
docs/development/4.5/phase-06-findings.md (1)
docs/development/4.5/phase-08-completion-report.md (3)
docs/development/4.5/phase-08-hardware-handoff.md (2)
docs/development/4.5/phase-08-validation-analysis.md (12)
docs/development/4.5/phase-09-completion.md (1)
docs/development/4.5/phase-09-pilot.md (1)
docs/development/4.5/phase-10-completion-report.md (2)
docs/development/4.5/phase-10-findings.md (2)
docs/development/4.5/phase-10-schema-inventory.md (10)
docs/development/4.5/shelly-phase-measurements.md (4)
docs/development/4.5/tasmota-grid-meter.md (5)
docs/development/4.5/time-series.md (2)
docs/development/4.5/validation-engine.md (1)
docs/development/4.5/validation-events.md (1)
docs/development/4.5/validation-profiles.md (1)
```

### Repository instructions and rebranding specification

Category: **historical/migration documentation**. Action: keep legacy
identifiers where they define source state, compatibility, searches, or
rollback. Product-facing changes are not made to these records.

```text
AGENTS.md (4)
docs/development/4.5/rebranding-work-order.yaml (109; untracked task input)
```

No match was classified as third-party or user-authored content. The ignored
`app/config.json` is potentially private local configuration and is therefore
listed but not read into this report.

## Filename inventory

The required filename search found these ten local paths:

| Path | State and planned action |
| --- | --- |
| `app/solarinspector.py` | Tracked; convert to a thin compatibility wrapper in R.3 after creating the canonical entry point. |
| `scripts/Diagnose-SolarInspector-RaspberryPi.sh` | Tracked; replace with a new canonical operator script in R.6/R.8 and retain old naming only if rollback requires it. |
| `scripts/Rollback-SolarInspector-RaspberryPi.sh` | Tracked; retain/source-name context for rollback and add the canonical migration path in R.5/R.6. |
| `scripts/Upgrade-SolarInspector-RaspberryPi.sh` | Tracked; supersede with the controlled direct migration in R.5/R.6. |
| `systemd/solarinspector-updater.path` | Tracked; introduce and test canonical unit in R.6. |
| `systemd/solarinspector-updater.service` | Tracked; introduce and test canonical unit in R.6. |
| `app/data/solarinspector.db` | Ignored local runtime data; never edit, copy, test against, or commit. |
| `app/data/solarinspector.log` | Ignored local runtime log; never edit or commit. |
| `app/__pycache__/solarinspector.cpython-311.pyc` | Ignored generated bytecode; no migration action. |
| `app/__pycache__/solarinspector.cpython-313.pyc` | Ignored generated bytecode; no migration action. |

The ignored database is not treated as the productive installation. Its
presence is nevertheless a guardrail: all migration tests must use temporary
copies or synthetic fixtures and must never operate on `app/data`.

## Interface and dependency inventory

| Surface | Current dependency | Risk | Planned block |
| --- | --- | --- | --- |
| Imports and entry point | `solarinspector.py`, `solarinspector_core` throughout app, tools, and tests | Import breakage, duplicate module state, circular imports | R.3 |
| Runtime paths | Defaults and environment overrides in core paths, configuration, updater, scripts | Selecting a wrong database or silently creating a fresh database | R.2/R.4 |
| SQLite persistence | Filename and paths in runtime, CLI, scripts, fixtures, docs | Data loss; changed rows, `NULL`, zero, timestamp, or schema semantics | R.4/R.5 |
| Logging and PID | Legacy basename and directories | Lost audit trail or concurrent processes | R.4/R.6 |
| Updater | GitHub owner/repository, user agent, archive names, cache/status/request paths | Updates become undiscoverable or unverified; rollback regression | R.2/R.6 |
| Release pipeline | Workflow, manifest, build script, installer copies | Mismatched asset/checksum/manifest names | R.6 |
| systemd | Application/updater/path units, users, paths, bootstrap scripts | Old and new collectors run in parallel; ownership failures | R.5/R.6 |
| Web/API | Titles, templates, update UI, metadata and download names | Mixed branding or client breakage | R.7 |
| Documentation | Installation, operation, updates, troubleshooting, examples | Operators execute old commands as current instructions | R.8 |
| Repository links | Badges, updater constants, documentation, release workflow | Rename happens too early or links/assets become inconsistent | R.6/R.8/R.9 |

Existing API endpoints, database schema, metric names, validation behavior,
source selection, energy balance, persistence, and CSV semantics are not
branding identifiers and must not be renamed merely for consistency.

## Risks and controls

1. **Only database and measurement history.** A path or basename change could
   select an empty database. R.4/R.5 must compare SQLite integrity, row counts,
   timestamps, real zeros, and `NULL` values before and after migration.
2. **Parallel collectors.** Renamed units could run beside legacy units and
   duplicate writes. R.5/R.6 must stop and disable the old collector before
   enabling the new one and must test rollback ordering.
3. **Environment ambiguity and secrets.** New and old variables may conflict.
   R.2 must prefer `ZRZAVY_ENERGY_MONITOR_*`, warn exactly once on legacy or
   conflicting values, and never log values of secrets.
4. **Python compatibility.** Moving 673 package references can break imports
   or create duplicate implementations. R.3 must use `git mv`, keep canonical
   code only in the new package, and add targeted wrappers with import tests.
5. **Updater and release atomicity.** Repository, archive, checksum, manifest,
   user-agent, and cache names must change as one verified surface in R.6.
   The 4.1.3 updater is not expanded into permanent dual-repository logic.
6. **Permissions and service user.** Renaming the existing Unix user could
   make data unreadable. Migration keeps `solarinspector` initially unless
   UID, ownership, permissions, and rollback have been verified.
7. **History versus current guidance.** Blind replacement would falsify
   changelog and completed phase records. Historical mentions remain; current
   operator documentation moves to canonical names and labels old commands.
8. **Repository rename timing.** Renaming before migration and rollback tests
   would strand links and the updater. It is prohibited before the R.9 gate.
9. **Private/local artifacts.** Ignored config, database, logs, and bytecode
   exist locally. Later tests must use temporary synthetic data and diff
   review must prevent their inclusion.
10. **Work-order ambiguity.** The source YAML contains duplicate `WR-05` IDs
    (direct migration and release automation). Execution blocks disambiguate
    the work by titles: R.5 is direct migration; R.6 owns release automation
    together with WR-06. This inventory does not alter the supplied order.

## R.1 review result

- Product-code changes: none.
- Repository rename: not performed.
- Productive installation: not accessed or changed.
- Public behavior and measurement semantics: unchanged.
- Proposed atomic commit: `Document SolarInspector rebranding inventory`.
- Next step: stop after R.1 and wait for explicit approval before R.2.
