"""Test deterministic aggregation and failure containment of the engine."""

from __future__ import annotations

from datetime import datetime, timezone

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import Unit
from zrzavy_energy_monitor_core.validation import (
    RuleEvaluation,
    ValidatedMeasurement,
    ValidationContext,
    ValidationDecision,
    ValidationEngine,
    ValidationEvent,
    ValidationFinding,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _measurement(
    value: float = 100.0,
    *,
    quality: MeasurementQuality = MeasurementQuality.REPORTED,
) -> Measurement:
    return Measurement(
        metric=Metric.GRID_POWER,
        value=value,
        unit=Unit.WATT,
        source_id="grid_meter_primary",
        role=MeasurementRole.GRID_METER,
        measured_at=NOW,
        received_at=NOW,
        quality=quality,
        raw_value=value,
    )


def _finding(
    rule_id: str,
    severity: ValidationSeverity,
    code: str,
) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule_id,
        code=code,
        message=code,
        severity=severity,
    )


class RecordingRule:
    """Return one configured evaluation and record deterministic order."""

    def __init__(
        self,
        rule_id: str,
        evaluation: RuleEvaluation,
        order: list[str],
    ) -> None:
        self.rule_id = rule_id
        self._evaluation = evaluation
        self._order = order

    def evaluate(
        self,
        candidate,
        context,
    ) -> RuleEvaluation:
        del candidate, context
        self._order.append(self.rule_id)
        return self._evaluation


class ThrowingRule:
    """Raise deliberately to verify collector-safe containment."""

    rule_id = "VAL-TEST-THROW"

    def evaluate(self, candidate, context) -> RuleEvaluation:
        del candidate, context
        raise RuntimeError("secret adapter details must not leak")


def test_engine_runs_rules_in_order_and_strongest_decision_wins() -> None:
    order: list[str] = []
    rules = (
        RecordingRule(
            "VAL-TEST-INFO",
            RuleEvaluation.accepted(
                _finding(
                    "VAL-TEST-INFO",
                    ValidationSeverity.INFO,
                    "info",
                )
            ),
            order,
        ),
        RecordingRule(
            "VAL-TEST-WARN",
            RuleEvaluation.warning(
                _finding(
                    "VAL-TEST-WARN",
                    ValidationSeverity.WARNING,
                    "warning",
                )
            ),
            order,
        ),
        RecordingRule(
            "VAL-TEST-REJECT",
            RuleEvaluation.rejected(
                _finding(
                    "VAL-TEST-REJECT",
                    ValidationSeverity.ERROR,
                    "rejected",
                )
            ),
            order,
        ),
    )

    result = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        rules,
    )

    assert order == [
        "VAL-TEST-INFO",
        "VAL-TEST-WARN",
        "VAL-TEST-REJECT",
    ]
    assert result.result.decision is ValidationDecision.REJECT
    assert result.measurement is None
    assert [finding.code for finding in result.result.findings] == [
        "info",
        "warning",
        "rejected",
    ]


def test_rule_exception_becomes_safe_internal_rejection() -> None:
    validated = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        (ThrowingRule(),),
    )

    assert validated.result.decision is ValidationDecision.REJECT
    finding = validated.result.findings[0]
    assert finding.rule_id == "VAL-ENGINE-001"
    assert finding.code == "rule_execution_failed"
    assert dict(finding.details) == {
        "failed_rule_id": "VAL-TEST-THROW",
        "exception_type": "RuntimeError",
    }
    assert "secret adapter details" not in repr(finding)


def test_warning_preserves_zero_and_marks_measurement_suspect() -> None:
    rule = RecordingRule(
        "VAL-TEST-WARN",
        RuleEvaluation.warning(
            _finding(
                "VAL-TEST-WARN",
                ValidationSeverity.WARNING,
                "warning",
            )
        ),
        [],
    )
    validated = ValidationEngine().validate(
        _measurement(0.0),
        ValidationContext(now=NOW),
        (rule,),
    )

    assert validated.accepted_value == 0.0
    assert validated.measurement is not None
    assert validated.measurement.value == 0.0
    assert validated.measurement.quality is MeasurementQuality.SUSPECT


def test_successful_cross_check_promotes_quality_to_validated() -> None:
    rule = RecordingRule(
        "VAL-XPLANT-001",
        RuleEvaluation.accepted(
            _finding(
                "VAL-XPLANT-001",
                ValidationSeverity.INFO,
                "cross_source_consistent",
            )
        ),
        [],
    )
    validated = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        (rule,),
    )

    assert validated.measurement is not None
    assert validated.result.quality is MeasurementQuality.VALIDATED


def test_validation_event_contains_only_actionable_findings() -> None:
    validated = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        (
            RecordingRule(
                "VAL-TEST-INFO",
                RuleEvaluation.accepted(
                    _finding(
                        "VAL-TEST-INFO",
                        ValidationSeverity.INFO,
                        "info",
                    )
                ),
                [],
            ),
        ),
    )
    assert (
        ValidationEvent.from_validated(
            validated,
            occurred_at=NOW,
        )
        is None
    )

    warning = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        (
            RecordingRule(
                "VAL-TEST-WARN",
                RuleEvaluation.warning(
                    _finding(
                        "VAL-TEST-WARN",
                        ValidationSeverity.WARNING,
                        "warning",
                    )
                ),
                [],
            ),
        ),
    )
    event = ValidationEvent.from_validated(
        warning,
        occurred_at=NOW,
    )

    assert event is not None
    assert event.decision is ValidationDecision.ACCEPT_WITH_WARNING
    assert event.accepted_value == 100.0


def test_validated_measurement_rejects_contradictory_usable_value() -> None:
    rejected = ValidationEngine().validate(
        _measurement(),
        ValidationContext(now=NOW),
        (ThrowingRule(),),
    )

    assert isinstance(rejected, ValidatedMeasurement)
    assert rejected.is_usable is False
