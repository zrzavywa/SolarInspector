"""Device communication adapters used by Zrzavy Energy Monitor.

Importing this package must not perform network communication.
"""

from zrzavy_energy_monitor_core.adapters.base import MeasurementAdapter
from zrzavy_energy_monitor_core.adapters.compatibility import (
    meter_reading_from_snapshot,
    solakon_reading_from_snapshot,
)
from zrzavy_energy_monitor_core.adapters.solakon_measurement import (
    SolakonMeasurementAdapter,
)

__all__ = [
    "MeasurementAdapter",
    "SolakonMeasurementAdapter",
    "meter_reading_from_snapshot",
    "solakon_reading_from_snapshot",
]
