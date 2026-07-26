# Phase 10 findings, decisions, and residual risks

## Scope and evidence

Phase 10 was implemented on branch
`feature/4.5-10-persistence-migration` from base commit `40e1cdd`.
Migration evidence uses reviewed synthetic v3-style, SolarInspector 4.1.3,
Phase 05–09, current, corrupt, and newer-schema fixtures. No unmodified real
4.1.x backup was available. The user-authorized local database was an empty
unversioned Phase-09-shaped file; it was inspected and dry-run migrated only,
with an unchanged SHA-256 digest.

No productive installation, customer data, private network, or real device was
accessed. Raspberry Pi and hardware conclusions are therefore explicitly
limited below.

## Architecture decisions

### ADR-10-01: Generic normalized measurements beside compatibility samples

- Decision: retain `samples` as compatibility parent and add one normalized
  `measurements` row per accepted source/role/metric value.
- Alternatives: widen `samples` for every device; replace it immediately.
- Reason: normalized source, quality, unit, and timestamps are queryable
  without breaking dashboard, API, energy integration, or legacy CSV.
- Consequence: temporary dual representation increases writes and storage.
  The wide table remains authoritative only for established compatibility
  consumers; new history reads use normalized rows.

### ADR-10-02: Forward-only ledger with verified checksums

- Decision: contiguous integer versions in `schema_migrations`, immutable
  descriptions/checksums, transactional application, and target verification.
- Alternatives: infer schema forever; mutable ad-hoc `ALTER TABLE` calls.
- Reason: known legacy and intermediate states become deterministic,
  idempotent, auditable, and reject unknown newer schemas.
- Consequence: changing released migration text/DDL requires a new version,
  not editing an old checksum.

### ADR-10-03: UTC ISO 8601 for new text timestamps

- Decision: normalize new measurement and source-decision timestamps to
  timezone-aware UTC text; retain parent `ts_epoch` for legacy range joins.
- Alternatives: mixed offsets; naive local text; integer epoch everywhere.
- Reason: lexical SQLite indexes are correct only under one normalized offset,
  while legacy local text cannot safely be reinterpreted.
- Consequence: exports expose explicit UTC columns. Uninterpretable legacy
  timestamps remain unchanged and produce migration findings.

### ADR-10-04: Opt-in bounded retention; no aggregation yet

- Decision: retention defaults disabled, runs once at startup only when
  enabled, deletes at most one configured batch per category, and never
  performs cycle-level cleanup or `VACUUM`.
- Alternatives: unconditional deletion; unbounded startup purge; collector
  cleanup every five seconds; immediate minute/hour aggregate tables.
- Reason: prevents surprise loss and long locks. Correct cumulative-counter
  aggregation needs first/last/delta and reset semantics not justified by
  current real-installation evidence.
- Consequence: expired backlogs may require multiple starts or explicit
  maintenance calls. Without opt-in retention, growth remains the operator's
  responsibility.

### ADR-10-05: Persist accepted values, not sensitive raw responses

- Decision: persist accepted and allowed `SUSPECT` values with source and
  quality; omit rejected/stale/unavailable values from fachliche Zeitreihen.
  Diagnostic JSON is bounded and allow-listed.
- Alternatives: save all raw device responses; coerce missing/rejected values
  to zero.
- Reason: prevents secrets and invalid points entering history while
  preserving genuine zero and actionable findings.
- Consequence: historical rejected raw payloads cannot be reconstructed.

### ADR-10-06: Normalize source decisions as bounded audit events

- Decision: store one event per sample/metric with selected identity, quality,
  fallback, reason, and bounded rejected-candidate metadata.
- Alternatives: keep only Phase-09 balance JSON; store full candidate values.
- Reason: supports indexed historical explanation without duplicating values
  or leaking raw payloads.
- Consequence: older decisions cannot be backfilled and trailing rejected
  candidates may be removed when the JSON cap is reached.

## Migration findings and non-migratable values

| Finding | Treatment | Data loss |
| --- | --- | --- |
| Unknown legacy column | Column/value preserved; column name recorded | No |
| Invalid or naive legacy `ts_local` | Text preserved; row finding recorded | No |
| Missing Phase 05–09 detail | New table/column remains empty or `NULL` | No invented history |
| Historical source/quality absent | Not reconstructed | Information was never stored |
| Physical cumulative counter absent | Not derived from interval Wh or power | Information was never stored |
| Rejected raw measurement | Validation event only when available | Deliberate exclusion from valid series |

The characterized 4.1.3 48-column shape and every intermediate fixture retain
all original rows and values. Unknown structural variants outside the
documented invariant columns fail safely or produce findings; they are not
silently interpreted.

## Performance measurement

The reproducible command was:

```bash
PYTHONPATH=app .venv/bin/python \
  scripts/persistence_timeseries_benchmark.py \
  --cycles 3000 \
  --output /tmp/solarinspector-phase10-persistence-benchmark.json
```

Environment: Python 3.11.14 on macOS 14.8.7 x86_64. This is development-machine
evidence, not a Raspberry Pi guarantee.

| Measurement | Result |
| --- | ---: |
| Poll interval represented | 5 s |
| Simulated cycles/duration | 3,000 / 15,000 s |
| Normalized measurements | 75,000 |
| Source decisions | 18,000 |
| Phase/grid/balance rows | 3,000 each |
| Database size after WAL checkpoint | 30,433,280 bytes |
| Bytes per representative cycle | 10,144 |
| Average / median write | 7.90 / 3.79 ms |
| p95 / maximum write | 28.59 / 254.37 ms |
| First/last-quarter average | 9.86 / 7.88 ms |
| Last/first trend ratio | 0.80 |
| Concurrent reader queries | 11,725 |
| Locking errors | 0 |
| Bounded one-day-range query | 24.75 ms / 3,000 rows |
| Bounded 30-day-range query | 31.53 ms / 3,000 rows |
| Integrity | `ok` |

The run represents 4.17 hours of consecutive five-second timestamps. The
30-day query exercises a 30-day predicate and the measured index path, but the
temporary database contains only those 3,000 points; it is not a full
518,400-cycle month.

Linear storage projection for this exact synthetic cardinality is 5.26 GB at
30 days and 63.98 GB at 365 days. Projection is not a capacity promise:
filesystem allocation, page reuse, metric count, validation frequency,
retention, WAL checkpointing, and SQLite version change it materially. It
does confirm that disabled retention must be an explicit operator choice.

No increasing write delay was observed, average/p95/max remained far below
the represented five-second interval, and concurrent WAL reads produced no
lock error. These results do not establish SD-card endurance or Raspberry Pi
latency.

## Technical debt and risks

| ID | Residual item | Risk and next action |
| --- | --- | --- |
| DB-001 | Legacy timestamps without timezone | Preserved with finding; operator must interpret source context |
| DB-002 | Ambiguous historical column semantics | Never reclassified; retain schema documentation |
| DB-003 | High-resolution growth | Enable retention after capacity planning; measure real metric cardinality |
| DB-004 | In-memory short windows | Restart loses averaging context; no false persistence claim |
| DB-005 | Pre-Phase-10 source decisions absent | Cannot reconstruct; normalized events begin after migration |
| DB-006 | SQLite lock behavior on Raspberry Pi | Development WAL test passed; run device soak with real SD/storage |
| DB-007 | `VACUUM` maintenance window | Never automatic; document/operator schedule if space reclamation is needed |
| DB-008 | No aggregate history | Design only after real growth evidence and counter-reset rules |
| DB-009 | Compatibility and normalized duplication | Required transition cost; reconsider only in a breaking major version |
| DB-010 | Startup retention drains one batch | Prevents long startup locks; repeated starts/maintenance needed for backlog |

## Raspberry Pi and hardware boundaries

Automated tests use temporary SQLite files and synthetic measurements. Before
productive rollout, manually verify on the target Raspberry Pi:

- backup directory ownership, `0700`/`0600` enforcement, disk space, and
  atomic rename on its filesystem;
- startup migration duration on a copy of the real database;
- at least a 24-hour five-second soak with actual enabled sources;
- p95/max write latency, WAL size/checkpoint behavior, CPU, memory, storage
  growth, and `database locked` count;
- retention duration with the expected expired backlog;
- backup restore while the systemd service is stopped;
- device position, sign, units, counter reset behavior, and clock quality.

Skipped hardware checks are unverified, not passed.
