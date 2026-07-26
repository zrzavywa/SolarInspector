"""Define explainable outcomes for measurement source selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole


class SourceSelectionReason(str, Enum):
    """Explain the final outcome of one source-selection request."""

    PRIMARY_SELECTED = "primary_selected"
    FALLBACK_SELECTED = "fallback_selected"
    NO_ELIGIBLE_SOURCE = "no_eligible_source"


class SourceAlignmentStatus(str, Enum):
    """Describe whether selected measurements may be combined safely."""

    ALIGNED = "aligned"
    SUSPECT = "suspect"
    INCOMPLETE = "incomplete"


class CandidateRejectionReason(str, Enum):
    """Explain why one configured candidate was not eligible."""

    SOURCE_NOT_CONFIGURED = "source_not_configured"
    METRIC_UNAVAILABLE = "metric_unavailable"
    METRIC_MISMATCH = "metric_mismatch"
    ROLE_MISMATCH = "role_mismatch"
    MEASUREMENT_POSITION_MISMATCH = "measurement_position_mismatch"
    VALIDATION_REJECTED = "validation_rejected"
    INVALID_QUALITY = "invalid_quality"
    SUSPECT_NOT_ALLOWED = "suspect_not_allowed"
    FALLBACK_NOT_ALLOWED = "fallback_not_allowed"
    INVALID_TIMESTAMP = "invalid_timestamp"
    MEASUREMENT_TOO_OLD = "measurement_too_old"


@dataclass(frozen=True, slots=True)
class SourceSelectionFinding:
    """Retain one structured validation or selection finding."""

    rule_id: str
    code: str
    message: str
    severity: str
    details: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        """Require stable, non-empty diagnostic fields and detail keys."""

        for field_name in ("rule_id", "code", "message", "severity"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        keys = [key.strip() for key, _value in self.details]
        if any(not key for key in keys):
            raise ValueError("finding detail keys must not be empty")
        if len(keys) != len(set(keys)):
            raise ValueError("finding detail keys must be unique")


@dataclass(frozen=True, slots=True)
class RejectedSourceCandidate:
    """Record one rejected source candidate without inventing a value."""

    source_id: str
    reason: CandidateRejectionReason
    source_role: MeasurementRole | None = None
    quality: MeasurementQuality | None = None
    measured_at: datetime | None = None
    findings: tuple[SourceSelectionFinding, ...] = ()

    def __post_init__(self) -> None:
        """Validate diagnostic identity and timestamps."""

        source_id = self.source_id.strip()
        if not source_id:
            raise ValueError("source_id must not be empty")
        object.__setattr__(self, "source_id", source_id)
        if self.measured_at is not None:
            _require_timezone_aware(self.measured_at, "measured_at")


@dataclass(frozen=True, slots=True)
class SourceSelectionResult:
    """Represent one deterministic, explainable source-selection result."""

    requested_metric: Metric
    measurement: Measurement | None
    selected_source_id: str | None
    selected_source_role: MeasurementRole | None
    selected_quality: MeasurementQuality
    selection_reason: SourceSelectionReason
    fallback_used: bool
    rejected_candidates: tuple[RejectedSourceCandidate, ...]
    selected_measurement_timestamp: datetime | None
    selection_timestamp: datetime
    findings: tuple[SourceSelectionFinding, ...] = ()

    def __post_init__(self) -> None:
        """Reject selected and unavailable states that contradict each other."""

        _require_timezone_aware(self.selection_timestamp, "selection_timestamp")

        if self.measurement is None:
            self._validate_unavailable()
            return

        self._validate_selected()

    def _validate_unavailable(self) -> None:
        """Validate the explicit no-source representation."""

        if self.selected_source_id is not None:
            raise ValueError("unavailable result cannot have selected_source_id")
        if self.selected_source_role is not None:
            raise ValueError("unavailable result cannot have selected_source_role")
        if self.selected_measurement_timestamp is not None:
            raise ValueError(
                "unavailable result cannot have selected_measurement_timestamp"
            )
        if self.selected_quality is not MeasurementQuality.UNAVAILABLE:
            raise ValueError("missing measurement requires unavailable quality")
        if self.selection_reason is not SourceSelectionReason.NO_ELIGIBLE_SOURCE:
            raise ValueError("missing measurement requires no_eligible_source reason")
        if self.fallback_used:
            raise ValueError("unavailable result cannot be a fallback")

    def _validate_selected(self) -> None:
        """Validate metadata copied from a selected measurement."""

        measurement = self.measurement
        if measurement is None:
            raise AssertionError("selected result requires a measurement")
        if self.selected_source_id != measurement.source_id:
            raise ValueError("selected_source_id must match measurement")
        if self.selected_source_role is not measurement.role:
            raise ValueError("selected_source_role must match measurement")
        if self.selected_quality is not measurement.quality:
            raise ValueError("selected_quality must match measurement")
        if self.requested_metric is not measurement.metric:
            raise ValueError("requested_metric must match measurement")
        if self.selected_measurement_timestamp != measurement.measured_at:
            raise ValueError("selected_measurement_timestamp must match measurement")
        expected_reason = (
            SourceSelectionReason.FALLBACK_SELECTED
            if self.fallback_used
            else SourceSelectionReason.PRIMARY_SELECTED
        )
        if self.selection_reason is not expected_reason:
            raise ValueError("selection_reason must match fallback_used")
        if self.selected_quality in {
            MeasurementQuality.REJECTED,
            MeasurementQuality.STALE,
            MeasurementQuality.UNAVAILABLE,
        }:
            raise ValueError("selected measurement quality must be usable")

    @classmethod
    def selected(
        cls,
        measurement: Measurement,
        *,
        selection_timestamp: datetime,
        fallback_used: bool,
        rejected_candidates: tuple[RejectedSourceCandidate, ...] = (),
        findings: tuple[SourceSelectionFinding, ...] = (),
    ) -> SourceSelectionResult:
        """Build a result whose metadata is copied from one measurement."""

        return cls(
            requested_metric=measurement.metric,
            measurement=measurement,
            selected_source_id=measurement.source_id,
            selected_source_role=measurement.role,
            selected_quality=measurement.quality,
            selection_reason=(
                SourceSelectionReason.FALLBACK_SELECTED
                if fallback_used
                else SourceSelectionReason.PRIMARY_SELECTED
            ),
            fallback_used=fallback_used,
            rejected_candidates=rejected_candidates,
            selected_measurement_timestamp=measurement.measured_at,
            selection_timestamp=selection_timestamp,
            findings=findings,
        )

    @classmethod
    def unavailable(
        cls,
        metric: Metric,
        *,
        selection_timestamp: datetime,
        rejected_candidates: tuple[RejectedSourceCandidate, ...] = (),
        findings: tuple[SourceSelectionFinding, ...] = (),
    ) -> SourceSelectionResult:
        """Build an explicit result when no eligible source exists."""

        return cls(
            requested_metric=metric,
            measurement=None,
            selected_source_id=None,
            selected_source_role=None,
            selected_quality=MeasurementQuality.UNAVAILABLE,
            selection_reason=SourceSelectionReason.NO_ELIGIBLE_SOURCE,
            fallback_used=False,
            rejected_candidates=rejected_candidates,
            selected_measurement_timestamp=None,
            selection_timestamp=selection_timestamp,
            findings=findings,
        )


@dataclass(frozen=True, slots=True)
class SourceAlignmentResult:
    """Describe temporal comparability across selected measurements."""

    status: SourceAlignmentStatus
    maximum_skew_seconds: float | None
    findings: tuple[SourceSelectionFinding, ...] = ()

    def __post_init__(self) -> None:
        """Validate the presence and range of the measured skew."""

        if self.maximum_skew_seconds is not None:
            skew = float(self.maximum_skew_seconds)
            if skew < 0:
                raise ValueError("maximum_skew_seconds must not be negative")
            object.__setattr__(self, "maximum_skew_seconds", skew)
        if (
            self.status is SourceAlignmentStatus.ALIGNED
            and self.maximum_skew_seconds is None
        ):
            raise ValueError("aligned result requires maximum_skew_seconds")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    """Require one timezone-aware diagnostic timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
