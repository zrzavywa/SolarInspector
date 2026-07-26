"""Compatibility package for the former SolarInspector core namespace.

Only the package root remains supported during the 4.5 compatibility period.
Application code and integrations must import concrete modules from
``zrzavy_energy_monitor_core``.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "solarinspector_core is deprecated; use zrzavy_energy_monitor_core. "
    "The compatibility package root is retained for the 4.5 series.",
    DeprecationWarning,
    stacklevel=2,
)
