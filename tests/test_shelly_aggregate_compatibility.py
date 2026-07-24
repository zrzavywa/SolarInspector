"""Tests for aggregate Shelly grid values across the legacy bridge."""

from __future__ import annotations

from typing import Any

import pytest
from solarinspector_core.adapters.compatibility import (
    meter_reading_from_snapshot,
)
from solarinspector_core.adapters.shelly import (
    ShellyMeasurementAdapter,
    ShellyReader,
)
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole


class StubShellyReader(ShellyReader):
    """Return one deterministic legacy meter reading."""

    def __init__(self, reading: MeterReading) -> None:
        self.reading = reading

    def read(
        self,
        _device: dict[str, Any],
        _role: str,
    ) -> MeterReading:
        """Return the configured reading without network communication."""

        return self.reading


def test_grid_round_trip_preserves_aggregate_voltage_and_current() -> None:
    adapter = ShellyMeasurementAdapter(
        source_id="house_meter",
        name="Hausanschluss",
        device={"type": "shelly_pro_3em"},
        role=MeasurementRole.GRID_METER,
        reader=StubShellyReader(
            MeterReading(
                power_w=-125.0,
                voltage_v=230.4,
                current_a=1.75,
                power_factor=0.98,
                frequency_hz=50.01,
                energy_total_wh=12_345.0,
                returned_energy_total_wh=678.0,
            )
        ),
    )

    snapshot = adapter.read_snapshot()
    values = {
        measurement.metric: measurement.value for measurement in snapshot.measurements
    }
    reading = meter_reading_from_snapshot(
        snapshot,
        MeasurementRole.GRID_METER,
    )

    assert values[Metric.GRID_VOLTAGE] == pytest.approx(230.4)
    assert values[Metric.GRID_CURRENT] == pytest.approx(1.75)
    assert reading is not None
    assert reading.power_w == pytest.approx(-125.0)
    assert reading.voltage_v == pytest.approx(230.4)
    assert reading.current_a == pytest.approx(1.75)
    assert reading.power_factor == pytest.approx(0.98)
    assert reading.frequency_hz == pytest.approx(50.01)
