"""Define normalized measurement metrics used by SolarInspector."""

from __future__ import annotations

from enum import Enum


class Metric(str, Enum):
    """Describe the semantic meaning of a normalized measurement."""

    GRID_POWER = "grid_power"
    GRID_IMPORT_POWER = "grid_import_power"
    GRID_EXPORT_POWER = "grid_export_power"
    GRID_IMPORT_TOTAL = "grid_import_total"
    GRID_EXPORT_TOTAL = "grid_export_total"

    HOUSE_POWER = "house_power"

    PHASE_POWER_L1 = "phase_power_l1"
    PHASE_POWER_L2 = "phase_power_l2"
    PHASE_POWER_L3 = "phase_power_l3"

    PHASE_VOLTAGE_L1 = "phase_voltage_l1"
    PHASE_VOLTAGE_L2 = "phase_voltage_l2"
    PHASE_VOLTAGE_L3 = "phase_voltage_l3"

    PHASE_CURRENT_L1 = "phase_current_l1"
    PHASE_CURRENT_L2 = "phase_current_l2"
    PHASE_CURRENT_L3 = "phase_current_l3"

    PHASE_POWER_FACTOR_L1 = "phase_power_factor_l1"
    PHASE_POWER_FACTOR_L2 = "phase_power_factor_l2"
    PHASE_POWER_FACTOR_L3 = "phase_power_factor_l3"

    PLANT_AC_POWER = "plant_ac_power"
    PLANT_AC_ENERGY_TOTAL = "plant_ac_energy_total"
    PLANT_AC_RETURNED_ENERGY_TOTAL = "plant_ac_returned_energy_total"
    PLANT_VOLTAGE = "plant_voltage"
    PLANT_CURRENT = "plant_current"
    PLANT_POWER_FACTOR = "plant_power_factor"

    PV_POWER = "pv_power"
    PV_ENERGY_TODAY = "pv_energy_today"
    PV_ENERGY_TOTAL = "pv_energy_total"

    PV_INPUT_POWER_1 = "pv_input_power_1"
    PV_INPUT_POWER_2 = "pv_input_power_2"
    PV_INPUT_POWER_3 = "pv_input_power_3"
    PV_INPUT_POWER_4 = "pv_input_power_4"

    PV_INPUT_VOLTAGE_1 = "pv_input_voltage_1"
    PV_INPUT_VOLTAGE_2 = "pv_input_voltage_2"
    PV_INPUT_VOLTAGE_3 = "pv_input_voltage_3"
    PV_INPUT_VOLTAGE_4 = "pv_input_voltage_4"

    PV_INPUT_CURRENT_1 = "pv_input_current_1"
    PV_INPUT_CURRENT_2 = "pv_input_current_2"
    PV_INPUT_CURRENT_3 = "pv_input_current_3"
    PV_INPUT_CURRENT_4 = "pv_input_current_4"

    BATTERY_POWER = "battery_power"
    BATTERY_CHARGE_POWER = "battery_charge_power"
    BATTERY_DISCHARGE_POWER = "battery_discharge_power"
    BATTERY_CHARGE_TOTAL = "battery_charge_total"
    BATTERY_DISCHARGE_TOTAL = "battery_discharge_total"
    BATTERY_SOC = "battery_soc"

    SYSTEM_LOAD_POWER = "system_load_power"
    FREQUENCY = "frequency"
    POWER_FACTOR = "power_factor"
    DEVICE_TEMPERATURE = "device_temperature"
