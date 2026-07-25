"""Define candidates and contextual data consumed by validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit


@dataclass(frozen=True, slots=True)
class MeasurementCandidate:
    """Retain one adapter value before strict measurement construction.

    The candidate intentionally permits missing, malformed, non-finite, or
    wrongly unit-labelled values so central rules can create structured
    findings. The locally generated ``received_at`` timestamp remains a strict
    invariant because it anchors age and ordering checks.
    """

    metric: Metric
    value: object
    unit: Unit | str | None
    source_id: str
    role: MeasurementRole
    measured_at: datetime | None
    received_at: datetime
    quality: MeasurementQuality
    raw_value: object | None = None
    diagnostics: tuple[str, ...] = ()
    metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        """Validate only invariants required before central rule execution."""

        if not isinstance(self.source_id, str):
            raise TypeError("source_id must be a string")
        _require_timezone_aware(self.received_at, "received_at")

        normalized_diagnostics = tuple(
            diagnostic.strip() for diagnostic in self.diagnostics if diagnostic.strip()
        )
        object.__setattr__(self, "diagnostics", normalized_diagnostics)

        metadata_keys: set[str] = set()
        for key, _value in self.metadata:
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("metadata keys must not be empty")
            if normalized_key in metadata_keys:
                raise ValueError(
                    f"metadata key {normalized_key!r} occurs more than once"
                )
            metadata_keys.add(normalized_key)

    @property
    def effective_raw_value(self) -> object:
        """Return an explicit raw value or fall back to the candidate value."""

        return self.value if self.raw_value is None else self.raw_value

    def build_measurement(
        self,
        *,
        value: float,
        quality: MeasurementQuality,
    ) -> Measurement:
        """Create a strict measurement after a successful validation result."""

        if not isinstance(self.unit, Unit):
            raise ValueError("validated candidate requires a canonical Unit")
        if self.measured_at is None:
            raise ValueError("validated candidate requires measured_at")
        return Measurement(
            metric=self.metric,
            value=value,
            unit=self.unit,
            source_id=self.source_id,
            role=self.role,
            measured_at=self.measured_at,
            received_at=self.received_at,
            quality=quality,
            raw_value=self.effective_raw_value,
        )


@dataclass(frozen=True, slots=True)
class ValidationStateKey:
    """Identify the historical stream used for stateful validation rules."""

    source_id: str
    role: MeasurementRole
    metric: Metric

    def __post_init__(self) -> None:
        """Require an accepted source identity before state storage."""

        normalized_source_id = self.source_id.strip()
        if not normalized_source_id:
            raise ValueError("source_id must not be empty")
        object.__setattr__(self, "source_id", normalized_source_id)


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Provide prepared historical and cross-source data to one rule run."""

    now: datetime
    previous_measurement: Measurement | None = None
    comparison_measurements: tuple[Measurement, ...] = ()
    profile_name: str | None = None
    source_settings: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        """Validate the rule execution clock and immutable setting keys."""

        _require_timezone_aware(self.now, "now")
        if self.profile_name is not None:
            profile_name = self.profile_name.strip()
            object.__setattr__(
                self,
                "profile_name",
                profile_name or None,
            )

        setting_keys: set[str] = set()
        for key, _value in self.source_settings:
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("source setting keys must not be empty")
            if normalized_key in setting_keys:
                raise ValueError(
                    f"source setting key {normalized_key!r} occurs more than once"
                )
            setting_keys.add(normalized_key)


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    """Reject naive timestamps in validation execution context."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
