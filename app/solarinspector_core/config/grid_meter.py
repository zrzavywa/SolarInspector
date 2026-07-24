"""Validate configuration for the official grid-meter source."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from enum import Enum
from typing import Any, Final

from solarinspector_core.config.shelly import normalize_direction_factor


class GridMeterAdapter(str, Enum):
    """Identify supported official grid-meter transports."""

    TASMOTA_HTTP = "tasmota_http"


GRID_METER_MAPPING_FIELDS: Final[tuple[str, ...]] = (
    "grid_power_w",
    "grid_import_power_w",
    "grid_export_power_w",
    "grid_import_total_kwh",
    "grid_export_total_kwh",
    "frequency_hz",
    "phase_voltage_l1_v",
    "phase_voltage_l2_v",
    "phase_voltage_l3_v",
    "phase_current_l1_a",
    "phase_current_l2_a",
    "phase_current_l3_a",
    "phase_power_l1_w",
    "phase_power_l2_w",
    "phase_power_l3_w",
)

DEFAULT_GRID_METER_MAPPING: Final[dict[str, str]] = {
    "grid_power_w": "StatusSNS.strom.Pges",
    "grid_import_power_w": "",
    "grid_export_power_w": "",
    "grid_import_total_kwh": "StatusSNS.strom.VerbrauchT0",
    "grid_export_total_kwh": "StatusSNS.strom.RetourT0",
    "frequency_hz": "",
    "phase_voltage_l1_v": "",
    "phase_voltage_l2_v": "",
    "phase_voltage_l3_v": "",
    "phase_current_l1_a": "",
    "phase_current_l2_a": "",
    "phase_current_l3_a": "",
    "phase_power_l1_w": "",
    "phase_power_l2_w": "",
    "phase_power_l3_w": "",
}

DEFAULT_GRID_METER_CONFIG: Final[dict[str, Any]] = {
    "enabled": False,
    "adapter": GridMeterAdapter.TASMOTA_HTTP.value,
    "source_id": "grid_meter_primary",
    "name": "Offizieller Netzstromzähler",
    "host": "",
    "port": 80,
    "scheme": "http",
    "timeout_seconds": 3,
    "poll_interval_seconds": 5,
    "username": "",
    "password": "",
    "direction_factor": 1,
    "mapping": DEFAULT_GRID_METER_MAPPING,
}


def normalize_grid_meter_config(value: object) -> dict[str, Any]:
    """Return one compatible and bounded grid-meter configuration."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)

    normalized["enabled"] = bool(
        raw.get("enabled", DEFAULT_GRID_METER_CONFIG["enabled"])
    )
    normalized["adapter"] = normalize_grid_meter_adapter(raw.get("adapter"))
    normalized["source_id"] = _non_empty_string(
        raw.get("source_id"),
        str(DEFAULT_GRID_METER_CONFIG["source_id"]),
    )
    normalized["name"] = _non_empty_string(
        raw.get("name"),
        str(DEFAULT_GRID_METER_CONFIG["name"]),
    )
    normalized["host"] = normalize_grid_meter_host(raw.get("host"))
    normalized["port"] = _bounded_int(
        raw.get("port"),
        default=int(DEFAULT_GRID_METER_CONFIG["port"]),
        minimum=1,
        maximum=65535,
    )
    normalized["scheme"] = normalize_grid_meter_scheme(raw.get("scheme"))
    normalized["timeout_seconds"] = _bounded_int(
        raw.get("timeout_seconds"),
        default=int(DEFAULT_GRID_METER_CONFIG["timeout_seconds"]),
        minimum=1,
        maximum=30,
    )
    normalized["poll_interval_seconds"] = _bounded_int(
        raw.get("poll_interval_seconds"),
        default=int(DEFAULT_GRID_METER_CONFIG["poll_interval_seconds"]),
        minimum=2,
        maximum=3600,
    )
    normalized["username"] = _string(raw.get("username")).strip()
    normalized["password"] = _string(raw.get("password"))
    normalized["direction_factor"] = normalize_direction_factor(
        raw.get(
            "direction_factor",
            DEFAULT_GRID_METER_CONFIG["direction_factor"],
        )
    )
    normalized["mapping"] = normalize_grid_meter_mapping(raw.get("mapping"))
    return normalized


def normalize_grid_meter_adapter(value: object) -> str:
    """Return the supported adapter name or the compatible default."""

    if isinstance(value, GridMeterAdapter):
        return value.value
    candidate = _string(value).strip().lower()
    try:
        return GridMeterAdapter(candidate).value
    except ValueError:
        return GridMeterAdapter.TASMOTA_HTTP.value


def normalize_grid_meter_scheme(value: object) -> str:
    """Return ``http`` or ``https`` with ``http`` as fallback."""

    candidate = _string(value).strip().lower()
    return candidate if candidate in {"http", "https"} else "http"


def normalize_grid_meter_host(value: object) -> str:
    """Normalize a local host without embedding scheme or path separators."""

    host = _string(value).strip()
    lowered = host.lower()
    for prefix in ("http://", "https://"):
        if lowered.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.rstrip("/")


def normalize_grid_meter_mapping(value: object) -> dict[str, Any]:
    """Normalize known field paths while retaining unknown mapping fields."""

    normalized: dict[str, Any] = deepcopy(DEFAULT_GRID_METER_MAPPING)
    if not isinstance(value, Mapping):
        return normalized

    for key, raw_value in value.items():
        key_text = str(key)
        if key_text in GRID_METER_MAPPING_FIELDS:
            normalized[key_text] = _string(raw_value).strip()
        else:
            normalized[key_text] = deepcopy(raw_value)
    return normalized


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Convert one integer setting and constrain it to inclusive bounds."""

    if isinstance(value, bool):
        converted = default
    elif isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            converted = int(value)
        except (TypeError, ValueError):
            converted = default
    else:
        converted = default

    return max(minimum, min(maximum, converted))


def _non_empty_string(value: object, default: str) -> str:
    """Return a trimmed string or the supplied default."""

    candidate = _string(value).strip()
    return candidate or default


def _string(value: object) -> str:
    """Convert optional scalar configuration content to text."""

    return "" if value is None else str(value)
