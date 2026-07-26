"""Test historical delta, counter, and energy-growth validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import Unit
from zrzavy_energy_monitor_core.validation import (
    EnergyDeltaRule,
    MaximumDeltaRule,
    MeasurementCandidate,
    MonotonicCounterRule,
    ValidationContext,
    ValidationDecision,
    ValidationRule,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _previous(**overrides: object) -> Measurement:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 100.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return Measurement(**values)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 120.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW + timedelta(seconds=10),
        "received_at": NOW + timedelta(seconds=10),
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _context(
    previous: Measurement | None = None,
) -> ValidationContext:
    return ValidationContext(
        now=NOW + timedelta(seconds=10),
        previous_measurement=previous,
    )


def _energy_previous(**overrides: object) -> Measurement:
    values: dict[str, object] = {
        "metric": Metric.GRID_IMPORT_TOTAL,
        "value": 1000.0,
        "unit": Unit.WATT_HOUR,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return Measurement(**values)  # type: ignore[arg-type]


def _energy_candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_IMPORT_TOTAL,
        "value": 1010.0,
        "unit": Unit.WATT_HOUR,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW + timedelta(hours=1),
        "received_at": NOW + timedelta(hours=1),
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def test_historical_rules_implement_common_protocol() -> None:
    rules = (
        MaximumDeltaRule(),
        MonotonicCounterRule(),
        EnergyDeltaRule(maximum_power_w=800),
    )

    assert all(isinstance(rule, ValidationRule) for rule in rules)


def test_delta_rule_accepts_first_sample_and_stream_mismatch() -> None:
    rule = MaximumDeltaRule(reject_absolute=10)

    first = rule.evaluate(_candidate(), _context())
    mismatch = rule.evaluate(
        _candidate(),
        _context(_previous(source_id="other")),
    )

    assert first.decision is ValidationDecision.ACCEPT
    assert mismatch.decision is ValidationDecision.ACCEPT


@pytest.mark.parametrize(
    ("value", "decision"),
    [
        (110.0, ValidationDecision.ACCEPT),
        (110.1, ValidationDecision.ACCEPT_WITH_WARNING),
        (120.0, ValidationDecision.ACCEPT_WITH_WARNING),
        (120.1, ValidationDecision.REJECT),
    ],
)
def test_delta_rule_applies_absolute_threshold_boundaries(
    value: float,
    decision: ValidationDecision,
) -> None:
    result = MaximumDeltaRule(
        warning_absolute=10,
        reject_absolute=20,
    ).evaluate(
        _candidate(value=value),
        _context(_previous()),
    )

    assert result.decision is decision


def test_delta_rule_uses_relative_percentage() -> None:
    warning = MaximumDeltaRule(
        warning_relative_percent=10,
        reject_relative_percent=20,
    ).evaluate(
        _candidate(value=115),
        _context(_previous(value=100)),
    )
    rejected = MaximumDeltaRule(
        warning_relative_percent=10,
        reject_relative_percent=20,
    ).evaluate(
        _candidate(value=121),
        _context(_previous(value=100)),
    )

    assert warning.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert rejected.decision is ValidationDecision.REJECT


def test_delta_rule_uses_minimum_reference_near_zero() -> None:
    result = MaximumDeltaRule(
        warning_relative_percent=10,
        reject_relative_percent=20,
        minimum_reference=100,
    ).evaluate(
        _candidate(value=15),
        _context(_previous(value=0)),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING


def test_delta_rule_uses_change_per_second() -> None:
    warning = MaximumDeltaRule(
        warning_per_second=1,
        reject_per_second=2,
    ).evaluate(
        _candidate(value=115),
        _context(_previous(value=100)),
    )
    rejected = MaximumDeltaRule(
        warning_per_second=1,
        reject_per_second=2,
    ).evaluate(
        _candidate(value=121),
        _context(_previous(value=100)),
    )

    assert warning.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert rejected.decision is ValidationDecision.REJECT


def test_delta_rule_reports_trigger_and_values() -> None:
    result = MaximumDeltaRule(
        warning_absolute=10,
        reject_absolute=20,
    ).evaluate(
        _candidate(value=121),
        _context(_previous()),
    )
    details = dict(result.findings[0].details)

    assert result.findings[0].rule_id == "VAL-DELTA-001"
    assert result.findings[0].severity is ValidationSeverity.ERROR
    assert details["limit_name"] == "reject_absolute"
    assert details["absolute_delta"] == 21.0
    assert details["current_value"] == 121.0


@pytest.mark.parametrize("value", [None, True, "120", float("nan")])
def test_delta_rule_defers_invalid_values_to_format_rule(
    value: object,
) -> None:
    result = MaximumDeltaRule(reject_absolute=10).evaluate(
        _candidate(value=value),
        _context(_previous()),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings == ()


def test_delta_rule_defers_non_positive_time_order() -> None:
    previous = _previous(measured_at=NOW + timedelta(seconds=10))
    result = MaximumDeltaRule(reject_absolute=1).evaluate(
        _candidate(value=1000),
        _context(previous),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_delta_rule_can_be_built_from_configuration() -> None:
    rule = MaximumDeltaRule.from_config(
        {
            "warning_absolute": "10",
            "reject_absolute": "20",
            "minimum_reference": "100",
        }
    )

    assert rule.warning_absolute == 10.0
    assert rule.reject_absolute == 20.0
    assert rule.minimum_reference == 100.0


@pytest.mark.parametrize("value", [1000, 1001])
def test_monotonic_rule_accepts_equal_or_increasing_counter(
    value: float,
) -> None:
    result = MonotonicCounterRule().evaluate(
        _energy_candidate(value=value),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_monotonic_rule_rejects_counter_rollback() -> None:
    result = MonotonicCounterRule().evaluate(
        _energy_candidate(value=999),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].rule_id == "VAL-COUNTER-001"
    assert result.findings[0].code == "counter_rollback"


def test_monotonic_rule_warns_for_tolerated_small_decrease() -> None:
    result = MonotonicCounterRule(warning_tolerance=0.5).evaluate(
        _energy_candidate(value=999.75),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].code == "counter_small_decrease"


def test_monotonic_rule_rejects_decrease_beyond_warning_tolerance() -> None:
    result = MonotonicCounterRule(warning_tolerance=0.5).evaluate(
        _energy_candidate(value=999.49),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.REJECT


def test_monotonic_rule_requires_non_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        MonotonicCounterRule(warning_tolerance=-0.1)


def test_energy_delta_rule_accepts_first_and_plausible_growth() -> None:
    rule = EnergyDeltaRule(maximum_power_w=800)

    first = rule.evaluate(_energy_candidate(), _context())
    plausible = rule.evaluate(
        _energy_candidate(value=1800),
        _context(_energy_previous(value=1000)),
    )

    assert first.decision is ValidationDecision.ACCEPT
    assert plausible.decision is ValidationDecision.ACCEPT


def test_energy_delta_rule_warns_between_power_factors() -> None:
    result = EnergyDeltaRule(
        maximum_power_w=800,
        warning_factor=1.0,
        reject_factor=1.2,
    ).evaluate(
        _energy_candidate(value=1880),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].code == "energy_delta_high"


def test_energy_delta_rule_rejects_impossible_growth() -> None:
    result = EnergyDeltaRule(
        maximum_power_w=800,
        warning_factor=1.0,
        reject_factor=1.2,
    ).evaluate(
        _energy_candidate(value=1961),
        _context(_energy_previous(value=1000)),
    )
    details = dict(result.findings[0].details)

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].rule_id == "VAL-COUNTER-002"
    assert result.findings[0].code == "energy_delta_impossible"
    assert details["physical_max_wh"] == 800.0


def test_energy_delta_rule_scales_limit_with_elapsed_time() -> None:
    result = EnergyDeltaRule(
        maximum_power_w=800,
        warning_factor=1.0,
        reject_factor=1.2,
    ).evaluate(
        _energy_candidate(
            value=1120,
            measured_at=NOW + timedelta(minutes=10),
            received_at=NOW + timedelta(minutes=10),
        ),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_energy_delta_rule_defers_rollback_to_monotonic_rule() -> None:
    result = EnergyDeltaRule(maximum_power_w=800).evaluate(
        _energy_candidate(value=999),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_energy_delta_rule_defers_missing_or_non_positive_time() -> None:
    rule = EnergyDeltaRule(maximum_power_w=800)
    missing = rule.evaluate(
        _energy_candidate(measured_at=None),
        _context(_energy_previous()),
    )
    non_positive = rule.evaluate(
        _energy_candidate(
            value=2000,
            measured_at=NOW,
            received_at=NOW,
        ),
        _context(_energy_previous()),
    )

    assert missing.decision is ValidationDecision.ACCEPT
    assert non_positive.decision is ValidationDecision.ACCEPT


def test_energy_delta_rule_rejects_growth_when_maximum_power_is_zero() -> None:
    result = EnergyDeltaRule(maximum_power_w=0).evaluate(
        _energy_candidate(value=1000.1),
        _context(_energy_previous(value=1000)),
    )

    assert result.decision is ValidationDecision.REJECT


def test_energy_delta_rule_validates_constructor_limits() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        EnergyDeltaRule(maximum_power_w=-1)

    with pytest.raises(ValueError, match="must not exceed"):
        EnergyDeltaRule(
            maximum_power_w=800,
            warning_factor=1.3,
            reject_factor=1.2,
        )
