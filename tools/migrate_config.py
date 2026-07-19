#!/usr/bin/env python3
"""Non-destructive SolarInspector config migration for Raspberry Pi."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "general": {
        "project_name": "SolarInspector",
        "site_name": "Solakon Anlage",
        "poll_interval_seconds": 10,
        "auto_start_collection": True,
        "bind_host": "0.0.0.0",
        "port": 8787,
        "open_browser": False,
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
    "house_meter": {
        "enabled": False,
        "type": "shelly_3em_gen1",
        "host": "",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": 1,
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


def deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            candidate = existing.get(key, {})
            if not isinstance(candidate, dict):
                candidate = {}
            result[key] = deep_merge(value, candidate)
        else:
            result[key] = existing.get(key, value)
    for key, value in existing.items():
        if key not in result:
            result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    path: Path = args.config

    existing: dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config.json enthält kein JSON-Objekt")
        existing = raw

    migrated = deep_merge(DEFAULTS, existing)
    general = migrated.setdefault("general", {})
    # Raspberry-Pi defaults are only forced when the old setting is absent.
    if "bind_host" not in existing.get("general", {}):
        general["bind_host"] = "0.0.0.0"
    if "open_browser" not in existing.get("general", {}):
        general["open_browser"] = False
    if "auto_start_collection" not in existing.get("general", {}):
        general["auto_start_collection"] = True

    temp = path.with_suffix(".json.new")
    temp.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    print(f"Konfiguration migriert: {path}")


if __name__ == "__main__":
    main()
