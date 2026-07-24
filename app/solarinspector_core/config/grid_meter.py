"""Validate configuration for the official grid-meter source."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from enum import Enum
from typing import Any, Final
from urllib.parse import urlsplit

from solarinspector_core.config.shelly import normalize_direction_factor


class GridMeterAdapter(str, Enum):
    """Identify supported official grid-meter transports."""

    TASMOTA_HTTP = "tasmota_http"
    SHRDZM_REST = "shrdzm_rest"


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

DEFAULT_SHRDZM_REST_MAPPING: Final[dict[str, str]] = {
    "grid_power_w": "16.7.0",
    "grid_import_power_w": "1.7.0",
    "grid_export_power_w": "2.7.0",
    "grid_import_total_kwh": "1.8.0",
    "grid_export_total_kwh": "2.8.0",
    "frequency_hz": "",
    "phase_voltage_l1_v": "32.7.0",
    "phase_voltage_l2_v": "52.7.0",
    "phase_voltage_l3_v": "72.7.0",
    "phase_current_l1_a": "31.7.0",
    "phase_current_l2_a": "51.7.0",
    "phase_current_l3_a": "71.7.0",
    "phase_power_l1_w": "",
    "phase_power_l2_w": "",
    "phase_power_l3_w": "",
}

DEFAULT_SHRDZM_REST_CONFIG: Final[dict[str, str]] = {
    "endpoint": "/getLastData",
    "authentication_mode": "query",
    "username_parameter": "user",
    "password_parameter": "password",
    "energy_total_unit": "auto",
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
    "shrdzm_rest": DEFAULT_SHRDZM_REST_CONFIG,
    "direction_factor": 1,
    "mapping": DEFAULT_GRID_METER_MAPPING,
}


def normalize_grid_meter_config(value: object) -> dict[str, Any]:
    """Return one compatible and bounded configuration."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    adapter = normalize_grid_meter_adapter(raw.get("adapter"))

    normalized["enabled"] = bool(
        raw.get("enabled", DEFAULT_GRID_METER_CONFIG["enabled"])
    )
    normalized["adapter"] = adapter
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
    normalized["shrdzm_rest"] = normalize_shrdzm_rest_config(raw.get("shrdzm_rest"))
    normalized["direction_factor"] = normalize_direction_factor(
        raw.get(
            "direction_factor",
            DEFAULT_GRID_METER_CONFIG["direction_factor"],
        )
    )
    normalized["mapping"] = normalize_grid_meter_mapping(
        raw.get("mapping"),
        adapter=adapter,
    )
    return normalized


def normalize_grid_meter_adapter(value: object) -> str:
    """Normalize known names and retain invalid names."""

    if isinstance(value, GridMeterAdapter):
        return value.value
    candidate = _string(value).strip().lower()
    if not candidate:
        return GridMeterAdapter.TASMOTA_HTTP.value
    try:
        return GridMeterAdapter(candidate).value
    except ValueError:
        return candidate


def normalize_grid_meter_scheme(value: object) -> str:
    """Return http or https with a safe fallback."""

    candidate = _string(value).strip().lower()
    return candidate if candidate in {"http", "https"} else "http"


def normalize_grid_meter_host(value: object) -> str:
    """Normalize a local host without a scheme."""

    host = _string(value).strip()
    lowered = host.lower()
    for prefix in ("http://", "https://"):
        if lowered.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.rstrip("/")


def normalize_grid_meter_mapping(
    value: object,
    *,
    adapter: object = GridMeterAdapter.TASMOTA_HTTP.value,
) -> dict[str, Any]:
    """Normalize one adapter-specific field mapping."""

    adapter_name = normalize_grid_meter_adapter(adapter)
    raw_mapping = dict(value) if isinstance(value, Mapping) else {}

    if adapter_name == GridMeterAdapter.SHRDZM_REST.value and _mapping_matches_profile(
        raw_mapping,
        DEFAULT_GRID_METER_MAPPING,
    ):
        raw_mapping = deepcopy(DEFAULT_SHRDZM_REST_MAPPING)
    elif (
        adapter_name == GridMeterAdapter.TASMOTA_HTTP.value
        and _mapping_matches_profile(
            raw_mapping,
            DEFAULT_SHRDZM_REST_MAPPING,
        )
    ):
        raw_mapping = deepcopy(DEFAULT_GRID_METER_MAPPING)

    normalized: dict[str, Any] = default_grid_meter_mapping(adapter_name)
    for key, raw_value in raw_mapping.items():
        key_text = str(key)
        if key_text in GRID_METER_MAPPING_FIELDS:
            normalized[key_text] = _string(raw_value).strip()
        else:
            normalized[key_text] = deepcopy(raw_value)
    return normalized


def default_grid_meter_mapping(adapter: object) -> dict[str, str]:
    """Return an independent mapping for one adapter."""

    adapter_name = normalize_grid_meter_adapter(adapter)
    if adapter_name == GridMeterAdapter.SHRDZM_REST.value:
        return deepcopy(DEFAULT_SHRDZM_REST_MAPPING)
    return deepcopy(DEFAULT_GRID_METER_MAPPING)


def normalize_shrdzm_rest_config(value: object) -> dict[str, Any]:
    """Normalize SHRDZM-specific REST settings."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    normalized["endpoint"] = normalize_grid_meter_endpoint(raw.get("endpoint"))

    authentication_mode = _string(raw.get("authentication_mode")).strip().lower()
    normalized["authentication_mode"] = (
        authentication_mode
        if authentication_mode in {"none", "query", "basic"}
        else DEFAULT_SHRDZM_REST_CONFIG["authentication_mode"]
    )
    normalized["username_parameter"] = _non_empty_string(
        raw.get("username_parameter"),
        DEFAULT_SHRDZM_REST_CONFIG["username_parameter"],
    )
    normalized["password_parameter"] = _non_empty_string(
        raw.get("password_parameter"),
        DEFAULT_SHRDZM_REST_CONFIG["password_parameter"],
    )

    energy_total_unit = _string(raw.get("energy_total_unit")).strip().lower()
    normalized["energy_total_unit"] = (
        energy_total_unit
        if energy_total_unit in {"auto", "wh", "kwh", "mwh"}
        else DEFAULT_SHRDZM_REST_CONFIG["energy_total_unit"]
    )
    return normalized


def normalize_grid_meter_endpoint(value: object) -> str:
    """Normalize one local read-only HTTP endpoint."""

    candidate = _string(value).strip()
    if not candidate:
        return DEFAULT_SHRDZM_REST_CONFIG["endpoint"]
    if candidate.lower().startswith(("http://", "https://")):
        candidate = urlsplit(candidate).path or DEFAULT_SHRDZM_REST_CONFIG["endpoint"]
    candidate = candidate.split("?", 1)[0]
    candidate = candidate.split("#", 1)[0]
    return "/" + candidate.lstrip("/")


def _mapping_matches_profile(
    value: Mapping[object, object],
    profile: Mapping[str, str],
) -> bool:
    """Return whether a mapping is one unchanged profile."""

    if any(str(key) not in GRID_METER_MAPPING_FIELDS for key in value):
        return False
    return all(
        _string(value.get(field)).strip() == expected
        for field, expected in profile.items()
    )


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Convert and bound one integer setting."""

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
    """Return a trimmed string or a default."""

    candidate = _string(value).strip()
    return candidate or default


def _string(value: object) -> str:
    """Convert optional scalar content to text."""

    return "" if value is None else str(value)
