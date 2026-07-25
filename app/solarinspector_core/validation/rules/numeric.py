"""Validate individual numeric values, units, and configured ranges."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import ClassVar

from solarinspector_core.models.units import Unit, unit_for_metric
from solarinspector_core.validation.config import normalize_range_config
from solarinspector_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from solarinspector_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)


def _details(
    candidate: MeasurementCandidate,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable diagnostic details shared by basic rules."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        *items,
    )


@dataclass(frozen=True, slots=True)
class FiniteNumberRule:
    """Require a real, non-boolean, finite numeric candidate value."""

    rule_id: ClassVar[str] = "VAL-FMT-001"

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Reject missing, malformed, boolean, NaN, and infinite values."""

        del context
        value = candidate.value

        if value is None or (isinstance(value, str) and not value.strip()):
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="value_missing",
                    message="Measurement value is missing.",
                    severity=ValidationSeverity.ERROR,
                    details=_details(candidate),
                )
            )

        if isinstance(value, bool):
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="boolean_value",
                    message="Boolean values are not valid measurements.",
                    severity=ValidationSeverity.ERROR,
                    details=_details(candidate, ("raw_type", "bool")),
                )
            )

        if not isinstance(value, Real):
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="invalid_numeric_type",
                    message="Measurement value must be a real number.",
                    severity=ValidationSeverity.ERROR,
                    details=_details(
                        candidate,
                        ("raw_type", type(value).__name__),
                    ),
                )
            )

        normalized = float(value)
        if not math.isfinite(normalized):
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="non_finite_value",
                    message="Measurement value must be finite.",
                    severity=ValidationSeverity.ERROR,
                    details=_details(
                        candidate,
                        ("value", repr(normalized)),
                    ),
                )
            )

        return RuleEvaluation.accepted()


@dataclass(frozen=True, slots=True)
class ExpectedUnitRule:
    """Require the canonical unit assigned to the candidate metric."""

    rule_id: ClassVar[str] = "VAL-UNIT-001"

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Reject missing, textual, or metrically incorrect units."""

        del context
        expected = unit_for_metric(candidate.metric)
        actual = candidate.unit

        if actual is expected:
            return RuleEvaluation.accepted()

        if actual is None:
            code = "unit_missing"
            actual_value = None
            message = "Measurement unit is missing."
        elif not isinstance(actual, Unit):
            code = "unit_not_canonical"
            actual_value = str(actual)
            message = "Measurement unit must be a canonical Unit value."
        else:
            code = "unexpected_unit"
            actual_value = actual.value
            message = "Measurement unit does not match the metric."

        return RuleEvaluation.rejected(
            ValidationFinding(
                rule_id=self.rule_id,
                code=code,
                message=message,
                severity=ValidationSeverity.ERROR,
                details=_details(
                    candidate,
                    ("expected_unit", expected.value),
                    ("actual_unit", actual_value),
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class RangeRule:
    """Apply configured warning and rejection limits to one finite value."""

    warning_min: float | None = None
    warning_max: float | None = None
    reject_min: float | None = None
    reject_max: float | None = None

    rule_id: ClassVar[str] = "VAL-RANGE-001"

    def __post_init__(self) -> None:
        """Validate the same ordering constraints as configuration loading."""

        normalized = normalize_range_config(
            {
                "warning_min": self.warning_min,
                "warning_max": self.warning_max,
                "reject_min": self.reject_min,
                "reject_max": self.reject_max,
            }
        )
        for field in (
            "warning_min",
            "warning_max",
            "reject_min",
            "reject_max",
        ):
            object.__setattr__(self, field, normalized[field])

    @classmethod
    def from_config(cls, value: object) -> RangeRule:
        """Build one rule from a normalized or raw range mapping."""

        normalized = normalize_range_config(value)
        return cls(
            warning_min=normalized["warning_min"],
            warning_max=normalized["warning_max"],
            reject_min=normalized["reject_min"],
            reject_max=normalized["reject_max"],
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn or reject when the finite value crosses configured limits."""

        del context
        value = candidate.value
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
        ):
            # VAL-FMT-001 owns malformed values. This rule contributes no
            # duplicate finding and remains safe when evaluated in isolation.
            return RuleEvaluation.accepted()

        numeric_value = float(value)

        rejection = self._rejection(candidate, numeric_value)
        if rejection is not None:
            return RuleEvaluation.rejected(rejection)

        warning = self._warning(candidate, numeric_value)
        if warning is not None:
            return RuleEvaluation.warning(warning)

        return RuleEvaluation.accepted()

    def _rejection(
        self,
        candidate: MeasurementCandidate,
        value: float,
    ) -> ValidationFinding | None:
        """Return the first deterministic hard-bound violation."""

        if self.reject_min is not None and value < self.reject_min:
            return self._finding(
                candidate,
                code="below_reject_minimum",
                message="Measurement is below the configured rejection minimum.",
                severity=ValidationSeverity.ERROR,
                value=value,
                limit_name="reject_min",
                limit=self.reject_min,
            )
        if self.reject_max is not None and value > self.reject_max:
            return self._finding(
                candidate,
                code="above_reject_maximum",
                message="Measurement is above the configured rejection maximum.",
                severity=ValidationSeverity.ERROR,
                value=value,
                limit_name="reject_max",
                limit=self.reject_max,
            )
        return None

    def _warning(
        self,
        candidate: MeasurementCandidate,
        value: float,
    ) -> ValidationFinding | None:
        """Return the first deterministic warning-bound violation."""

        if self.warning_min is not None and value < self.warning_min:
            return self._finding(
                candidate,
                code="below_warning_minimum",
                message="Measurement is below the configured warning minimum.",
                severity=ValidationSeverity.WARNING,
                value=value,
                limit_name="warning_min",
                limit=self.warning_min,
            )
        if self.warning_max is not None and value > self.warning_max:
            return self._finding(
                candidate,
                code="above_warning_maximum",
                message="Measurement is above the configured warning maximum.",
                severity=ValidationSeverity.WARNING,
                value=value,
                limit_name="warning_max",
                limit=self.warning_max,
            )
        return None

    def _finding(
        self,
        candidate: MeasurementCandidate,
        *,
        code: str,
        message: str,
        severity: ValidationSeverity,
        value: float,
        limit_name: str,
        limit: float,
    ) -> ValidationFinding:
        """Build one range finding with enough context for later persistence."""

        return ValidationFinding(
            rule_id=self.rule_id,
            code=code,
            message=message,
            severity=severity,
            details=_details(
                candidate,
                ("value", value),
                ("limit_name", limit_name),
                ("limit", limit),
            ),
        )
