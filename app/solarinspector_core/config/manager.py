"""Load, validate, and persist the existing SolarInspector configuration.

This module preserves the configuration behavior of SolarInspector 4.1.3.
It does not access devices, databases, Flask, or the collector.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

from solarinspector_core.config.defaults import (
    DEFAULT_CONFIG,
    DEVICE_TYPES,
)
from solarinspector_core.logging import log as default_log

LogFunction = Callable[[str], None]


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge override values into a shallow copy of base."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(
            result.get(key),
            dict,
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """Load, validate, copy, and atomically save configuration data."""

    def __init__(
        self,
        path: Path,
        logger: LogFunction = default_log,
    ) -> None:
        self.path = path
        self._logger = logger
        self._lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.write_text(
                json.dumps(
                    DEFAULT_CONFIG,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return deep_merge(DEFAULT_CONFIG, {})

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            return self.validate(deep_merge(DEFAULT_CONFIG, loaded))
        except Exception as exc:
            self._logger(
                "Konfiguration konnte nicht gelesen werden: "
                f"{exc}; Standardwerte werden verwendet."
            )
            return deep_merge(DEFAULT_CONFIG, {})

    def get(self) -> dict[str, Any]:
        """Return an independent copy of the current configuration."""
        with self._lock:
            return json.loads(json.dumps(self._config))

    def save(self, config: dict[str, Any]) -> None:
        """Validate and atomically persist a configuration."""
        validated = self.validate(deep_merge(DEFAULT_CONFIG, config))
        with self._lock:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    validated,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._config = validated

    @staticmethod
    def validate(
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply the existing SolarInspector validation rules."""
        general = config["general"]
        general["poll_interval_seconds"] = max(
            2,
            min(
                3600,
                int(
                    general.get(
                        "poll_interval_seconds",
                        10,
                    )
                ),
            ),
        )
        general["port"] = max(
            1,
            min(
                65535,
                int(general.get("port", 8787)),
            ),
        )
        general["bind_host"] = (
            str(
                general.get(
                    "bind_host",
                    "127.0.0.1",
                )
            ).strip()
            or "127.0.0.1"
        )
        general["project_name"] = str(
            general.get(
                "project_name",
                "SolarInspector",
            )
        ).strip()
        general["site_name"] = str(general.get("site_name", "")).strip()
        general["auto_start_collection"] = bool(
            general.get(
                "auto_start_collection",
                False,
            )
        )
        general["open_browser"] = bool(general.get("open_browser", True))

        if general.get("solar_power_source") not in {
            "auto",
            "shelly_ac",
            "solakon_ac",
            "solakon_pv",
        }:
            general["solar_power_source"] = "auto"

        if general.get("grid_power_source") not in {
            "auto",
            "house_meter",
            "solakon_one",
        }:
            general["grid_power_source"] = "auto"

        solakon = config["solakon_one"]
        solakon["enabled"] = bool(solakon.get("enabled", False))
        solakon["host"] = (
            str(solakon.get("host", ""))
            .strip()
            .replace("http://", "")
            .replace("https://", "")
            .rstrip("/")
        )
        solakon["port"] = max(
            1,
            min(
                65535,
                int(solakon.get("port", 502)),
            ),
        )
        solakon["device_id"] = max(
            1,
            min(
                247,
                int(solakon.get("device_id", 1)),
            ),
        )
        solakon["timeout_seconds"] = max(
            1,
            min(
                30,
                int(
                    solakon.get(
                        "timeout_seconds",
                        5,
                    )
                ),
            ),
        )
        solakon["simulation"] = bool(solakon.get("simulation", False))

        for role in ("house_meter", "solakon_meter"):
            device = config[role]

            if device.get("type") not in DEVICE_TYPES:
                device["type"] = DEFAULT_CONFIG[role]["type"]

            device["enabled"] = bool(device.get("enabled", False))
            device["host"] = (
                str(device.get("host", ""))
                .strip()
                .replace("http://", "")
                .replace("https://", "")
                .rstrip("/")
            )
            device["username"] = str(device.get("username", "")).strip()
            device["password"] = str(device.get("password", ""))
            device["timeout_seconds"] = max(
                1,
                min(
                    30,
                    int(
                        device.get(
                            "timeout_seconds",
                            3,
                        )
                    ),
                ),
            )

            try:
                factor = int(
                    device.get(
                        "direction_factor",
                        1,
                    )
                )
            except (TypeError, ValueError):
                factor = 1

            device["direction_factor"] = -1 if factor < 0 else 1

        return config
