"""Test the stateless basis rules introduced in phase 08 block 08.3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit
from solarinspector_core.validation import (
    ExpectedUnitRule,
    FiniteNumberRule,
    MeasurementAgeRule,
    MeasurementCandidate,
    RangeRule,
    TimestampRule,
    ValidationContext,
    ValidationDecision,
    ValidationRule,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 0.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
        "raw_value": "0",
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _context(**overrides: object) -> ValidationContext:
    values: dict[str, object] = {"now": NOW}
    values.update(overrides)
    return ValidationContext(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, 0.0, -12.5, 800])
def test_finite_number_rule_accepts_real_finite_values(value: object) -> None:
    result = FiniteNumberRule().evaluate(_candidate(value=value), _context())

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings == ()


@pytest.mark.parametrize(
    ("value", "expected_code"),
    [
        (None, "value_missing"),
        ("", "value_missing"),
        ("   ", "value_missing"),
        (True, "boolean_value"),
        (False, "boolean_value"),
        ("12.5", "invalid_numeric_type"),
        (["12.5"], "invalid_numeric_type"),
        (float("nan"), "non_finite_value"),
        (float("inf"), "non_finite_value"),
        (float("-inf"), "non_finite_value"),
    ],
)
def test_finite_number_rule_rejects_unsafe_values(
    value: object,
    expected_code: str,
) -> None:
    result = FiniteNumberRule().evaluate(_candidate(value=value), _context())

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].rule_id == "VAL-FMT-001"
    assert result.findings[0].code == expected_code
    assert result.findings[0].severity is ValidationSeverity.ERROR


def test_expected_unit_rule_accepts_only_the_metric_unit_enum() -> None:
    accepted = ExpectedUnitRule().evaluate(_candidate(unit=Unit.WATT), _context())
    textual = ExpectedUnitRule().evaluate(_candidate(unit="W"), _context())
    missing = ExpectedUnitRule().evaluate(_candidate(unit=None), _context())
    wrong = ExpectedUnitRule().evaluate(
        _candidate(unit=Unit.WATT_HOUR),
        _context(),
    )

    assert accepted.decision is ValidationDecision.ACCEPT
    assert textual.findings[0].code == "unit_not_canonical"
    assert missing.findings[0].code == "unit_missing"
    assert wrong.findings[0].code == "unexpected_unit"


def test_expected_unit_rule_uses_the_metric_mapping() -> None:
    result = ExpectedUnitRule().evaluate(
        _candidate(
            metric=Metric.GRID_IMPORT_TOTAL,
            unit=Unit.WATT_HOUR,
        ),
        _context(),
    )

    assert result.decision is ValidationDecision.ACCEPT


@pytest.mark.parametrize(
    ("value", "decision"),
    [
        (-100, ValidationDecision.ACCEPT_WITH_WARNING),
        (0, ValidationDecision.ACCEPT),
        (800, ValidationDecision.ACCEPT),
        (960, ValidationDecision.ACCEPT_WITH_WARNING),
    ],
)
def test_range_rule_keeps_reject_boundaries_usable(
    value: float,
    decision: ValidationDecision,
) -> None:
    result = RangeRule(
        warning_min=0,
        warning_max=800,
        reject_min=-100,
        reject_max=960,
    ).evaluate(_candidate(value=value), _context())

    assert result.decision is decision


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (-0.1, "below_warning_minimum"),
        (800.1, "above_warning_maximum"),
    ],
)
def test_range_rule_emits_warning_between_warning_and_reject_bounds(
    value: float,
    code: str,
) -> None:
    result = RangeRule(
        warning_min=0,
        warning_max=800,
        reject_min=-100,
        reject_max=960,
    ).evaluate(_candidate(value=value), _context())

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].rule_id == "VAL-RANGE-001"
    assert result.findings[0].code == code
    assert result.findings[0].severity is ValidationSeverity.WARNING


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (-100.1, "below_reject_minimum"),
        (960.1, "above_reject_maximum"),
    ],
)
def test_range_rule_rejects_values_outside_hard_bounds(
    value: float,
    code: str,
) -> None:
    result = RangeRule(
        warning_min=0,
        warning_max=800,
        reject_min=-100,
        reject_max=960,
    ).evaluate(_candidate(value=value), _context())

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].code == code
    assert result.findings[0].severity is ValidationSeverity.ERROR


def test_range_rule_can_be_built_from_configuration() -> None:
    rule = RangeRule.from_config(
        {
            "warning_max": "800",
            "reject_max": "960",
            "future_field": "preserved by configuration, ignored by rule",
        }
    )

    assert rule.warning_max == 800.0
    assert rule.reject_max == 960.0


@pytest.mark.parametrize("value", [None, "800", True, float("nan")])
def test_range_rule_does_not_duplicate_numeric_format_findings(
    value: object,
) -> None:
    result = RangeRule(reject_max=960).evaluate(
        _candidate(value=value),
        _context(),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings == ()


def test_basic_rules_implement_the_common_protocol() -> None:
    rules = (
        FiniteNumberRule(),
        ExpectedUnitRule(),
        RangeRule(),
        TimestampRule(),
        MeasurementAgeRule(),
    )

    assert all(isinstance(rule, ValidationRule) for rule in rules)


def test_timestamp_rule_accepts_small_clock_skew_within_tolerance() -> None:
    result = TimestampRule(maximum_future_seconds=5).evaluate(
        _candidate(
            measured_at=NOW + timedelta(seconds=4),
            received_at=NOW,
        ),
        _context(),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_timestamp_rule_rejects_missing_and_naive_measurement_time() -> None:
    missing = TimestampRule().evaluate(
        _candidate(measured_at=None),
        _context(),
    )
    naive = TimestampRule().evaluate(
        _candidate(measured_at=datetime(2026, 7, 25, 8, 0)),
        _context(),
    )

    assert missing.findings[0].code == "measured_at_missing"
    assert naive.findings[0].code == "measured_at_naive"


def test_timestamp_rule_rejects_measurement_too_far_in_future() -> None:
    result = TimestampRule(maximum_future_seconds=5).evaluate(
        _candidate(measured_at=NOW + timedelta(seconds=6)),
        _context(),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].code == "measured_at_in_future"


def test_timestamp_rule_rejects_receive_time_too_far_in_future() -> None:
    result = TimestampRule(maximum_future_seconds=5).evaluate(
        _candidate(
            measured_at=NOW,
            received_at=NOW + timedelta(seconds=6),
        ),
        _context(),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].code == "received_at_in_future"


def test_timestamp_rule_rejects_measurement_after_receive_time() -> None:
    context_now = NOW + timedelta(minutes=1)
    result = TimestampRule(maximum_future_seconds=5).evaluate(
        _candidate(
            measured_at=NOW + timedelta(seconds=10),
            received_at=NOW,
        ),
        _context(now=context_now),
    )

    assert result.decision is ValidationDecision.REJECT
    assert result.findings[0].code == "measured_after_received"


def test_timestamp_rules_can_be_built_from_time_configuration() -> None:
    timestamp = TimestampRule.from_config(
        {
            "fresh_seconds": 10,
            "stale_seconds": 20,
            "maximum_future_seconds": 3,
        }
    )
    age = MeasurementAgeRule.from_config(
        {
            "fresh_seconds": 10,
            "stale_seconds": 20,
            "maximum_future_seconds": 3,
        }
    )

    assert timestamp.maximum_future_seconds == 3.0
    assert age.fresh_seconds == 10.0
    assert age.stale_seconds == 20.0


@pytest.mark.parametrize(
    ("age_seconds", "decision", "code"),
    [
        (0, ValidationDecision.ACCEPT, None),
        (15, ValidationDecision.ACCEPT, None),
        (15.1, ValidationDecision.ACCEPT_WITH_WARNING, "measurement_aged"),
        (60, ValidationDecision.ACCEPT_WITH_WARNING, "measurement_aged"),
        (60.1, ValidationDecision.REJECT, "measurement_stale"),
    ],
)
def test_measurement_age_rule_applies_fresh_and_stale_boundaries(
    age_seconds: float,
    decision: ValidationDecision,
    code: str | None,
) -> None:
    result = MeasurementAgeRule(
        fresh_seconds=15,
        stale_seconds=60,
    ).evaluate(
        _candidate(measured_at=NOW - timedelta(seconds=age_seconds)),
        _context(),
    )

    assert result.decision is decision
    if code is None:
        assert result.findings == ()
    else:
        assert result.findings[0].code == code


def test_measurement_age_rule_defers_invalid_or_future_timestamps() -> None:
    rule = MeasurementAgeRule()

    missing = rule.evaluate(_candidate(measured_at=None), _context())
    naive = rule.evaluate(
        _candidate(measured_at=datetime(2026, 7, 25, 8, 0)),
        _context(),
    )
    future = rule.evaluate(
        _candidate(measured_at=NOW + timedelta(seconds=30)),
        _context(),
    )

    assert missing.decision is ValidationDecision.ACCEPT
    assert naive.decision is ValidationDecision.ACCEPT
    assert future.decision is ValidationDecision.ACCEPT


def test_time_rule_constructors_reject_unsafe_thresholds() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        TimestampRule(maximum_future_seconds=-1)

    with pytest.raises(ValueError, match="must not exceed"):
        MeasurementAgeRule(fresh_seconds=61, stale_seconds=60)
