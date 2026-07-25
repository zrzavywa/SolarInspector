"""Define reusable, explicit device validation profile factories."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any

from solarinspector_core.models.metrics import Metric
from solarinspector_core.validation.config import normalize_range_config

_PHASE_POWER_METRICS = (
    Metric.PHASE_POWER_L1,
    Metric.PHASE_POWER_L2,
    Metric.PHASE_POWER_L3,
)


def _positive_finite(value: object, field_name: str) -> float:
    """Normalize one strictly positive finite profile parameter."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized


def _non_negative_finite(value: object, field_name: str) -> float:
    """Normalize one non-negative finite profile parameter."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


@dataclass(frozen=True, slots=True)
class RangeLimits:
    """Store warning and rejection limits for one profile metric."""

    warning_min: float | None = None
    warning_max: float | None = None
    reject_min: float | None = None
    reject_max: float | None = None

    def __post_init__(self) -> None:
        """Apply the same invariants as the public configuration loader."""

        normalized = normalize_range_config(
            {
                "warning_min": self.warning_min,
                "warning_max": self.warning_max,
                "reject_min": self.reject_min,
                "reject_max": self.reject_max,
            }
        )
        for field in (
            "warning_min",
            "warning_max",
            "reject_min",
            "reject_max",
        ):
            object.__setattr__(self, field, normalized[field])

    def as_config(self) -> dict[str, float | None]:
        """Return a JSON-compatible range configuration."""

        return {
            "warning_min": self.warning_min,
            "warning_max": self.warning_max,
            "reject_min": self.reject_min,
            "reject_max": self.reject_max,
        }


@dataclass(frozen=True, slots=True)
class PhaseConsistencyLimits:
    """Configure phase completeness and device-total comparison."""

    warning_absolute_w: float = 20.0
    warning_relative: float = 0.03
    reject_absolute_w: float = 100.0
    reject_relative: float = 0.10
    maximum_phase_skew_seconds: float = 2.0

    def __post_init__(self) -> None:
        """Require non-negative, ordered phase tolerances."""

        warning_absolute = _non_negative_finite(
            self.warning_absolute_w,
            "warning_absolute_w",
        )
        warning_relative = _non_negative_finite(
            self.warning_relative,
            "warning_relative",
        )
        reject_absolute = _non_negative_finite(
            self.reject_absolute_w,
            "reject_absolute_w",
        )
        reject_relative = _non_negative_finite(
            self.reject_relative,
            "reject_relative",
        )
        skew = _non_negative_finite(
            self.maximum_phase_skew_seconds,
            "maximum_phase_skew_seconds",
        )
        if warning_absolute > reject_absolute:
            raise ValueError("warning_absolute_w must not exceed reject_absolute_w")
        if warning_relative > reject_relative:
            raise ValueError("warning_relative must not exceed reject_relative")
        object.__setattr__(self, "warning_absolute_w", warning_absolute)
        object.__setattr__(self, "warning_relative", warning_relative)
        object.__setattr__(self, "reject_absolute_w", reject_absolute)
        object.__setattr__(self, "reject_relative", reject_relative)
        object.__setattr__(self, "maximum_phase_skew_seconds", skew)

    def as_config(self) -> dict[str, float]:
        """Return a JSON-compatible phase rule configuration."""

        return {
            "warning_absolute_w": self.warning_absolute_w,
            "warning_relative": self.warning_relative,
            "reject_absolute_w": self.reject_absolute_w,
            "reject_relative": self.reject_relative,
            "maximum_phase_skew_seconds": self.maximum_phase_skew_seconds,
        }


@dataclass(frozen=True, slots=True)
class DeviceValidationProfile:
    """Describe one reusable set of device-specific validation limits."""

    name: str
    required_metrics: tuple[Metric, ...]
    ranges: tuple[tuple[Metric, RangeLimits], ...]
    known_error_values: tuple[tuple[Metric, tuple[float, ...]], ...] = ()
    phase_consistency: PhaseConsistencyLimits | None = None

    def __post_init__(self) -> None:
        """Require stable names and unique metric definitions."""

        name = self.name.strip()
        if not name:
            raise ValueError("profile name must not be empty")
        object.__setattr__(self, "name", name)

        required_unique = tuple(dict.fromkeys(self.required_metrics))
        object.__setattr__(self, "required_metrics", required_unique)

        range_metrics = [metric for metric, _limits in self.ranges]
        if len(range_metrics) != len(set(range_metrics)):
            raise ValueError("profile ranges must not repeat a metric")

        error_metrics = [metric for metric, _values in self.known_error_values]
        if len(error_metrics) != len(set(error_metrics)):
            raise ValueError("known error values must not repeat a metric")

        normalized_errors: list[tuple[Metric, tuple[float, ...]]] = []
        for metric, values in self.known_error_values:
            unique_values: list[float] = []
            for value in values:
                normalized = _non_negative_finite(
                    value,
                    f"known_error_values.{metric.value}",
                )
                if normalized not in unique_values:
                    unique_values.append(normalized)
            normalized_errors.append((metric, tuple(unique_values)))
        object.__setattr__(
            self,
            "known_error_values",
            tuple(normalized_errors),
        )

    def range_for(self, metric: Metric) -> RangeLimits | None:
        """Return configured limits for one metric."""

        return dict(self.ranges).get(metric)

    def error_values_for(self, metric: Metric) -> tuple[float, ...]:
        """Return configured device sentinel values for one metric."""

        return dict(self.known_error_values).get(metric, ())

    def as_config(self) -> dict[str, Any]:
        """Return a profile accepted by ``normalize_validation_profile``."""

        config: dict[str, Any] = {
            "required_metrics": [metric.value for metric in self.required_metrics],
            "ranges": {
                metric.value: limits.as_config() for metric, limits in self.ranges
            },
            "known_error_values": {
                metric.value: list(values) for metric, values in self.known_error_values
            },
        }
        if self.phase_consistency is not None:
            config["phase_consistency"] = self.phase_consistency.as_config()
        return config


def solarkon_800w_profile(
    *,
    nominal_ac_power_w: float = 800.0,
    reject_factor: float = 1.20,
    standby_import_limit_w: float = 100.0,
) -> DeviceValidationProfile:
    """Return the explicit Solakon 800 W operating profile.

    The 800 W nominal value and 20 percent rejection margin are project
    defaults, not legal, normative, or calibration limits.
    """

    nominal = _positive_finite(
        nominal_ac_power_w,
        "nominal_ac_power_w",
    )
    factor = _positive_finite(reject_factor, "reject_factor")
    if factor < 1.0:
        raise ValueError("reject_factor must be at least 1.0")
    standby = _non_negative_finite(
        standby_import_limit_w,
        "standby_import_limit_w",
    )

    return DeviceValidationProfile(
        name="solarkon_800w",
        required_metrics=(Metric.PLANT_AC_POWER,),
        ranges=(
            (
                Metric.PLANT_AC_POWER,
                RangeLimits(
                    warning_min=0.0,
                    warning_max=nominal,
                    reject_min=-standby,
                    reject_max=nominal * factor,
                ),
            ),
            (
                Metric.BATTERY_SOC,
                RangeLimits(
                    reject_min=0.0,
                    reject_max=100.0,
                ),
            ),
        ),
    )


def shelly_plant_profile(
    *,
    nominal_ac_power_w: float = 800.0,
    reject_factor: float = 1.20,
    standby_import_limit_w: float = 100.0,
) -> DeviceValidationProfile:
    """Return a Shelly PM profile bounded by the connected installation."""

    solarkon_profile = solarkon_800w_profile(
        nominal_ac_power_w=nominal_ac_power_w,
        reject_factor=reject_factor,
        standby_import_limit_w=standby_import_limit_w,
    )
    plant_limits = solarkon_profile.range_for(Metric.PLANT_AC_POWER)
    assert plant_limits is not None
    return DeviceValidationProfile(
        name="shelly_pm_plant_meter",
        required_metrics=(Metric.PLANT_AC_POWER,),
        ranges=((Metric.PLANT_AC_POWER, plant_limits),),
    )


def shelly_house_profile(
    *,
    nominal_voltage_v: float,
    main_fuse_a: float,
    rejection_factor: float = 1.20,
    phase_consistency: PhaseConsistencyLimits | None = None,
    name: str = "shelly_3em_house_meter",
) -> DeviceValidationProfile:
    """Build a three-phase Shelly profile from explicit installation data.

    No default main-fuse value is guessed. The returned limits are simple
    apparent single-phase planning limits (V × A), not a normative statement
    about the electrical installation.
    """

    voltage = _positive_finite(
        nominal_voltage_v,
        "nominal_voltage_v",
    )
    current = _positive_finite(main_fuse_a, "main_fuse_a")
    factor = _positive_finite(
        rejection_factor,
        "rejection_factor",
    )
    if factor < 1.0:
        raise ValueError("rejection_factor must be at least 1.0")

    phase_limit_w = voltage * current
    total_limit_w = phase_limit_w * 3.0

    symmetric_phase_limits = RangeLimits(
        warning_min=-phase_limit_w,
        warning_max=phase_limit_w,
        reject_min=-phase_limit_w * factor,
        reject_max=phase_limit_w * factor,
    )
    symmetric_total_limits = RangeLimits(
        warning_min=-total_limit_w,
        warning_max=total_limit_w,
        reject_min=-total_limit_w * factor,
        reject_max=total_limit_w * factor,
    )

    return DeviceValidationProfile(
        name=name,
        required_metrics=_PHASE_POWER_METRICS,
        ranges=(
            (Metric.GRID_POWER, symmetric_total_limits),
            (Metric.HOUSE_POWER, symmetric_total_limits),
            *((metric, symmetric_phase_limits) for metric in _PHASE_POWER_METRICS),
        ),
        phase_consistency=(
            phase_consistency
            if phase_consistency is not None
            else PhaseConsistencyLimits()
        ),
    )


def shelly_pro_3em_house_profile(
    *,
    nominal_voltage_v: float,
    main_fuse_a: float,
    rejection_factor: float = 1.20,
    phase_consistency: PhaseConsistencyLimits | None = None,
) -> DeviceValidationProfile:
    """Build the equivalent installation profile for Shelly Pro 3EM."""

    return shelly_house_profile(
        nominal_voltage_v=nominal_voltage_v,
        main_fuse_a=main_fuse_a,
        rejection_factor=rejection_factor,
        phase_consistency=phase_consistency,
        name="shelly_pro_3em_house_meter",
    )
