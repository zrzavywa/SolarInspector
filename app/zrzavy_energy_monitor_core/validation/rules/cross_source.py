"""Compare redundant power measurements over explicit time windows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from statistics import fmean
from typing import ClassVar

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.validation.config import normalize_comparison_config
from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from zrzavy_energy_monitor_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)

_UNUSABLE_QUALITIES = {
    MeasurementQuality.REJECTED,
    MeasurementQuality.STALE,
    MeasurementQuality.UNAVAILABLE,
}


def _candidate_time(candidate: MeasurementCandidate) -> datetime:
    """Return the best available timestamp for one candidate."""

    return candidate.measured_at or candidate.received_at


def _finite_candidate_value(
    candidate: MeasurementCandidate,
) -> float | None:
    """Return a finite candidate number without duplicating format rules."""

    value = candidate.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _details(
    candidate: MeasurementCandidate,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable cross-source diagnostic details."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        *items,
    )


@dataclass(frozen=True, slots=True)
class ComparisonWindow:
    """Summarize accepted values from one source inside a lookback window."""

    source_id: str
    values: tuple[float, ...]
    timestamps: tuple[datetime, ...]

    def __post_init__(self) -> None:
        """Require aligned, non-empty, finite window content."""

        source_id = self.source_id.strip()
        if not source_id:
            raise ValueError("comparison window source_id must not be empty")
        if not self.values:
            raise ValueError("comparison window requires at least one value")
        if len(self.values) != len(self.timestamps):
            raise ValueError("comparison window values and timestamps must align")

        normalized_values: list[float] = []
        for value in self.values:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError("comparison window values must be real numbers")
            normalized = float(value)
            if not math.isfinite(normalized):
                raise ValueError("comparison window values must be finite")
            normalized_values.append(normalized)

        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "values", tuple(normalized_values))

    @property
    def average(self) -> float:
        """Return the arithmetic mean of the accepted window values."""

        return float(fmean(self.values))

    @property
    def duration_seconds(self) -> float:
        """Return the observed span between oldest and newest value."""

        return max(
            0.0,
            (max(self.timestamps) - min(self.timestamps)).total_seconds(),
        )

    @property
    def sample_count(self) -> int:
        """Return the number of accepted values in the window."""

        return len(self.values)


@dataclass(frozen=True, slots=True)
class CrossSourceComparisonLimits:
    """Configure warning, rejection, window, and persistence thresholds."""

    warning_absolute_w: float = 30.0
    reject_absolute_w: float = 100.0
    warning_relative_percent: float = 10.0
    reject_relative_percent: float = 30.0
    window_seconds: float = 30.0
    minimum_duration_seconds: float = 30.0
    minimum_reference_w: float = 100.0
    minimum_samples: int = 2
    allow_rejection: bool = False

    def __post_init__(self) -> None:
        """Apply the public comparison configuration invariants."""

        normalized = normalize_comparison_config(
            {
                "warning_absolute_w": self.warning_absolute_w,
                "reject_absolute_w": self.reject_absolute_w,
                "warning_relative_percent": self.warning_relative_percent,
                "reject_relative_percent": self.reject_relative_percent,
                "window_seconds": self.window_seconds,
                "minimum_duration_seconds": (self.minimum_duration_seconds),
                "minimum_reference_w": self.minimum_reference_w,
                "minimum_samples": self.minimum_samples,
                "allow_rejection": self.allow_rejection,
            }
        )
        for field in (
            "warning_absolute_w",
            "reject_absolute_w",
            "warning_relative_percent",
            "reject_relative_percent",
            "window_seconds",
            "minimum_duration_seconds",
            "minimum_reference_w",
            "minimum_samples",
            "allow_rejection",
        ):
            object.__setattr__(self, field, normalized[field])

    @classmethod
    def from_config(
        cls,
        value: object,
    ) -> CrossSourceComparisonLimits:
        """Build one immutable limit set from raw configuration."""

        normalized = normalize_comparison_config(value)
        return cls(
            warning_absolute_w=normalized["warning_absolute_w"],
            reject_absolute_w=normalized["reject_absolute_w"],
            warning_relative_percent=normalized["warning_relative_percent"],
            reject_relative_percent=normalized["reject_relative_percent"],
            window_seconds=normalized["window_seconds"],
            minimum_duration_seconds=normalized["minimum_duration_seconds"],
            minimum_reference_w=normalized["minimum_reference_w"],
            minimum_samples=normalized["minimum_samples"],
            allow_rejection=normalized["allow_rejection"],
        )


def _accepted_measurements(
    context: ValidationContext,
    *,
    source_id: str,
    roles: tuple[MeasurementRole, ...],
    metrics: tuple[Metric, ...],
    reference_time: datetime,
    window_seconds: float,
) -> tuple[Measurement, ...]:
    """Return usable measurements in the inclusive lookback window."""

    start_time = reference_time.timestamp() - window_seconds
    matches = tuple(
        measurement
        for measurement in context.comparison_measurements
        if measurement.source_id == source_id
        and measurement.role in roles
        and measurement.metric in metrics
        and measurement.quality not in _UNUSABLE_QUALITIES
        and start_time
        <= measurement.measured_at.timestamp()
        <= reference_time.timestamp()
    )
    return tuple(sorted(matches, key=lambda item: item.measured_at))


def _candidate_window(
    candidate: MeasurementCandidate,
    context: ValidationContext,
    *,
    window_seconds: float,
) -> ComparisonWindow | None:
    """Build the candidate-source window including the current value."""

    current_value = _finite_candidate_value(candidate)
    source_id = candidate.source_id.strip()
    if current_value is None or not source_id:
        return None

    reference_time = _candidate_time(candidate)
    history = _accepted_measurements(
        context,
        source_id=source_id,
        roles=(candidate.role,),
        metrics=(candidate.metric,),
        reference_time=reference_time,
        window_seconds=window_seconds,
    )
    values = [measurement.value for measurement in history]
    timestamps = [measurement.measured_at for measurement in history]

    if not any(
        measurement.measured_at == reference_time and measurement.value == current_value
        for measurement in history
    ):
        values.append(current_value)
        timestamps.append(reference_time)

    return ComparisonWindow(
        source_id=source_id,
        values=tuple(values),
        timestamps=tuple(timestamps),
    )


def _peer_window(
    context: ValidationContext,
    *,
    source_id: str,
    roles: tuple[MeasurementRole, ...],
    metrics: tuple[Metric, ...],
    reference_time: datetime,
    window_seconds: float,
) -> ComparisonWindow | None:
    """Build one accepted peer-source window."""

    measurements = _accepted_measurements(
        context,
        source_id=source_id,
        roles=roles,
        metrics=metrics,
        reference_time=reference_time,
        window_seconds=window_seconds,
    )
    if not measurements:
        return None

    return ComparisonWindow(
        source_id=source_id,
        values=tuple(item.value for item in measurements),
        timestamps=tuple(item.measured_at for item in measurements),
    )


def _tolerance_w(
    left_average: float,
    right_average: float,
    *,
    absolute_w: float,
    relative_percent: float,
    minimum_reference_w: float,
) -> float:
    """Return the larger absolute or relative comparison tolerance."""

    reference = max(
        abs(left_average),
        abs(right_average),
        minimum_reference_w,
    )
    return max(
        absolute_w,
        reference * relative_percent / 100.0,
    )


@dataclass(frozen=True, slots=True)
class CrossSourceTimeAlignmentRule:
    """Report an existing peer that is outside the permitted time skew."""

    comparison_source_id: str
    comparison_roles: tuple[MeasurementRole, ...]
    comparison_metrics: tuple[Metric, ...]
    maximum_skew_seconds: float = 30.0

    rule_id: ClassVar[str] = "VAL-XTIME-001"

    def __post_init__(self) -> None:
        """Validate source identity and time tolerance."""

        source_id = self.comparison_source_id.strip()
        if not source_id:
            raise ValueError("comparison_source_id must not be empty")
        if not self.comparison_roles:
            raise ValueError("comparison_roles must not be empty")
        if not self.comparison_metrics:
            raise ValueError("comparison_metrics must not be empty")

        normalized = normalize_comparison_config(
            {
                "window_seconds": self.maximum_skew_seconds,
                "minimum_duration_seconds": 0,
            }
        )
        object.__setattr__(self, "comparison_source_id", source_id)
        object.__setattr__(
            self,
            "maximum_skew_seconds",
            normalized["window_seconds"],
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Accept aligned peers and warn for an existing but stale peer."""

        candidate_time = _candidate_time(candidate)
        relevant = tuple(
            measurement
            for measurement in context.comparison_measurements
            if measurement.source_id == self.comparison_source_id
            and measurement.role in self.comparison_roles
            and measurement.metric in self.comparison_metrics
            and measurement.quality not in _UNUSABLE_QUALITIES
        )
        if not relevant:
            return RuleEvaluation.accepted()

        nearest_skew = min(
            abs((measurement.measured_at - candidate_time).total_seconds())
            for measurement in relevant
        )
        details = _details(
            candidate,
            ("comparison_source_id", self.comparison_source_id),
            ("nearest_skew_seconds", nearest_skew),
            ("maximum_skew_seconds", self.maximum_skew_seconds),
        )

        if nearest_skew <= self.maximum_skew_seconds:
            return RuleEvaluation.accepted(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="cross_source_time_aligned",
                    message=("Comparison source is within the configured time window."),
                    severity=ValidationSeverity.INFO,
                    details=details,
                )
            )

        return RuleEvaluation.warning(
            ValidationFinding(
                rule_id=self.rule_id,
                code="cross_source_time_not_aligned",
                message=(
                    "Comparison source exists but is outside the "
                    "configured time window."
                ),
                severity=ValidationSeverity.WARNING,
                details=details,
            )
        )


@dataclass(frozen=True, slots=True)
class _PowerCrossCheck:
    """Shared implementation for time-window power consistency checks."""

    comparison_source_id: str
    comparison_roles: tuple[MeasurementRole, ...]
    comparison_metrics: tuple[Metric, ...]
    limits: CrossSourceComparisonLimits
    rule_id: str
    comparison_name: str
    protect_candidate_reference: bool = False

    def __post_init__(self) -> None:
        """Require an explicit comparison contract."""

        source_id = self.comparison_source_id.strip()
        if not source_id:
            raise ValueError("comparison_source_id must not be empty")
        if not self.comparison_roles:
            raise ValueError("comparison_roles must not be empty")
        if not self.comparison_metrics:
            raise ValueError("comparison_metrics must not be empty")
        object.__setattr__(self, "comparison_source_id", source_id)

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Compare window averages without modifying either source value."""

        reference_time = _candidate_time(candidate)
        candidate_window = _candidate_window(
            candidate,
            context,
            window_seconds=self.limits.window_seconds,
        )
        peer_window = _peer_window(
            context,
            source_id=self.comparison_source_id,
            roles=self.comparison_roles,
            metrics=self.comparison_metrics,
            reference_time=reference_time,
            window_seconds=self.limits.window_seconds,
        )
        if candidate_window is None or peer_window is None:
            return RuleEvaluation.accepted()

        candidate_average = candidate_window.average
        peer_average = peer_window.average
        absolute_delta = abs(candidate_average - peer_average)
        warning_tolerance = _tolerance_w(
            candidate_average,
            peer_average,
            absolute_w=self.limits.warning_absolute_w,
            relative_percent=self.limits.warning_relative_percent,
            minimum_reference_w=self.limits.minimum_reference_w,
        )
        reject_tolerance = _tolerance_w(
            candidate_average,
            peer_average,
            absolute_w=self.limits.reject_absolute_w,
            relative_percent=self.limits.reject_relative_percent,
            minimum_reference_w=self.limits.minimum_reference_w,
        )
        persistent = (
            candidate_window.sample_count >= self.limits.minimum_samples
            and peer_window.sample_count >= self.limits.minimum_samples
            and candidate_window.duration_seconds
            >= self.limits.minimum_duration_seconds
            and peer_window.duration_seconds >= self.limits.minimum_duration_seconds
        )
        details = _details(
            candidate,
            ("comparison_name", self.comparison_name),
            ("comparison_source_id", self.comparison_source_id),
            ("candidate_average_w", candidate_average),
            ("comparison_average_w", peer_average),
            ("absolute_delta_w", absolute_delta),
            ("warning_tolerance_w", warning_tolerance),
            ("reject_tolerance_w", reject_tolerance),
            ("candidate_sample_count", candidate_window.sample_count),
            ("comparison_sample_count", peer_window.sample_count),
            (
                "candidate_duration_seconds",
                candidate_window.duration_seconds,
            ),
            ("comparison_duration_seconds", peer_window.duration_seconds),
            ("persistent", persistent),
            ("window_seconds", self.limits.window_seconds),
        )

        if absolute_delta <= warning_tolerance:
            return RuleEvaluation.accepted(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="cross_source_consistent",
                    message=(
                        "Source window averages are within the configured tolerance."
                    ),
                    severity=ValidationSeverity.INFO,
                    details=details,
                )
            )

        if (
            absolute_delta > reject_tolerance
            and persistent
            and self.limits.allow_rejection
            and not self.protect_candidate_reference
        ):
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="cross_source_persistent_difference_rejected",
                    message=(
                        "Persistent source difference exceeds the "
                        "configured rejection tolerance."
                    ),
                    severity=ValidationSeverity.ERROR,
                    details=details,
                )
            )

        if absolute_delta > reject_tolerance and persistent:
            code = "cross_source_persistent_difference"
            message = (
                "Persistent source difference exceeds the rejection "
                "tolerance, but automatic rejection is disabled."
            )
        elif absolute_delta > reject_tolerance:
            code = "cross_source_large_transient_difference"
            message = (
                "Large source difference is not yet persistent for automatic rejection."
            )
        else:
            code = "cross_source_difference"
            message = "Source window averages exceed the configured warning tolerance."

        return RuleEvaluation.warning(
            ValidationFinding(
                rule_id=self.rule_id,
                code=code,
                message=message,
                severity=ValidationSeverity.WARNING,
                details=details,
            )
        )


@dataclass(frozen=True, slots=True)
class PlantPowerCrossCheckRule:
    """Compare Solakon AC reporting with a Shelly PM plant measurement."""

    comparison_source_id: str = "solakon_meter"
    limits: CrossSourceComparisonLimits = CrossSourceComparisonLimits()

    rule_id: ClassVar[str] = "VAL-XPLANT-001"

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Compare only the Solakon plant-AC candidate contract."""

        if (
            candidate.role is not MeasurementRole.SOLAR_SYSTEM
            or candidate.metric is not Metric.PLANT_AC_POWER
        ):
            return RuleEvaluation.accepted()

        return _PowerCrossCheck(
            comparison_source_id=self.comparison_source_id,
            comparison_roles=(MeasurementRole.PLANT_METER,),
            comparison_metrics=(Metric.PLANT_AC_POWER,),
            limits=self.limits,
            rule_id=self.rule_id,
            comparison_name="solarkon_vs_shelly_pm",
        ).evaluate(candidate, context)


@dataclass(frozen=True, slots=True)
class GridMeterCrossCheckRule:
    """Compare the official grid meter with a comparable Shelly 3EM total."""

    comparison_source_id: str = "house_meter"
    limits: CrossSourceComparisonLimits = CrossSourceComparisonLimits(
        warning_absolute_w=50.0,
        reject_absolute_w=250.0,
        warning_relative_percent=10.0,
        reject_relative_percent=30.0,
        window_seconds=30.0,
        minimum_duration_seconds=30.0,
        minimum_reference_w=200.0,
        minimum_samples=2,
        allow_rejection=False,
    )

    rule_id: ClassVar[str] = "VAL-XGRID-001"

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Compare only when both measurement positions are declared comparable."""

        if (
            candidate.role is not MeasurementRole.GRID_METER
            or candidate.metric is not Metric.GRID_POWER
        ):
            return RuleEvaluation.accepted()

        comparable = dict(context.source_settings).get(
            "measurement_position_comparable",
            False,
        )
        if comparable is not True:
            return RuleEvaluation.accepted(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="grid_comparison_not_enabled",
                    message=(
                        "Grid comparison is skipped because measurement "
                        "positions are not declared comparable."
                    ),
                    severity=ValidationSeverity.INFO,
                    details=_details(
                        candidate,
                        ("measurement_position_comparable", False),
                    ),
                )
            )

        protected_limits = CrossSourceComparisonLimits(
            warning_absolute_w=self.limits.warning_absolute_w,
            reject_absolute_w=self.limits.reject_absolute_w,
            warning_relative_percent=(self.limits.warning_relative_percent),
            reject_relative_percent=self.limits.reject_relative_percent,
            window_seconds=self.limits.window_seconds,
            minimum_duration_seconds=(self.limits.minimum_duration_seconds),
            minimum_reference_w=self.limits.minimum_reference_w,
            minimum_samples=self.limits.minimum_samples,
            allow_rejection=False,
        )
        return _PowerCrossCheck(
            comparison_source_id=self.comparison_source_id,
            comparison_roles=(
                MeasurementRole.GRID_METER,
                MeasurementRole.HOUSE_METER,
            ),
            comparison_metrics=(
                Metric.GRID_POWER,
                Metric.HOUSE_POWER,
            ),
            limits=protected_limits,
            rule_id=self.rule_id,
            comparison_name="official_grid_vs_shelly_3em",
            protect_candidate_reference=True,
        ).evaluate(candidate, context)
