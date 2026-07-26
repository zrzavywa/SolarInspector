"""Test the immutable validation models introduced in phase 08."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit
from solarinspector_core.validation import (
    MeasurementCandidate,
    RuleEvaluation,
    ValidationContext,
    ValidationDecision,
    ValidationFinding,
    ValidationResult,
    ValidationRule,
    ValidationSeverity,
    ValidationStateKey,
    quality_for_decision,
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
        "raw_value": "0.0",
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def _warning_finding() -> ValidationFinding:
    return ValidationFinding(
        rule_id="VAL-RANGE-001",
        code="above_warning_maximum",
        message="Value exceeds the configured warning maximum.",
        severity=ValidationSeverity.WARNING,
    )


def _error_finding() -> ValidationFinding:
    return ValidationFinding(
        rule_id="VAL-FMT-001",
        code="not_finite",
        message="Value is not finite.",
        severity=ValidationSeverity.ERROR,
    )


def test_candidate_retains_values_that_strict_measurement_rejects() -> None:
    candidate = _candidate(
        value=None,
        unit="kW",
        source_id="",
        measured_at=None,
        raw_value={"value": None},
    )

    assert candidate.value is None
    assert candidate.unit == "kW"
    assert candidate.source_id == ""
    assert candidate.measured_at is None
    assert candidate.effective_raw_value == {"value": None}


def test_candidate_requires_timezone_aware_receive_time() -> None:
    with pytest.raises(ValueError, match="received_at must be timezone-aware"):
        _candidate(received_at=datetime(2026, 7, 25, 8, 0))


def test_candidate_builds_strict_measurement_after_acceptance() -> None:
    measurement = _candidate().build_measurement(
        value=0.0,
        quality=MeasurementQuality.VALIDATED,
    )

    assert measurement.value == 0.0
    assert measurement.unit is Unit.WATT
    assert measurement.raw_value == "0.0"
    assert measurement.quality is MeasurementQuality.VALIDATED


def test_candidate_cannot_build_measurement_with_unresolved_unit() -> None:
    with pytest.raises(ValueError, match="canonical Unit"):
        _candidate(unit="W").build_measurement(
            value=10.0,
            quality=MeasurementQuality.REPORTED,
        )


def test_finding_requires_unique_non_empty_diagnostic_keys() -> None:
    with pytest.raises(ValueError, match="occurs more than once"):
        ValidationFinding(
            rule_id="VAL-RANGE-001",
            code="range",
            message="Range finding",
            severity=ValidationSeverity.WARNING,
            details=(("limit", 800.0), ("limit", 960.0)),
        )


def test_rule_evaluation_enforces_severity_contract() -> None:
    assert RuleEvaluation.accepted().decision is ValidationDecision.ACCEPT
    assert (
        RuleEvaluation.warning(_warning_finding()).decision
        is ValidationDecision.ACCEPT_WITH_WARNING
    )
    assert (
        RuleEvaluation.rejected(_error_finding()).decision is ValidationDecision.REJECT
    )

    with pytest.raises(ValueError, match="requires at least one warning"):
        RuleEvaluation(ValidationDecision.ACCEPT_WITH_WARNING)


def test_quality_mapping_is_central_and_explicit() -> None:
    assert (
        quality_for_decision(
            ValidationDecision.ACCEPT,
            current_quality=MeasurementQuality.REPORTED,
        )
        is MeasurementQuality.REPORTED
    )
    assert (
        quality_for_decision(
            ValidationDecision.ACCEPT,
            current_quality=MeasurementQuality.REPORTED,
            cross_validated=True,
        )
        is MeasurementQuality.VALIDATED
    )
    assert (
        quality_for_decision(
            ValidationDecision.ACCEPT_WITH_WARNING,
            current_quality=MeasurementQuality.MEASURED,
        )
        is MeasurementQuality.SUSPECT
    )
    assert (
        quality_for_decision(
            ValidationDecision.REJECT,
            current_quality=MeasurementQuality.REPORTED,
            rejection_quality=MeasurementQuality.STALE,
        )
        is MeasurementQuality.STALE
    )


def test_validation_result_never_corrects_an_accepted_value() -> None:
    with pytest.raises(ValueError, match="must not automatically correct"):
        ValidationResult(
            decision=ValidationDecision.ACCEPT,
            quality=MeasurementQuality.REPORTED,
            raw_value=1000.0,
            candidate_value=1000.0,
            accepted_value=800.0,
        )


def test_validation_result_builders_preserve_zero_and_rejection_reason() -> None:
    accepted = ValidationResult.accepted(
        0.0,
        current_quality=MeasurementQuality.REPORTED,
        raw_value="0",
    )
    warning = ValidationResult.warning(
        810.0,
        raw_value=810,
        findings=(_warning_finding(),),
    )
    rejected = ValidationResult.rejected(
        raw_value=None,
        findings=(_error_finding(),),
        quality=MeasurementQuality.UNAVAILABLE,
    )

    assert accepted.accepted_value == 0.0
    assert accepted.quality is MeasurementQuality.REPORTED
    assert warning.quality is MeasurementQuality.SUSPECT
    assert rejected.accepted_value is None
    assert rejected.quality is MeasurementQuality.UNAVAILABLE


def test_rejected_result_accepts_candidate_value_for_diagnostics() -> None:
    result = ValidationResult.rejected(
        raw_value=1200,
        candidate_value=1200.0,
        findings=(_error_finding(),),
    )

    assert result.candidate_value == 1200.0
    assert result.accepted_value is None


def test_validation_state_key_requires_accepted_identity() -> None:
    key = ValidationStateKey(
        source_id=" grid_meter_primary ",
        role=MeasurementRole.GRID_METER,
        metric=Metric.GRID_POWER,
    )
    assert key.source_id == "grid_meter_primary"

    with pytest.raises(ValueError, match="source_id must not be empty"):
        ValidationStateKey(
            source_id=" ",
            role=MeasurementRole.GRID_METER,
            metric=Metric.GRID_POWER,
        )


def test_context_requires_timezone_aware_execution_clock() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        ValidationContext(now=datetime(2026, 7, 25, 8, 0))


def test_validation_rule_protocol_is_runtime_checkable() -> None:
    class FakeRule:
        @property
        def rule_id(self) -> str:
            return "VAL-TEST-001"

        def evaluate(
            self,
            candidate: MeasurementCandidate,
            context: ValidationContext,
        ) -> RuleEvaluation:
            del candidate, context
            return RuleEvaluation.accepted()

    assert isinstance(FakeRule(), ValidationRule)
