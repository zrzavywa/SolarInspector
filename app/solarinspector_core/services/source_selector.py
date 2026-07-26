"""Select validated measurements by deterministic, explainable priority."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.source_selection import (
    CandidateRejectionReason,
    RejectedSourceCandidate,
    SourceAlignmentResult,
    SourceAlignmentStatus,
    SourceSelectionFinding,
    SourceSelectionResult,
)
from solarinspector_core.validation.engine import ValidatedMeasurement
from solarinspector_core.validation.result import (
    ValidationDecision,
    ValidationFinding,
)

_UNUSABLE_QUALITIES: Final[frozenset[MeasurementQuality]] = frozenset(
    {
        MeasurementQuality.REJECTED,
        MeasurementQuality.STALE,
        MeasurementQuality.UNAVAILABLE,
    }
)
_EXPECTED_ROLES: Final[dict[Metric, frozenset[MeasurementRole]]] = {
    Metric.GRID_POWER: frozenset({MeasurementRole.GRID_METER}),
    Metric.PLANT_AC_POWER: frozenset(
        {
            MeasurementRole.PLANT_METER,
            MeasurementRole.SOLAR_SYSTEM,
        }
    ),
    Metric.PV_POWER: frozenset({MeasurementRole.SOLAR_SYSTEM}),
    Metric.BATTERY_POWER: frozenset({MeasurementRole.BATTERY_SYSTEM}),
    Metric.BATTERY_CHARGE_POWER: frozenset({MeasurementRole.BATTERY_SYSTEM}),
    Metric.BATTERY_DISCHARGE_POWER: frozenset({MeasurementRole.BATTERY_SYSTEM}),
    Metric.BATTERY_SOC: frozenset({MeasurementRole.BATTERY_SYSTEM}),
}
_GRID_FALLBACK_POSITIONS: Final[frozenset[str]] = frozenset(
    {
        "grid_fallback",
        "grid_total",
        "legacy_grid_source",
    }
)


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """Keep one validation outcome and its configured measurement position."""

    source_id: str
    metric: Metric
    source_role: MeasurementRole
    decision: ValidationDecision
    quality: MeasurementQuality
    measurement: Measurement | None
    measured_at: datetime
    measurement_position: str | None = None
    findings: tuple[SourceSelectionFinding, ...] = ()

    def __post_init__(self) -> None:
        """Validate candidate identity and accepted-value consistency."""

        source_id = self.source_id.strip()
        if not source_id:
            raise ValueError("source_id must not be empty")
        object.__setattr__(self, "source_id", source_id)
        position = (
            None
            if self.measurement_position is None
            else self.measurement_position.strip().lower()
        )
        object.__setattr__(self, "measurement_position", position or None)
        _require_timezone_aware(self.measured_at, "measured_at")

        if self.decision is ValidationDecision.REJECT:
            if self.measurement is not None:
                raise ValueError("rejected candidate cannot expose a measurement")
            return
        if self.measurement is None:
            raise ValueError("accepted candidate requires a measurement")
        if self.measurement.source_id != self.source_id:
            raise ValueError("candidate source_id must match measurement")
        if self.measurement.metric is not self.metric:
            raise ValueError("candidate metric must match measurement")
        if self.measurement.role is not self.source_role:
            raise ValueError("candidate source_role must match measurement")
        if self.measurement.quality is not self.quality:
            raise ValueError("candidate quality must match measurement")
        if self.measurement.measured_at != self.measured_at:
            raise ValueError("candidate measured_at must match measurement")

    @classmethod
    def from_validated(
        cls,
        validated: ValidatedMeasurement,
        *,
        measurement_position: str | None = None,
    ) -> SourceCandidate:
        """Build a selector candidate without losing validation findings."""

        measurement = validated.measurement
        original = validated.original
        return cls(
            source_id=original.source_id,
            metric=original.metric,
            source_role=original.role,
            decision=validated.result.decision,
            quality=validated.result.quality,
            measurement=measurement,
            measured_at=original.measured_at,
            measurement_position=measurement_position,
            findings=tuple(
                _selection_finding(finding) for finding in validated.result.findings
            ),
        )


class SourceSelector:
    """Select the first eligible candidate from configured source priorities."""

    def __init__(
        self,
        source_priorities: Mapping[str, Sequence[str]],
        *,
        allow_suspect_measurements: bool = True,
        allow_grid_fallback: bool = True,
        allow_plant_fallback: bool = True,
        maximum_measurement_age_seconds: float = 30.0,
        short_window_average_seconds: float = 0.0,
    ) -> None:
        """Create a selector from already normalized configuration."""

        self._source_priorities = {
            str(metric): tuple(str(source_id) for source_id in source_ids)
            for metric, source_ids in source_priorities.items()
        }
        self._allow_suspect_measurements = allow_suspect_measurements
        self._allow_grid_fallback = allow_grid_fallback
        self._allow_plant_fallback = allow_plant_fallback
        if maximum_measurement_age_seconds <= 0:
            raise ValueError(
                "maximum_measurement_age_seconds must be greater than zero"
            )
        if short_window_average_seconds < 0:
            raise ValueError("short_window_average_seconds must not be negative")
        self._maximum_measurement_age_seconds = float(maximum_measurement_age_seconds)
        self._short_window_average_seconds = float(short_window_average_seconds)

    def select(
        self,
        metric: Metric,
        candidates: Sequence[SourceCandidate],
        *,
        selection_timestamp: datetime,
    ) -> SourceSelectionResult:
        """Select one usable measurement and explain every skipped priority."""

        _require_timezone_aware(selection_timestamp, "selection_timestamp")
        priorities = self._source_priorities.get(metric.value, ())
        rejected: list[RejectedSourceCandidate] = []
        for index, source_id in enumerate(priorities):
            source_candidates = sorted(
                (
                    candidate
                    for candidate in candidates
                    if candidate.source_id == source_id and candidate.metric is metric
                ),
                key=lambda candidate: candidate.measured_at,
                reverse=True,
            )
            if not source_candidates:
                rejected.append(
                    RejectedSourceCandidate(
                        source_id=source_id,
                        reason=CandidateRejectionReason.METRIC_UNAVAILABLE,
                    )
                )
                continue

            eligible: list[SourceCandidate] = []
            for candidate in source_candidates:
                rejection = self._rejection_reason(
                    metric,
                    candidate,
                    fallback_used=index > 0,
                    selection_timestamp=selection_timestamp,
                )
                if rejection is not None:
                    rejected.append(_rejected_candidate(candidate, rejection))
                    continue
                eligible.append(candidate)

            if not eligible:
                continue
            measurement, findings = self._selected_measurement(
                eligible,
                selection_timestamp=selection_timestamp,
            )
            return SourceSelectionResult.selected(
                measurement,
                selection_timestamp=selection_timestamp,
                fallback_used=index > 0,
                rejected_candidates=tuple(rejected),
                findings=findings,
            )

        configured_sources = set(priorities)
        rejected.extend(
            _rejected_candidate(
                candidate,
                CandidateRejectionReason.SOURCE_NOT_CONFIGURED,
            )
            for candidate in candidates
            if candidate.metric is metric
            and candidate.source_id not in configured_sources
        )
        return SourceSelectionResult.unavailable(
            metric,
            selection_timestamp=selection_timestamp,
            rejected_candidates=tuple(rejected),
        )

    def _rejection_reason(
        self,
        metric: Metric,
        candidate: SourceCandidate,
        *,
        fallback_used: bool,
        selection_timestamp: datetime,
    ) -> CandidateRejectionReason | None:
        """Return the first deterministic eligibility failure."""

        if candidate.decision is ValidationDecision.REJECT:
            return CandidateRejectionReason.VALIDATION_REJECTED
        if candidate.quality in _UNUSABLE_QUALITIES:
            return CandidateRejectionReason.INVALID_QUALITY
        if (
            candidate.quality is MeasurementQuality.SUSPECT
            and not self._allow_suspect_measurements
        ):
            return CandidateRejectionReason.SUSPECT_NOT_ALLOWED
        if candidate.source_role not in _EXPECTED_ROLES.get(metric, frozenset()):
            return CandidateRejectionReason.ROLE_MISMATCH
        if fallback_used and not self._fallback_allowed(metric):
            return CandidateRejectionReason.FALLBACK_NOT_ALLOWED
        if (
            metric is Metric.GRID_POWER
            and fallback_used
            and candidate.measurement_position not in _GRID_FALLBACK_POSITIONS
        ):
            return CandidateRejectionReason.MEASUREMENT_POSITION_MISMATCH
        age_seconds = (selection_timestamp - candidate.measured_at).total_seconds()
        if age_seconds < 0:
            return CandidateRejectionReason.INVALID_TIMESTAMP
        if age_seconds > self._maximum_measurement_age_seconds:
            return CandidateRejectionReason.MEASUREMENT_TOO_OLD
        return None

    def _selected_measurement(
        self,
        eligible: Sequence[SourceCandidate],
        *,
        selection_timestamp: datetime,
    ) -> tuple[Measurement, tuple[SourceSelectionFinding, ...]]:
        """Return the nearest value or an explicitly configured short average."""

        nearest = eligible[0]
        measurement = nearest.measurement
        if measurement is None:
            raise AssertionError("eligible candidate requires measurement")
        if self._short_window_average_seconds <= 0:
            return measurement, nearest.findings

        window_start = selection_timestamp - timedelta(
            seconds=self._short_window_average_seconds
        )
        averaged = tuple(
            candidate
            for candidate in eligible
            if candidate.measured_at >= window_start
            and candidate.source_role is nearest.source_role
            and candidate.measurement is not None
        )
        if len(averaged) < 2:
            return measurement, nearest.findings

        measurements = tuple(
            candidate.measurement
            for candidate in averaged
            if candidate.measurement is not None
        )
        quality = (
            MeasurementQuality.SUSPECT
            if any(item.quality is MeasurementQuality.SUSPECT for item in measurements)
            else MeasurementQuality.CALCULATED
        )
        return (
            Measurement(
                metric=measurement.metric,
                value=sum(item.value for item in measurements) / len(measurements),
                unit=measurement.unit,
                source_id=measurement.source_id,
                role=measurement.role,
                measured_at=max(item.measured_at for item in measurements),
                received_at=max(item.received_at for item in measurements),
                quality=quality,
            ),
            tuple(finding for candidate in averaged for finding in candidate.findings),
        )

    def _fallback_allowed(self, metric: Metric) -> bool:
        """Return whether the requested metric permits a lower priority."""

        if metric is Metric.GRID_POWER:
            return self._allow_grid_fallback
        if metric is Metric.PLANT_AC_POWER:
            return self._allow_plant_fallback
        return True


def _selection_finding(finding: ValidationFinding) -> SourceSelectionFinding:
    """Copy one validation finding into the independent selection model."""

    return SourceSelectionFinding(
        rule_id=finding.rule_id,
        code=finding.code,
        message=finding.message,
        severity=finding.severity.value,
        details=finding.details,
    )


def _rejected_candidate(
    candidate: SourceCandidate,
    reason: CandidateRejectionReason,
) -> RejectedSourceCandidate:
    """Copy safe candidate metadata into an explainable rejection."""

    return RejectedSourceCandidate(
        source_id=candidate.source_id,
        reason=reason,
        source_role=candidate.source_role,
        quality=candidate.quality,
        measured_at=candidate.measured_at,
        findings=candidate.findings,
    )


def assess_source_alignment(
    selections: Sequence[SourceSelectionResult],
    *,
    maximum_source_skew_seconds: float,
) -> SourceAlignmentResult:
    """Assess whether selected measurements are temporally comparable."""

    if maximum_source_skew_seconds <= 0:
        raise ValueError("maximum_source_skew_seconds must be greater than zero")
    if not selections or any(selection.measurement is None for selection in selections):
        return SourceAlignmentResult(
            status=SourceAlignmentStatus.INCOMPLETE,
            maximum_skew_seconds=None,
            findings=(
                SourceSelectionFinding(
                    rule_id="ENERGY-ALIGN-001",
                    code="source_measurement_missing",
                    message="At least one required source measurement is unavailable.",
                    severity="warning",
                ),
            ),
        )

    timestamps = tuple(
        selection.selected_measurement_timestamp
        for selection in selections
        if selection.selected_measurement_timestamp is not None
    )
    skew_seconds = (max(timestamps) - min(timestamps)).total_seconds()
    if skew_seconds > maximum_source_skew_seconds:
        return SourceAlignmentResult(
            status=SourceAlignmentStatus.INCOMPLETE,
            maximum_skew_seconds=skew_seconds,
            findings=(
                SourceSelectionFinding(
                    rule_id="ENERGY-ALIGN-001",
                    code="source_skew_exceeded",
                    message=(
                        "Selected source measurements are too far apart "
                        "to calculate a current balance."
                    ),
                    severity="warning",
                    details=(
                        ("actual_skew_seconds", skew_seconds),
                        (
                            "maximum_skew_seconds",
                            float(maximum_source_skew_seconds),
                        ),
                    ),
                ),
            ),
        )

    suspect_findings = tuple(
        finding
        for selection in selections
        if selection.selected_quality is MeasurementQuality.SUSPECT
        for finding in selection.findings
    )
    return SourceAlignmentResult(
        status=(
            SourceAlignmentStatus.SUSPECT
            if any(
                selection.selected_quality is MeasurementQuality.SUSPECT
                for selection in selections
            )
            else SourceAlignmentStatus.ALIGNED
        ),
        maximum_skew_seconds=skew_seconds,
        findings=suspect_findings,
    )


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    """Require one timezone-aware selector timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
