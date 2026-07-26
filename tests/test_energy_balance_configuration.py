"""Test additive Phase-09 energy-balance configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from solarinspector_core.config.energy_balance import (
    DEFAULT_ENERGY_BALANCE_CONFIG,
    EnergyBalanceConfigurationError,
    normalize_energy_balance_config,
)
from solarinspector_core.config.manager import ConfigManager


def test_defaults_use_existing_stable_source_ids() -> None:
    normalized = normalize_energy_balance_config(None)

    assert normalized == DEFAULT_ENERGY_BALANCE_CONFIG
    assert normalized["source_priorities"]["grid_power"] == [
        "grid_meter_primary",
        "house_meter",
    ]
    assert normalized["source_priorities"]["plant_ac_power"] == [
        "solakon_meter",
        "solakon_one",
    ]


def test_explicit_values_are_normalized_and_unknown_fields_preserved() -> None:
    normalized = normalize_energy_balance_config(
        {
            "enabled": "false",
            "maximum_measurement_age_seconds": "45",
            "maximum_source_skew_seconds": "8",
            "allow_suspect_measurements": "false",
            "negative_house_power_tolerance_w": "25",
            "short_window_average_seconds": "0",
            "future_option": {"keep": True},
            "source_priorities": {
                "grid_power": [" official ", "fallback"],
            },
        }
    )

    assert normalized["enabled"] is False
    assert normalized["maximum_measurement_age_seconds"] == 45.0
    assert normalized["maximum_source_skew_seconds"] == 8.0
    assert normalized["allow_suspect_measurements"] is False
    assert normalized["negative_house_power_tolerance_w"] == 25.0
    assert normalized["source_priorities"]["grid_power"] == [
        "official",
        "fallback",
    ]
    assert normalized["future_option"] == {"keep": True}


def test_source_priorities_must_be_ordered_unique_known_metric_lists() -> None:
    with pytest.raises(EnergyBalanceConfigurationError, match="duplicate"):
        normalize_energy_balance_config(
            {
                "source_priorities": {
                    "grid_power": ["grid", "grid"],
                }
            }
        )
    with pytest.raises(EnergyBalanceConfigurationError, match="configured as a list"):
        normalize_energy_balance_config(
            {
                "source_priorities": {
                    "grid_power": "grid",
                }
            }
        )
    with pytest.raises(EnergyBalanceConfigurationError, match="not selectable"):
        normalize_energy_balance_config(
            {
                "source_priorities": {
                    "house_power": ["house"],
                }
            }
        )


def test_time_and_tolerance_limits_reject_unsafe_values() -> None:
    with pytest.raises(
        EnergyBalanceConfigurationError,
        match="must not exceed",
    ):
        normalize_energy_balance_config(
            {
                "maximum_measurement_age_seconds": 10,
                "maximum_source_skew_seconds": 11,
            }
        )
    with pytest.raises(
        EnergyBalanceConfigurationError,
        match="greater than zero",
    ):
        normalize_energy_balance_config(
            {
                "maximum_measurement_age_seconds": 0,
            }
        )
    with pytest.raises(
        EnergyBalanceConfigurationError,
        match="must not be negative",
    ):
        normalize_energy_balance_config(
            {
                "negative_house_power_tolerance_w": -1,
            }
        )


def test_legacy_configuration_receives_additive_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "general": {"site_name": "Legacy site"},
                "future_section": {"keep": True},
            }
        ),
        encoding="utf-8",
    )

    config = ConfigManager(path, logger=lambda _message: None).get()

    assert config["energy_balance"] == DEFAULT_ENERGY_BALANCE_CONFIG
    assert config["general"]["site_name"] == "Legacy site"
    assert config["future_section"] == {"keep": True}


def test_manager_save_preserves_unknown_balance_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    manager = ConfigManager(path, logger=lambda _message: None)
    config = manager.get()
    config["energy_balance"]["future_option"] = "preserved"
    config["energy_balance"]["source_priorities"]["grid_power"] = [
        "custom_grid",
    ]

    manager.save(config)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["energy_balance"]["future_option"] == "preserved"
    assert saved["energy_balance"]["source_priorities"]["grid_power"] == ["custom_grid"]


def test_example_configuration_documents_energy_balance_defaults() -> None:
    example = json.loads(Path("app/config.example.json").read_text(encoding="utf-8"))

    assert (
        normalize_energy_balance_config(example["energy_balance"])
        == DEFAULT_ENERGY_BALANCE_CONFIG
    )
    assert example["house_meter"]["measurement_role"] == "grid_fallback"
