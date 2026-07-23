"""Define legacy measurement data types used by SolarInspector.

These models preserve the data structures of SolarInspector 4.1.3.
The redesigned SolarInspector 4.5 measurement model is not introduced
during Phase 03.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MeterReading:
    """Represent a normalized reading from an existing Shelly device."""

    power_w: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_factor: Optional[float] = None
    frequency_hz: Optional[float] = None
    energy_total_wh: Optional[float] = None
    returned_energy_total_wh: Optional[float] = None
    source: str = ""
