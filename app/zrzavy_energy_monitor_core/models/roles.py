"""Define device-independent measurement roles."""

from __future__ import annotations

from enum import Enum


class MeasurementRole(str, Enum):
    """Describe the functional role of a measurement source."""

    GRID_METER = "grid_meter"
    HOUSE_METER = "house_meter"
    PLANT_METER = "plant_meter"
    SOLAR_SYSTEM = "solar_system"
    BATTERY_SYSTEM = "battery_system"
