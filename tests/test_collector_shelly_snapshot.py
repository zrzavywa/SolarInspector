"""Tests for the collector's temporary normalized Shelly bridge."""

from __future__ import annotations

from typing import Any

import pytest
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.services.collector import Collector


class StubConfigManager:
    """Provide the minimal collector configuration dependency."""

    def get(self) -> dict[str, Any]:
        """Return an unused configuration for focused bridge tests."""

        return {}


class StubDatabase:
    """Provide the minimal collector database dependency."""

    def latest(self) -> None:
        """Return no previously persisted sample."""

        return None


class StubShellyReader:
    """Return or raise one configured legacy Shelly result."""

    def __init__(
        self,
        *,
        reading: MeterReading | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reading = reading
        self.error = error
        self.roles: list[str] = []

    def read(
        self,
        _config: dict[str, Any],
        role: str,
    ) -> MeterReading:
        """Record the legacy role and return the configured result."""

        self.roles.append(role)
        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("stub has no reading")
        return self.reading


def make_collector(reader: StubShellyReader) -> Collector:
    """Create a collector and replace only its Shelly reader."""

    collector = Collector(StubConfigManager(), StubDatabase())
    collector.reader = reader
    return collector


@pytest.mark.parametrize(
    ("role", "legacy_role"),
    [
        (MeasurementRole.GRID_METER, "house_meter"),
        (MeasurementRole.PLANT_METER, "solakon_meter"),
    ],
)
def test_bridge_round_trip_preserves_existing_meter_values(
    role: MeasurementRole,
    legacy_role: str,
) -> None:
    reader = StubShellyReader(
        reading=MeterReading(
            power_w=-125.0,
            voltage_v=230.4,
            current_a=1.75,
            power_factor=0.98,
            frequency_hz=50.01,
            energy_total_wh=12_345.0,
            returned_energy_total_wh=678.0,
        )
    )
    collector = make_collector(reader)

    reading, error = collector._read_shelly_snapshot(
        {"type": "shelly_pro_3em"},
        source_id="source",
        name="Shelly",
        role=role,
    )

    assert error is None
    assert reading is not None
    assert reading.power_w == pytest.approx(-125.0)
    assert reading.voltage_v == pytest.approx(230.4)
    assert reading.current_a == pytest.approx(1.75)
    assert reading.power_factor == pytest.approx(0.98)
    assert reading.frequency_hz == pytest.approx(50.01)
    assert reading.energy_total_wh == pytest.approx(12_345.0)
    assert reading.returned_energy_total_wh == pytest.approx(678.0)
    assert reader.roles == [legacy_role]


def test_bridge_preserves_unhandled_reader_error_text() -> None:
    collector = make_collector(StubShellyReader(error=RuntimeError("shelly failed")))

    reading, error = collector._read_shelly_snapshot(
        {"type": "shelly_pro_3em"},
        source_id="house_meter",
        name="Hausanschluss",
        role=MeasurementRole.GRID_METER,
    )

    assert reading is None
    assert error == "shelly failed"
