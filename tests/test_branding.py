"""Tests for canonical Zrzavy Energy Monitor branding metadata."""

from __future__ import annotations

import importlib
import sys


def test_branding_constants_are_canonical() -> None:
    """Expose the approved complete product and repository identifiers."""

    from zrzavy_energy_monitor_core import branding

    assert branding.PRODUCT_NAME == "Zrzavy Energy Monitor"
    assert branding.PRODUCT_ID == "zrzavy-energy-monitor"
    assert (
        branding.PRODUCT_DESCRIPTION
        == "Open-source home energy monitoring and validation"
    )
    assert branding.PRODUCT_ABBREVIATION == "ZEM"
    assert branding.GITHUB_OWNER == "zrzavywa"
    assert branding.GITHUB_REPOSITORY == "zrzavy-energy-monitor"
    assert branding.LEGACY_PRODUCT_NAME == "SolarInspector"
    assert branding.LEGACY_GITHUB_REPOSITORY == "SolarInspector"
    assert branding.USER_AGENT_PRODUCT == "ZrzavyEnergyMonitor"


def test_branding_import_has_no_observable_side_effects(
    monkeypatch,
) -> None:
    """Import branding metadata without network or filesystem access."""

    def unexpected_side_effect(*args, **kwargs) -> None:
        raise AssertionError("branding import attempted an external side effect")

    monkeypatch.setattr("builtins.open", unexpected_side_effect)
    monkeypatch.setattr("pathlib.Path.mkdir", unexpected_side_effect)
    monkeypatch.setattr("requests.get", unexpected_side_effect)
    sys.modules.pop("zrzavy_energy_monitor_core.branding", None)

    module = importlib.import_module("zrzavy_energy_monitor_core.branding")

    assert module.PRODUCT_NAME == "Zrzavy Energy Monitor"
