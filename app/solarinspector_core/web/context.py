"""Build the shared SolarInspector template context.

This module preserves the existing labels, source selections, device types,
version information, and collector status exposed to HTML templates.
"""

from __future__ import annotations

from typing import Any


def build_template_context(
    config: dict[str, Any],
    collector_running: bool,
    app_version: str,
    device_types: dict[str, str],
) -> dict[str, Any]:
    return {
        "app_version": app_version,
        "project_name": config["general"]["project_name"],
        "site_name": config["general"]["site_name"],
        "collector_running": collector_running,
        "device_types": device_types,
        "solar_source_types": {
            "auto": "Automatisch: Shelly AC, sonst Solakon ONE AC",
            "shelly_ac": "Shelly PM Mini Gen 3 – AC-Ausgang",
            "solakon_ac": "Solakon ONE – AC-Wirkleistung",
            "solakon_pv": "Solakon ONE – PV-Eingangsleistung (DC)",
        },
        "grid_source_types": {
            "auto": "Automatisch: separate Hausmessung, sonst Solakon ONE Meter",
            "house_meter": "Separate Hausmessung (Shelly 3EM)",
            "solakon_one": "Solakon ONE – verbundenes Meter/CT",
        },
    }
