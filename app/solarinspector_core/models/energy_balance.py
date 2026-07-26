"""Define immutable inputs and results for the current energy balance."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from numbers import Real

from solarinspector_core.models.source_selection import (
    SourceSelectionFinding,
    SourceSelectionResult,
)


class EnergyBalanceQuality(str, Enum):
    """Describe the quality and completeness of one calculated balance."""

    VALIDATED = "validated"
    CALCULATED = "calculated"
    SUSPECT = "suspect"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class EnergyBalanceInput:
    """Contain selected measurements for one current balance calculation."""

    grid_power: SourceSelectionResult
    plant_ac_power: SourceSelectionResult
    pv_power: SourceSelectionResult
    battery_charge_power: SourceSelectionResult
    battery_discharge_power: SourceSelectionResult
    battery_soc: SourceSelectionResult
    calculation_timestamp: datetime

    def __post_init__(self) -> None:
        """Require one timezone-aware calculation clock."""

        _require_timezone_aware(
            self.calculation_timestamp,
            "calculation_timestamp",
        )

    @property
    def source_metadata(self) -> tuple[SourceSelectionResult, ...]:
        """Return every source decision in stable API order."""

        return (
            self.grid_power,
            self.plant_ac_power,
            self.pv_power,
            self.battery_charge_power,
            self.battery_discharge_power,
            self.battery_soc,
        )


@dataclass(frozen=True, slots=True)
class EnergyBalanceResult:
    """Represent current power flows without inventing missing values."""

    house_power_w: float | None
    grid_power_w: float | None
    grid_import_power_w: float | None
    grid_export_power_w: float | None
    plant_ac_power_w: float | None
    pv_power_w: float | None
    battery_charge_power_w: float | None
    battery_discharge_power_w: float | None
    battery_soc_percent: float | None
    self_consumed_power_w: float | None
    self_consumption_rate_percent: float | None
    autonomy_rate_percent: float | None
    residual_power_w: float | None
    quality: EnergyBalanceQuality
    calculated_at: datetime
    source_metadata: tuple[SourceSelectionResult, ...]
    findings: tuple[SourceSelectionFinding, ...] = ()

    def __post_init__(self) -> None:
        """Normalize finite optional numbers and validate result invariants."""

        _require_timezone_aware(self.calculated_at, "calculated_at")
        for field_name in (
            "house_power_w",
            "grid_power_w",
            "grid_import_power_w",
            "grid_export_power_w",
            "plant_ac_power_w",
            "pv_power_w",
            "battery_charge_power_w",
            "battery_discharge_power_w",
            "battery_soc_percent",
            "self_consumed_power_w",
            "self_consumption_rate_percent",
            "autonomy_rate_percent",
            "residual_power_w",
        ):
            value = _finite_optional(
                getattr(self, field_name),
                field_name,
            )
            object.__setattr__(self, field_name, value)

        for field_name in (
            "grid_import_power_w",
            "grid_export_power_w",
            "battery_charge_power_w",
            "battery_discharge_power_w",
            "self_consumed_power_w",
        ):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")
        for field_name in (
            "battery_soc_percent",
            "self_consumption_rate_percent",
            "autonomy_rate_percent",
        ):
            value = getattr(self, field_name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")
        if (
            self.grid_import_power_w is not None
            and self.grid_export_power_w is not None
            and self.grid_import_power_w > 0
            and self.grid_export_power_w > 0
        ):
            raise ValueError("grid import and export cannot both be positive")


def _finite_optional(value: object, field_name: str) -> float | None:
    """Return a finite optional float without accepting booleans."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number or None")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
