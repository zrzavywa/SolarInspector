"""Device communication adapters used by SolarInspector.

Importing this package must not perform network communication.
"""

from solarinspector_core.adapters.base import MeasurementAdapter

__all__ = ["MeasurementAdapter"]
