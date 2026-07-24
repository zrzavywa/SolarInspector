"""Tests for Shelly measurement roles and phase directions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.config.manager import ConfigManager, deep_merge
from solarinspector_core.config.shelly import (
    Phase,
    ShellyMeasurementRole,
    phase_direction_factor,
)
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.web.api import build_test_device_api_response
from solarinspector_core.web.configuration import apply_configuration_form


class ReaderStub:
    """Capture the validated configuration used by the device-test API."""

    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None
        self.role: str | None = None

    def read(self, config: dict[str, Any], role: str) -> MeterReading:
        """Return one deterministic compatible reading."""

        self.config = deepcopy(config)
        self.role = role
        return MeterReading(power_w=0.0, source="Fixture")


def test_phase_and_measurement_role_values_are_stable() -> None:
    assert [phase.value for phase in Phase] == ["l1", "l2", "l3"]
    assert [role.value for role in ShellyMeasurementRole] == [
        "house_total",
        "distribution",
        "sub_distribution",
        "consumer_group",
        "grid_fallback",
    ]


def test_legacy_config_inherits_global_direction_for_all_phases(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "house_meter": {
                    "enabled": True,
                    "direction_factor": -1,
                }
            }
        ),
        encoding="utf-8",
    )

    config = ConfigManager(config_path).get()
    house_meter = config["house_meter"]

    assert house_meter["measurement_role"] == "house_total"
    assert house_meter["phase_direction"] == {}
    assert all(phase_direction_factor(house_meter, phase) == -1 for phase in Phase)


def test_explicit_phase_directions_override_the_global_factor() -> None:
    config = deep_merge(
        deepcopy(DEFAULT_CONFIG),
        {
            "house_meter": {
                "direction_factor": -1,
                "phase_direction": {
                    "l1": 1,
                    "l3": "1",
                },
            }
        },
    )

    house_meter = ConfigManager.validate(config)["house_meter"]

    assert house_meter["phase_direction"] == {"l1": 1, "l3": 1}
    assert phase_direction_factor(house_meter, Phase.L1) == 1
    assert phase_direction_factor(house_meter, Phase.L2) == -1
    assert phase_direction_factor(house_meter, Phase.L3) == 1


@pytest.mark.parametrize(
    "phase_direction",
    [
        None,
        [],
        {"l1": 0, "l2": -9, "l3": "invalid"},
        {"l1": True, "l2": False},
    ],
)
def test_invalid_phase_directions_fall_back_to_global(
    phase_direction: object,
) -> None:
    config = deep_merge(
        deepcopy(DEFAULT_CONFIG),
        {
            "house_meter": {
                "direction_factor": -1,
                "phase_direction": phase_direction,
            }
        },
    )

    house_meter = ConfigManager.validate(config)["house_meter"]

    assert house_meter["phase_direction"] == {}
    assert all(phase_direction_factor(house_meter, phase) == -1 for phase in Phase)


def test_invalid_measurement_role_uses_legacy_house_total_default() -> None:
    config = deep_merge(
        deepcopy(DEFAULT_CONFIG),
        {
            "house_meter": {
                "measurement_role": "unsupported",
            }
        },
    )

    validated = ConfigManager.validate(config)

    assert validated["house_meter"]["measurement_role"] == "house_total"


def test_configuration_form_sets_and_clears_phase_overrides() -> None:
    current = deep_merge(
        deepcopy(DEFAULT_CONFIG),
        {
            "house_meter": {
                "phase_direction": {"l2": -1},
            }
        },
    )

    updated = apply_configuration_form(
        current,
        {
            "house_meter_measurement_role": "distribution",
            "house_meter_phase_direction_l1": "-1",
            "house_meter_phase_direction_l2": "",
            "house_meter_phase_direction_l3": "1",
        },
    )

    assert updated["house_meter"]["measurement_role"] == "distribution"
    assert updated["house_meter"]["phase_direction"] == {
        "l1": -1,
        "l3": 1,
    }


def test_device_test_api_uses_validated_role_and_phase_directions() -> None:
    reader = ReaderStub()
    root_config = deepcopy(DEFAULT_CONFIG)

    payload, status_code = build_test_device_api_response(
        root_config,
        "house_meter",
        {
            "enabled": True,
            "type": "simulation",
            "direction_factor": -1,
            "measurement_role": "consumer_group",
            "phase_direction": {
                "l1": 1,
                "l2": "invalid",
            },
        },
        reader,
    )

    assert status_code is None
    assert payload["ok"] is True
    assert reader.role == "house_meter"
    assert reader.config is not None
    assert reader.config["measurement_role"] == "consumer_group"
    assert reader.config["phase_direction"] == {"l1": 1}
    assert phase_direction_factor(reader.config, Phase.L1) == 1
    assert phase_direction_factor(reader.config, Phase.L2) == -1
    assert phase_direction_factor(reader.config, Phase.L3) == -1
