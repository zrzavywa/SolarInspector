"""Store accepted historical measurements for stateful validation rules."""

from __future__ import annotations

import threading
from datetime import datetime

from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
    ValidationStateKey,
)

_NON_REFERENCE_QUALITIES = {
    MeasurementQuality.REJECTED,
    MeasurementQuality.STALE,
    MeasurementQuality.UNAVAILABLE,
}


class ValidationStateStore:
    """Maintain the latest accepted measurement for each independent stream.

    The store deliberately contains no validation logic. It accepts strict
    ``Measurement`` instances after an external decision and prepares immutable
    ``ValidationContext`` objects for subsequent rule evaluation.
    """

    def __init__(self) -> None:
        """Create one empty, thread-safe in-memory state store."""

        self._lock = threading.RLock()
        self._measurements: dict[ValidationStateKey, Measurement] = {}

    def record_accepted(self, measurement: Measurement) -> bool:
        """Record a usable measurement unless a newer reference already exists.

        Returns:
            ``True`` when the stream reference was inserted or replaced.
            ``False`` when the measurement quality is unusable or its timestamp
            is older than the currently stored reference.
        """

        if measurement.quality in _NON_REFERENCE_QUALITIES:
            return False

        key = ValidationStateKey(
            source_id=measurement.source_id,
            role=measurement.role,
            metric=measurement.metric,
        )
        with self._lock:
            previous = self._measurements.get(key)
            if previous is not None and measurement.measured_at < previous.measured_at:
                return False
            self._measurements[key] = measurement
        return True

    def previous_for(
        self,
        candidate: MeasurementCandidate,
    ) -> Measurement | None:
        """Return the latest accepted measurement for the candidate stream."""

        source_id = candidate.source_id.strip()
        if not source_id:
            return None
        key = ValidationStateKey(
            source_id=source_id,
            role=candidate.role,
            metric=candidate.metric,
        )
        with self._lock:
            return self._measurements.get(key)

    def context_for(
        self,
        candidate: MeasurementCandidate,
        *,
        now: datetime,
        comparison_measurements: tuple[Measurement, ...] = (),
        profile_name: str | None = None,
        source_settings: tuple[tuple[str, object], ...] = (),
    ) -> ValidationContext:
        """Build one immutable context using the matching stream reference."""

        return ValidationContext(
            now=now,
            previous_measurement=self.previous_for(candidate),
            comparison_measurements=comparison_measurements,
            profile_name=profile_name,
            source_settings=source_settings,
        )

    def clear(self) -> None:
        """Remove all historical references."""

        with self._lock:
            self._measurements.clear()

    def __len__(self) -> int:
        """Return the number of independent historical streams."""

        with self._lock:
            return len(self._measurements)
