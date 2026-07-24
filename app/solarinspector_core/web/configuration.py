"""Map the configuration form onto SolarInspector settings.

This module preserves the existing field names, fallback values, string
handling, enabled flags, and device configuration behavior.
"""

from __future__ import annotations

from typing import Any

from solarinspector_core.config.shelly import (
    Phase,
    ShellyMeasurementRole,
)


def apply_configuration_form(
    current: dict[str, Any],
    form: Any,
) -> dict[str, Any]:
    """Apply submitted form fields to an existing configuration."""
    general = current["general"]
    general.update(
        {
            "project_name": form.get("project_name", ""),
            "site_name": form.get("site_name", ""),
            "poll_interval_seconds": form.get("poll_interval_seconds", "10"),
            "auto_start_collection": form.get("auto_start_collection") == "on",
            "bind_host": form.get("bind_host", "127.0.0.1"),
            "port": form.get("port", "8787"),
            "open_browser": form.get("open_browser") == "on",
            "solar_power_source": form.get("solar_power_source", "auto"),
            "grid_power_source": form.get("grid_power_source", "auto"),
        }
    )
    current["solakon_one"].update(
        {
            "enabled": form.get("solakon_one_enabled") == "on",
            "host": form.get("solakon_one_host", ""),
            "port": form.get("solakon_one_port", "502"),
            "device_id": form.get("solakon_one_device_id", "1"),
            "timeout_seconds": form.get("solakon_one_timeout_seconds", "5"),
            "simulation": form.get("solakon_one_simulation") == "on",
        }
    )
    for role in ("house_meter", "solakon_meter"):
        current[role].update(
            {
                "enabled": form.get(f"{role}_enabled") == "on",
                "type": form.get(f"{role}_type", current[role]["type"]),
                "host": form.get(f"{role}_host", ""),
                "username": form.get(f"{role}_username", ""),
                "password": form.get(f"{role}_password", ""),
                "timeout_seconds": form.get(f"{role}_timeout_seconds", "3"),
                "direction_factor": form.get(f"{role}_direction_factor", "1"),
            }
        )

        if role == "house_meter":
            current[role]["measurement_role"] = form.get(
                f"{role}_measurement_role",
                current[role].get(
                    "measurement_role",
                    ShellyMeasurementRole.HOUSE_TOTAL.value,
                ),
            )
            phase_direction: dict[str, int] = {}
            for phase in Phase:
                value = form.get(f"{role}_phase_direction_{phase.value}", "")
                if value in {"1", "-1"}:
                    phase_direction[phase.value] = int(value)
            current[role]["phase_direction"] = phase_direction

    return current
