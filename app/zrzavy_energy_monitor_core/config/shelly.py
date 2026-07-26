"""Validate Shelly phase and measurement-role configuration."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any


class Phase(str, Enum):
    """Identify one electrical phase in configuration and parsing."""

    L1 = "l1"
    L2 = "l2"
    L3 = "l3"


class ShellyMeasurementRole(str, Enum):
    """Describe the configured installation position of a Shelly meter."""

    HOUSE_TOTAL = "house_total"
    DISTRIBUTION = "distribution"
    SUB_DISTRIBUTION = "sub_distribution"
    CONSUMER_GROUP = "consumer_group"
    GRID_FALLBACK = "grid_fallback"


def normalize_direction_factor(value: object, *, default: int = 1) -> int:
    """Normalize the compatible global direction factor to ``1`` or ``-1``."""

    if isinstance(value, bool):
        return default
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return default
    try:
        factor = int(value)
    except (TypeError, ValueError):
        return default
    return -1 if factor < 0 else 1


def normalize_phase_direction(value: object) -> dict[str, int]:
    """Return only explicit valid per-phase direction overrides.

    Missing or invalid entries are intentionally omitted so that they inherit
    the compatible global ``direction_factor``.
    """

    if not isinstance(value, Mapping):
        return {}

    normalized: dict[str, int] = {}
    for phase in Phase:
        raw_value = value.get(phase.value)
        if isinstance(raw_value, bool):
            continue
        if raw_value in (1, -1, "1", "-1"):
            normalized[phase.value] = int(raw_value)
    return normalized


def normalize_measurement_role(value: object) -> str:
    """Normalize one configured Shelly installation role."""

    if isinstance(value, ShellyMeasurementRole):
        return value.value
    try:
        return ShellyMeasurementRole(str(value)).value
    except ValueError:
        return ShellyMeasurementRole.HOUSE_TOTAL.value


def phase_direction_factor(
    device: Mapping[str, Any],
    phase: Phase,
) -> int:
    """Resolve one phase factor, preferring its explicit override."""

    phase_direction = normalize_phase_direction(device.get("phase_direction"))
    if phase.value in phase_direction:
        return phase_direction[phase.value]
    return normalize_direction_factor(device.get("direction_factor", 1))
