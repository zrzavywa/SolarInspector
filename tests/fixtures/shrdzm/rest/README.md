# SHRDZM REST fixtures

These fixtures are sanitized, synthetic test data based on publicly
documented SHRDZM response conventions.

Confirmed transport contract:

- local HTTP GET endpoint `/getLastData`
- optional query parameters `user` and `password`
- JSON object response
- direct OBIS keys such as `1.7.0`, `2.7.0`, `1.8.0`, and `2.8.0`
- numeric values may be encoded as JSON strings
- the set of available OBIS values depends on the connected meter and
  utility configuration

The fixture values do not contain real serial numbers, meter identifiers,
MAC addresses, passwords, tokens, public IP addresses, or personal data.

Energy totals in the standard SHRDZM OBIS fields are represented as raw
watt-hours. SolarInspector therefore keeps them in its canonical internal
Wh unit. Explicit `kwh` and `mwh` overrides remain available for custom
mappings. `auto` is intentionally accepted only for the standard total
OBIS fields and never guesses a unit for arbitrary custom paths.

Files:

- `grid_import_normal.json`: complete grid-import sample
- `grid_export_normal.json`: complete grid-export sample
- `grid_zero_power.json`: valid zero-power sample
- `grid_partial_values.json`: intentionally incomplete sample
- `grid_invalid_values.json`: malformed required numeric values

A later hardware block must capture and sanitize the exact response from
Walter's eventual device before Phase 07 is declared fully complete.
