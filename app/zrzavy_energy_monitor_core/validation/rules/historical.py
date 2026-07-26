"""Validate changes against the latest accepted historical measurement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import ClassVar

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.validation.config import normalize_delta_config
from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from zrzavy_energy_monitor_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)


def _finite_candidate_value(
    candidate: MeasurementCandidate,
) -> float | None:
    """Return one finite real candidate value without duplicating format errors."""

    value = candidate.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _matching_previous(
    candidate: MeasurementCandidate,
    context: ValidationContext,
) -> Measurement | None:
    """Return the previous measurement only when it belongs to the same stream."""

    previous = context.previous_measurement
    if previous is None:
        return None
    if previous.source_id != candidate.source_id.strip():
        return None
    if previous.role is not candidate.role:
        return None
    if previous.metric is not candidate.metric:
        return None
    return previous


def _details(
    candidate: MeasurementCandidate,
    previous: Measurement,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable history diagnostics suitable for later persistence."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        ("previous_value", previous.value),
        ("previous_measured_at", previous.measured_at.isoformat()),
        *items,
    )


def _non_negative_finite(value: object, field_name: str) -> float:
    """Normalize one non-negative finite constructor parameter."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


@dataclass(frozen=True, slots=True)
class MaximumDeltaRule:
    """Validate absolute, relative, and per-second value changes."""

    warning_absolute: float | None = None
    reject_absolute: float | None = None
    warning_relative_percent: float | None = None
    reject_relative_percent: float | None = None
    warning_per_second: float | None = None
    reject_per_second: float | None = None
    minimum_reference: float = 0.0

    rule_id: ClassVar[str] = "VAL-DELTA-001"

    def __post_init__(self) -> None:
        """Apply the shared delta configuration invariants."""

        normalized = normalize_delta_config(
            {
                "warning_absolute": self.warning_absolute,
                "reject_absolute": self.reject_absolute,
                "warning_relative_percent": self.warning_relative_percent,
                "reject_relative_percent": self.reject_relative_percent,
                "warning_per_second": self.warning_per_second,
                "reject_per_second": self.reject_per_second,
                "minimum_reference": self.minimum_reference,
            }
        )
        for field in (
            "warning_absolute",
            "reject_absolute",
            "warning_relative_percent",
            "reject_relative_percent",
            "warning_per_second",
            "reject_per_second",
            "minimum_reference",
        ):
            object.__setattr__(self, field, normalized[field])

    @classmethod
    def from_config(cls, value: object) -> MaximumDeltaRule:
        """Build one rule from a raw or normalized delta configuration."""

        normalized = normalize_delta_config(value)
        return cls(
            warning_absolute=normalized["warning_absolute"],
            reject_absolute=normalized["reject_absolute"],
            warning_relative_percent=normalized["warning_relative_percent"],
            reject_relative_percent=normalized["reject_relative_percent"],
            warning_per_second=normalized["warning_per_second"],
            reject_per_second=normalized["reject_per_second"],
            minimum_reference=normalized["minimum_reference"],
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn or reject when any configured change threshold is crossed."""

        current = _finite_candidate_value(candidate)
        previous = _matching_previous(candidate, context)
        if current is None or previous is None:
            return RuleEvaluation.accepted()

        elapsed_seconds = (candidate.received_at - previous.measured_at).total_seconds()
        if candidate.measured_at is not None:
            elapsed_seconds = (
                candidate.measured_at - previous.measured_at
            ).total_seconds()
        if elapsed_seconds <= 0:
            return RuleEvaluation.accepted()

        absolute_delta = abs(current - previous.value)
        denominator = max(abs(previous.value), self.minimum_reference)
        relative_percent = (
            absolute_delta / denominator * 100.0 if denominator > 0 else None
        )
        per_second = absolute_delta / elapsed_seconds

        reject_trigger = self._trigger(
            absolute_delta=absolute_delta,
            relative_percent=relative_percent,
            per_second=per_second,
            rejection=True,
        )
        if reject_trigger is not None:
            limit_name, limit, observed = reject_trigger
            return RuleEvaluation.rejected(
                self._finding(
                    candidate,
                    previous,
                    code="delta_reject_threshold_exceeded",
                    message=(
                        "Measurement change exceeds a configured rejection threshold."
                    ),
                    severity=ValidationSeverity.ERROR,
                    current=current,
                    elapsed_seconds=elapsed_seconds,
                    absolute_delta=absolute_delta,
                    relative_percent=relative_percent,
                    per_second=per_second,
                    limit_name=limit_name,
                    limit=limit,
                    observed=observed,
                )
            )

        warning_trigger = self._trigger(
            absolute_delta=absolute_delta,
            relative_percent=relative_percent,
            per_second=per_second,
            rejection=False,
        )
        if warning_trigger is not None:
            limit_name, limit, observed = warning_trigger
            return RuleEvaluation.warning(
                self._finding(
                    candidate,
                    previous,
                    code="delta_warning_threshold_exceeded",
                    message=(
                        "Measurement change exceeds a configured warning threshold."
                    ),
                    severity=ValidationSeverity.WARNING,
                    current=current,
                    elapsed_seconds=elapsed_seconds,
                    absolute_delta=absolute_delta,
                    relative_percent=relative_percent,
                    per_second=per_second,
                    limit_name=limit_name,
                    limit=limit,
                    observed=observed,
                )
            )

        return RuleEvaluation.accepted()

    def _trigger(
        self,
        *,
        absolute_delta: float,
        relative_percent: float | None,
        per_second: float,
        rejection: bool,
    ) -> tuple[str, float, float] | None:
        """Return the first deterministic crossed threshold."""

        prefix = "reject" if rejection else "warning"
        checks = (
            (
                f"{prefix}_absolute",
                self.reject_absolute if rejection else self.warning_absolute,
                absolute_delta,
            ),
            (
                f"{prefix}_relative_percent",
                (
                    self.reject_relative_percent
                    if rejection
                    else self.warning_relative_percent
                ),
                relative_percent,
            ),
            (
                f"{prefix}_per_second",
                (self.reject_per_second if rejection else self.warning_per_second),
                per_second,
            ),
        )
        for name, limit, observed in checks:
            if limit is not None and observed is not None and observed > limit:
                return name, limit, observed
        return None

    def _finding(
        self,
        candidate: MeasurementCandidate,
        previous: Measurement,
        *,
        code: str,
        message: str,
        severity: ValidationSeverity,
        current: float,
        elapsed_seconds: float,
        absolute_delta: float,
        relative_percent: float | None,
        per_second: float,
        limit_name: str,
        limit: float,
        observed: float,
    ) -> ValidationFinding:
        """Build one detailed delta finding."""

        return ValidationFinding(
            rule_id=self.rule_id,
            code=code,
            message=message,
            severity=severity,
            details=_details(
                candidate,
                previous,
                ("current_value", current),
                ("elapsed_seconds", elapsed_seconds),
                ("absolute_delta", absolute_delta),
                ("relative_percent", relative_percent),
                ("delta_per_second", per_second),
                ("limit_name", limit_name),
                ("limit", limit),
                ("observed", observed),
            ),
        )


@dataclass(frozen=True, slots=True)
class MonotonicCounterRule:
    """Reject backwards cumulative counters while allowing tiny warned noise."""

    warning_tolerance: float = 0.0

    rule_id: ClassVar[str] = "VAL-COUNTER-001"

    def __post_init__(self) -> None:
        """Require a non-negative finite tolerated decrease."""

        object.__setattr__(
            self,
            "warning_tolerance",
            _non_negative_finite(
                self.warning_tolerance,
                "warning_tolerance",
            ),
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn for a configured tiny decrease and reject larger rollbacks."""

        current = _finite_candidate_value(candidate)
        previous = _matching_previous(candidate, context)
        if current is None or previous is None:
            return RuleEvaluation.accepted()
        if current >= previous.value:
            return RuleEvaluation.accepted()

        decrease = previous.value - current
        finding_details = _details(
            candidate,
            previous,
            ("current_value", current),
            ("decrease", decrease),
            ("warning_tolerance", self.warning_tolerance),
        )

        if self.warning_tolerance > 0 and decrease <= self.warning_tolerance:
            return RuleEvaluation.warning(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="counter_small_decrease",
                    message=(
                        "Cumulative counter decreased within the configured "
                        "warning tolerance."
                    ),
                    severity=ValidationSeverity.WARNING,
                    details=finding_details,
                )
            )

        return RuleEvaluation.rejected(
            ValidationFinding(
                rule_id=self.rule_id,
                code="counter_rollback",
                message="Cumulative counter moved backwards.",
                severity=ValidationSeverity.ERROR,
                details=finding_details,
            )
        )


@dataclass(frozen=True, slots=True)
class EnergyDeltaRule:
    """Validate cumulative energy growth against power and elapsed time."""

    maximum_power_w: float
    warning_factor: float = 1.0
    reject_factor: float = 1.2

    rule_id: ClassVar[str] = "VAL-COUNTER-002"

    def __post_init__(self) -> None:
        """Validate power and tolerance factors."""

        maximum_power = _non_negative_finite(
            self.maximum_power_w,
            "maximum_power_w",
        )
        warning_factor = _non_negative_finite(
            self.warning_factor,
            "warning_factor",
        )
        reject_factor = _non_negative_finite(
            self.reject_factor,
            "reject_factor",
        )
        if warning_factor > reject_factor:
            raise ValueError("warning_factor must not exceed reject_factor")
        object.__setattr__(self, "maximum_power_w", maximum_power)
        object.__setattr__(self, "warning_factor", warning_factor)
        object.__setattr__(self, "reject_factor", reject_factor)

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn or reject an energy increase impossible for the time interval."""

        current = _finite_candidate_value(candidate)
        previous = _matching_previous(candidate, context)
        if current is None or previous is None:
            return RuleEvaluation.accepted()

        energy_delta_wh = current - previous.value
        if energy_delta_wh <= 0:
            # VAL-COUNTER-001 owns backwards counter movement.
            return RuleEvaluation.accepted()

        if candidate.measured_at is None:
            return RuleEvaluation.accepted()
        elapsed_seconds = (candidate.measured_at - previous.measured_at).total_seconds()
        if elapsed_seconds <= 0:
            return RuleEvaluation.accepted()

        physical_max_wh = self.maximum_power_w * elapsed_seconds / 3600.0
        reject_max_wh = physical_max_wh * self.reject_factor
        warning_max_wh = physical_max_wh * self.warning_factor

        details = _details(
            candidate,
            previous,
            ("current_value", current),
            ("elapsed_seconds", elapsed_seconds),
            ("energy_delta_wh", energy_delta_wh),
            ("maximum_power_w", self.maximum_power_w),
            ("physical_max_wh", physical_max_wh),
            ("warning_max_wh", warning_max_wh),
            ("reject_max_wh", reject_max_wh),
        )

        if energy_delta_wh > reject_max_wh:
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="energy_delta_impossible",
                    message=(
                        "Cumulative energy increase exceeds the configured "
                        "maximum power and rejection factor."
                    ),
                    severity=ValidationSeverity.ERROR,
                    details=details,
                )
            )

        if energy_delta_wh > warning_max_wh:
            return RuleEvaluation.warning(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="energy_delta_high",
                    message=(
                        "Cumulative energy increase exceeds the configured "
                        "maximum power warning threshold."
                    ),
                    severity=ValidationSeverity.WARNING,
                    details=details,
                )
            )

        return RuleEvaluation.accepted()
