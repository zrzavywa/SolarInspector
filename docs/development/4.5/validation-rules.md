# Validation rules

All rules return deterministic findings with stable rule IDs. A rule never
queries a device, writes to SQLite, or changes configuration.

| Rule ID | Purpose | Warning | Rejection |
|---|---|---|---|
| `VAL-FMT-001` | finite numeric type | — | bool, `None`, non-number, NaN, infinity |
| `VAL-UNIT-001` | canonical unit | — | missing or unexpected unit |
| `VAL-RANGE-001` | configured range | warning boundary crossed | hard boundary crossed |
| `VAL-TIME-001` | timestamp structure/order | selected skew cases | invalid or future timestamp |
| `VAL-AGE-001` | measurement age | warning age | stale age |
| `VAL-DELTA-001` | absolute/relative/rate change | warning delta | hard delta |
| `VAL-COUNT-001` | monotonic counters | tolerated small decrease | counter rollback |
| `VAL-ENERGY-001` | counter increase versus elapsed time | warning factor | impossible increase |
| `VAL-DEVICE-001` | known device sentinels | — | configured sentinel value |
| `VAL-DIAG-001` | adapter diagnostics | warning marker | error marker |
| `VAL-PHASE-001` | three-phase completeness | missing comparable phase | — |
| `VAL-PHASE-002` | phase sum versus device total | warning tolerance | hard tolerance |
| `VAL-XTIME-001` | peer timestamp alignment | peer outside window | — |
| `VAL-XPLANT-001` | Solakon versus Shelly PM | transient/persistent difference | optional persistent rejection |
| `VAL-XGRID-001` | grid meter versus Shelly 3EM | comparable-source difference | official reference protected |
| `VAL-ENGINE-001` | rule execution containment | — | unexpected rule exception |

## Evaluation principles

- all applicable rules run in deterministic order
- all findings are retained
- the strongest decision wins
- a warning never modifies the numeric value
- a rejection sets accepted value to `None`
- an accepted successful source comparison may upgrade quality to `validated`
- malformed values are owned by format rules to avoid duplicate findings
- incomplete phases are not treated as zero
- phase-sum consistency runs only with three comparable phases
- cross-source windows use absolute and relative tolerances
- persistent rejection requires configured duration, sample count, and explicit
  permission
- official grid-meter comparison remains non-destructive

## Deferred energy-balance rule

Phase 08 prepares validated values for Phase 09 but does not introduce a new
whole-site energy-balance architecture. Balance equations, source priority, and
fallback policy remain Phase-09 work.
