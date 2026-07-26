"""Define normalized measurement quality states."""

from __future__ import annotations

from enum import Enum


class MeasurementQuality(str, Enum):
    """Describe the current quality classification of a measurement."""

    MEASURED = "measured"
    REPORTED = "reported"
    CALCULATED = "calculated"
    VALIDATED = "validated"
    SUSPECT = "suspect"
    REJECTED = "rejected"
    STALE = "stale"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"
