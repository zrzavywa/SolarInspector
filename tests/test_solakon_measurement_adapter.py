"""Tests for normalized Solakon ONE measurement snapshots."""

from __future__ import annotations

from typing import Any

import pytest
from solarinspector_core.adapters import (
    MeasurementAdapter,
    SolakonMeasurementAdapter,
)
from solarinspector_core.adapters.solakon import ModbusError, SolakonOneReading
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole


class StubSolakonReader:
    """Return a configured reading or raise a configured exception."""

    def __init__(
        self,
        *,
        reading: SolakonOneReading | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reading = reading
        self.error = error
        self.config: dict[str, Any] | None = None

    def read(self, config: dict[str, Any]) -> SolakonOneReading:
        """Record configuration and return the configured result."""

        self.config = dict(config)
        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("stub has no reading")
        return self.reading


def make_adapter(
    reading: SolakonOneReading | None = None,
    *,
    error: Exception | None = None,
    simulation: bool = False,
) -> SolakonMeasurementAdapter:
    """Create one adapter with stable source metadata."""

    return SolakonMeasurementAdapter(
        source_id="solakon_one",
        name="Solakon ONE",
        config={
            "host": "192.168.188.60",
            "simulation": simulation,
        },
        reader=StubSolakonReader(reading=reading, error=error),
    )


def values_by_identity(
    adapter: SolakonMeasurementAdapter,
) -> dict[tuple[MeasurementRole, Metric], float]:
    """Read one snapshot and index normalized numeric values."""

    snapshot = adapter.read_snapshot()
    return {
        (measurement.role, measurement.metric): measurement.value
        for measurement in snapshot.measurements
    }


def full_reading(**changes: object) -> SolakonOneReading:
    """Build a representative legacy reading for mapping tests."""

    values: dict[str, object] = {
        "status": "Betrieb",
        "total_pv_power_w": 960.0,
        "active_power_w": 740.0,
        "battery_power_w": 220.0,
        "battery_soc_pct": 76.0,
        "load_power_w": 590.0,
        "meter_power_w": -150.0,
        "internal_temperature_c": 31.5,
        "grid_frequency_hz": 50.01,
        "power_factor": 0.99,
        "total_pv_energy_kwh": 1234.56,
        "daily_pv_energy_kwh": 3.45,
        "battery_total_charge_kwh": 456.78,
        "battery_total_discharge_kwh": 419.22,
        "pv1_voltage_v": 36.2,
        "pv1_current_a": 1.23,
        "pv1_power_w": 480.0,
        "pv2_voltage_v": 35.8,
        "pv2_current_a": 1.11,
        "pv2_power_w": 480.0,
    }
    values.update(changes)
    return SolakonOneReading(**values)  # type: ignore[arg-type]


def test_adapter_satisfies_contract_and_exposes_all_roles() -> None:
    adapter = make_adapter(full_reading())

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.source_id == "solakon_one"
    assert adapter.source.device_type == "solakon_one"
    assert adapter.source.roles == frozenset(
        {
            MeasurementRole.GRID_METER,
            MeasurementRole.SOLAR_SYSTEM,
            MeasurementRole.BATTERY_SYSTEM,
        }
    )


def test_complete_reading_maps_signs_units_and_energy_counters() -> None:
    adapter = make_adapter(full_reading())

    snapshot = adapter.read_snapshot()
    values = {
        (measurement.role, measurement.metric): measurement.value
        for measurement in snapshot.measurements
    }

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)] == pytest.approx(
        150.0
    )
    assert values[(MeasurementRole.SOLAR_SYSTEM, Metric.PV_POWER)] == pytest.approx(
        960.0
    )
    assert values[
        (MeasurementRole.SOLAR_SYSTEM, Metric.PLANT_AC_POWER)
    ] == pytest.approx(740.0)
    assert values[
        (MeasurementRole.SOLAR_SYSTEM, Metric.PV_ENERGY_TOTAL)
    ] == pytest.approx(1_234_560.0)
    assert values[
        (MeasurementRole.SOLAR_SYSTEM, Metric.PV_ENERGY_TODAY)
    ] == pytest.approx(3_450.0)
    assert values[
        (MeasurementRole.BATTERY_SYSTEM, Metric.BATTERY_CHARGE_POWER)
    ] == pytest.approx(220.0)
    assert (
        values[
            (
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_DISCHARGE_POWER,
            )
        ]
        == 0.0
    )
    assert all(
        measurement.quality is MeasurementQuality.REPORTED
        for measurement in snapshot.measurements
    )
    assert all(
        measurement.measured_at == snapshot.received_at
        for measurement in snapshot.measurements
    )


def test_negative_battery_power_becomes_discharge_power() -> None:
    values = values_by_identity(make_adapter(full_reading(battery_power_w=-300.0)))

    assert values[(MeasurementRole.BATTERY_SYSTEM, Metric.BATTERY_CHARGE_POWER)] == 0.0
    assert values[
        (
            MeasurementRole.BATTERY_SYSTEM,
            Metric.BATTERY_DISCHARGE_POWER,
        )
    ] == pytest.approx(300.0)


def test_zero_battery_power_emits_two_valid_zero_values() -> None:
    values = values_by_identity(make_adapter(full_reading(battery_power_w=0.0)))

    assert values[(MeasurementRole.BATTERY_SYSTEM, Metric.BATTERY_CHARGE_POWER)] == 0.0
    assert (
        values[
            (
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_DISCHARGE_POWER,
            )
        ]
        == 0.0
    )


def test_partial_register_read_returns_degraded_partial_snapshot() -> None:
    adapter = make_adapter(
        SolakonOneReading(
            total_pv_power_w=100.0,
            warnings="Register 39601–39632: synthetic failure",
        )
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert snapshot.error == "Register 39601–39632: synthetic failure"
    assert len(snapshot.measurements) == 1
    assert snapshot.measurements[0].metric is Metric.PV_POWER


def test_wrapped_transport_error_returns_offline_snapshot() -> None:
    try:
        raise ModbusError("connection failed") from OSError("network down")
    except ModbusError as error:
        adapter = make_adapter(error=error)

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()
    assert "connection failed" in (snapshot.error or "")


def test_protocol_or_register_error_returns_degraded_snapshot() -> None:
    adapter = make_adapter(error=ModbusError("no recognizable registers"))

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert snapshot.measurements == ()


def test_configuration_error_returns_degraded_snapshot() -> None:
    adapter = make_adapter(error=ValueError("missing host"))

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert "missing host" in (snapshot.error or "")


def test_simulated_readings_are_marked_calculated() -> None:
    adapter = make_adapter(full_reading(), simulation=True)

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert snapshot.measurements
    assert all(
        measurement.quality is MeasurementQuality.CALCULATED
        for measurement in snapshot.measurements
    )
