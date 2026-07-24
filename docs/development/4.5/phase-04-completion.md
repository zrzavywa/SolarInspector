# Phase 04 completion: normalized measurement model

## Delivered

Phase 04 introduces a device-independent acquisition boundary while preserving
SolarInspector 4.1.3-compatible output:

- Controlled roles, metrics, canonical units, quality states, and device
  connection states.
- Immutable `Measurement`, `MeasurementSource`, and `DeviceSnapshot` models.
- A small structural `MeasurementAdapter` protocol and deterministic fake.
- Normalized Shelly and Solakon production adapters.
- Explicit legacy compatibility mappings.
- Collector migration for all currently configured Shelly and Solakon sources.
- Device metadata preservation for Solakon model, serial number, and operating
  status.
- Contract, adapter, compatibility, collector, and regression tests.

## Compatibility retained

Phase 04 does not change:

- Database schema or historical rows.
- Public API payloads.
- Dashboard and CSV fields.
- Existing source-selection and fallback order.
- Household balance and self-consumption formulas.
- Trapezoidal energy integration.
- Legacy device-test endpoints.

## Acceptance checks

The branch is accepted only when all of the following pass:

```text
ruff format --check app tests
ruff check app tests
mypy
pytest -q tests
python -m compileall -q app tests
application import smoke test
git diff --check
```

Production contract tests additionally verify stable source metadata, canonical
units, timezone-aware timestamps, preservation of valid zero power, and
contained communication failures for both device families.

## Deliberately deferred technical debt

The following work belongs to later phases:

- Device-specific plausibility limits and configurable expected ranges.
- Cross-source comparison and validation decisions.
- `VALIDATED`, `SUSPECT`, `REJECTED`, `STALE`, and `FALLBACK` assignment.
- Official-grid-meter integration and full `HOUSE_METER` adoption.
- Per-phase normalization beyond values retained by the current legacy parsers.
- Trustworthy device timestamps where available.
- Dynamic source registry and configuration migration for stable source IDs.
- Direct normalized persistence and removal of temporary legacy mappings.

## Branch review

The Phase 04 branch is based on the Phase 03 merge commit and changes only the
measurement model, device adapters, collector acquisition boundary, supporting
quality configuration, tests, and Phase 04 documentation. Persistence behavior,
API, dashboard, and CSV outputs remain structurally unchanged.
