"""Convert normalized snapshots to temporary SolarInspector legacy types."""

from __future__ import annotations

from solarinspector_core.adapters.solakon import SolakonOneReading
from solarinspector_core.models.device import DeviceSnapshot
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole


def meter_reading_from_snapshot(
    snapshot: DeviceSnapshot,
    role: MeasurementRole,
    *,
    source: str = "Normalized measurement snapshot",
) -> MeterReading | None:
    """Map one Shelly-style snapshot back to the existing meter structure.

    ``None`` mirrors the current collector behavior when the required power
    measurement is unavailable. Only roles already supported by the normalized
    Shelly adapter are accepted.
    """

    if role is MeasurementRole.GRID_METER:
        power = _value(snapshot, role, Metric.GRID_POWER)
        if power is None:
            return None
        return MeterReading(
            power_w=power,
            power_factor=_value(snapshot, role, Metric.POWER_FACTOR),
            frequency_hz=_value(snapshot, role, Metric.FREQUENCY),
            energy_total_wh=_value(
                snapshot,
                role,
                Metric.GRID_IMPORT_TOTAL,
            ),
            returned_energy_total_wh=_value(
                snapshot,
                role,
                Metric.GRID_EXPORT_TOTAL,
            ),
            source=source,
        )

    if role is MeasurementRole.PLANT_METER:
        power = _value(snapshot, role, Metric.PLANT_AC_POWER)
        if power is None:
            return None
        return MeterReading(
            power_w=power,
            voltage_v=_value(snapshot, role, Metric.PLANT_VOLTAGE),
            current_a=_value(snapshot, role, Metric.PLANT_CURRENT),
            power_factor=_value(
                snapshot,
                role,
                Metric.PLANT_POWER_FACTOR,
            ),
            frequency_hz=_value(snapshot, role, Metric.FREQUENCY),
            energy_total_wh=_value(
                snapshot,
                role,
                Metric.PLANT_AC_ENERGY_TOTAL,
            ),
            returned_energy_total_wh=_value(
                snapshot,
                role,
                Metric.PLANT_AC_RETURNED_ENERGY_TOTAL,
            ),
            source=source,
        )

    raise ValueError(f"Unsupported legacy meter role: {role.value}")


def solakon_reading_from_snapshot(
    snapshot: DeviceSnapshot,
    *,
    source: str = "Normalized Solakon snapshot",
) -> SolakonOneReading | None:
    """Map normalized Solakon metrics back to the current collector structure."""

    if not snapshot.measurements and not snapshot.metadata:
        return None

    metadata = dict(snapshot.metadata)
    charge_power = _value(
        snapshot,
        MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_CHARGE_POWER,
    )
    discharge_power = _value(
        snapshot,
        MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_DISCHARGE_POWER,
    )
    battery_power = _legacy_battery_power(
        charge_power=charge_power,
        discharge_power=discharge_power,
    )

    grid_power = _value(
        snapshot,
        MeasurementRole.GRID_METER,
        Metric.GRID_POWER,
    )

    return SolakonOneReading(
        model_name=metadata.get("model_name"),
        serial_number=metadata.get("serial_number"),
        status=metadata.get("operating_status", "Unbekannt"),
        total_pv_power_w=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PV_POWER,
        ),
        active_power_w=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PLANT_AC_POWER,
        ),
        battery_power_w=battery_power,
        battery_soc_pct=_value(
            snapshot,
            MeasurementRole.BATTERY_SYSTEM,
            Metric.BATTERY_SOC,
        ),
        load_power_w=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.SYSTEM_LOAD_POWER,
        ),
        meter_power_w=None if grid_power is None else -grid_power,
        internal_temperature_c=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.DEVICE_TEMPERATURE,
        ),
        grid_frequency_hz=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.FREQUENCY,
        ),
        power_factor=_value(
            snapshot,
            MeasurementRole.SOLAR_SYSTEM,
            Metric.POWER_FACTOR,
        ),
        total_pv_energy_kwh=_watt_hours_to_kilowatt_hours(
            _value(
                snapshot,
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_ENERGY_TOTAL,
            )
        ),
        daily_pv_energy_kwh=_watt_hours_to_kilowatt_hours(
            _value(
                snapshot,
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_ENERGY_TODAY,
            )
        ),
        battery_total_charge_kwh=_watt_hours_to_kilowatt_hours(
            _value(
                snapshot,
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_CHARGE_TOTAL,
            )
        ),
        battery_total_discharge_kwh=_watt_hours_to_kilowatt_hours(
            _value(
                snapshot,
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_DISCHARGE_TOTAL,
            )
        ),
        pv1_voltage_v=_solar_value(snapshot, Metric.PV_INPUT_VOLTAGE_1),
        pv1_current_a=_solar_value(snapshot, Metric.PV_INPUT_CURRENT_1),
        pv1_power_w=_solar_value(snapshot, Metric.PV_INPUT_POWER_1),
        pv2_voltage_v=_solar_value(snapshot, Metric.PV_INPUT_VOLTAGE_2),
        pv2_current_a=_solar_value(snapshot, Metric.PV_INPUT_CURRENT_2),
        pv2_power_w=_solar_value(snapshot, Metric.PV_INPUT_POWER_2),
        pv3_voltage_v=_solar_value(snapshot, Metric.PV_INPUT_VOLTAGE_3),
        pv3_current_a=_solar_value(snapshot, Metric.PV_INPUT_CURRENT_3),
        pv3_power_w=_solar_value(snapshot, Metric.PV_INPUT_POWER_3),
        pv4_voltage_v=_solar_value(snapshot, Metric.PV_INPUT_VOLTAGE_4),
        pv4_current_a=_solar_value(snapshot, Metric.PV_INPUT_CURRENT_4),
        pv4_power_w=_solar_value(snapshot, Metric.PV_INPUT_POWER_4),
        source=source,
        warnings=snapshot.error or "",
    )


def _value(
    snapshot: DeviceSnapshot,
    role: MeasurementRole,
    metric: Metric,
) -> float | None:
    """Return one role-specific metric without treating zero as missing."""

    for measurement in snapshot.measurements:
        if measurement.role is role and measurement.metric is metric:
            return measurement.value
    return None


def _solar_value(snapshot: DeviceSnapshot, metric: Metric) -> float | None:
    """Return one Solakon solar-system value."""

    return _value(snapshot, MeasurementRole.SOLAR_SYSTEM, metric)


def _legacy_battery_power(
    *,
    charge_power: float | None,
    discharge_power: float | None,
) -> float | None:
    """Restore the existing positive-charge, negative-discharge convention."""

    if charge_power is None and discharge_power is None:
        return None
    return (charge_power or 0.0) - (discharge_power or 0.0)


def _watt_hours_to_kilowatt_hours(value: float | None) -> float | None:
    """Convert canonical watt-hours back to legacy Solakon kilowatt-hours."""

    return None if value is None else value / 1000.0
