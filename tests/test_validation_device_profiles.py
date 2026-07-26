"""Test device profiles, sentinels, diagnostics, and battery SOC limits."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit
from solarinspector_core.validation import (
    DeviceDiagnosticRule,
    KnownDeviceErrorValueRule,
    MeasurementCandidate,
    PhaseConsistencyLimits,
    RangeRule,
    ValidationContext,
    ValidationDecision,
    ValidationRule,
    normalize_validation_profile,
    shelly_house_profile,
    shelly_plant_profile,
    shelly_pro_3em_house_profile,
    solarkon_800w_profile,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.PLANT_AC_POWER,
        "value": 0.0,
        "unit": Unit.WATT,
        "source_id": "solakon_one",
        "role": MeasurementRole.SOLAR_SYSTEM,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _context() -> ValidationContext:
    return ValidationContext(now=NOW)


def test_solarkon_profile_warns_above_nominal_and_rejects_extreme_power() -> None:
    profile = solarkon_800w_profile()
    limits = profile.range_for(Metric.PLANT_AC_POWER)
    assert limits is not None
    rule = RangeRule.from_config(limits.as_config())

    warning = rule.evaluate(_candidate(value=835), _context())
    rejected = rule.evaluate(_candidate(value=8350), _context())

    assert warning.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert rejected.decision is ValidationDecision.REJECT


@pytest.mark.parametrize(
    ("value", "decision"),
    [
        (-100.0, ValidationDecision.ACCEPT_WITH_WARNING),
        (0.0, ValidationDecision.ACCEPT),
        (800.0, ValidationDecision.ACCEPT),
        (960.0, ValidationDecision.ACCEPT_WITH_WARNING),
        (960.1, ValidationDecision.REJECT),
    ],
)
def test_solarkon_profile_has_explicit_power_boundaries(
    value: float,
    decision: ValidationDecision,
) -> None:
    limits = solarkon_800w_profile().range_for(Metric.PLANT_AC_POWER)
    assert limits is not None

    result = RangeRule.from_config(limits.as_config()).evaluate(
        _candidate(value=value),
        _context(),
    )

    assert result.decision is decision


@pytest.mark.parametrize(
    ("value", "decision"),
    [
        (0.0, ValidationDecision.ACCEPT),
        (100.0, ValidationDecision.ACCEPT),
        (-0.1, ValidationDecision.REJECT),
        (100.1, ValidationDecision.REJECT),
    ],
)
def test_solarkon_profile_validates_battery_soc(
    value: float,
    decision: ValidationDecision,
) -> None:
    limits = solarkon_800w_profile().range_for(Metric.BATTERY_SOC)
    assert limits is not None
    result = RangeRule.from_config(limits.as_config()).evaluate(
        _candidate(
            metric=Metric.BATTERY_SOC,
            value=value,
            unit=Unit.PERCENT,
            role=MeasurementRole.BATTERY_SYSTEM,
        ),
        _context(),
    )

    assert result.decision is decision


def test_shelly_plant_profile_uses_connected_plant_limit() -> None:
    profile = shelly_plant_profile(
        nominal_ac_power_w=600,
        reject_factor=1.25,
    )
    limits = profile.range_for(Metric.PLANT_AC_POWER)
    assert limits is not None

    assert limits.warning_max == 600.0
    assert limits.reject_max == 750.0


def test_shelly_house_profile_derives_limits_from_explicit_installation() -> None:
    profile = shelly_house_profile(
        nominal_voltage_v=230,
        main_fuse_a=35,
    )
    phase_limits = profile.range_for(Metric.PHASE_POWER_L1)
    total_limits = profile.range_for(Metric.GRID_POWER)

    assert phase_limits is not None
    assert total_limits is not None
    assert phase_limits.warning_max == 8050.0
    assert phase_limits.reject_max == 9660.0
    assert total_limits.warning_max == 24150.0
    assert total_limits.reject_max == 28980.0


def test_shelly_house_profile_does_not_guess_installation_limits() -> None:
    with pytest.raises(TypeError, match="must be a real number"):
        shelly_house_profile(
            nominal_voltage_v=230,
            main_fuse_a=True,
        )

    with pytest.raises(ValueError, match="greater than zero"):
        shelly_house_profile(
            nominal_voltage_v=230,
            main_fuse_a=0,
        )


def test_shelly_pro_profile_keeps_distinct_profile_name() -> None:
    profile = shelly_pro_3em_house_profile(
        nominal_voltage_v=230,
        main_fuse_a=35,
    )

    assert profile.name == "shelly_pro_3em_house_meter"


def test_profile_configuration_is_accepted_and_preserves_phase_settings() -> None:
    profile = shelly_house_profile(
        nominal_voltage_v=230,
        main_fuse_a=35,
        phase_consistency=PhaseConsistencyLimits(
            warning_absolute_w=25,
            warning_relative=0.04,
            reject_absolute_w=120,
            reject_relative=0.12,
            maximum_phase_skew_seconds=3,
        ),
    )

    normalized = normalize_validation_profile(profile.as_config())

    assert normalized["required_metrics"] == [
        "phase_power_l1",
        "phase_power_l2",
        "phase_power_l3",
    ]
    assert normalized["ranges"]["grid_power"]["reject_max"] == 28980.0
    assert normalized["phase_consistency"]["warning_absolute_w"] == 25.0
    assert normalized["phase_consistency"]["maximum_phase_skew_seconds"] == 3.0


def test_known_device_error_rule_checks_raw_value_before_scaling() -> None:
    rule = KnownDeviceErrorValueRule((65535.0,))
    result = rule.evaluate(
        _candidate(
            metric=Metric.BATTERY_SOC,
            value=65.535,
            unit=Unit.PERCENT,
            role=MeasurementRole.BATTERY_SYSTEM,
            raw_value=65535,
        ),
        _context(),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].rule_id == "VAL-FMT-002"
    assert dict(result.findings[0].details)["matched_field"] == "raw_value"


def test_known_device_error_rule_preserves_valid_zero() -> None:
    result = KnownDeviceErrorValueRule((65535.0,)).evaluate(
        _candidate(value=0, raw_value=0),
        _context(),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_device_diagnostic_rule_prioritizes_errors_over_warnings() -> None:
    rule = DeviceDiagnosticRule(
        warning_markers=("partial",),
        error_markers=("invalid",),
    )
    result = rule.evaluate(
        _candidate(
            diagnostics=(
                "Partial register block",
                "Phase value invalid",
            )
        ),
        _context(),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].code == "device_diagnostic_error"


def test_device_diagnostic_rule_warns_without_error_marker() -> None:
    result = DeviceDiagnosticRule(
        warning_markers=("partial",),
        error_markers=("invalid",),
    ).evaluate(
        _candidate(diagnostics=("Partial register block",)),
        _context(),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].code == "device_diagnostic_warning"


def test_device_rules_implement_common_protocol() -> None:
    rules = (
        KnownDeviceErrorValueRule((65535.0,)),
        DeviceDiagnosticRule(warning_markers=("partial",)),
    )

    assert all(isinstance(rule, ValidationRule) for rule in rules)
