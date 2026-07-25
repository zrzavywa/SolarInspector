"""Aggregate validation rules into deterministic measurement decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from typing import Iterable

from solarinspector_core.models.device import DeviceSnapshot
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.validation.base import ValidationRule
from solarinspector_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from solarinspector_core.validation.result import (
    RuleEvaluation,
    ValidationDecision,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)
from solarinspector_core.validation.state import ValidationStateStore

_DECISION_RANK = {
    ValidationDecision.ACCEPT: 0,
    ValidationDecision.ACCEPT_WITH_WARNING: 1,
    ValidationDecision.REJECT: 2,
}
_UNAVAILABLE_CODES = {
    "value_missing",
    "unit_missing",
    "measured_at_missing",
}
_CROSS_VALIDATED_CODES = {"cross_source_consistent"}


@dataclass(frozen=True, slots=True)
class ValidatedMeasurement:
    """Keep the original measurement beside its classified usable form."""

    original: Measurement
    result: ValidationResult
    measurement: Measurement | None

    def __post_init__(self) -> None:
        """Require the usable measurement to match the validation decision."""

        if self.result.decision is ValidationDecision.REJECT:
            if self.measurement is not None:
                raise ValueError(
                    "rejected validation cannot expose a usable measurement"
                )
            return
        if self.measurement is None:
            raise ValueError("accepted validation requires a usable measurement")
        if self.measurement.value != self.result.accepted_value:
            raise ValueError("usable measurement must preserve the accepted value")
        if self.measurement.quality is not self.result.quality:
            raise ValueError("usable measurement quality must match validation result")

    @property
    def accepted_value(self) -> float | None:
        """Return the accepted value or ``None`` for a rejection."""

        return self.result.accepted_value

    @property
    def is_usable(self) -> bool:
        """Return whether downstream calculations may use the value."""

        return self.measurement is not None


@dataclass(frozen=True, slots=True)
class ValidationEvent:
    """Represent one actionable validation outcome before persistence."""

    occurred_at: datetime
    source_id: str
    role: MeasurementRole
    metric: Metric
    decision: ValidationDecision
    quality: MeasurementQuality
    raw_value: object | None
    accepted_value: float | None
    findings: tuple[ValidationFinding, ...]

    @classmethod
    def from_validated(
        cls,
        validated: ValidatedMeasurement,
        *,
        occurred_at: datetime,
    ) -> ValidationEvent | None:
        """Create an event only for warnings, errors, or engine failures."""

        actionable = tuple(
            finding
            for finding in validated.result.findings
            if finding.severity
            in {
                ValidationSeverity.WARNING,
                ValidationSeverity.ERROR,
            }
        )
        if not actionable:
            return None
        return cls(
            occurred_at=occurred_at,
            source_id=validated.original.source_id,
            role=validated.original.role,
            metric=validated.original.metric,
            decision=validated.result.decision,
            quality=validated.result.quality,
            raw_value=validated.result.raw_value,
            accepted_value=validated.result.accepted_value,
            findings=actionable,
        )


@dataclass(frozen=True, slots=True)
class ValidatedDeviceSnapshot:
    """Keep the original snapshot beside its filtered usable snapshot."""

    original: DeviceSnapshot
    snapshot: DeviceSnapshot
    measurements: tuple[ValidatedMeasurement, ...]
    events: tuple[ValidationEvent, ...]

    @property
    def rejected_count(self) -> int:
        """Return the number of rejected measurements in this snapshot."""

        return sum(
            validated.result.decision is ValidationDecision.REJECT
            for validated in self.measurements
        )


class ValidationEngine:
    """Run ordered rules, contain failures, and derive one final decision."""

    def __init__(
        self,
        *,
        state_store: ValidationStateStore | None = None,
    ) -> None:
        """Create an engine with an explicit, isolated history store."""

        self._state_store = state_store or ValidationStateStore()

    @property
    def state_store(self) -> ValidationStateStore:
        """Return the explicit historical state dependency."""

        return self._state_store

    def validate(
        self,
        measurement: Measurement,
        context: ValidationContext,
        rules: Iterable[ValidationRule],
        *,
        diagnostics: tuple[str, ...] = (),
        record_state: bool = True,
    ) -> ValidatedMeasurement:
        """Validate one strict measurement without changing its original data."""

        candidate = MeasurementCandidate(
            metric=measurement.metric,
            value=measurement.value,
            unit=measurement.unit,
            source_id=measurement.source_id,
            role=measurement.role,
            measured_at=measurement.measured_at,
            received_at=measurement.received_at,
            quality=measurement.quality,
            raw_value=measurement.raw_value,
            diagnostics=diagnostics,
        )
        result = self._evaluate_candidate(candidate, context, tuple(rules))
        accepted_measurement = (
            None
            if result.accepted_value is None
            else candidate.build_measurement(
                value=result.accepted_value,
                quality=result.quality,
            )
        )
        validated = ValidatedMeasurement(
            original=measurement,
            result=result,
            measurement=accepted_measurement,
        )
        if record_state and accepted_measurement is not None:
            self._state_store.record_accepted(accepted_measurement)
        return validated

    def _evaluate_candidate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
        rules: tuple[ValidationRule, ...],
    ) -> ValidationResult:
        """Collect all findings while the strongest ordered decision wins."""

        final_decision = ValidationDecision.ACCEPT
        findings: list[ValidationFinding] = []

        for rule in rules:
            try:
                rule_id = rule.rule_id
                evaluation = rule.evaluate(candidate, context)
            except Exception as exc:
                rule_id = _safe_rule_id(rule)
                evaluation = RuleEvaluation.rejected(
                    ValidationFinding(
                        rule_id="VAL-ENGINE-001",
                        code="rule_execution_failed",
                        message=(
                            "Validation rule failed and the affected "
                            "measurement was rejected safely."
                        ),
                        severity=ValidationSeverity.ERROR,
                        details=(
                            ("failed_rule_id", rule_id),
                            ("exception_type", type(exc).__name__),
                        ),
                    )
                )

            findings.extend(evaluation.findings)
            if _DECISION_RANK[evaluation.decision] > _DECISION_RANK[final_decision]:
                final_decision = evaluation.decision

        candidate_value = _finite_candidate_value(candidate.value)
        if candidate_value is None and final_decision is not ValidationDecision.REJECT:
            findings.append(
                ValidationFinding(
                    rule_id="VAL-ENGINE-001",
                    code="candidate_not_usable",
                    message=(
                        "Validation completed without a finite candidate "
                        "value; the measurement was rejected safely."
                    ),
                    severity=ValidationSeverity.ERROR,
                )
            )
            final_decision = ValidationDecision.REJECT

        raw_value = candidate.effective_raw_value
        findings_tuple = tuple(findings)

        if final_decision is ValidationDecision.REJECT:
            return ValidationResult.rejected(
                raw_value=raw_value,
                candidate_value=candidate_value,
                findings=findings_tuple,
                quality=_rejection_quality(findings_tuple),
            )

        assert candidate_value is not None
        if final_decision is ValidationDecision.ACCEPT_WITH_WARNING:
            return ValidationResult.warning(
                candidate_value,
                raw_value=raw_value,
                findings=findings_tuple,
            )

        cross_validated = any(
            finding.code in _CROSS_VALIDATED_CODES for finding in findings_tuple
        )
        return ValidationResult.accepted(
            candidate_value,
            current_quality=candidate.quality,
            raw_value=raw_value,
            findings=findings_tuple,
            cross_validated=cross_validated,
        )

    def clear(self) -> None:
        """Reset historical state for deterministic restart behavior."""

        self._state_store.clear()


def _safe_rule_id(rule: object) -> str:
    """Return a credential-free identifier even for a broken rule property."""

    try:
        value = getattr(rule, "rule_id", type(rule).__name__)
    except Exception:
        return type(rule).__name__
    text = str(value).strip()
    return text or type(rule).__name__


def _finite_candidate_value(value: object) -> float | None:
    """Return one finite real candidate value."""

    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _rejection_quality(
    findings: tuple[ValidationFinding, ...],
) -> MeasurementQuality:
    """Derive stale, unavailable, or generic rejected quality."""

    codes = {finding.code for finding in findings}
    if "measurement_stale" in codes:
        return MeasurementQuality.STALE
    if codes & _UNAVAILABLE_CODES:
        return MeasurementQuality.UNAVAILABLE
    return MeasurementQuality.REJECTED
