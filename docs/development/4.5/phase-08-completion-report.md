# SolarInspector 4.5 – Phase 08 completion report

## Status

| Item | Result |
|---|---|
| Phase | 08 – Central plausibility validation of all measurements |
| Branch | `feature/4.5-08-validation-engine` |
| Ausgangscommit | `48dad9350f131f16c07112f8f361e84642a12e57` |
| Letzter Commit vor Block 08.10 | `8e2fdde3ba7d94ac9f9b131eedc6f94c5907e87e` |
| Target version | 4.5.0 |
| Automated status | Completed |
| Real Phase-08 hardware observation | Not executed; optional observer provided |

## Implemented blocks

- 08.1 analysis and rule catalog
- 08.2 validation models and configuration
- 08.3 numeric, range, unit, timestamp, and age rules
- 08.4 delta, rate, counter, and energy-increase rules
- 08.5 device profiles and phase rules
- 08.6 cross-source time-window comparison
- 08.7 engine and collector integration
- 08.8 event persistence and deduplication
- 08.9 configuration, API, and dashboard
- 08.10 replay, performance, documentation, and final acceptance

## Architecture and behavior

- strict `Measurement` remains unchanged
- permissive candidates are validated before downstream use
- rules are stateless; history belongs to the state store and collector bridge
- warning values remain unchanged and become `suspect`
- rejected values are removed before source selection and energy integration
- valid sibling metrics survive a rejection
- official grid-meter values are protected from automatic cross-source rejection
- no automatic calibration or non-transparent correction was introduced

## Rules and profiles

Implemented rule groups:

- format, finite number, and canonical unit
- range and known device error values
- timestamp and age
- absolute, relative, and per-second delta
- monotonic counter and maximum energy increase
- device diagnostics
- phase completeness and phase-sum consistency
- Solakon/Shelly PM comparison
- official grid-meter/Shelly 3EM comparison
- engine exception containment

Profiles cover Solakon 800 W, Shelly plant measurement, configurable Shelly
house installations, and configurable official grid-meter limits.

## Persistence and public visibility

- SQLite `validation_events`
- deduplication and occurrence counts
- first/last occurrence and sample references
- bounded and sanitized raw values and details
- retention and rate-limited pruning
- summary and filtered-events APIs
- 24-hour dashboard quality panel
- configuration controls for comparisons and persistence

## Automated verification

Baseline before Block 08.10:

```text
622 passed, 1 skipped
```

Final test result:

```text
632 passed, 1 skipped
```

Coverage:

```text
TOTAL 90%
```

Replay scenarios:

- normal day
- grid-meter spike
- invalid Solakon power
- Shelly phase dropout
- counter reset
- network recovery

Performance report:

```text
cycles: 5000
average cycle: 1.836748 ms
peak Python allocation: 0.115533 MiB
bounded history: 301
events for normal generated data: 0
result: passed
```

Ruff, mypy, compileall, import checks, Flask route checks, and repository diff
checks are executed by Block 08.10 before commit.

## Hardware and manual start

A real 15–60-minute validation observation was not performed automatically.
Use:

```bash
PYTHONPATH=app python scripts/validation_hardware_soak.py \
  --base-url http://<solarinspector-host>:8787 \
  --duration-minutes 15 \
  --output validation-hardware-soak.json
```

A skipped hardware observation is not a passed hardware test.

The block performs an application import and Flask test-client smoke test.
Starting the real Waitress server with the installation's live configuration
remains a manual deployment check:

```bash
python app/solarinspector.py --no-browser
```

## Impact on existing energy calculation

The existing formulas were not redesigned. Phase 08 changes the input boundary:
only accepted or warning-classified values may reach the existing source
selection and integration path.

## Deferred to Phase 09

- complete whole-site energy-balance model
- final source-priority and fallback policy
- balance-specific contradiction rules
- use of validation quality in source scoring
- explicit treatment of overlapping measurement positions

## Recommended next step

Merge Phase 08 after review, perform an observational hardware run without
changing thresholds, and begin Phase 09 using validated measurements and their
quality metadata as the only source-selection inputs.
