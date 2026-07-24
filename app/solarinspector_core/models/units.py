"""Define canonical physical units for normalized measurements."""

from __future__ import annotations

from enum import Enum
from typing import Final

from solarinspector_core.models.metrics import Metric


class Unit(str, Enum):
    """Describe a canonical physical unit used by SolarInspector."""

    WATT = "W"
    WATT_HOUR = "Wh"
    VOLT = "V"
    AMPERE = "A"
    PERCENT = "%"
    HERTZ = "Hz"
    POWER_FACTOR = "ratio"
    CELSIUS = "°C"


METRIC_UNITS: Final[dict[Metric, Unit]] = {
    Metric.GRID_POWER: Unit.WATT,
    Metric.GRID_IMPORT_POWER: Unit.WATT,
    Metric.GRID_EXPORT_POWER: Unit.WATT,
    Metric.GRID_IMPORT_TOTAL: Unit.WATT_HOUR,
    Metric.GRID_EXPORT_TOTAL: Unit.WATT_HOUR,
    Metric.GRID_VOLTAGE: Unit.VOLT,
    Metric.GRID_CURRENT: Unit.AMPERE,
    Metric.HOUSE_POWER: Unit.WATT,
    Metric.PHASE_POWER_L1: Unit.WATT,
    Metric.PHASE_POWER_L2: Unit.WATT,
    Metric.PHASE_POWER_L3: Unit.WATT,
    Metric.PHASE_VOLTAGE_L1: Unit.VOLT,
    Metric.PHASE_VOLTAGE_L2: Unit.VOLT,
    Metric.PHASE_VOLTAGE_L3: Unit.VOLT,
    Metric.PHASE_CURRENT_L1: Unit.AMPERE,
    Metric.PHASE_CURRENT_L2: Unit.AMPERE,
    Metric.PHASE_CURRENT_L3: Unit.AMPERE,
    Metric.PHASE_POWER_FACTOR_L1: Unit.POWER_FACTOR,
    Metric.PHASE_POWER_FACTOR_L2: Unit.POWER_FACTOR,
    Metric.PHASE_POWER_FACTOR_L3: Unit.POWER_FACTOR,
    Metric.PLANT_AC_POWER: Unit.WATT,
    Metric.PLANT_AC_ENERGY_TOTAL: Unit.WATT_HOUR,
    Metric.PLANT_AC_RETURNED_ENERGY_TOTAL: Unit.WATT_HOUR,
    Metric.PLANT_VOLTAGE: Unit.VOLT,
    Metric.PLANT_CURRENT: Unit.AMPERE,
    Metric.PLANT_POWER_FACTOR: Unit.POWER_FACTOR,
    Metric.PV_POWER: Unit.WATT,
    Metric.PV_ENERGY_TODAY: Unit.WATT_HOUR,
    Metric.PV_ENERGY_TOTAL: Unit.WATT_HOUR,
    Metric.PV_INPUT_POWER_1: Unit.WATT,
    Metric.PV_INPUT_POWER_2: Unit.WATT,
    Metric.PV_INPUT_POWER_3: Unit.WATT,
    Metric.PV_INPUT_POWER_4: Unit.WATT,
    Metric.PV_INPUT_VOLTAGE_1: Unit.VOLT,
    Metric.PV_INPUT_VOLTAGE_2: Unit.VOLT,
    Metric.PV_INPUT_VOLTAGE_3: Unit.VOLT,
    Metric.PV_INPUT_VOLTAGE_4: Unit.VOLT,
    Metric.PV_INPUT_CURRENT_1: Unit.AMPERE,
    Metric.PV_INPUT_CURRENT_2: Unit.AMPERE,
    Metric.PV_INPUT_CURRENT_3: Unit.AMPERE,
    Metric.PV_INPUT_CURRENT_4: Unit.AMPERE,
    Metric.BATTERY_POWER: Unit.WATT,
    Metric.BATTERY_CHARGE_POWER: Unit.WATT,
    Metric.BATTERY_DISCHARGE_POWER: Unit.WATT,
    Metric.BATTERY_CHARGE_TOTAL: Unit.WATT_HOUR,
    Metric.BATTERY_DISCHARGE_TOTAL: Unit.WATT_HOUR,
    Metric.BATTERY_SOC: Unit.PERCENT,
    Metric.SYSTEM_LOAD_POWER: Unit.WATT,
    Metric.FREQUENCY: Unit.HERTZ,
    Metric.POWER_FACTOR: Unit.POWER_FACTOR,
    Metric.DEVICE_TEMPERATURE: Unit.CELSIUS,
}


def unit_for_metric(metric: Metric) -> Unit:
    """Return the canonical unit for a normalized metric."""

    return METRIC_UNITS[metric]
