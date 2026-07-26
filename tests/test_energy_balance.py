"""Test the validated current AC power balance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from solarinspector_core.models.energy_balance import (
    EnergyBalanceInput,
    EnergyBalanceQuality,
    EnergyBalanceResult,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.source_selection import SourceSelectionResult
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.services.energy_balance import EnergyBalanceService

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=timezone.utc)


def _selection(
    metric: Metric,
    value: float | None,
    *,
    measured_at: datetime = NOW,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
) -> SourceSelectionResult:
    if value is None:
        return SourceSelectionResult.unavailable(
            metric,
            selection_timestamp=NOW,
        )
    role = {
        Metric.GRID_POWER: MeasurementRole.GRID_METER,
        Metric.PLANT_AC_POWER: MeasurementRole.PLANT_METER,
        Metric.PV_POWER: MeasurementRole.SOLAR_SYSTEM,
        Metric.BATTERY_CHARGE_POWER: MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_DISCHARGE_POWER: MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_SOC: MeasurementRole.BATTERY_SYSTEM,
    }[metric]
    measurement = Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id={
            Metric.GRID_POWER: "grid_meter_primary",
            Metric.PLANT_AC_POWER: "solakon_meter",
        }.get(metric, "solakon_one"),
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=quality,
    )
    return SourceSelectionResult.selected(
        measurement,
        selection_timestamp=NOW,
        fallback_used=False,
    )


def _inputs(
    grid_power_w: float | None,
    plant_ac_power_w: float | None,
    *,
    grid_at: datetime = NOW,
    plant_at: datetime = NOW,
    plant_quality: MeasurementQuality = MeasurementQuality.VALIDATED,
    pv_power_w: float | None = None,
    battery_charge_power_w: float | None = None,
    battery_discharge_power_w: float | None = None,
    battery_soc_percent: float | None = None,
) -> EnergyBalanceInput:
    return EnergyBalanceInput(
        grid_power=_selection(
            Metric.GRID_POWER,
            grid_power_w,
            measured_at=grid_at,
        ),
        plant_ac_power=_selection(
            Metric.PLANT_AC_POWER,
            plant_ac_power_w,
            measured_at=plant_at,
            quality=plant_quality,
        ),
        pv_power=_selection(Metric.PV_POWER, pv_power_w),
        battery_charge_power=_selection(
            Metric.BATTERY_CHARGE_POWER,
            battery_charge_power_w,
        ),
        battery_discharge_power=_selection(
            Metric.BATTERY_DISCHARGE_POWER,
            battery_discharge_power_w,
        ),
        battery_soc=_selection(Metric.BATTERY_SOC, battery_soc_percent),
        calculation_timestamp=NOW,
    )


@pytest.mark.parametrize(
    (
        "grid_power_w",
        "plant_ac_power_w",
        "expected_house_w",
        "expected_import_w",
        "expected_export_w",
    ),
    [
        (900.0, 600.0, 1500.0, 900.0, 0.0),
        (-150.0, 600.0, 450.0, 0.0, 150.0),
        (500.0, 0.0, 500.0, 500.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0),
    ],
)
def test_current_power_balance_examples(
    grid_power_w: float,
    plant_ac_power_w: float,
    expected_house_w: float,
    expected_import_w: float,
    expected_export_w: float,
) -> None:
    result = EnergyBalanceService().calculate(_inputs(grid_power_w, plant_ac_power_w))

    assert result.house_power_w == expected_house_w
    assert result.grid_import_power_w == expected_import_w
    assert result.grid_export_power_w == expected_export_w
    assert result.residual_power_w == 0.0
    assert result.quality is EnergyBalanceQuality.CALCULATED


@pytest.mark.parametrize(
    (
        "grid_power_w",
        "plant_ac_power_w",
        "expected_self_consumed_w",
        "expected_self_consumption_pct",
        "expected_autonomy_pct",
    ),
    [
        (900.0, 600.0, 600.0, 100.0, 40.0),
        (-150.0, 600.0, 450.0, 75.0, 100.0),
        (500.0, 0.0, 0.0, None, 0.0),
        (0.0, 0.0, 0.0, None, None),
    ],
)
def test_self_consumption_and_autonomy(
    grid_power_w: float,
    plant_ac_power_w: float,
    expected_self_consumed_w: float,
    expected_self_consumption_pct: float | None,
    expected_autonomy_pct: float | None,
) -> None:
    result = EnergyBalanceService().calculate(_inputs(grid_power_w, plant_ac_power_w))

    assert result.self_consumed_power_w == expected_self_consumed_w
    assert result.self_consumption_rate_percent == expected_self_consumption_pct
    assert result.autonomy_rate_percent == expected_autonomy_pct


def test_missing_input_keeps_partial_values_but_not_house_balance() -> None:
    result = EnergyBalanceService().calculate(_inputs(-150.0, None))

    assert result.grid_power_w == -150.0
    assert result.grid_import_power_w == 0.0
    assert result.grid_export_power_w == 150.0
    assert result.plant_ac_power_w is None
    assert result.house_power_w is None
    assert result.residual_power_w is None
    assert result.quality is EnergyBalanceQuality.INCOMPLETE


def test_all_required_inputs_missing_is_unavailable() -> None:
    result = EnergyBalanceService().calculate(_inputs(None, None))

    assert result.house_power_w is None
    assert result.grid_power_w is None
    assert result.quality is EnergyBalanceQuality.UNAVAILABLE


def test_source_skew_prevents_unmarked_calculation() -> None:
    result = EnergyBalanceService(maximum_source_skew_seconds=10).calculate(
        _inputs(
            500.0,
            300.0,
            plant_at=NOW - timedelta(seconds=10, microseconds=1),
        )
    )

    assert result.house_power_w is None
    assert result.quality is EnergyBalanceQuality.INCOMPLETE
    assert result.findings[0].code == "source_skew_exceeded"


def test_small_negative_house_power_is_normalized_and_residual_is_visible() -> None:
    result = EnergyBalanceService(negative_house_power_tolerance_w=30).calculate(
        _inputs(-620.0, 600.0)
    )

    assert result.house_power_w == 0.0
    assert result.residual_power_w == 20.0
    assert result.quality is EnergyBalanceQuality.SUSPECT
    assert result.findings[0].code == "negative_house_power_normalized"


def test_negative_house_power_at_tolerance_boundary_is_normalized() -> None:
    result = EnergyBalanceService(negative_house_power_tolerance_w=30).calculate(
        _inputs(-630.0, 600.0)
    )

    assert result.house_power_w == 0.0
    assert result.residual_power_w == 30.0
    assert result.quality is EnergyBalanceQuality.SUSPECT


def test_negative_house_power_below_tolerance_rejects_balance() -> None:
    result = EnergyBalanceService(negative_house_power_tolerance_w=30).calculate(
        _inputs(-630.0001, 600.0)
    )

    assert result.house_power_w is None
    assert result.residual_power_w is None
    assert result.quality is EnergyBalanceQuality.UNAVAILABLE
    assert result.findings[0].code == "negative_house_power_rejected"


def test_pv_power_is_reported_but_never_used_as_plant_ac_fallback() -> None:
    result = EnergyBalanceService().calculate(_inputs(500.0, None, pv_power_w=700.0))

    assert result.pv_power_w == 700.0
    assert result.plant_ac_power_w is None
    assert result.house_power_w is None
    assert result.quality is EnergyBalanceQuality.INCOMPLETE


def test_suspect_aligned_input_produces_suspect_calculation() -> None:
    result = EnergyBalanceService().calculate(
        _inputs(
            500.0,
            300.0,
            plant_quality=MeasurementQuality.SUSPECT,
        )
    )

    assert result.house_power_w == 800.0
    assert result.quality is EnergyBalanceQuality.SUSPECT


def test_battery_channels_and_soc_are_forwarded_without_loss_estimate() -> None:
    result = EnergyBalanceService().calculate(
        _inputs(
            500.0,
            300.0,
            battery_charge_power_w=120.0,
            battery_discharge_power_w=0.0,
            battery_soc_percent=74.0,
        )
    )

    assert result.battery_charge_power_w == 120.0
    assert result.battery_discharge_power_w == 0.0
    assert result.battery_soc_percent == 74.0
    assert result.quality is EnergyBalanceQuality.CALCULATED
    assert all("loss" not in finding.code for finding in result.findings)


def test_simultaneous_battery_flows_are_visible_and_suspect() -> None:
    result = EnergyBalanceService().calculate(
        _inputs(
            500.0,
            300.0,
            battery_charge_power_w=10.0,
            battery_discharge_power_w=20.0,
        )
    )

    assert result.battery_charge_power_w == 10.0
    assert result.battery_discharge_power_w == 20.0
    assert result.quality is EnergyBalanceQuality.SUSPECT
    assert result.findings[0].code == "simultaneous_battery_charge_and_discharge"


def test_invalid_battery_values_are_not_exposed_as_valid_outputs() -> None:
    result = EnergyBalanceService().calculate(
        _inputs(
            500.0,
            300.0,
            battery_charge_power_w=-1.0,
            battery_discharge_power_w=-2.0,
            battery_soc_percent=101.0,
        )
    )

    assert result.battery_charge_power_w is None
    assert result.battery_discharge_power_w is None
    assert result.battery_soc_percent is None
    assert result.quality is EnergyBalanceQuality.SUSPECT
    assert {finding.code for finding in result.findings} == {
        "negative_battery_charge_power",
        "negative_battery_discharge_power",
        "battery_soc_out_of_range",
    }


def test_battery_values_remain_visible_when_ac_balance_is_incomplete() -> None:
    result = EnergyBalanceService().calculate(
        _inputs(
            500.0,
            None,
            battery_charge_power_w=100.0,
            battery_discharge_power_w=0.0,
            battery_soc_percent=50.0,
        )
    )

    assert result.house_power_w is None
    assert result.battery_charge_power_w == 100.0
    assert result.battery_soc_percent == 50.0
    assert result.quality is EnergyBalanceQuality.INCOMPLETE


def test_result_model_rejects_simultaneous_grid_directions() -> None:
    base = EnergyBalanceService().calculate(_inputs(500.0, 300.0))

    with pytest.raises(ValueError, match="cannot both be positive"):
        EnergyBalanceResult(
            house_power_w=base.house_power_w,
            grid_power_w=base.grid_power_w,
            grid_import_power_w=1.0,
            grid_export_power_w=1.0,
            plant_ac_power_w=base.plant_ac_power_w,
            pv_power_w=None,
            battery_charge_power_w=None,
            battery_discharge_power_w=None,
            battery_soc_percent=None,
            self_consumed_power_w=None,
            self_consumption_rate_percent=None,
            autonomy_rate_percent=None,
            residual_power_w=base.residual_power_w,
            quality=base.quality,
            calculated_at=NOW,
            source_metadata=base.source_metadata,
        )
