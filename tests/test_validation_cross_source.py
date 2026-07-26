"""Contract tests for time-window cross-source validation rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import Unit
from zrzavy_energy_monitor_core.validation import (
    CrossSourceComparisonLimits,
    CrossSourceTimeAlignmentRule,
    GridMeterCrossCheckRule,
    MeasurementCandidate,
    PlantPowerCrossCheckRule,
    ValidationContext,
    ValidationDecision,
    ValidationRule,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _measurement(
    *,
    source_id: str,
    role: MeasurementRole,
    metric: Metric,
    value: float,
    seconds_ago: float,
    quality: MeasurementQuality = MeasurementQuality.MEASURED,
) -> Measurement:
    measured_at = NOW - timedelta(seconds=seconds_ago)
    return Measurement(
        metric=metric,
        value=value,
        unit=Unit.WATT,
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=quality,
    )


def _plant_candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.PLANT_AC_POWER,
        "value": 400.0,
        "unit": Unit.WATT,
        "source_id": "solakon_one",
        "role": MeasurementRole.SOLAR_SYSTEM,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _grid_candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 500.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _context(
    *measurements: Measurement,
    comparable: bool | None = None,
) -> ValidationContext:
    settings: tuple[tuple[str, object], ...] = ()
    if comparable is not None:
        settings = (("measurement_position_comparable", comparable),)
    return ValidationContext(
        now=NOW,
        comparison_measurements=tuple(measurements),
        source_settings=settings,
    )


def _plant_history(
    *,
    solarkon_values: tuple[float, ...],
    shelly_values: tuple[float, ...],
    step_seconds: int = 15,
) -> tuple[Measurement, ...]:
    measurements: list[Measurement] = []
    for index, value in enumerate(solarkon_values, start=1):
        measurements.append(
            _measurement(
                source_id="solakon_one",
                role=MeasurementRole.SOLAR_SYSTEM,
                metric=Metric.PLANT_AC_POWER,
                value=value,
                seconds_ago=index * step_seconds,
            )
        )
    for index, value in enumerate(shelly_values):
        measurements.append(
            _measurement(
                source_id="solakon_meter",
                role=MeasurementRole.PLANT_METER,
                metric=Metric.PLANT_AC_POWER,
                value=value,
                seconds_ago=index * step_seconds,
            )
        )
    return tuple(measurements)


def _grid_history(
    *,
    official_values: tuple[float, ...],
    shelly_values: tuple[float, ...],
    step_seconds: int = 15,
) -> tuple[Measurement, ...]:
    measurements: list[Measurement] = []
    for index, value in enumerate(official_values, start=1):
        measurements.append(
            _measurement(
                source_id="grid_meter_primary",
                role=MeasurementRole.GRID_METER,
                metric=Metric.GRID_POWER,
                value=value,
                seconds_ago=index * step_seconds,
            )
        )
    for index, value in enumerate(shelly_values):
        measurements.append(
            _measurement(
                source_id="house_meter",
                role=MeasurementRole.HOUSE_METER,
                metric=Metric.HOUSE_POWER,
                value=value,
                seconds_ago=index * step_seconds,
            )
        )
    return tuple(measurements)


def test_cross_source_rules_implement_common_protocol() -> None:
    rules = (
        CrossSourceTimeAlignmentRule(
            comparison_source_id="solakon_meter",
            comparison_roles=(MeasurementRole.PLANT_METER,),
            comparison_metrics=(Metric.PLANT_AC_POWER,),
        ),
        PlantPowerCrossCheckRule(),
        GridMeterCrossCheckRule(),
    )

    assert all(isinstance(rule, ValidationRule) for rule in rules)


def test_time_alignment_accepts_peer_inside_window() -> None:
    result = CrossSourceTimeAlignmentRule(
        comparison_source_id="solakon_meter",
        comparison_roles=(MeasurementRole.PLANT_METER,),
        comparison_metrics=(Metric.PLANT_AC_POWER,),
        maximum_skew_seconds=10,
    ).evaluate(
        _plant_candidate(),
        _context(
            _measurement(
                source_id="solakon_meter",
                role=MeasurementRole.PLANT_METER,
                metric=Metric.PLANT_AC_POWER,
                value=405,
                seconds_ago=8,
            )
        ),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings[0].code == "cross_source_time_aligned"


def test_time_alignment_warns_for_known_but_old_peer() -> None:
    result = CrossSourceTimeAlignmentRule(
        comparison_source_id="solakon_meter",
        comparison_roles=(MeasurementRole.PLANT_METER,),
        comparison_metrics=(Metric.PLANT_AC_POWER,),
        maximum_skew_seconds=10,
    ).evaluate(
        _plant_candidate(),
        _context(
            _measurement(
                source_id="solakon_meter",
                role=MeasurementRole.PLANT_METER,
                metric=Metric.PLANT_AC_POWER,
                value=405,
                seconds_ago=11,
            )
        ),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].rule_id == "VAL-XTIME-001"


def test_time_alignment_does_not_warn_when_peer_is_absent() -> None:
    result = CrossSourceTimeAlignmentRule(
        comparison_source_id="solakon_meter",
        comparison_roles=(MeasurementRole.PLANT_METER,),
        comparison_metrics=(Metric.PLANT_AC_POWER,),
    ).evaluate(_plant_candidate(), _context())

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings == ()


def test_plant_check_uses_window_average_not_only_latest_value() -> None:
    history = _plant_history(
        solarkon_values=(400, 400),
        shelly_values=(100, 550, 550),
    )
    result = PlantPowerCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            warning_absolute_w=30,
            reject_absolute_w=100,
            warning_relative_percent=10,
            reject_relative_percent=30,
            window_seconds=30,
            minimum_duration_seconds=0,
            minimum_reference_w=100,
            minimum_samples=1,
        )
    ).evaluate(
        _plant_candidate(value=400),
        _context(*history),
    )

    assert result.decision is ValidationDecision.ACCEPT
    details = dict(result.findings[0].details)
    assert details["candidate_average_w"] == 400.0
    assert details["comparison_average_w"] == 400.0


def test_plant_check_warns_above_warning_tolerance() -> None:
    result = PlantPowerCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            warning_absolute_w=30,
            reject_absolute_w=150,
            warning_relative_percent=5,
            reject_relative_percent=40,
            window_seconds=30,
            minimum_duration_seconds=0,
            minimum_samples=1,
        )
    ).evaluate(
        _plant_candidate(value=400),
        _context(
            *_plant_history(
                solarkon_values=(400,),
                shelly_values=(470,),
            )
        ),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].rule_id == "VAL-XPLANT-001"
    assert result.findings[0].code == "cross_source_difference"


def test_large_transient_plant_difference_is_not_rejected() -> None:
    result = PlantPowerCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            warning_absolute_w=30,
            reject_absolute_w=100,
            warning_relative_percent=5,
            reject_relative_percent=20,
            window_seconds=30,
            minimum_duration_seconds=30,
            minimum_samples=2,
            allow_rejection=True,
        )
    ).evaluate(
        _plant_candidate(value=400),
        _context(
            *_plant_history(
                solarkon_values=(),
                shelly_values=(700,),
            )
        ),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].code == "cross_source_large_transient_difference"


def test_persistent_plant_difference_requires_explicit_rejection() -> None:
    history = _plant_history(
        solarkon_values=(400, 400),
        shelly_values=(700, 700, 700),
    )
    common = {
        "warning_absolute_w": 30,
        "reject_absolute_w": 100,
        "warning_relative_percent": 5,
        "reject_relative_percent": 20,
        "window_seconds": 30,
        "minimum_duration_seconds": 30,
        "minimum_reference_w": 100,
        "minimum_samples": 2,
    }
    safe_default = PlantPowerCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            **common,
            allow_rejection=False,
        )
    ).evaluate(_plant_candidate(), _context(*history))
    explicit_secondary = PlantPowerCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            **common,
            allow_rejection=True,
        )
    ).evaluate(_plant_candidate(), _context(*history))

    assert safe_default.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert explicit_secondary.decision is ValidationDecision.REJECT


def test_plant_check_ignores_wrong_contract_and_rejected_peer() -> None:
    wrong_candidate = PlantPowerCrossCheckRule().evaluate(
        _plant_candidate(metric=Metric.PV_POWER),
        _context(),
    )
    rejected_peer = PlantPowerCrossCheckRule().evaluate(
        _plant_candidate(),
        _context(
            _measurement(
                source_id="solakon_meter",
                role=MeasurementRole.PLANT_METER,
                metric=Metric.PLANT_AC_POWER,
                value=900,
                seconds_ago=0,
                quality=MeasurementQuality.REJECTED,
            )
        ),
    )

    assert wrong_candidate.decision is ValidationDecision.ACCEPT
    assert rejected_peer.findings == ()


def test_grid_check_is_skipped_without_comparable_position() -> None:
    history = _grid_history(
        official_values=(500, 500),
        shelly_values=(900, 900, 900),
    )
    result = GridMeterCrossCheckRule().evaluate(
        _grid_candidate(),
        _context(*history, comparable=False),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings[0].code == "grid_comparison_not_enabled"


def test_grid_check_accepts_comparable_consistent_windows() -> None:
    history = _grid_history(
        official_values=(500, 500),
        shelly_values=(510, 490, 500),
    )
    result = GridMeterCrossCheckRule().evaluate(
        _grid_candidate(),
        _context(*history, comparable=True),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings[0].code == "cross_source_consistent"


def test_grid_check_never_rejects_official_reference() -> None:
    history = _grid_history(
        official_values=(500, 500),
        shelly_values=(1200, 1200, 1200),
    )
    result = GridMeterCrossCheckRule(
        limits=CrossSourceComparisonLimits(
            warning_absolute_w=50,
            reject_absolute_w=250,
            warning_relative_percent=5,
            reject_relative_percent=20,
            window_seconds=30,
            minimum_duration_seconds=30,
            minimum_reference_w=200,
            minimum_samples=2,
            allow_rejection=True,
        )
    ).evaluate(
        _grid_candidate(),
        _context(*history, comparable=True),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].code == "cross_source_persistent_difference"


def test_grid_check_supports_house_total_and_legacy_grid_total() -> None:
    house_total = GridMeterCrossCheckRule().evaluate(
        _grid_candidate(),
        _context(
            _measurement(
                source_id="house_meter",
                role=MeasurementRole.HOUSE_METER,
                metric=Metric.HOUSE_POWER,
                value=500,
                seconds_ago=0,
            ),
            comparable=True,
        ),
    )
    legacy_grid_total = GridMeterCrossCheckRule().evaluate(
        _grid_candidate(),
        _context(
            _measurement(
                source_id="house_meter",
                role=MeasurementRole.GRID_METER,
                metric=Metric.GRID_POWER,
                value=500,
                seconds_ago=0,
            ),
            comparable=True,
        ),
    )

    assert house_total.decision is ValidationDecision.ACCEPT
    assert legacy_grid_total.decision is ValidationDecision.ACCEPT


def test_cross_source_limits_validate_order_and_duration() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        CrossSourceComparisonLimits(
            warning_absolute_w=101,
            reject_absolute_w=100,
        )

    with pytest.raises(ValueError, match="must not exceed window_seconds"):
        CrossSourceComparisonLimits(
            window_seconds=10,
            minimum_duration_seconds=11,
        )


def test_cross_source_limits_can_be_built_from_configuration() -> None:
    limits = CrossSourceComparisonLimits.from_config(
        {
            "warning_absolute_w": "30",
            "reject_absolute_w": "100",
            "window_seconds": "60",
            "minimum_duration_seconds": "30",
            "minimum_samples": "3",
            "allow_rejection": "true",
        }
    )

    assert limits.window_seconds == 60.0
    assert limits.minimum_samples == 3
    assert limits.allow_rejection is True
