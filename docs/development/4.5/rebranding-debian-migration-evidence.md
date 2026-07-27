# R.9 Debian migration evidence

## Scope and system

- Date: 2026-07-27
- Host: `solarinspector-test`
- Operating system: Debian GNU/Linux 13 (trixie), systemd 257
- Python: 3.13.5 on the host; project-local virtual environments only
- Repository branch: `feature/4.5-rebrand-zrzavy-energy-monitor`
- Repository base at test start: `bdaf0b9`
- Productive systems contacted: none

Secret-bearing configuration, private addresses, tokens, passwords and full
service journals are deliberately excluded from this document.

## Legacy source and paths

The release commit was identified from the local Git history rather than from
the inconsistent working-tree version strings:

```text
LEGACY_SOURCE_DIR=/home/zrzavywa/SolarInspector_Test
LEGACY_VERSION=4.1.3
LEGACY_COMMIT=a19026b
```

Commit `a19026b` is titled `Release SolarInspector 4.1.3`. Its archive was
installed under `/opt/solarinspector` without `.git`, `.venv`, databases, logs,
bytecode or caches. The runtime used:

- `/etc/solarinspector/config.json`
- `/var/lib/solarinspector/data/solarinspector.db`
- `/opt/solarinspector`
- `solarinspector.service`
- `solarinspector-updater.service`
- `solarinspector-updater.path`

The side-by-side 4.5.0 release was built, checksum-verified, validated as a safe
190-member archive and installed at
`/opt/zrzavy-energy-monitor/releases/4.5.0`, with `current` pointing to it.

## Backup

A private dated backup was created at:

```text
/home/zrzavywa/r9-migration-backups/20260727T071225+0200
```

It contains the existing system state and a separate Git archive of commit
`a19026b`. Both archives passed SHA-256 verification and archive listing.
Missing pre-existing `/opt/solarinspector` and legacy unit paths were recorded
before the realistic legacy installation was prepared.

The migrator also created its immutable verified backup at:

```text
/var/lib/zrzavy-energy-monitor/backups/solarinspector-4.1.3-to-zrzavy-energy-monitor-4.5.0
```

A separate backup root was used for the post-rollback reapply so no previous
backup was overwritten.

## Dry-run and apply

Both data-only and `--orchestrate-systemd` dry-runs passed. Before/after
SHA-256 hashes of the legacy config/database and all relevant unit states were
identical. No canonical config, database, migration backup or active target
installation was created by either dry-run.

The first apply completed with:

- `zrzavy-energy-monitor.service`: enabled and active
- `solarinspector.service`: inactive
- health status: `ok`
- version: `4.5.0`
- product ID: `zrzavy-energy-monitor`
- product name: `Zrzavy Energy Monitor`
- database and web status: `ok`
- exact process inventory: zero old, one new collector

The subsequent service restart produced the same result. A full Debian reboot
was not run.

The first configuration save after migration exposed a missing systemd
allowlist entry: `ProtectSystem=strict` correctly made `/etc` read-only, but
the unit had not allowlisted `/etc/zrzavy-energy-monitor`. The canonical unit
now includes that specific directory in `ReadWritePaths`; the broader
filesystem protection remains enabled. After installing and restarting the
unit, an atomic temporary-file write and `os.replace()` in an equivalently
hardened transient service succeeded without changing the real configuration.
Health and single-collector checks remained green.

## SQLite comparison

Immediately before apply:

- integrity: `ok`
- `samples`: 368 rows
- minimum epoch: `1785078492.87102`
- maximum epoch: `1785082162.92157`

The 368 historical rows were serialized in column order and compared with the
migration backup and target. The before/after digest was:

```text
39409d52849be362edddea08616d5e68f2c6a2f98f511607b97308865494c1dc
```

All rows were identical. This comparison includes timestamps, real zeroes,
`NULL` values, measurements, counters and energy totals. Post-migration
integrity was `ok`; no historical loss or substitution was detected.

## Rollback and reapply

The first real reapply attempt safely refused because rollback had retained
the canonical target files. It also exposed an unnecessary trap rollback
against a fresh backup root without a manifest. No collector overlap or
database corruption occurred; the error trap restored the old service.

The implementation was corrected and covered by focused tests:

- preserve canonical target evidence under `failed-target`;
- remove only the inactive canonical copies and SQLite sidecars after their
  verified preservation;
- stop and verify both collectors before data rollback;
- invoke trap rollback only after successful data apply;
- suppress root-owned bytecode generation in the repository.

The corrected rollback restored SolarInspector 4.1.3 with health and database
status `ok`. The same 368 rows and digest were restored, with one old and zero
new collectors. The second apply used a fresh immutable backup root and again
produced health `ok`, integrity `ok`, identical historical rows, zero old and
one new collector.

## Automated verification

The canonical Debian run of `./scripts/verify.sh` completed successfully:

```text
Ruff format: passed (170 files)
Ruff lint: passed
Mypy: passed (59 source files)
Compileall: passed
Pytest: 824 passed, 1 skipped, 2 warnings
git diff --check: passed
```

The skipped test requires unavailable real hardware and is not reported as
passed. The two warnings are Python tar extraction deprecation notices in
existing release-installer tests.

## Remaining risks and recommendation

- No controlled Debian reboot was performed; the systemd service restart did
  pass.
- Real-device hardware checks remain unavailable.
- The test uses copied legacy state on the isolated Debian host, not a
  productive installation.
- The synthetic systemd test secret must be removed with the rest of the
  isolated test setup; no real secret is stored in the repository.

The direct migration, rollback, data preservation, service exclusion and
reapply gates are verified on Debian. The GitHub remote already uses
`zrzavywa/zrzavy-energy-monitor`; this task observed but did not perform that
external rename.

```text
REPOSITORY RENAME GATE: PASSED
```
