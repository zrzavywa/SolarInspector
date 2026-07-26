"""Test configuration mapping for validation controls."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from zrzavy_energy_monitor_core.config.defaults import DEFAULT_CONFIG
from zrzavy_energy_monitor_core.config.manager import ConfigManager
from zrzavy_energy_monitor_core.web.configuration import apply_configuration_form


def _form() -> dict[str, str]:
    return {
        "project_name": "SolarInspector",
        "site_name": "Test",
        "poll_interval_seconds": "10",
        "bind_host": "127.0.0.1",
        "port": "8787",
        "solar_power_source": "auto",
        "grid_power_source": "auto",
        "validation_enabled": "on",
        "validation_grid_positions_comparable": "on",
        "validation_plant_warning_absolute_w": "25",
        "validation_plant_reject_absolute_w": "120",
        "validation_plant_warning_relative_percent": "8",
        "validation_plant_reject_relative_percent": "25",
        "validation_plant_window_seconds": "45",
        "validation_plant_minimum_duration_seconds": "30",
        "validation_plant_minimum_reference_w": "100",
        "validation_plant_minimum_samples": "3",
        "validation_plant_allow_rejection": "on",
        "validation_grid_warning_absolute_w": "60",
        "validation_grid_reject_absolute_w": "300",
        "validation_grid_warning_relative_percent": "12",
        "validation_grid_reject_relative_percent": "35",
        "validation_grid_window_seconds": "60",
        "validation_grid_minimum_duration_seconds": "30",
        "validation_grid_minimum_reference_w": "200",
        "validation_grid_minimum_samples": "3",
        "validation_dedup_window_seconds": "600",
        "validation_retention_days": "120",
        "validation_prune_interval_seconds": "7200",
    }


def test_validation_form_builds_typed_runtime_configuration() -> None:
    current = deepcopy(DEFAULT_CONFIG)
    updated = apply_configuration_form(current, _form())
    validated = ConfigManager.validate(updated)

    validation = validated["validation"]
    assert validation["enabled"] is True
    assert validation["persistence"]["dedup_window_seconds"] == 600.0
    assert validation["persistence"]["retention_days"] == 120.0

    plant = validation["sources"]["solakon_one"]
    plant_limits = plant["comparisons"]["plant_meter"]
    assert plant["plant_comparison_source_id"] == "solakon_meter"
    assert plant_limits["warning_absolute_w"] == 25.0
    assert plant_limits["minimum_samples"] == 3
    assert plant_limits["allow_rejection"] is True

    grid_source_id = validated["grid_meter"]["source_id"]
    grid = validation["sources"][grid_source_id]
    grid_limits = grid["comparisons"]["grid_meter"]
    assert grid["authoritative_grid_meter"] is True
    assert grid["measurement_position_comparable"] is True
    assert grid["grid_comparison_source_id"] == "house_meter"
    assert grid_limits["warning_absolute_w"] == 60.0
    assert grid_limits["allow_rejection"] is False


def test_configuration_template_exposes_validation_controls() -> None:
    template = Path("app/templates/configuration.html").read_text(encoding="utf-8")

    for field_name in (
        "validation_enabled",
        "validation_grid_positions_comparable",
        "validation_plant_warning_absolute_w",
        "validation_grid_warning_absolute_w",
        "validation_dedup_window_seconds",
        "validation_retention_days",
    ):
        assert f'name="{field_name}"' in template
