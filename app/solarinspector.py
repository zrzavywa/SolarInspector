#!/usr/bin/env python3
"""Compatibility entry point for the former SolarInspector command.

This wrapper remains available during the 4.5 compatibility period. New
installations and integrations must use :mod:`zrzavy_energy_monitor`.
"""

from __future__ import annotations

import warnings

from zrzavy_energy_monitor import main


def _warn_deprecated_entrypoint() -> None:
    """Warn that the legacy command will be removed after the 4.5 series."""

    warnings.warn(
        "app/solarinspector.py is deprecated; use "
        "app/zrzavy_energy_monitor.py instead. The compatibility entry point "
        "is retained for the 4.5 series.",
        DeprecationWarning,
        stacklevel=2,
    )


_warn_deprecated_entrypoint()

if __name__ == "__main__":
    main()
