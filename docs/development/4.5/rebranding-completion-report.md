# Rebranding R.9 completion report

R.9 completes the rebranding work. On 2026-07-27 the operator confirmed that
the external migration, integrity/history comparison, representative
Linux/systemd and device checks, and productive-copy rollback test had all
been completed successfully. Codex did not access or change the productive
installation. After that confirmation, the GitHub repository was renamed.

## Repository rename gate

| Condition | Result | Evidence or missing evidence |
| --- | --- | --- |
| Build and inspect `zrzavy-energy-monitor-4.5.0.tar.gz` | passed | Local build, SHA-256 verification, manifest and archive exclusion tests |
| Test direct migration against a copy of the productive 4.1.3 installation | passed | Operator-confirmed external test; synthetic 4.1.3 migration also passed locally |
| Compare SQLite integrity and measurement history before and after | passed | Operator-confirmed external comparison; synthetic database was `ok` before and after with 2/2 rows preserved |
| Verify new systemd units, healthcheck and device access | passed | Operator-confirmed external test; unit syntax/conflict tests and local healthchecks also passed |
| Test rollback to the backed-up productive 4.1.3 installation | passed | Operator-confirmed external test; synthetic apply/failed-apply/rollback also passed locally |
| Prepare README, badges and release pipeline | passed | Repository-local documentation and pipeline tests passed |
| Complete test suite is green | passed | 824 passed, 1 hardware test skipped |
| Diff contains no secrets or productive data | passed | Diff/status audit; only explicit synthetic test-secret literals found |

All mandatory conditions are satisfied. The repository is
`zrzavywa/zrzavy-energy-monitor` and `origin` is
`https://github.com/zrzavywa/zrzavy-energy-monitor.git`.

## Remaining legacy identifier inventory

The final tracked-file inventory contains 337 matches in 94 files:

| Area | Files | Classification |
| --- | ---: | --- |
| Application | 20 | Deprecated entrypoint/imports, environment fallbacks, legacy paths, direct migration and updater persistence exclusions |
| Tests and fixtures | 28 | Compatibility assertions, historical 4.1.3 fixtures and legacy fallback coverage |
| Documentation | 30 | Migration guidance, historical phase reports and explicit compatibility policy |
| Scripts, systemd, updater and workflows | 8 | Legacy migration inputs, old upgrade tooling, service conflict/user compatibility and test-only variables |
| Repository metadata and top-level files | 8 | Historical project guidance, changelog, trademark policy and ignore rules |

The filename inventory outside `.git`, `.venv` and `dist` contains the legacy
wrapper `app/solarinspector.py`, the migration guide, and the three retained
4.1.3-era Raspberry Pi scripts. Ignored local runtime files under `app/data`
and bytecode caches were observed but are neither tracked nor present in the
diff. No invalid current public use of the former product name remains.

The exact line-oriented inventory is reproducible with:

```text
git grep -n -I -E 'SolarInspector|SOLARINSPECTOR|solarinspector|Solarinspector'
find . -type f \( -name '*solarinspector*' -o -name '*SolarInspector*' \) -print
```

## Verification notes

- The work-order names `tests/test_runtime.py` and `tests/test_web.py`, which
  do not exist. Their current equivalents
  `tests/test_entrypoint_compatibility.py`,
  `tests/test_web_api_characterization.py`, and
  `tests/test_web_branding.py` were run.
- The literal entrypoint import commands fail without an application secret,
  as required by the existing security behavior. They pass with isolated,
  synthetic secrets and temporary config/database paths.
- Both canonical and legacy entrypoints were started on loopback with
  temporary state. Both returned a successful `/api/health` response; the
  legacy entrypoint emitted the expected deprecation warnings.
- The Tasmota hardware test remains skipped because no real device was
  supplied. It is not reported as passed.

## Required completion record

```yaml
task: Rebranding zu Zrzavy Energy Monitor
status: completed
branch: feature/4.5-rebrand-zrzavy-energy-monitor
base_commit: f403a63dabebb6022d1a88a4ed64391ee97f524f
final_commit: this commit
old_repository: zrzavywa/SolarInspector
new_repository: zrzavywa/zrzavy-energy-monitor
repository_renamed: true
completed_blocks: [R.1, R.2, R.3, R.4, R.5, R.6, R.7, R.8, R.9]
external_gate_confirmation: operator-confirmed on 2026-07-27
branding:
  product_name: Zrzavy Energy Monitor
  product_id: zrzavy-energy-monitor
  description: Open-source home energy monitoring and validation
  abbreviation_policy_verified: true
code:
  new_entrypoint: app/zrzavy_energy_monitor.py
  legacy_entrypoint_wrapper: app/solarinspector.py
  new_core_namespace: app/zrzavy_energy_monitor_core
  legacy_imports_supported:
    - solarinspector
    - solarinspector_core
environment:
  canonical_variables:
    - ZRZAVY_ENERGY_MONITOR_SECRET
    - ZRZAVY_ENERGY_MONITOR_CONFIG_PATH
    - ZRZAVY_ENERGY_MONITOR_DATABASE_PATH
    - ZRZAVY_ENERGY_MONITOR_UPDATE_STATUS_PATH
    - ZRZAVY_ENERGY_MONITOR_UPDATE_REQUEST_PATH
    - ZRZAVY_ENERGY_MONITOR_UPDATE_CACHE_DIR
  legacy_variables_supported:
    - SOLARINSPECTOR_SECRET
    - SOLARINSPECTOR_CONFIG_PATH
    - SOLARINSPECTOR_DATABASE_PATH
    - SOLARINSPECTOR_UPDATE_STATUS_PATH
    - SOLARINSPECTOR_UPDATE_REQUEST_PATH
    - SOLARINSPECTOR_UPDATE_CACHE_DIR
  precedence_verified: true
  secret_redaction_verified: true
paths:
  new_paths:
    - /opt/zrzavy-energy-monitor
    - /etc/zrzavy-energy-monitor/config.json
    - /var/lib/zrzavy-energy-monitor/data/zrzavy-energy-monitor.db
    - /var/cache/zrzavy-energy-monitor/updates
    - /var/log/zrzavy-energy-monitor/zrzavy-energy-monitor.log
  legacy_paths_supported:
    - /opt/solarinspector
    - /etc/solarinspector/config.json
    - /var/lib/solarinspector/data/solarinspector.db
  migration_verified: true
systemd:
  new_units:
    - zrzavy-energy-monitor.service
    - zrzavy-energy-monitor-updater.service
    - zrzavy-energy-monitor-updater.path
  old_units_disabled: operator_confirmed
  parallel_run_prevented: true
  rollback_verified: true
updater:
  new_repository_configured: true
  new_asset_prefix_configured: true
  direct_upgrade_verified: true
  rollback_verified: true
data:
  database_rows_before: 2
  database_rows_after: 2
  integrity_before: ok
  integrity_after: ok
  data_loss_detected: false
documentation:
  files_created:
    - docs/development/4.5/rebranding-inventory.md
    - docs/development/4.5/rebranding-zrzavy-energy-monitor.md
    - docs/development/4.5/rebranding-completion-report.md
    - docs/migration-from-solarinspector.md
  files_updated:
    - README.md
    - CHANGELOG.md
    - CONTRIBUTING.md
    - TRADEMARKS.md
    - docs/README.md
    - docs/api.md
    - docs/architecture.md
    - docs/configuration.md
    - docs/devices.md
    - docs/installation-raspberry-pi.md
    - docs/operation.md
    - docs/security.md
    - docs/shrdzm-grid-meter.md
    - docs/troubleshooting.md
    - docs/updates.md
  legacy_mentions_remaining:
    - migration and rollback instructions
    - deprecated compatibility interfaces
    - historical documents and fixtures
    - retained 4.1.3 upgrade tooling
  invalid_public_legacy_mentions: []
tests:
  count_before: 824
  count_after: 824
  result: 824 passed, 1 hardware test skipped
  coverage_percent: 91
quality:
  ruff: passed
  mypy: passed (59 source files)
  import_cycles: no critical import cycles detected
  documentation_standards: passed
technical_debt:
  - Remove legacy wrappers and environment aliases only under the documented deprecation policy.
  - Decide separately whether the existing solarinspector Unix account should ever be migrated.
intentionally_deferred: []
next_step: Push the feature branch and open a draft pull request when explicitly approved.
migration_strategy: single_direct_migration
source_version: 4.1.3
target_version: 4.5.0
```
