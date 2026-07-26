"""Test the bridge from validated collector cycles to the energy balance."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.energy_balance import EnergyBalanceQuality
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.services.energy_balance_collector import (
    build_cycle_energy_balance,
)
from solarinspector_core.validation import (
    ValidatedCycle,
    ValidatedDeviceSnapshot,
    ValidatedMeasurement,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)


def _measurement(
    metric: Metric,
    value: float,
    *,
    source_id: str,
    role: MeasurementRole,
) -> Measurement:
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.VALIDATED,
    )


def _accepted(measurement: Measurement) -> ValidatedMeasurement:
    return ValidatedMeasurement(
        original=measurement,
        result=ValidationResult.accepted(
            measurement.value,
            current_quality=measurement.quality,
        ),
        measurement=measurement,
    )


def _rejected(measurement: Measurement) -> ValidatedMeasurement:
    finding = ValidationFinding(
        rule_id="VAL-TEST",
        code="rejected_for_test",
        message="Rejected for test.",
        severity=ValidationSeverity.ERROR,
    )
    return ValidatedMeasurement(
        original=measurement,
        result=ValidationResult.rejected(
            raw_value=measurement.value,
            candidate_value=measurement.value,
            findings=(finding,),
        ),
        measurement=None,
    )


def _snapshot(
    source_id: str,
    *measurements: ValidatedMeasurement,
) -> ValidatedDeviceSnapshot:
    original = DeviceSnapshot(
        source_id=source_id,
        status=DeviceConnectionStatus.ONLINE,
        measurements=tuple(item.original for item in measurements),
        received_at=NOW,
    )
    accepted = tuple(
        item.measurement for item in measurements if item.measurement is not None
    )
    filtered = DeviceSnapshot(
        source_id=source_id,
        status=DeviceConnectionStatus.ONLINE,
        measurements=accepted,
        received_at=NOW,
    )
    return ValidatedDeviceSnapshot(
        original=original,
        snapshot=filtered,
        measurements=measurements,
        events=(),
    )


def _config() -> dict[str, object]:
    config = deepcopy(DEFAULT_CONFIG)
    config["validation"]["enabled"] = True
    config["house_meter"]["measurement_role"] = "grid_fallback"
    return config


def test_cycle_bridge_selects_validated_sources_and_calculates_balance() -> None:
    grid = _accepted(
        _measurement(
            Metric.GRID_POWER,
            900.0,
            source_id="grid_meter_primary",
            role=MeasurementRole.GRID_METER,
        )
    )
    house_fallback = _accepted(
        _measurement(
            Metric.GRID_POWER,
            800.0,
            source_id="house_meter",
            role=MeasurementRole.GRID_METER,
        )
    )
    plant = _accepted(
        _measurement(
            Metric.PLANT_AC_POWER,
            600.0,
            source_id="solakon_meter",
            role=MeasurementRole.PLANT_METER,
        )
    )
    solakon = (
        _accepted(
            _measurement(
                Metric.PV_POWER,
                720.0,
                source_id="solakon_one",
                role=MeasurementRole.SOLAR_SYSTEM,
            )
        ),
        _accepted(
            _measurement(
                Metric.BATTERY_CHARGE_POWER,
                100.0,
                source_id="solakon_one",
                role=MeasurementRole.BATTERY_SYSTEM,
            )
        ),
        _accepted(
            _measurement(
                Metric.BATTERY_DISCHARGE_POWER,
                0.0,
                source_id="solakon_one",
                role=MeasurementRole.BATTERY_SYSTEM,
            )
        ),
        _accepted(
            _measurement(
                Metric.BATTERY_SOC,
                74.0,
                source_id="solakon_one",
                role=MeasurementRole.BATTERY_SYSTEM,
            )
        ),
    )
    validated = (
        _snapshot("grid_meter_primary", grid),
        _snapshot("house_meter", house_fallback),
        _snapshot("solakon_meter", plant),
        _snapshot("solakon_one", *solakon),
    )
    cycle = ValidatedCycle(
        snapshots=tuple(item.snapshot for item in validated),
        validated_snapshots=validated,
        events=(),
    )

    result = build_cycle_energy_balance(
        cycle,
        config=_config(),
        calculation_timestamp=NOW,
    )

    assert result.house_power_w == 1500.0
    assert result.pv_power_w == 720.0
    assert result.battery_charge_power_w == 100.0
    assert result.battery_soc_percent == 74.0
    assert result.source_metadata[0].selected_source_id == "grid_meter_primary"
    assert result.source_metadata[0].fallback_used is False
    assert result.quality is EnergyBalanceQuality.CALCULATED


def test_rejected_primary_uses_explicit_grid_fallback() -> None:
    primary = _rejected(
        _measurement(
            Metric.GRID_POWER,
            9000.0,
            source_id="grid_meter_primary",
            role=MeasurementRole.GRID_METER,
        )
    )
    fallback = _accepted(
        _measurement(
            Metric.GRID_POWER,
            400.0,
            source_id="house_meter",
            role=MeasurementRole.GRID_METER,
        )
    )
    plant = _accepted(
        _measurement(
            Metric.PLANT_AC_POWER,
            300.0,
            source_id="solakon_meter",
            role=MeasurementRole.PLANT_METER,
        )
    )
    validated = (
        _snapshot("grid_meter_primary", primary),
        _snapshot("house_meter", fallback),
        _snapshot("solakon_meter", plant),
    )
    cycle = ValidatedCycle(
        snapshots=tuple(item.snapshot for item in validated),
        validated_snapshots=validated,
        events=(),
    )

    result = build_cycle_energy_balance(
        cycle,
        config=_config(),
        calculation_timestamp=NOW,
    )

    grid_selection = result.source_metadata[0]
    assert result.house_power_w == 700.0
    assert grid_selection.selected_source_id == "house_meter"
    assert grid_selection.fallback_used is True
    assert grid_selection.rejected_candidates[0].source_id == ("grid_meter_primary")


def test_sub_distribution_and_disabled_validation_are_explicitly_unavailable() -> None:
    fallback = _accepted(
        _measurement(
            Metric.GRID_POWER,
            400.0,
            source_id="house_meter",
            role=MeasurementRole.GRID_METER,
        )
    )
    validated = (_snapshot("house_meter", fallback),)
    cycle = ValidatedCycle(
        snapshots=tuple(item.snapshot for item in validated),
        validated_snapshots=validated,
        events=(),
    )
    sub_distribution = _config()
    sub_distribution["house_meter"]["measurement_role"] = "sub_distribution"  # type: ignore[index]
    validation_disabled = _config()
    validation_disabled["validation"]["enabled"] = False  # type: ignore[index]

    positioned = build_cycle_energy_balance(
        cycle,
        config=sub_distribution,
        calculation_timestamp=NOW,
    )
    disabled = build_cycle_energy_balance(
        cycle,
        config=validation_disabled,
        calculation_timestamp=NOW,
    )

    assert positioned.grid_power_w is None
    assert positioned.quality is EnergyBalanceQuality.UNAVAILABLE
    assert disabled.quality is EnergyBalanceQuality.UNAVAILABLE
    assert any(finding.code == "validation_disabled" for finding in disabled.findings)
