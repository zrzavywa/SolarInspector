"""Normalize additive source-selection and energy-balance configuration."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from numbers import Real
from typing import Any, Final

from solarinspector_core.models.metrics import Metric


class EnergyBalanceConfigurationError(ValueError):
    """Report contradictory or unsafe energy-balance settings."""


DEFAULT_SOURCE_PRIORITIES: Final[dict[str, list[str]]] = {
    Metric.GRID_POWER.value: [
        "grid_meter_primary",
        "house_meter",
    ],
    Metric.PLANT_AC_POWER.value: [
        "solakon_meter",
        "solakon_one",
    ],
    Metric.PV_POWER.value: ["solakon_one"],
    Metric.BATTERY_POWER.value: ["solakon_one"],
    Metric.BATTERY_CHARGE_POWER.value: ["solakon_one"],
    Metric.BATTERY_DISCHARGE_POWER.value: ["solakon_one"],
    Metric.BATTERY_SOC.value: ["solakon_one"],
}

DEFAULT_ENERGY_BALANCE_CONFIG: Final[dict[str, Any]] = {
    "enabled": True,
    "maximum_measurement_age_seconds": 30.0,
    "maximum_source_skew_seconds": 10.0,
    "allow_suspect_measurements": True,
    "allow_grid_fallback": True,
    "allow_plant_fallback": True,
    "negative_house_power_tolerance_w": 30.0,
    "short_window_average_seconds": 0.0,
    "persist_source_decisions": True,
    "source_priorities": deepcopy(DEFAULT_SOURCE_PRIORITIES),
}

_SELECTABLE_METRICS: Final[frozenset[Metric]] = frozenset(
    {
        Metric.GRID_POWER,
        Metric.PLANT_AC_POWER,
        Metric.PV_POWER,
        Metric.BATTERY_POWER,
        Metric.BATTERY_CHARGE_POWER,
        Metric.BATTERY_DISCHARGE_POWER,
        Metric.BATTERY_SOC,
    }
)


def normalize_energy_balance_config(value: object) -> dict[str, Any]:
    """Return backward-compatible, internally consistent balance settings."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    normalized["enabled"] = _boolean(
        raw.get("enabled"),
        default=bool(DEFAULT_ENERGY_BALANCE_CONFIG["enabled"]),
    )
    maximum_age = _positive_float(
        raw.get("maximum_measurement_age_seconds"),
        default=float(DEFAULT_ENERGY_BALANCE_CONFIG["maximum_measurement_age_seconds"]),
        field_name="maximum_measurement_age_seconds",
    )
    maximum_skew = _positive_float(
        raw.get("maximum_source_skew_seconds"),
        default=float(DEFAULT_ENERGY_BALANCE_CONFIG["maximum_source_skew_seconds"]),
        field_name="maximum_source_skew_seconds",
    )
    if maximum_skew > maximum_age:
        raise EnergyBalanceConfigurationError(
            "maximum_source_skew_seconds must not exceed "
            "maximum_measurement_age_seconds"
        )
    normalized["maximum_measurement_age_seconds"] = maximum_age
    normalized["maximum_source_skew_seconds"] = maximum_skew
    normalized["allow_suspect_measurements"] = _boolean(
        raw.get("allow_suspect_measurements"),
        default=bool(DEFAULT_ENERGY_BALANCE_CONFIG["allow_suspect_measurements"]),
    )
    normalized["allow_grid_fallback"] = _boolean(
        raw.get("allow_grid_fallback"),
        default=bool(DEFAULT_ENERGY_BALANCE_CONFIG["allow_grid_fallback"]),
    )
    normalized["allow_plant_fallback"] = _boolean(
        raw.get("allow_plant_fallback"),
        default=bool(DEFAULT_ENERGY_BALANCE_CONFIG["allow_plant_fallback"]),
    )
    normalized["negative_house_power_tolerance_w"] = _non_negative_float(
        raw.get("negative_house_power_tolerance_w"),
        default=float(
            DEFAULT_ENERGY_BALANCE_CONFIG["negative_house_power_tolerance_w"]
        ),
        field_name="negative_house_power_tolerance_w",
    )
    normalized["short_window_average_seconds"] = _non_negative_float(
        raw.get("short_window_average_seconds"),
        default=float(DEFAULT_ENERGY_BALANCE_CONFIG["short_window_average_seconds"]),
        field_name="short_window_average_seconds",
    )
    normalized["persist_source_decisions"] = _boolean(
        raw.get("persist_source_decisions"),
        default=bool(DEFAULT_ENERGY_BALANCE_CONFIG["persist_source_decisions"]),
    )
    normalized["source_priorities"] = _normalize_source_priorities(
        raw.get("source_priorities")
    )
    return normalized


def _normalize_source_priorities(value: object) -> dict[str, list[str]]:
    """Normalize ordered, duplicate-free source IDs for supported metrics."""

    if value is None:
        return deepcopy(DEFAULT_SOURCE_PRIORITIES)
    if not isinstance(value, Mapping):
        raise EnergyBalanceConfigurationError(
            "source_priorities must be configured as an object"
        )

    priorities = deepcopy(DEFAULT_SOURCE_PRIORITIES)
    for raw_metric, raw_sources in value.items():
        metric = _selectable_metric(raw_metric)
        if isinstance(raw_sources, (str, bytes, bytearray)) or not isinstance(
            raw_sources,
            Sequence,
        ):
            raise EnergyBalanceConfigurationError(
                f"source priority for {metric.value} must be configured as a list"
            )
        source_ids: list[str] = []
        for raw_source_id in raw_sources:
            source_id = str(raw_source_id).strip()
            if not source_id:
                raise EnergyBalanceConfigurationError(
                    "source priority IDs must not be empty"
                )
            if source_id in source_ids:
                raise EnergyBalanceConfigurationError(
                    f"source priority for {metric.value} contains duplicate "
                    f"{source_id!r}"
                )
            source_ids.append(source_id)
        priorities[metric.value] = source_ids
    return priorities


def _selectable_metric(value: object) -> Metric:
    """Return one metric supported by the Phase-09 source selector."""

    candidate = str(value).strip()
    try:
        metric = Metric(candidate)
    except ValueError as exc:
        raise EnergyBalanceConfigurationError(
            f"unknown source-priority metric {candidate!r}"
        ) from exc
    if metric not in _SELECTABLE_METRICS:
        raise EnergyBalanceConfigurationError(
            f"metric {metric.value!r} is not selectable"
        )
    return metric


def _boolean(value: object, *, default: bool) -> bool:
    """Normalize explicit boolean representations."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"true", "yes", "on", "1"}:
            return True
        if candidate in {"false", "no", "off", "0"}:
            return False
    return default


def _positive_float(
    value: object,
    *,
    default: float,
    field_name: str,
) -> float:
    """Normalize a finite value greater than zero."""

    normalized = _finite_float(value, default=default, field_name=field_name)
    if normalized <= 0:
        raise EnergyBalanceConfigurationError(f"{field_name} must be greater than zero")
    return normalized


def _non_negative_float(
    value: object,
    *,
    default: float,
    field_name: str,
) -> float:
    """Normalize a finite value greater than or equal to zero."""

    normalized = _finite_float(value, default=default, field_name=field_name)
    if normalized < 0:
        raise EnergyBalanceConfigurationError(f"{field_name} must not be negative")
    return normalized


def _finite_float(
    value: object,
    *,
    default: float,
    field_name: str,
) -> float:
    """Normalize a finite real value or numeric string."""

    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (Real, str)):
        raise EnergyBalanceConfigurationError(f"{field_name} must be a finite number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise EnergyBalanceConfigurationError(
            f"{field_name} must be a finite number"
        ) from exc
    if not math.isfinite(normalized):
        raise EnergyBalanceConfigurationError(f"{field_name} must be finite")
    return normalized
