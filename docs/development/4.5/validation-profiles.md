# Validation profiles

Validation profiles separate reusable device limits from installation-specific
source settings. All defaults are project defaults, not legal, normative,
eichrechtliche, or calibration limits.

## Solakon 800 W profile

Built-in source: `solakon_one`

- AC nominal warning boundary: 800 W
- default upper rejection boundary: 960 W
- default permitted standby import: down to -100 W
- battery state of charge: 0–100 %
- required metric: plant AC power

A value between the warning and rejection boundaries remains usable as
`suspect`. A value outside the hard boundary is rejected.

## Shelly plant-meter profile

Built-in source: `solakon_meter`

The Shelly PM Mini Gen3 at the plant outlet uses the same installation power
envelope as the connected Solakon plant. It is an independent physical
measurement and is not automatically calibrated against Solakon reporting.

## Shelly 3EM / Pro 3EM house profile

House limits require explicit installation information such as nominal voltage
and main-fuse current. SolarInspector does not guess a main-fuse rating.

The profile may include:

- signed total-power range
- signed phase-power ranges
- voltage and current ranges
- phase completeness
- device-total versus phase-sum tolerances

The resulting values are planning and plausibility limits, not a statement
about electrical-code compliance.

## Official grid meter

The official grid meter can use an explicit profile and a stable configured
source ID. It remains the leading grid reference when technically valid.

A comparison with Shelly 3EM is performed only when
`measurement_position_comparable` is explicitly true. Even a persistent large
difference does not automatically reject the official reference.

### Comparison-window timing

Cross-source rules compare the arithmetic means of the accepted measurements
from each source inside the inclusive lookback window. The configured
`minimum_duration_seconds` is the observed span between the oldest and newest
measurement in each source window; it is not a delay timer.

`window_seconds` should be larger than `minimum_duration_seconds`. Configuring
both to the same value is sensitive to polling and network jitter because the
oldest sample can fall just outside the lookback window. The minimum sample
count should normally be at least:

```text
ceil(minimum_duration_seconds / effective_sample_interval_seconds) + 1
```

For an official Tasmota meter with an effective ten-second update interval, the
recommended pilot settings are:

```text
window_seconds: 60
minimum_duration_seconds: 30
minimum_samples: 4
```

This covers samples near 0, 10, 20, and 30 seconds while retaining enough
window margin for jitter or one delayed poll. Thresholds remain
installation-specific and independent of this timing recommendation.

## Source-specific overrides

A source can select a named profile and add:

- known device error values
- diagnostic warning or error markers
- counter warning tolerance
- comparison source IDs
- comparison windows and thresholds
- explicit comparability of measurement positions

Source comparison settings override reusable profile comparison defaults.
No setting changes a measured value.

## Persistence settings

`validation.persistence` supports:

- `dedup_window_seconds`
- `retention_days`
- `prune_interval_seconds`
- bounded reason, detail, and raw-value lengths

Legacy configuration files without an explicit persistence section remain
structurally unchanged. Runtime defaults are applied by the persistence policy.
