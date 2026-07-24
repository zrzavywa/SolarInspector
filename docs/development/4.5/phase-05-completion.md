# Phase 05 completion: Shelly phase measurements

## Delivered

SolarInspector 4.5 Phase 05 implements the complete Shelly three-phase path:

1. Configuration of phase roles and direction overrides.
2. Stable L1/L2/L3 parsing for Shelly 3EM Gen 1.
3. Stable L1/L2/L3 parsing and diagnostics for Shelly Pro 3EM.
4. Normalized phase metrics under the `HOUSE_METER` role.
5. Quality classification for reported and suspect phase values.
6. Pure phase-sum, load-distribution, and spread analysis.
7. Atomic SQLite persistence linked to aggregate samples.
8. Additive live and historical phase APIs.
9. Responsive live and historical dashboard presentation.

## Compatibility retained

The phase implementation does not intentionally change:

- Existing `samples` columns.
- Existing aggregate `GRID_POWER` semantics.
- Grid import and feed-in calculations.
- Solar source selection and fallback order.
- Household consumption and self-consumption formulas.
- Trapezoidal energy integration.
- Existing `/api/live` and `/api/dashboard` payloads.
- Existing CSV fields.
- Single-phase Shelly PM Mini behavior.
- Solakon ONE acquisition and persistence behavior.

## Commit sequence

```text
0b9dd44 Add Shelly phase roles and direction configuration
c6b45db Parse Shelly 3EM Gen 1 phase measurements
a0ac77b Parse Shelly Pro 3EM phase diagnostics
c42dbfc Normalize Shelly phase measurements and analyze load distribution
83bd96f Persist Shelly phase snapshots atomically
5aa96ea Expose Shelly phase data in API and dashboard
```

## Acceptance checks

Phase 05 completion requires all of the following:

```text
ruff format --check app tests
ruff check app tests
mypy
pytest -q tests
python -m compileall -q app tests
git diff --check
```

The final implementation baseline has 335 passing tests before this
documentation-only block.

Focused coverage includes:

- Gen 1 and Pro 3EM parser behavior.
- Phase direction handling.
- Aggregate-authority and fallback behavior.
- Quality and degraded-state decisions.
- Phase analysis calculations.
- SQLite migration, atomic inserts, range queries, and deletion.
- Collector persistence for online, degraded, and offline sources.
- Live and historical phase API payloads.
- Dashboard template and JavaScript integration.
- Existing API and persistence characterization tests.

## Operational behavior

A deployment using an existing SolarInspector database receives the new
`phase_samples` table during normal initialization. Existing sample rows and
columns remain intact.

New phase history starts when the updated collector first stores a multi-phase
Shelly snapshot. The implementation does not backfill phase data from historic
aggregate rows because the original per-phase measurements are not available.

## Deferred work

The following is intentionally outside Phase 05:

- Central device-specific plausibility limits.
- Validation against the official utility meter.
- Cross-source trust and fallback decisions.
- Stale-value classification across collection cycles.
- Phase-energy counters and energy charts.
- Phase-aware CSV export.
- Automatic wiring diagnosis.
- Full removal of the temporary normalized-to-legacy compatibility layer.
- Dynamic measurement-source configuration.

These items belong to later SolarInspector 4.5 phases and should not be mixed
into the completed Shelly phase acquisition feature.
