# Rebranding R.9 completion report

R.9 was verified on the isolated Debian host `solarinspector-test` on
2026-07-27. The verification used a real SolarInspector 4.1.3 checkout and the
copied legacy configuration and SQLite history. No productive installation,
private device validation, release, push, or pull request was performed during
the migration run. The GitHub repository had already been renamed externally;
this task did not perform that rename.

## Repository rename gate

| Condition | Result | Evidence |
| --- | --- | --- |
| Identify the 4.1.3 source | passed | `/home/zrzavywa/SolarInspector_Test`, commit `a19026b` (`Release SolarInspector 4.1.3`) |
| Prepare a realistic legacy installation | passed | `/opt/solarinspector`, project-local virtual environment, canonical legacy config/database paths and three systemd units |
| Create and inspect a complete pre-migration backup | passed | Dated private archive plus source archive; both SHA-256 and `tar -tzf` checks passed |
| Run immutable migration dry-runs | passed | Data-only and systemd-orchestrated plans passed; hashes, units and target paths remained unchanged |
| Apply the 4.1.3-to-4.5.0 migration | passed | New service enabled and active; old service inactive |
| Compare SQLite integrity and history | passed | `ok` before and after; all 368 historical `samples` rows were field-for-field identical |
| Verify systemd exclusion and health | passed | Exact `/proc` checks found one new and zero old collectors; health reported version `4.5.0`, canonical product metadata, database `ok` and web `ok` |
| Save configuration under systemd hardening | passed | `ProtectSystem=strict` retained; an isolated atomic write/replace test passed through the allowlisted canonical config directory |
| Restart the new service | passed | Service, health, integrity and process checks passed after restart |
| Roll back to 4.1.3 | passed | Legacy health reported `4.1.3`; 368 rows and their digest were restored exactly; no new collector ran |
| Apply again after rollback | passed | Fresh immutable backup root used; service, health, integrity, history and process checks passed again |
| Complete repository verification | passed | 824 passed, 1 hardware test skipped; Ruff format/lint, mypy, compileall and `git diff --check` passed |

The first real reapply exposed two safety defects: rollback retained canonical
target files, and the systemd error trap attempted data rollback even when the
data apply had not completed. R.9 now preserves the inactive target files
under `failed-target`, removes their canonical active copies and SQLite
sidecars, stops both collectors before rollback, and only invokes trap rollback
after a completed data apply. Privileged migration also disables repository
bytecode generation. Focused migration/Linux tests cover these behaviors.

A controlled Debian reboot was not run. The required systemd service restart
was run successfully. Real-device hardware checks remain unavailable and are
not reported as passed.

## Required completion record

```yaml
task: Rebranding zu Zrzavy Energy Monitor
status: completed
branch: feature/4.5-rebrand-zrzavy-energy-monitor
base_commit: f403a63dabebb6022d1a88a4ed64391ee97f524f
final_commit: 85cc8329572c9acb9bfd9b23da6793de54b1d1bf
merge_commit: bbffb65a44d7b6552b017b1fbac9d4e40a2db99d
old_repository: zrzavywa/SolarInspector
new_repository: zrzavywa/zrzavy-energy-monitor
repository_renamed: true
repository_rename_performed_by_this_task: false

paths:
  migration_verified: verified_on_debian
  legacy_source_dir: /home/zrzavywa/SolarInspector_Test
  legacy_version: 4.1.3
  legacy_commit: a19026b

systemd:
  new_service_enabled: true
  new_service_active: true
  old_service_active: false
  parallel_run_prevented: verified_on_debian
  atomic_configuration_save: verified_on_debian
  service_restart_verified: verified_on_debian
  debian_reboot: not_run
  rollback_verified: verified_on_debian

updater:
  new_repository_configured: true
  new_asset_prefix_configured: true
  direct_upgrade_verified: verified_on_debian
  rollback_verified: verified_on_debian

data:
  historical_samples_before: 368
  historical_samples_after: 368
  historical_digest: 39409d52849be362edddea08616d5e68f2c6a2f98f511607b97308865494c1dc
  integrity_before: ok
  integrity_after: ok
  data_loss_detected: false

tests:
  result: 824 passed, 1 hardware test skipped
  ruff_format: passed
  ruff_lint: passed
  mypy: passed (59 source files)
  compileall: passed
  diff_check: passed

intentionally_deferred:
  - unavailable real-device hardware checks
  - controlled Debian reboot
```

The Debian migration gate is passed. The already completed external GitHub
rename was observed but was not performed or modified by this task.
