"""Tests for the official grid-meter configuration and migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.config.grid_meter import (
    DEFAULT_GRID_METER_CONFIG,
    DEFAULT_GRID_METER_MAPPING,
    DEFAULT_SHRDZM_REST_CONFIG,
    DEFAULT_SHRDZM_REST_MAPPING,
)
from solarinspector_core.config.manager import ConfigManager


def _write_config(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_default_grid_meter_is_disabled_with_real_tasmota_mapping() -> None:
    """Defaults are inert but ready for the confirmed Hichi field paths."""

    grid_meter = DEFAULT_CONFIG["grid_meter"]

    assert grid_meter["enabled"] is False
    assert grid_meter["adapter"] == "tasmota_http"
    assert grid_meter["source_id"] == "grid_meter_primary"
    assert grid_meter["direction_factor"] == 1
    assert grid_meter["mapping"]["grid_power_w"] == "StatusSNS.strom.Pges"
    assert (
        grid_meter["mapping"]["grid_import_total_kwh"] == "StatusSNS.strom.VerbrauchT0"
    )
    assert grid_meter["mapping"]["grid_export_total_kwh"] == "StatusSNS.strom.RetourT0"


def test_legacy_configuration_receives_grid_meter_defaults(
    tmp_path: Path,
) -> None:
    """An older configuration gains an inert grid-meter section."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {"general": {"site_name": "Legacy installation"}},
    )

    config = ConfigManager(config_path).get()

    assert config["general"]["site_name"] == "Legacy installation"
    assert config["grid_meter"] == DEFAULT_GRID_METER_CONFIG


def test_complete_grid_meter_configuration_is_normalized(
    tmp_path: Path,
) -> None:
    """Connection, timing, direction, and mapping settings are bounded."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {
            "grid_meter": {
                "enabled": True,
                "adapter": "unsupported",
                "source_id": " official-grid ",
                "name": " Hauptzähler ",
                "host": " https://192.0.2.50/ ",
                "port": "8080",
                "scheme": "HTTPS",
                "timeout_seconds": 99,
                "poll_interval_seconds": 1,
                "username": " admin ",
                "password": "  keep spaces  ",
                "direction_factor": -7,
                "mapping": {
                    "grid_power_w": " StatusSNS.strom.Pges ",
                    "grid_import_total_kwh": None,
                    "future_mapping": {"path": "StatusSNS.future.Value"},
                },
                "future_option": {"preserve": True},
            }
        },
    )

    grid_meter = ConfigManager(config_path).get()["grid_meter"]

    assert grid_meter["enabled"] is True
    assert grid_meter["adapter"] == "unsupported"
    assert grid_meter["source_id"] == "official-grid"
    assert grid_meter["name"] == "Hauptzähler"
    assert grid_meter["host"] == "192.0.2.50"
    assert grid_meter["port"] == 8080
    assert grid_meter["scheme"] == "https"
    assert grid_meter["timeout_seconds"] == 30
    assert grid_meter["poll_interval_seconds"] == 2
    assert grid_meter["username"] == "admin"
    assert grid_meter["password"] == "  keep spaces  "
    assert grid_meter["direction_factor"] == -1
    assert grid_meter["mapping"]["grid_power_w"] == "StatusSNS.strom.Pges"
    assert grid_meter["mapping"]["grid_import_total_kwh"] == ""
    assert grid_meter["mapping"]["future_mapping"] == {"path": "StatusSNS.future.Value"}
    assert grid_meter["future_option"] == {"preserve": True}


def test_invalid_grid_meter_section_uses_defaults(tmp_path: Path) -> None:
    """A malformed optional section cannot break legacy startup."""

    config_path = tmp_path / "config.json"
    _write_config(config_path, {"grid_meter": "invalid"})

    config = ConfigManager(config_path).get()

    assert config["grid_meter"] == DEFAULT_GRID_METER_CONFIG


def test_invalid_numeric_values_fall_back_without_crashing(
    tmp_path: Path,
) -> None:
    """Invalid numeric settings use safe defaults and supported bounds."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {
            "grid_meter": {
                "port": "not-a-port",
                "timeout_seconds": None,
                "poll_interval_seconds": "not-an-interval",
                "direction_factor": True,
            }
        },
    )

    grid_meter = ConfigManager(config_path).get()["grid_meter"]

    assert grid_meter["port"] == 80
    assert grid_meter["timeout_seconds"] == 3
    assert grid_meter["poll_interval_seconds"] == 5
    assert grid_meter["direction_factor"] == 1


def test_grid_meter_migration_is_repeatable(tmp_path: Path) -> None:
    """Saving and loading the migrated configuration is idempotent."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {
            "grid_meter": {
                "enabled": True,
                "host": "tasmota-grid.local",
                "mapping": {
                    "grid_power_w": "StatusSNS.strom.Pges",
                },
            }
        },
    )

    first_manager = ConfigManager(config_path)
    first = first_manager.get()
    first_manager.save(first)
    second = ConfigManager(config_path).get()

    assert second == first
    assert second["grid_meter"]["host"] == "tasmota-grid.local"


def test_example_configuration_contains_disabled_grid_meter() -> None:
    """The distributed example documents the confirmed default mapping."""

    root = Path(__file__).parents[1]
    example = json.loads((root / "app/config.example.json").read_text(encoding="utf-8"))

    assert example["grid_meter"]["enabled"] is False
    assert example["grid_meter"]["adapter"] == "tasmota_http"
    assert example["grid_meter"]["direction_factor"] == 1
    assert example["grid_meter"]["mapping"] == DEFAULT_GRID_METER_MAPPING
    assert example["grid_meter"]["shrdzm_rest"] == DEFAULT_SHRDZM_REST_CONFIG


def test_shrdzm_configuration_uses_documented_defaults(
    tmp_path: Path,
) -> None:
    """SHRDZM receives its independent REST and OBIS profile."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {
            "grid_meter": {
                "enabled": True,
                "adapter": "shrdzm_rest",
                "shrdzm_rest": {
                    "endpoint": "getLastData?ignored=true",
                    "authentication_mode": "QUERY",
                    "username_parameter": "",
                    "password_parameter": "",
                    "energy_total_unit": "invalid",
                    "future_option": {"preserve": True},
                },
            }
        },
    )

    grid_meter = ConfigManager(config_path).get()["grid_meter"]

    assert grid_meter["adapter"] == "shrdzm_rest"
    assert grid_meter["mapping"] == DEFAULT_SHRDZM_REST_MAPPING
    assert grid_meter["shrdzm_rest"]["endpoint"] == "/getLastData"
    assert grid_meter["shrdzm_rest"]["authentication_mode"] == "query"
    assert grid_meter["shrdzm_rest"]["username_parameter"] == "user"
    assert grid_meter["shrdzm_rest"]["password_parameter"] == "password"
    assert grid_meter["shrdzm_rest"]["energy_total_unit"] == "auto"
    assert grid_meter["shrdzm_rest"]["future_option"] == {"preserve": True}
