"""Validate three-phase completeness and reported device totals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from typing import ClassVar

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.services.phase_power import (
    analyze_phase_power,
    phase_total_tolerance_w,
)
from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from zrzavy_energy_monitor_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)

_PHASE_METRICS = (
    Metric.PHASE_POWER_L1,
    Metric.PHASE_POWER_L2,
    Metric.PHASE_POWER_L3,
)
_UNUSABLE_QUALITIES = {
    MeasurementQuality.REJECTED,
    MeasurementQuality.STALE,
    MeasurementQuality.UNAVAILABLE,
}


def _non_negative_finite(value: object, field_name: str) -> float:
    """Normalize one non-negative finite phase parameter."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


def _finite_candidate_value(
    candidate: MeasurementCandidate,
) -> float | None:
    """Return one finite candidate total without duplicating format rules."""

    value = candidate.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _reference_time(candidate: MeasurementCandidate) -> datetime:
    """Return the best available candidate timestamp for phase matching."""

    return (
        candidate.measured_at
        if candidate.measured_at is not None
        else candidate.received_at
    )


def _matching_phase_values(
    candidate: MeasurementCandidate,
    context: ValidationContext,
    *,
    maximum_phase_skew_seconds: float,
) -> tuple[
    tuple[float | None, float | None, float | None],
    tuple[str, ...],
]:
    """Select the closest usable phase value for each expected metric."""

    reference_time = _reference_time(candidate)
    closest: dict[Metric, tuple[float, Measurement]] = {}

    for measurement in context.comparison_measurements:
        if measurement.metric not in _PHASE_METRICS:
            continue
        if measurement.source_id != candidate.source_id.strip():
            continue
        if measurement.role is not candidate.role:
            continue
        if measurement.quality in _UNUSABLE_QUALITIES:
            continue

        skew = abs((measurement.measured_at - reference_time).total_seconds())
        if skew > maximum_phase_skew_seconds:
            continue

        previous = closest.get(measurement.metric)
        if previous is None or skew < previous[0]:
            closest[measurement.metric] = (skew, measurement)

    values = tuple(
        (closest[metric][1].value if metric in closest else None)
        for metric in _PHASE_METRICS
    )
    missing = tuple(
        metric.value for metric, value in zip(_PHASE_METRICS, values) if value is None
    )
    return (values[0], values[1], values[2]), missing


def _details(
    candidate: MeasurementCandidate,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable phase finding details."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        *items,
    )


@dataclass(frozen=True, slots=True)
class PhaseCompletenessRule:
    """Warn when fewer than three comparable phase values are available."""

    maximum_phase_skew_seconds: float = 2.0

    rule_id: ClassVar[str] = "VAL-PHASE-001"

    def __post_init__(self) -> None:
        """Validate the timestamp matching tolerance."""

        object.__setattr__(
            self,
            "maximum_phase_skew_seconds",
            _non_negative_finite(
                self.maximum_phase_skew_seconds,
                "maximum_phase_skew_seconds",
            ),
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Accept three phases or report a non-destructive warning."""

        values, missing = _matching_phase_values(
            candidate,
            context,
            maximum_phase_skew_seconds=(self.maximum_phase_skew_seconds),
        )
        available_count = sum(value is not None for value in values)
        if available_count == 3:
            return RuleEvaluation.accepted()

        return RuleEvaluation.warning(
            ValidationFinding(
                rule_id=self.rule_id,
                code="phase_data_incomplete",
                message=("Not all three comparable phase-power values are available."),
                severity=ValidationSeverity.WARNING,
                details=_details(
                    candidate,
                    ("available_count", available_count),
                    ("missing_metrics", missing),
                    (
                        "maximum_phase_skew_seconds",
                        self.maximum_phase_skew_seconds,
                    ),
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class PhaseSumConsistencyRule:
    """Compare three signed phase values with a reported device total."""

    warning_absolute_w: float = 20.0
    warning_relative: float = 0.03
    reject_absolute_w: float = 100.0
    reject_relative: float = 0.10
    maximum_phase_skew_seconds: float = 2.0

    rule_id: ClassVar[str] = "VAL-PHASE-002"

    def __post_init__(self) -> None:
        """Require non-negative and ordered warning/rejection tolerances."""

        warning_absolute = _non_negative_finite(
            self.warning_absolute_w,
            "warning_absolute_w",
        )
        warning_relative = _non_negative_finite(
            self.warning_relative,
            "warning_relative",
        )
        reject_absolute = _non_negative_finite(
            self.reject_absolute_w,
            "reject_absolute_w",
        )
        reject_relative = _non_negative_finite(
            self.reject_relative,
            "reject_relative",
        )
        skew = _non_negative_finite(
            self.maximum_phase_skew_seconds,
            "maximum_phase_skew_seconds",
        )
        if warning_absolute > reject_absolute:
            raise ValueError("warning_absolute_w must not exceed reject_absolute_w")
        if warning_relative > reject_relative:
            raise ValueError("warning_relative must not exceed reject_relative")
        object.__setattr__(self, "warning_absolute_w", warning_absolute)
        object.__setattr__(self, "warning_relative", warning_relative)
        object.__setattr__(self, "reject_absolute_w", reject_absolute)
        object.__setattr__(self, "reject_relative", reject_relative)
        object.__setattr__(self, "maximum_phase_skew_seconds", skew)

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn or reject only when three comparable phases exist."""

        reported_total = _finite_candidate_value(candidate)
        if reported_total is None:
            return RuleEvaluation.accepted()

        phase_values, _missing = _matching_phase_values(
            candidate,
            context,
            maximum_phase_skew_seconds=(self.maximum_phase_skew_seconds),
        )
        if any(value is None for value in phase_values):
            # VAL-PHASE-001 owns completeness. No misleading sum
            # decision is produced for partial phase data.
            return RuleEvaluation.accepted()

        analysis = analyze_phase_power(
            phase_values,
            reported_total_w=reported_total,
            absolute_total_tolerance_w=self.reject_absolute_w,
            relative_total_tolerance=self.reject_relative,
        )
        calculated_total = analysis.calculated_total_w
        total_delta = analysis.total_delta_w
        if calculated_total is None or total_delta is None:
            return RuleEvaluation.accepted()

        warning_tolerance = phase_total_tolerance_w(
            reported_total,
            calculated_total,
            absolute_tolerance_w=self.warning_absolute_w,
            relative_tolerance=self.warning_relative,
        )
        reject_tolerance = phase_total_tolerance_w(
            reported_total,
            calculated_total,
            absolute_tolerance_w=self.reject_absolute_w,
            relative_tolerance=self.reject_relative,
        )
        absolute_delta = abs(total_delta)
        details = _details(
            candidate,
            ("phase_values_w", phase_values),
            ("calculated_total_w", calculated_total),
            ("reported_total_w", reported_total),
            ("total_delta_w", total_delta),
            ("total_delta_pct", analysis.total_delta_pct),
            ("warning_tolerance_w", warning_tolerance),
            ("reject_tolerance_w", reject_tolerance),
        )

        if absolute_delta > reject_tolerance:
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="phase_sum_rejected",
                    message=(
                        "Reported device total differs too far from "
                        "the sum of all three phases."
                    ),
                    severity=ValidationSeverity.ERROR,
                    details=details,
                )
            )

        if absolute_delta > warning_tolerance:
            return RuleEvaluation.warning(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="phase_sum_suspect",
                    message=(
                        "Reported device total differs from the "
                        "sum of all three phases."
                    ),
                    severity=ValidationSeverity.WARNING,
                    details=details,
                )
            )

        return RuleEvaluation.accepted()
