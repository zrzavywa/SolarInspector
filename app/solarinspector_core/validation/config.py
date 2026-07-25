"""Normalize the additive SolarInspector validation configuration."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from numbers import Real
from typing import Any, Final

from solarinspector_core.models.metrics import Metric


class ValidationConfigurationError(ValueError):
    """Report contradictory or unsafe validation settings."""


DEFAULT_VALIDATION_CONFIG: Final[dict[str, Any]] = {
    "enabled": False,
    "profiles": {},
    "sources": {},
}

DEFAULT_TIME_CONFIG: Final[dict[str, float]] = {
    "fresh_seconds": 15.0,
    "stale_seconds": 60.0,
    "maximum_future_seconds": 5.0,
}

_RANGE_FIELDS: Final[tuple[str, ...]] = (
    "warning_min",
    "warning_max",
    "reject_min",
    "reject_max",
)

_DELTA_FIELDS: Final[tuple[str, ...]] = (
    "warning_absolute",
    "reject_absolute",
    "warning_relative_percent",
    "reject_relative_percent",
    "warning_per_second",
    "reject_per_second",
)


def normalize_validation_config(value: object) -> dict[str, Any]:
    """Return one backward-compatible and internally consistent configuration."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    normalized["enabled"] = _boolean(
        raw.get("enabled"),
        default=bool(DEFAULT_VALIDATION_CONFIG["enabled"]),
    )
    normalized["profiles"] = _normalize_named_mapping(
        raw.get("profiles"),
        item_name="profile",
        normalizer=normalize_validation_profile,
    )
    normalized["sources"] = _normalize_named_mapping(
        raw.get("sources"),
        item_name="source",
        normalizer=normalize_validation_source,
    )
    _validate_source_profile_references(
        normalized["profiles"],
        normalized["sources"],
    )
    return normalized


def normalize_validation_profile(value: object) -> dict[str, Any]:
    """Normalize one reusable set of rule limits."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    normalized["required_metrics"] = _normalize_metric_sequence(
        raw.get("required_metrics")
    )
    normalized["time"] = normalize_time_config(raw.get("time"))
    normalized["ranges"] = _normalize_metric_mapping(
        raw.get("ranges"),
        normalizer=normalize_range_config,
    )
    normalized["deltas"] = _normalize_metric_mapping(
        raw.get("deltas"),
        normalizer=normalize_delta_config,
    )
    normalized["known_error_values"] = _normalize_metric_mapping(
        raw.get("known_error_values"),
        normalizer=_normalize_known_error_values,
    )
    return normalized


def normalize_validation_source(value: object) -> dict[str, Any]:
    """Normalize one source-to-profile assignment."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    normalized["enabled"] = _boolean(raw.get("enabled"), default=True)
    normalized["profile"] = _string(raw.get("profile")).strip()
    normalized["measurement_position_comparable"] = _boolean(
        raw.get("measurement_position_comparable"),
        default=False,
    )
    return normalized


def normalize_time_config(value: object) -> dict[str, Any]:
    """Normalize freshness and clock-skew limits."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    fresh_seconds = _non_negative_float(
        raw.get("fresh_seconds"),
        default=DEFAULT_TIME_CONFIG["fresh_seconds"],
        field_name="fresh_seconds",
    )
    stale_seconds = _non_negative_float(
        raw.get("stale_seconds"),
        default=DEFAULT_TIME_CONFIG["stale_seconds"],
        field_name="stale_seconds",
    )
    maximum_future_seconds = _non_negative_float(
        raw.get("maximum_future_seconds"),
        default=DEFAULT_TIME_CONFIG["maximum_future_seconds"],
        field_name="maximum_future_seconds",
    )
    if fresh_seconds > stale_seconds:
        raise ValidationConfigurationError(
            "fresh_seconds must not exceed stale_seconds"
        )
    normalized["fresh_seconds"] = fresh_seconds
    normalized["stale_seconds"] = stale_seconds
    normalized["maximum_future_seconds"] = maximum_future_seconds
    return normalized


def normalize_range_config(value: object) -> dict[str, Any]:
    """Normalize warning and rejection bounds for one metric."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    limits = {
        field: _optional_finite_float(
            raw.get(field),
            field_name=field,
        )
        for field in _RANGE_FIELDS
    }
    normalized.update(limits)

    _require_order(
        limits["reject_min"],
        limits["reject_max"],
        "reject_min",
        "reject_max",
    )
    _require_order(
        limits["warning_min"],
        limits["warning_max"],
        "warning_min",
        "warning_max",
    )
    if (
        limits["reject_min"] is not None
        and limits["warning_min"] is not None
        and limits["warning_min"] < limits["reject_min"]
    ):
        raise ValidationConfigurationError("warning_min must not be below reject_min")
    if (
        limits["reject_max"] is not None
        and limits["warning_max"] is not None
        and limits["warning_max"] > limits["reject_max"]
    ):
        raise ValidationConfigurationError("warning_max must not exceed reject_max")
    return normalized


def normalize_delta_config(value: object) -> dict[str, Any]:
    """Normalize absolute, relative, and rate-of-change limits."""

    raw = dict(value) if isinstance(value, Mapping) else {}
    normalized = deepcopy(raw)
    limits = {
        field: _optional_non_negative_float(
            raw.get(field),
            field_name=field,
        )
        for field in _DELTA_FIELDS
    }
    normalized.update(limits)
    normalized["minimum_reference"] = _non_negative_float(
        raw.get("minimum_reference"),
        default=0.0,
        field_name="minimum_reference",
    )

    _require_optional_warning_not_above_reject(
        limits["warning_absolute"],
        limits["reject_absolute"],
        "absolute",
    )
    _require_optional_warning_not_above_reject(
        limits["warning_relative_percent"],
        limits["reject_relative_percent"],
        "relative_percent",
    )
    _require_optional_warning_not_above_reject(
        limits["warning_per_second"],
        limits["reject_per_second"],
        "per_second",
    )
    return normalized


def _normalize_named_mapping(
    value: object,
    *,
    item_name: str,
    normalizer: Callable[[object], dict[str, Any]],
) -> dict[str, Any]:
    """Normalize a mapping addressed by stable non-empty names."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationConfigurationError(
            f"{item_name}s must be configured as an object"
        )

    normalized: dict[str, Any] = {}
    for raw_name, raw_config in value.items():
        name = str(raw_name).strip()
        if not name:
            raise ValidationConfigurationError(f"{item_name} names must not be empty")
        normalized[name] = normalizer(raw_config)
    return normalized


def _normalize_metric_mapping(
    value: object,
    *,
    normalizer: Callable[[object], object],
) -> dict[str, Any]:
    """Normalize a mapping keyed by known metric values."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationConfigurationError(
            "metric settings must be configured as an object"
        )

    normalized: dict[str, Any] = {}
    for raw_metric, raw_config in value.items():
        metric = _metric(raw_metric)
        normalized[metric.value] = normalizer(raw_config)
    return normalized


def _normalize_metric_sequence(value: object) -> list[str]:
    """Normalize a sequence of unique known metric values."""

    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value,
        Sequence,
    ):
        raise ValidationConfigurationError(
            "required_metrics must be configured as a list"
        )

    normalized: list[str] = []
    for raw_metric in value:
        metric_value = _metric(raw_metric).value
        if metric_value not in normalized:
            normalized.append(metric_value)
    return normalized


def _normalize_known_error_values(value: object) -> list[float]:
    """Normalize finite numeric sentinel values for one source metric."""

    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value,
        Sequence,
    ):
        raise ValidationConfigurationError(
            "known_error_values must be configured as a list"
        )

    normalized: list[float] = []
    for raw_value in value:
        sentinel = _finite_float(
            raw_value,
            field_name="known_error_value",
        )
        if sentinel not in normalized:
            normalized.append(sentinel)
    return normalized


def _validate_source_profile_references(
    profiles: object,
    sources: object,
) -> None:
    """Reject enabled sources that refer to a missing profile."""

    if not isinstance(profiles, Mapping) or not isinstance(sources, Mapping):
        raise TypeError("normalized validation mappings are required")

    for source_name, source_value in sources.items():
        if not isinstance(source_value, Mapping):
            continue
        profile_name = _string(source_value.get("profile")).strip()
        enabled = _boolean(source_value.get("enabled"), default=True)
        if enabled and profile_name and profile_name not in profiles:
            raise ValidationConfigurationError(
                f"source {source_name!r} refers to unknown profile {profile_name!r}"
            )


def _metric(value: object) -> Metric:
    """Return one known metric or raise a configuration error."""

    if isinstance(value, Metric):
        return value
    candidate = _string(value).strip()
    try:
        return Metric(candidate)
    except ValueError as exc:
        raise ValidationConfigurationError(
            f"unknown validation metric {candidate!r}"
        ) from exc


def _boolean(value: object, *, default: bool) -> bool:
    """Normalize explicit boolean representations without truthy-string traps."""

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


def _optional_non_negative_float(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize an optional finite value that must not be negative."""

    if value is None or value == "":
        return None
    normalized = _finite_float(value, field_name=field_name)
    if normalized < 0:
        raise ValidationConfigurationError(f"{field_name} must not be negative")
    return normalized


def _non_negative_float(
    value: object,
    *,
    default: float,
    field_name: str,
) -> float:
    """Normalize a finite non-negative value with a missing-value default."""

    if value is None or value == "":
        return default
    normalized = _finite_float(value, field_name=field_name)
    if normalized < 0:
        raise ValidationConfigurationError(f"{field_name} must not be negative")
    return normalized


def _optional_finite_float(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize an optional finite numeric limit."""

    if value is None or value == "":
        return None
    return _finite_float(value, field_name=field_name)


def _finite_float(value: object, *, field_name: str) -> float:
    """Normalize a real or numeric string and reject booleans and infinities."""

    if isinstance(value, bool):
        raise ValidationConfigurationError(f"{field_name} must be a finite number")
    if not isinstance(value, (Real, str)):
        raise ValidationConfigurationError(f"{field_name} must be a finite number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationConfigurationError(
            f"{field_name} must be a finite number"
        ) from exc
    if not math.isfinite(normalized):
        raise ValidationConfigurationError(f"{field_name} must be finite")
    return normalized


def _require_order(
    minimum: float | None,
    maximum: float | None,
    minimum_name: str,
    maximum_name: str,
) -> None:
    """Require one optional lower bound not to exceed an upper bound."""

    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValidationConfigurationError(
            f"{minimum_name} must not exceed {maximum_name}"
        )


def _require_optional_warning_not_above_reject(
    warning: float | None,
    reject: float | None,
    label: str,
) -> None:
    """Require one warning threshold not to exceed its rejection threshold."""

    if warning is not None and reject is not None and warning > reject:
        raise ValidationConfigurationError(
            f"warning_{label} must not exceed reject_{label}"
        )


def _string(value: object) -> str:
    """Convert optional scalar content to text."""

    return "" if value is None else str(value)
