# Phase 04 measurement inventory

## Scope and repository baseline

This inventory describes the measurement values present after Phase 03 on commit
`c8a713b1c5a37a6312405b6283c5e989836fb011`. It records current behavior; it
does not introduce plausibility checks, new register reads, source priorities, or
database changes.

## Existing common Shelly result

`solarinspector_core.models.legacy.MeterReading` currently contains:

| Field | Meaning | Unit | Required | Missing-value behavior |
| --- | --- | --- | --- | --- |
| `power_w` | Active power after `direction_factor` | W | yes | Device parsers currently produce a float |
| `voltage_v` | Voltage or an aggregate voltage | V | no | `None` |
| `current_a` | Current or an aggregate current | A | no | `None` |
| `power_factor` | Power factor | ratio | no | `None` |
| `frequency_hz` | Grid frequency | Hz | no | `None` |
| `energy_total_wh` | Forward active energy | Wh | no | `None` or parser-specific zero |
| `returned_energy_total_wh` | Returned active energy | Wh | no | `None` or parser-specific zero |
| `source` | Diagnostic parser label | text | no | empty string |

The model has no stable configured source identifier, role, measured timestamp,
received timestamp, quality state, or device connection state.

## Shelly PM Mini Gen3

Endpoint: `/rpc/PM1.GetStatus?id=0`

| Device field | Current field | Meaning | Unit | Sign and scaling | Missing and zero behavior | Consumers |
| --- | --- | --- | --- | --- | --- | --- |
| `apower` | `power_w` | Active AC power | W | Converted to float, then multiplied by `direction_factor` | Missing currently becomes `0.0`; a real zero is indistinguishable | Collector solar or house source selection |
| `voltage` | `voltage_v` | AC voltage | V | Converted to float | Missing or invalid becomes `None` | Collector legacy sample |
| `current` | `current_a` | AC current | A | Converted to float | Missing or invalid becomes `None` | Collector legacy sample |
| `pf` | `power_factor` | Power factor | ratio | Converted to float | Missing or invalid becomes `None` | Collector legacy sample |
| `freq` | `frequency_hz` | Frequency | Hz | Converted to float | Missing or invalid becomes `None` | Collector legacy sample |
| `aenergy.total` | `energy_total_wh` | Forward active energy | Wh | Converted to float | Missing or invalid becomes `None` | Device test response; not persisted directly |
| `ret_aenergy.total` | `returned_energy_total_wh` | Returned active energy | Wh | Converted to float | Missing or invalid becomes `None` | Device test response; not persisted directly |

The configured role is currently supplied separately as `house_meter` or
`solakon_meter`. The configured host is not a stable source identity.

## Shelly 3EM Gen1

Endpoint: `/status`

| Device field | Current result | Meaning | Unit | Sign and scaling | Missing and zero behavior | Consumers |
| --- | --- | --- | --- | --- | --- | --- |
| `total_power` | `power_w` | Total active power | W | Preferred total, then multiplied by `direction_factor` | If missing, per-phase powers are summed | Collector grid/house source selection |
| `emeters[].power` | fallback for `power_w` | Per-phase active power | W | Converted to float and summed | Missing phase power currently contributes `0.0` | Total fallback only |
| `emeters[].voltage` | `voltage_v` | Mean of available phase voltages | V | Converted to float, arithmetic mean | Missing phases are excluded | Collector legacy sample |
| `emeters[].total` | `energy_total_wh` | Sum of phase forward energy | Wh | Converted to float and summed | Missing phase total currently contributes `0.0` | Device test response |
| `emeters[].total_returned` | `returned_energy_total_wh` | Sum of returned phase energy | Wh | Converted to float and summed | Missing phase total currently contributes `0.0` | Device test response |

The current parser does not retain individual phase measurements in
`MeterReading`. It does not currently expose phase current, phase power factor,
or validity flags. Phase 04 must not invent values that the existing parser does
not read.

## Shelly Pro 3EM

Endpoint: `/rpc/EM.GetStatus?id=0`

| Device field | Current result | Meaning | Unit | Sign and scaling | Missing and zero behavior | Consumers |
| --- | --- | --- | --- | --- | --- | --- |
| `total_act_power` | `power_w` | Total active power | W | Converted to float, then multiplied by `direction_factor` | If missing, available phase powers are summed; missing phases contribute zero to the fallback | Collector grid/house source selection |
| `a_act_power`, `b_act_power`, `c_act_power` | total fallback | Per-phase active power | W | Converted to float | Missing becomes `None`; `c_active_power` is an accepted legacy alias | Total fallback only |
| `a_voltage`, `b_voltage`, `c_voltage` | `voltage_v` | Mean phase voltage | V | Arithmetic mean of available phases | Missing phases are excluded | Collector legacy sample |
| `a_current`, `b_current`, `c_current` | `current_a` | Sum of available phase currents | A | Sum | Missing phases are excluded | Collector legacy sample |
| `a_pf`, `b_pf`, `c_pf` | `power_factor` | Mean phase power factor | ratio | Arithmetic mean | Missing phases are excluded | Collector legacy sample |
| `a_freq`, `b_freq`, `c_freq` | `frequency_hz` | Mean phase frequency | Hz | Arithmetic mean | Missing phases are excluded | Collector legacy sample |

The current parser does not read Pro 3EM energy counters or validity fields.
Those values are therefore outside the Phase 04 normalization scope unless a
separate decision explicitly expands the existing read behavior.

## Solakon ONE

Source: read-only Modbus TCP function code 03.

| Current field | Register source | Meaning | Unit | Scaling | Current sign | Consumers |
| --- | --- | --- | --- | --- | --- | --- |
| `total_pv_power_w` | 39118 | Combined PV input power | W | signed 32-bit / 1 | Device value | Collector production source and diagnostics |
| `active_power_w` | 39134 | AC active output power | W | signed 32-bit / 1 | Positive generation in existing behavior | Collector production source and household balance |
| `battery_power_w` | 39237, fallback 39162/39230 | Combined battery power | W | signed 32-bit / 1 | Positive charging, negative discharging | Collector splits charge and discharge power |
| `battery_soc_pct` | 39424 | Battery state of charge | % | signed 16-bit / 1 | Non-directional | Collector sample and dashboard |
| `load_power_w` | 39225 | Solakon-reported load | W | signed 32-bit / 1 | Existing device value | Household fallback |
| `meter_power_w` | 39168 | Connected meter power | W | signed 32-bit / 1 | Positive feed-in, negative import | Collector reverses sign for SolarInspector grid convention |
| `internal_temperature_c` | 39141 | Internal temperature | °C | signed 16-bit / 10 | Non-directional | Persistence and CSV |
| `grid_frequency_hz` | 39139 | Grid frequency | Hz | signed 16-bit / 100 | Non-directional | Collector legacy sample |
| `power_factor` | 39138 | Power factor | ratio | signed 16-bit / 1000 | Existing device value | Collector legacy sample |
| `total_pv_energy_kwh` | 39601, fallback 39149 | Total PV energy | kWh | unsigned 32-bit / 100 | Counter | Persistence and CSV |
| `daily_pv_energy_kwh` | 39603, fallback 39151 | Daily PV energy | kWh | unsigned 32-bit / 100 | Counter | Persistence and CSV |
| `battery_total_charge_kwh` | 39605 | Total battery charge energy | kWh | unsigned 32-bit / 100 | Positive counter | Returned reading; not currently persisted directly |
| `battery_total_discharge_kwh` | 39609 | Total battery discharge energy | kWh | unsigned 32-bit / 100 | Positive counter | Returned reading; not currently persisted directly |
| `pv1..pv4_voltage_v` | 39070, 39072, 39074, 39076 | PV input voltage | V | signed 16-bit / 10 | Non-directional | Returned reading |
| `pv1..pv4_current_a` | 39071, 39073, 39075, 39077 | PV input current | A | signed 16-bit / 100 | Existing device value | Returned reading |
| `pv1..pv4_power_w` | 39279, 39281, 39283, 39285 | PV input power | W | signed 32-bit / 1 | Existing device value | Persistence and CSV |
| `status` | 39063 | Decoded operating bits | text | bit decoding | Not a measurement | API, persistence, CSV |
| `warnings` | failed register blocks | Partial-read diagnostics | text | concatenated messages | Not a measurement | Diagnostic reading only |

Model name and serial number are device identity metadata, not physical
measurements. Status and warnings belong to device status rather than
measurement quality.

## Collector-derived legacy values

The collector currently derives values that must not move into adapters during
Phase 04:

- Solar source selection and existing automatic fallback order.
- Solakon meter sign reversal.
- `grid_import_w = max(0, grid_power_w)`.
- `feed_in_w = max(0, -grid_power_w)`.
- Household power and self-consumption balance.
- Shelly/Solakon difference values.
- Trapezoidal energy integration in Wh.
- Existing `house_ok`, `solar_ok`, and `solakon_ok` flags.

These remain legacy calculation and persistence concerns until their dedicated
follow-up phases.

## Initial findings

| ID | Finding | Phase 04 decision | Suggested follow-up |
| --- | --- | --- | --- |
| MM-001 | PM Mini missing `apower` currently becomes `0.0` | Normalized parser must omit the measurement instead of inventing zero | Adapter migration in Phase 04 |
| MM-002 | 3EM fallback sums missing phase power as zero | Preserve legacy total output through compatibility mapping while keeping missing normalized phases absent | Adapter migration in Phase 04 |
| MM-003 | Pro 3EM energy and validity fields are not currently read | Do not add them implicitly | Later Shelly phase |
| MM-004 | Solakon battery power is positive while charging | Emit separate positive charge/discharge metrics first | Phase 04 conventions |
| MM-005 | Solakon ONE serves more than one functional role | Permit multiple source roles and attach a role to each measurement | Phase 04 model |
| MM-006 | Current devices provide no consistently used measurement timestamp | Use `measured_at = received_at` until an adapter has a trustworthy device timestamp | Later timestamp enhancement |
| MM-007 | Device status and measurement status are conflated in legacy flags | Introduce `DeviceSnapshot` separately from `MeasurementQuality` | Phase 04 model |
| MM-008 | Legacy database and APIs depend on a flat sample dictionary | Add an explicit compatibility mapping; do not change public output yet | Phase 04 collector migration |
