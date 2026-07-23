"""Tests for the collector's temporary normalized Solakon bridge."""

from __future__ import annotations

from typing import Any

import pytest
from solarinspector_core.adapters.solakon import SolakonOneReading
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


class StubSolakonReader:
    """Return or raise one configured legacy Solakon result."""

    def __init__(
        self,
        *,
        reading: SolakonOneReading | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reading = reading
        self.error = error

    def read(self, _config: dict[str, Any]) -> SolakonOneReading:
        """Return the configured value using the existing reader contract."""

        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("stub has no reading")
        return self.reading


def make_collector(reader: StubSolakonReader) -> Collector:
    """Create a collector and replace only its Solakon reader."""

    collector = Collector(StubConfigManager(), StubDatabase())
    collector.solakon_reader = reader
    return collector


def test_bridge_round_trip_preserves_collector_values() -> None:
    collector = make_collector(
        StubSolakonReader(
            reading=SolakonOneReading(
                model_name="Solakon ONE H3",
                serial_number="SYNTHETIC-001",
                status="Betrieb",
                total_pv_power_w=960.0,
                active_power_w=740.0,
                battery_power_w=-300.0,
                battery_soc_pct=38.0,
                load_power_w=590.0,
                meter_power_w=-150.0,
                total_pv_energy_kwh=1234.56,
            )
        )
    )

    reading, error = collector._read_solakon_snapshot({"simulation": False})

    assert error is None
    assert reading is not None
    assert reading.model_name == "Solakon ONE H3"
    assert reading.serial_number == "SYNTHETIC-001"
    assert reading.status == "Betrieb"
    assert reading.total_pv_power_w == pytest.approx(960.0)
    assert reading.active_power_w == pytest.approx(740.0)
    assert reading.battery_power_w == pytest.approx(-300.0)
    assert reading.meter_power_w == pytest.approx(-150.0)
    assert reading.total_pv_energy_kwh == pytest.approx(1234.56)


def test_bridge_preserves_identity_only_partial_response() -> None:
    collector = make_collector(
        StubSolakonReader(
            reading=SolakonOneReading(
                model_name="Solakon ONE H3",
                serial_number="SYNTHETIC-PART",
                warnings="Register blocks unavailable",
            )
        )
    )

    reading, error = collector._read_solakon_snapshot({"simulation": False})

    assert error is None
    assert reading is not None
    assert reading.model_name == "Solakon ONE H3"
    assert reading.serial_number == "SYNTHETIC-PART"
    assert reading.warnings == "Register blocks unavailable"


def test_bridge_preserves_unhandled_reader_error_text() -> None:
    collector = make_collector(StubSolakonReader(error=RuntimeError("solakon failed")))

    reading, error = collector._read_solakon_snapshot({"simulation": False})

    assert reading is None
    assert error == "solakon failed"
