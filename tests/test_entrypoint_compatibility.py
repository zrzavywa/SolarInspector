"""Tests for canonical and legacy application entry points."""

from __future__ import annotations

import importlib
import runpy
import sys

import pytest


def test_canonical_entrypoint_is_importable() -> None:
    """Expose the application and main callable under the canonical name."""

    application = importlib.import_module("zrzavy_energy_monitor")

    assert application.app is not None
    assert callable(application.main)


def test_legacy_entrypoint_is_a_thin_deprecated_wrapper() -> None:
    """Delegate execution to the canonical entry point with one warning."""

    application = importlib.import_module("zrzavy_energy_monitor")
    calls: list[str] = []
    original_main = application.main
    application.main = lambda: calls.append("main")
    sys.modules.pop("solarinspector", None)

    try:
        with pytest.warns(
            DeprecationWarning,
            match="app/zrzavy_energy_monitor.py",
        ):
            runpy.run_module("solarinspector", run_name="__main__")
    finally:
        application.main = original_main

    assert calls == ["main"]


def test_legacy_core_package_root_warns_and_canonical_imports_work() -> None:
    """Keep one documented package-root bridge without duplicate modules."""

    sys.modules.pop("solarinspector_core", None)

    with pytest.warns(
        DeprecationWarning,
        match="zrzavy_energy_monitor_core",
    ):
        legacy_package = importlib.import_module("solarinspector_core")

    canonical_package = importlib.import_module("zrzavy_energy_monitor_core")
    measurement_module = importlib.import_module(
        "zrzavy_energy_monitor_core.models.measurement"
    )

    assert legacy_package.__name__ == "solarinspector_core"
    assert canonical_package.__name__ == "zrzavy_energy_monitor_core"
    assert measurement_module.Measurement.__module__.startswith(
        "zrzavy_energy_monitor_core."
    )
