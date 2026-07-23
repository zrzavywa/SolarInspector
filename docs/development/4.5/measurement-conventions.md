# Normalized measurement conventions

## Purpose

These conventions define the internal representation introduced in
SolarInspector 4.5 Phase 04. They do not change the existing database schema,
public API, dashboard, CSV format, source priority, or energy calculations.

## Functional roles

| Role | Meaning | Current sources |
| --- | --- | --- |
| `GRID_METER` | Measurement at the public grid connection point | Future Hichi/Tasmota or SHRDZM; optional existing meter fallback |
| `HOUSE_METER` | Internal household and phase measurement | Shelly 3EM, Shelly Pro 3EM |
| `PLANT_METER` | Physical AC measurement of the balcony plant | Shelly PM Mini Gen3 |
| `SOLAR_SYSTEM` | Internal solar-system values | Solakon ONE |
| `BATTERY_SYSTEM` | Battery state and flow | Solakon ONE |

A configured device may support more than one role. Each normalized measurement
therefore carries its applicable role.

## Canonical units

Only one canonical internal unit is permitted for each metric:

- Power: watt (`W`).
- Energy: watt-hour (`Wh`).
- Voltage: volt (`V`).
- Current: ampere (`A`).
- Battery state of charge: percent (`%`).
- Frequency: hertz (`Hz`).
- Power factor: dimensionless ratio (`ratio`).
- Temperature: degrees Celsius (`°C`).

Adapters perform scaling. In particular, Solakon energy counters currently
reported as kWh are multiplied by 1000 before creating normalized measurements.
Legacy output may convert normalized Wh values back to the existing kWh fields.

## Sign conventions

### Grid power

`GRID_POWER` uses:

- Positive: import from the public grid.
- Negative: export to the public grid.
- Zero: neither import nor export.

Solakon register 39168 currently uses the opposite sign and must be reversed by
the adapter when it creates a normalized `GRID_POWER` measurement. Separate
import and export power remain calculated values and are not adapter metrics.

### Plant AC power

`PLANT_AC_POWER` uses:

- Positive: the plant supplies power to the household AC network.
- Negative: the plant consumes power from the household AC network.
- Zero: no current AC exchange.

Phase 04 does not clamp negative measurements in the adapter. Existing legacy
calculations may retain their current `max(0, value)` behavior through the
compatibility layer.

### Battery power

The normalized `BATTERY_POWER` convention is reserved as:

- Positive: battery discharging.
- Negative: battery charging.

The existing Solakon value uses the opposite sign. To avoid an unnecessary
behavioral change during the first migration, adapters initially emit the
separate non-negative metrics `BATTERY_CHARGE_POWER` and
`BATTERY_DISCHARGE_POWER`. `BATTERY_POWER` is not required until its consumers
are migrated explicitly.

## Source identity

Every configured source has a stable `source_id`, for example:

- `grid_meter_primary`
- `house_meter_main`
- `plant_meter_shelly`
- `solakon_one`

Rules:

- `source_id` is non-empty and unique within the configuration.
- It is not derived solely from an IP address or hostname.
- Changing the technical address does not change source identity.
- Display name, device type, technical address, and credentials are separate
  configuration concerns.

Phase 04 introduces the model but does not yet require a full dynamic source
registry or configuration migration.

## Timestamps

Each measurement carries:

- `measured_at`: time at which the device measured or reported the value.
- `received_at`: time at which SolarInspector received the value.

Both values are timezone-aware `datetime` instances. Naive timestamps are
rejected by the normalized model.

When a device has no trustworthy timestamp:

```text
measured_at = received_at
```

The first adapter migration uses SolarInspector's timezone-aware receipt time.
No stale-value decision is made in Phase 04.

## Zero, missing, invalid, and unavailable values

The normalized model distinguishes:

| Situation | Representation |
| --- | --- |
| Valid zero | `Measurement(value=0.0, ...)` |
| Field missing from a partial response | No `Measurement` for that metric |
| Field present but not numeric or not finite | No measurement; snapshot may be `DEGRADED` with diagnostic detail |
| Device unreachable | `DeviceSnapshot(status=OFFLINE, measurements=())` |
| Device disabled | `DeviceSnapshot(status=DISABLED, measurements=())` |
| Not read yet | No snapshot exists |

`MeasurementQuality.UNAVAILABLE` is defined for future workflows but Phase 04
does not create a numeric measurement merely to represent absence.

## Measurement quality

Phase 04 may assign:

- `MEASURED`: value from a physical meter or sensor.
- `REPORTED`: value reported by a device's internal controller.
- `CALCULATED`: value arithmetically derived from reported values.
- `UNAVAILABLE`: reserved status; normally absence is represented by no
  measurement.

The following values are defined but not assigned by Phase 04 without their
later decision logic:

- `VALIDATED`
- `SUSPECT`
- `REJECTED`
- `STALE`
- `FALLBACK`

Receiving and parsing a value does not make it `VALIDATED`.

## Device connection status

- `ONLINE`: the read completed and expected values were available.
- `DEGRADED`: the device responded but only partial values were available or a
  non-fatal parsing/register error occurred.
- `OFFLINE`: communication failed and no measurements were produced.
- `DISABLED`: source is configured but disabled.
- `UNKNOWN`: no reliable connection decision is available.

A missing individual measurement does not automatically make the whole device
offline.

## Structural validation versus plausibility

The model may reject structurally invalid objects, including:

- Empty `source_id`.
- Naive timestamps.
- `None`, boolean, NaN, or infinite numeric values.
- A unit that does not match the metric's canonical unit.
- Duplicate role/metric values in one source snapshot.
- Measurements whose source does not match their snapshot.

These are representation invariants, not device-specific plausibility checks.
Phase 04 does not validate power ranges, compare sources, mark stale values, or
select fallbacks.
