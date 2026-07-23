"""Device communication adapters used by SolarInspector.

Importing this package must not perform network communication.
"""

from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.solakon_measurement import (
    SolakonMeasurementAdapter,
)

__all__ = ["MeasurementAdapter", "SolakonMeasurementAdapter"]
