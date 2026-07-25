"""Test phase completeness and configurable device-total consistency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit
from solarinspector_core.services.phase_power import (
    analyze_phase_power,
    phase_total_tolerance_w,
)
from solarinspector_core.validation import (
    MeasurementCandidate,
    PhaseCompletenessRule,
    PhaseSumConsistencyRule,
    ValidationContext,
    ValidationDecision,
    ValidationRule,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
PHASE_METRICS = (
    Metric.PHASE_POWER_L1,
    Metric.PHASE_POWER_L2,
    Metric.PHASE_POWER_L3,
)


def _phase(
    metric: Metric,
    value: float,
    **overrides: object,
) -> Measurement:
    values: dict[str, object] = {
        "metric": metric,
        "value": value,
        "unit": Unit.WATT,
        "source_id": "house_meter",
        "role": MeasurementRole.HOUSE_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.MEASURED,
    }
    values.update(overrides)
    return Measurement(**values)  # type: ignore[arg-type]


def _phases(
    values: tuple[float, float, float] = (100.0, 200.0, 300.0),
    **overrides: object,
) -> tuple[Measurement, ...]:
    return tuple(
        _phase(metric, value, **overrides)
        for metric, value in zip(PHASE_METRICS, values)
    )


def _candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 600.0,
        "unit": Unit.WATT,
        "source_id": "house_meter",
        "role": MeasurementRole.HOUSE_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _context(
    measurements: tuple[Measurement, ...],
) -> ValidationContext:
    return ValidationContext(
        now=NOW,
        comparison_measurements=measurements,
    )


def test_phase_tolerance_uses_larger_absolute_or_relative_limit() -> None:
    assert (
        phase_total_tolerance_w(
            600,
            600,
            absolute_tolerance_w=20,
            relative_tolerance=0.03,
        )
        == 20.0
    )
    assert (
        phase_total_tolerance_w(
            1000,
            1000,
            absolute_tolerance_w=20,
            relative_tolerance=0.03,
        )
        == 30.0
    )


def test_phase_analysis_keeps_legacy_defaults_and_accepts_custom_limits() -> None:
    legacy = analyze_phase_power(
        (100.0, 200.0, 300.0),
        reported_total_w=650.0,
    )
    relaxed = analyze_phase_power(
        (100.0, 200.0, 300.0),
        reported_total_w=650.0,
        absolute_total_tolerance_w=60.0,
        relative_total_tolerance=0.03,
    )

    assert legacy.total_consistent is False
    assert relaxed.total_consistent is True


def test_phase_completeness_accepts_three_comparable_phases() -> None:
    result = PhaseCompletenessRule().evaluate(
        _candidate(),
        _context(_phases()),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_phase_completeness_warns_for_missing_phase() -> None:
    result = PhaseCompletenessRule().evaluate(
        _candidate(),
        _context(_phases()[:2]),
    )
    details = dict(result.findings[0].details)

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert result.findings[0].rule_id == "VAL-PHASE-001"
    assert details["available_count"] == 2
    assert details["missing_metrics"] == ("phase_power_l3",)


def test_phase_completeness_ignores_other_source_and_rejected_phase() -> None:
    measurements = (
        _phase(Metric.PHASE_POWER_L1, 100),
        _phase(
            Metric.PHASE_POWER_L2,
            200,
            source_id="other",
        ),
        _phase(
            Metric.PHASE_POWER_L3,
            300,
            quality=MeasurementQuality.REJECTED,
        ),
    )
    result = PhaseCompletenessRule().evaluate(
        _candidate(),
        _context(measurements),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert dict(result.findings[0].details)["available_count"] == 1


def test_phase_completeness_applies_timestamp_skew() -> None:
    measurements = (
        *_phases()[:2],
        _phase(
            Metric.PHASE_POWER_L3,
            300,
            measured_at=NOW + timedelta(seconds=3),
            received_at=NOW + timedelta(seconds=3),
        ),
    )
    result = PhaseCompletenessRule(
        maximum_phase_skew_seconds=2,
    ).evaluate(
        _candidate(),
        _context(measurements),
    )

    assert result.decision is ValidationDecision.ACCEPT_WITH_WARNING


@pytest.mark.parametrize(
    ("reported_total", "decision"),
    [
        (610.0, ValidationDecision.ACCEPT),
        (650.0, ValidationDecision.ACCEPT_WITH_WARNING),
        (750.0, ValidationDecision.REJECT),
    ],
)
def test_phase_sum_rule_separates_warning_and_rejection(
    reported_total: float,
    decision: ValidationDecision,
) -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value=reported_total),
        _context(_phases()),
    )

    assert result.decision is decision


def test_phase_sum_rule_exposes_calculated_and_reported_totals() -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value=650),
        _context(_phases()),
    )
    details = dict(result.findings[0].details)

    assert result.findings[0].rule_id == "VAL-PHASE-002"
    assert details["calculated_total_w"] == 600.0
    assert details["reported_total_w"] == 650.0
    assert details["total_delta_w"] == 50.0


def test_phase_sum_rule_skips_incomplete_phase_set() -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value=900),
        _context(_phases()[:2]),
    )

    assert result.decision is ValidationDecision.ACCEPT
    assert result.findings == ()


def test_phase_sum_rule_preserves_real_zero() -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value=0),
        _context(_phases((0.0, 0.0, 0.0))),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_phase_sum_rule_uses_signed_values_without_magnitude_sum() -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value=-600),
        _context(_phases((-100.0, -200.0, -300.0))),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_phase_sum_rule_defers_invalid_total_to_format_rule() -> None:
    result = PhaseSumConsistencyRule().evaluate(
        _candidate(value="600"),
        _context(_phases()),
    )

    assert result.decision is ValidationDecision.ACCEPT


def test_phase_rules_validate_constructor_ordering() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        PhaseSumConsistencyRule(
            warning_absolute_w=101,
            reject_absolute_w=100,
        )

    with pytest.raises(ValueError, match="must not exceed"):
        PhaseSumConsistencyRule(
            warning_relative=0.11,
            reject_relative=0.10,
        )


def test_phase_rules_implement_common_protocol() -> None:
    rules = (
        PhaseCompletenessRule(),
        PhaseSumConsistencyRule(),
    )

    assert all(isinstance(rule, ValidationRule) for rule in rules)
