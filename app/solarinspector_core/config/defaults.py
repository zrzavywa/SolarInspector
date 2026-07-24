"""Define the existing SolarInspector configuration defaults.

This module contains only the configuration values and supported device
names of SolarInspector 4.1.3. It does not load, validate, migrate, or
persist configuration files.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from solarinspector_core.config.grid_meter import (
    DEFAULT_GRID_METER_CONFIG,
)
from solarinspector_core.config.shelly import ShellyMeasurementRole

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "project_name": "SolarInspector",
        "site_name": "Solakon Anlage",
        "poll_interval_seconds": 10,
        "auto_start_collection": False,
        "bind_host": "127.0.0.1",
        "port": 8787,
        "open_browser": True,
        "solar_power_source": "auto",
        "grid_power_source": "auto",
    },
    "solakon_one": {
        "enabled": False,
        "host": "",
        "port": 502,
        "device_id": 1,
        "timeout_seconds": 5,
        "simulation": False,
    },
    "grid_meter": deepcopy(DEFAULT_GRID_METER_CONFIG),
    "house_meter": {
        "enabled": False,
        "type": "shelly_3em_gen1",
        "host": "",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": 1,
        "measurement_role": ShellyMeasurementRole.HOUSE_TOTAL.value,
        "phase_direction": {},
    },
    "solakon_meter": {
        "enabled": False,
        "type": "shelly_pm_mini_gen3",
        "host": "",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": 1,
    },
}


DEVICE_TYPES: dict[str, str] = {
    "shelly_pm_mini_gen3": "Shelly PM Mini Gen 3 / PM1",
    "shelly_3em_gen1": "Shelly 3EM Gen 1",
    "shelly_pro_3em": "Shelly Pro 3EM / EM RPC",
    "simulation": "Simulation",
}
