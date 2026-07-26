"""Define immutable outcomes produced by validation rules and the engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Real

from solarinspector_core.models.quality import MeasurementQuality


class ValidationDecision(str, Enum):
    """Describe whether a candidate may be used by SolarInspector."""

    ACCEPT = "accept"
    ACCEPT_WITH_WARNING = "accept_with_warning"
    REJECT = "reject"


class ValidationSeverity(str, Enum):
    """Describe the operational severity of one validation finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """Explain one rule observation without changing the measured value."""

    rule_id: str
    code: str
    message: str
    severity: ValidationSeverity
    details: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        """Validate stable identifiers and immutable diagnostic details."""

        rule_id = self.rule_id.strip()
        code = self.code.strip()
        message = self.message.strip()
        if not rule_id:
            raise ValueError("rule_id must not be empty")
        if not code:
            raise ValueError("code must not be empty")
        if not message:
            raise ValueError("message must not be empty")

        keys: set[str] = set()
        for key, _value in self.details:
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("finding detail keys must not be empty")
            if normalized_key in keys:
                raise ValueError(
                    f"finding detail key {normalized_key!r} occurs more than once"
                )
            keys.add(normalized_key)

        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """Represent the contribution of one rule before engine aggregation."""

    decision: ValidationDecision
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        """Reject contradictory rule outcomes."""

        severities = {finding.severity for finding in self.findings}
        if self.decision is ValidationDecision.ACCEPT:
            if ValidationSeverity.WARNING in severities:
                raise ValueError("accepted rule evaluation cannot contain warnings")
            if ValidationSeverity.ERROR in severities:
                raise ValueError("accepted rule evaluation cannot contain errors")
        elif self.decision is ValidationDecision.ACCEPT_WITH_WARNING:
            if ValidationSeverity.ERROR in severities:
                raise ValueError("warning rule evaluation cannot contain errors")
            if ValidationSeverity.WARNING not in severities:
                raise ValueError(
                    "warning rule evaluation requires at least one warning finding"
                )
        elif ValidationSeverity.ERROR not in severities:
            raise ValueError("rejected rule evaluation requires an error finding")

    @classmethod
    def accepted(
        cls,
        *findings: ValidationFinding,
    ) -> RuleEvaluation:
        """Build one successful rule evaluation."""

        return cls(ValidationDecision.ACCEPT, tuple(findings))

    @classmethod
    def warning(
        cls,
        *findings: ValidationFinding,
    ) -> RuleEvaluation:
        """Build one accepted rule evaluation with warnings."""

        return cls(ValidationDecision.ACCEPT_WITH_WARNING, tuple(findings))

    @classmethod
    def rejected(
        cls,
        *findings: ValidationFinding,
    ) -> RuleEvaluation:
        """Build one rejected rule evaluation."""

        return cls(ValidationDecision.REJECT, tuple(findings))


_REJECTION_QUALITIES = {
    MeasurementQuality.REJECTED,
    MeasurementQuality.STALE,
    MeasurementQuality.UNAVAILABLE,
}


def quality_for_decision(
    decision: ValidationDecision,
    *,
    current_quality: MeasurementQuality,
    cross_validated: bool = False,
    rejection_quality: MeasurementQuality = MeasurementQuality.REJECTED,
) -> MeasurementQuality:
    """Derive one measurement quality from a validation decision."""

    if decision is ValidationDecision.ACCEPT:
        return MeasurementQuality.VALIDATED if cross_validated else current_quality
    if decision is ValidationDecision.ACCEPT_WITH_WARNING:
        return MeasurementQuality.SUSPECT
    if rejection_quality not in _REJECTION_QUALITIES:
        raise ValueError("rejection_quality must be rejected, stale, or unavailable")
    return rejection_quality


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Represent the final decision for one normalized measurement candidate."""

    decision: ValidationDecision
    quality: MeasurementQuality
    raw_value: object | None
    candidate_value: float | None
    accepted_value: float | None
    findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        """Validate value and quality invariants."""

        candidate_value = _finite_optional_value(
            self.candidate_value,
            "candidate_value",
        )
        accepted_value = _finite_optional_value(
            self.accepted_value,
            "accepted_value",
        )
        object.__setattr__(self, "candidate_value", candidate_value)
        object.__setattr__(self, "accepted_value", accepted_value)

        if self.decision is ValidationDecision.REJECT:
            if accepted_value is not None:
                raise ValueError("rejected result cannot contain an accepted value")
            if self.quality not in _REJECTION_QUALITIES:
                raise ValueError(
                    "rejected result requires rejected, stale, or unavailable quality"
                )
            if not self.findings:
                raise ValueError("rejected result requires at least one finding")
            return

        if accepted_value is None:
            raise ValueError("accepted result requires an accepted value")
        if candidate_value is None:
            raise ValueError("accepted result requires a candidate value")
        if accepted_value != candidate_value:
            raise ValueError("Phase 08 must not automatically correct accepted values")

        if self.decision is ValidationDecision.ACCEPT_WITH_WARNING:
            if self.quality is not MeasurementQuality.SUSPECT:
                raise ValueError("warning result requires suspect quality")
            if not any(
                finding.severity is ValidationSeverity.WARNING
                for finding in self.findings
            ):
                raise ValueError("warning result requires a warning finding")

    @classmethod
    def accepted(
        cls,
        value: float,
        *,
        current_quality: MeasurementQuality,
        raw_value: object | None = None,
        findings: tuple[ValidationFinding, ...] = (),
        cross_validated: bool = False,
    ) -> ValidationResult:
        """Build a successful final validation result."""

        quality = quality_for_decision(
            ValidationDecision.ACCEPT,
            current_quality=current_quality,
            cross_validated=cross_validated,
        )
        return cls(
            decision=ValidationDecision.ACCEPT,
            quality=quality,
            raw_value=raw_value,
            candidate_value=value,
            accepted_value=value,
            findings=findings,
        )

    @classmethod
    def warning(
        cls,
        value: float,
        *,
        raw_value: object | None = None,
        findings: tuple[ValidationFinding, ...],
    ) -> ValidationResult:
        """Build an accepted result with one or more warnings."""

        return cls(
            decision=ValidationDecision.ACCEPT_WITH_WARNING,
            quality=MeasurementQuality.SUSPECT,
            raw_value=raw_value,
            candidate_value=value,
            accepted_value=value,
            findings=findings,
        )

    @classmethod
    def rejected(
        cls,
        *,
        raw_value: object | None = None,
        candidate_value: float | None = None,
        findings: tuple[ValidationFinding, ...],
        quality: MeasurementQuality = MeasurementQuality.REJECTED,
    ) -> ValidationResult:
        """Build a rejected final validation result."""

        return cls(
            decision=ValidationDecision.REJECT,
            quality=quality,
            raw_value=raw_value,
            candidate_value=candidate_value,
            accepted_value=None,
            findings=findings,
        )


def _finite_optional_value(
    value: float | None,
    field_name: str,
) -> float | None:
    """Normalize one optional real value and reject booleans or infinities."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number or None")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized
