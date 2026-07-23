"""Define immutable normalized measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real

from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit, unit_for_metric


@dataclass(frozen=True, slots=True)
class Measurement:
    """Represent one normalized value received from a configured source.

    Attributes:
        metric: Semantic meaning of the measurement.
        value: Numeric value normalized to the canonical metric unit.
        unit: Physical unit used by the normalized value.
        source_id: Stable identifier of the configured source.
        role: Functional role under which the value was measured.
        measured_at: Time at which the source measured or reported the value.
        received_at: Time at which SolarInspector received the value.
        quality: Current quality classification.
        raw_value: Original device value retained for diagnostics, if useful.
    """

    metric: Metric
    value: float
    unit: Unit
    source_id: str
    role: MeasurementRole
    measured_at: datetime
    received_at: datetime
    quality: MeasurementQuality
    raw_value: object | None = None

    def __post_init__(self) -> None:
        """Validate structural invariants without applying plausibility rules."""

        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if isinstance(self.value, bool) or not isinstance(self.value, Real):
            raise TypeError("value must be a real number")
        normalized_value = float(self.value)
        if not math.isfinite(normalized_value):
            raise ValueError("value must be finite")
        object.__setattr__(self, "value", normalized_value)
        _require_timezone_aware(self.measured_at, "measured_at")
        _require_timezone_aware(self.received_at, "received_at")
        expected_unit = unit_for_metric(self.metric)
        if self.unit is not expected_unit:
            raise ValueError(
                f"metric {self.metric.value} requires unit {expected_unit.value}"
            )


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    """Reject naive timestamps in the normalized measurement model."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
