# SHRDZM REST fixtures

These fixtures are sanitized test data based on documented SHRDZM response
conventions. The real import fixture contains no device identity or
credentials.

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

Energy totals in the standard SHRDZM OBIS fields are confirmed as raw Wh;
the operator display may show the corresponding values in kWh. With `auto`,
ZEM normalizes those standard paths as Wh. Explicit `wh`, `kwh`, or `mwh`
overrides remain available for custom mappings.

Files:

- `grid_import_normal.json`: complete grid-import sample
- `grid_import_real_sanitized.json`: supplied real import evidence, sanitized
  for repository use
- `grid_zero_real_sanitized.json`: supplied real zero-point evidence, sanitized
  for repository use
- `grid_export_real_sanitized.json`: supplied real export evidence, sanitized
  for repository use
- `grid_export_normal.json`: complete grid-export sample
- `grid_zero_power.json`: valid zero-power sample
- `grid_partial_values.json`: intentionally incomplete sample
- `grid_invalid_values.json`: malformed required numeric values

The `13.7.0` field remains intentionally unused; real export, zero-point, and
energy-unit evidence is represented by the sanitized fixtures above.
