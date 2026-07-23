"""Characterization tests for measurement-source priority and fallback rules."""

from copy import deepcopy
from typing import Any

import pytest
import solarinspector as si


class StubConfigManager:
    """Return one deterministic collector configuration."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class StubDatabase:
    """Capture samples without using SQLite."""

    def __init__(self):
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> None:
        return None

    def insert_sample(self, sample: dict[str, Any]) -> int:
        self.samples.append(dict(sample))
        return len(self.samples)


class StubShellyReader:
    """Return fixed house and solar readings or configured errors."""

    def __init__(
        self,
        *,
        house: si.MeterReading | None = None,
        solar: si.MeterReading | None = None,
        house_error: Exception | None = None,
        solar_error: Exception | None = None,
    ):
        self.house = house
        self.solar = solar
        self.house_error = house_error
        self.solar_error = solar_error

    def read(
        self,
        _config: dict[str, Any],
        role: str,
    ) -> si.MeterReading:
        if role == "house_meter":
            if self.house_error is not None:
                raise self.house_error
            if self.house is None:
                raise AssertionError("No house reading configured")
            return self.house

        if role == "solakon_meter":
            if self.solar_error is not None:
                raise self.solar_error
            if self.solar is None:
                raise AssertionError("No solar reading configured")
            return self.solar

        raise AssertionError(f"Unexpected role: {role}")


class StubSolakonReader:
    """Return one fixed Solakon reading or a configured error."""

    def __init__(
        self,
        reading: si.SolakonOneReading | None = None,
        error: Exception | None = None,
    ):
        self.reading = reading
        self.error = error

    def read(
        self,
        _config: dict[str, Any],
    ) -> si.SolakonOneReading:
        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("No Solakon reading configured")
        return self.reading


def source_config(
    *,
    solar_source: str = "auto",
    grid_source: str = "auto",
) -> dict[str, Any]:
    """Create a configuration with all three measurement sources enabled."""
    return si.deep_merge(
        si.DEFAULT_CONFIG,
        {
            "general": {
                "poll_interval_seconds": 10,
                "solar_power_source": solar_source,
                "grid_power_source": grid_source,
            },
            "house_meter": {
                "enabled": True,
            },
            "solakon_meter": {
                "enabled": True,
            },
            "solakon_one": {
                "enabled": True,
                "simulation": False,
            },
        },
    )


def house_reading(
    power_w: float = 100.0,
) -> si.MeterReading:
    """Create a deterministic separate house-meter reading."""
    return si.MeterReading(
        power_w=power_w,
        voltage_v=231.0,
        current_a=0.43,
        power_factor=0.95,
        frequency_hz=50.02,
        source="House fixture",
    )


def solar_reading(
    power_w: float = 400.0,
) -> si.MeterReading:
    """Create a deterministic Shelly AC-production reading."""
    return si.MeterReading(
        power_w=power_w,
        voltage_v=229.0,
        current_a=1.75,
        power_factor=0.98,
        frequency_hz=49.99,
        source="Solar fixture",
    )


def solakon_reading(
    *,
    ac_power_w: float | None = 380.0,
    pv_power_w: float | None = 500.0,
    meter_power_w: float | None = -120.0,
    load_power_w: float | None = 500.0,
) -> si.SolakonOneReading:
    """Create a deterministic Solakon ONE reading."""
    return si.SolakonOneReading(
        model_name="Synthetic Solakon",
        serial_number="SYNTHETIC-SOURCE",
        status="Betrieb",
        active_power_w=ac_power_w,
        total_pv_power_w=pv_power_w,
        meter_power_w=meter_power_w,
        load_power_w=load_power_w,
        battery_power_w=50.0,
        battery_soc_pct=65.0,
        power_factor=0.99,
        grid_frequency_hz=50.0,
    )


def make_collector(
    *,
    solar_source: str = "auto",
    grid_source: str = "auto",
    house: si.MeterReading | None = None,
    solar: si.MeterReading | None = None,
    solakon: si.SolakonOneReading | None = None,
    house_error: Exception | None = None,
    solar_error: Exception | None = None,
    solakon_error: Exception | None = None,
) -> tuple[si.Collector, StubDatabase]:
    """Create a collector with deterministic readers and in-memory persistence."""
    database = StubDatabase()
    collector = si.Collector(
        StubConfigManager(
            source_config(
                solar_source=solar_source,
                grid_source=grid_source,
            )
        ),
        database,
    )
    collector.reader = StubShellyReader(
        house=house,
        solar=solar,
        house_error=house_error,
        solar_error=solar_error,
    )
    collector.solakon_reader = StubSolakonReader(
        reading=solakon,
        error=solakon_error,
    )
    return collector, database


@pytest.mark.parametrize(
    ("source", "expected_power", "expected_label"),
    [
        ("shelly_ac", 410.0, "Shelly AC"),
        ("solakon_ac", 380.0, "Solakon ONE AC"),
        ("solakon_pv", 500.0, "Solakon ONE PV-Eingang"),
    ],
)
def test_explicit_solar_source_is_used(
    source: str,
    expected_power: float,
    expected_label: str,
) -> None:
    """Each explicit production source returns its corresponding measurement."""
    selected = si.Collector._select_solar_power(
        source,
        410.0,
        solakon_reading(),
    )

    assert selected == (expected_power, expected_label)


@pytest.mark.parametrize(
    ("shelly_power", "ac_power", "pv_power", "expected_power", "expected_label"),
    [
        (410.0, 380.0, 500.0, 410.0, "Shelly AC (Auto)"),
        (None, 380.0, 500.0, 380.0, "Solakon ONE AC (Auto)"),
        (None, None, 500.0, 500.0, "Solakon ONE PV-Eingang (Auto)"),
        (None, None, None, None, "Keine Quelle"),
    ],
)
def test_automatic_solar_priority(
    shelly_power: float | None,
    ac_power: float | None,
    pv_power: float | None,
    expected_power: float | None,
    expected_label: str,
) -> None:
    """Automatic production priority is Shelly AC, Solakon AC, then PV input."""
    selected = si.Collector._select_solar_power(
        "auto",
        shelly_power,
        solakon_reading(
            ac_power_w=ac_power,
            pv_power_w=pv_power,
        ),
    )

    assert selected == (expected_power, expected_label)


def test_automatic_solar_priority_treats_zero_as_available() -> None:
    """A Shelly value of zero wins over positive Solakon values."""
    selected = si.Collector._select_solar_power(
        "auto",
        0.0,
        solakon_reading(
            ac_power_w=380.0,
            pv_power_w=500.0,
        ),
    )

    assert selected == (0.0, "Shelly AC (Auto)")


def test_negative_solakon_ac_is_clipped_and_remains_available() -> None:
    """A negative Solakon AC value becomes zero and wins over its PV value."""
    selected = si.Collector._select_solar_power(
        "auto",
        None,
        solakon_reading(
            ac_power_w=-25.0,
            pv_power_w=500.0,
        ),
    )

    assert selected == (0.0, "Solakon ONE AC (Auto)")


def test_explicit_missing_solar_source_does_not_fallback() -> None:
    """Explicit Shelly selection returns None even when Solakon is available."""
    selected = si.Collector._select_solar_power(
        "shelly_ac",
        None,
        solakon_reading(),
    )

    assert selected == (None, "Shelly AC")


@pytest.mark.parametrize(
    ("source", "expected_power", "expected_label"),
    [
        ("house_meter", 125.0, "Separate Hausmessung"),
        ("solakon_one", 80.0, "Solakon ONE Meter"),
    ],
)
def test_explicit_grid_source_is_used(
    source: str,
    expected_power: float,
    expected_label: str,
) -> None:
    """Explicit grid selection uses the requested meter and sign convention."""
    selected = si.Collector._select_grid_power(
        source,
        house_reading(125.0),
        solakon_reading(meter_power_w=-80.0),
    )

    assert selected == (expected_power, expected_label)


@pytest.mark.parametrize(
    ("house", "meter_power", "expected_power", "expected_label"),
    [
        (
            house_reading(125.0),
            -80.0,
            125.0,
            "Separate Hausmessung (Auto)",
        ),
        (
            None,
            -80.0,
            80.0,
            "Solakon ONE Meter (Auto)",
        ),
        (
            None,
            None,
            None,
            "Keine Quelle",
        ),
    ],
)
def test_automatic_grid_priority(
    house: si.MeterReading | None,
    meter_power: float | None,
    expected_power: float | None,
    expected_label: str,
) -> None:
    """Automatic grid priority is the separate meter, then Solakon ONE."""
    selected = si.Collector._select_grid_power(
        "auto",
        house,
        solakon_reading(meter_power_w=meter_power),
    )

    assert selected == (expected_power, expected_label)


def test_automatic_grid_priority_treats_zero_as_available() -> None:
    """A separate house-meter value of zero wins over the Solakon meter."""
    selected = si.Collector._select_grid_power(
        "auto",
        house_reading(0.0),
        solakon_reading(meter_power_w=-80.0),
    )

    assert selected == (0.0, "Separate Hausmessung (Auto)")


def test_explicit_missing_grid_source_does_not_fallback() -> None:
    """Explicit house-meter selection returns None despite Solakon availability."""
    selected = si.Collector._select_grid_power(
        "house_meter",
        None,
        solakon_reading(meter_power_w=-80.0),
    )

    assert selected == (None, "Separate Hausmessung")


def test_solakon_grid_sign_is_reversed() -> None:
    """Positive Solakon feed-in becomes negative SolarInspector grid power."""
    selected = si.Collector._select_grid_power(
        "solakon_one",
        None,
        solakon_reading(meter_power_w=150.0),
    )

    assert selected == (-150.0, "Solakon ONE Meter")


def test_collect_once_uses_automatic_source_priorities() -> None:
    """With all sources available, Shelly solar and house grid measurements win."""
    collector, database = make_collector(
        house=house_reading(100.0),
        solar=solar_reading(400.0),
        solakon=solakon_reading(
            ac_power_w=380.0,
            pv_power_w=500.0,
            meter_power_w=-120.0,
        ),
    )

    sample = collector.collect_once()

    assert sample["solar_power_w"] == 400.0
    assert sample["solar_source"] == "Shelly AC (Auto)"
    assert sample["grid_power_w"] == 100.0
    assert sample["grid_source"] == "Separate Hausmessung (Auto)"
    assert sample["grid_import_w"] == 100.0
    assert sample["feed_in_w"] == 0.0
    assert sample["house_power_w"] == 500.0
    assert sample["self_consumption_w"] == 400.0
    assert sample["solar_difference_w"] == 20.0
    assert sample["solar_difference_pct"] == pytest.approx(20.0 / 380.0 * 100.0)
    assert sample["voltage_v"] == 229.0
    assert sample["house_ok"] == 1
    assert sample["solar_ok"] == 1
    assert sample["solakon_ok"] == 1
    assert database.samples[0]["solar_power_w"] == 400.0


def test_explicit_pv_source_does_not_control_house_balance() -> None:
    """House balance still prefers Shelly AC when displayed solar uses PV input."""
    collector, _ = make_collector(
        solar_source="solakon_pv",
        house=house_reading(100.0),
        solar=solar_reading(400.0),
        solakon=solakon_reading(
            ac_power_w=380.0,
            pv_power_w=500.0,
            meter_power_w=-120.0,
        ),
    )

    sample = collector.collect_once()

    assert sample["solar_power_w"] == 500.0
    assert sample["solar_source"] == "Solakon ONE PV-Eingang"
    assert sample["house_power_w"] == 500.0
    assert sample["self_consumption_w"] == 400.0


def test_explicit_solakon_grid_source_overrides_house_meter() -> None:
    """Explicit Solakon meter selection wins despite a valid house measurement."""
    collector, _ = make_collector(
        grid_source="solakon_one",
        house=house_reading(100.0),
        solar=solar_reading(400.0),
        solakon=solakon_reading(meter_power_w=-120.0),
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 120.0
    assert sample["grid_source"] == "Solakon ONE Meter"
    assert sample["house_power_w"] == 520.0


def test_failed_shelly_solar_falls_back_to_solakon_ac() -> None:
    """A Shelly production error is recorded while automatic mode uses Solakon."""
    collector, _ = make_collector(
        house=house_reading(100.0),
        solar_error=RuntimeError("solar offline"),
        solakon=solakon_reading(
            ac_power_w=380.0,
            pv_power_w=500.0,
        ),
    )

    sample = collector.collect_once()

    assert sample["solar_power_w"] == 380.0
    assert sample["solar_source"] == "Solakon ONE AC (Auto)"
    assert sample["house_power_w"] == 480.0
    assert sample["solar_ok"] == 0
    assert sample["solakon_ok"] == 1
    assert sample["error_text"] == "Shelly AC-Erzeugung: solar offline"


def test_failed_house_meter_falls_back_to_solakon_meter() -> None:
    """A house-meter error is recorded while automatic mode uses Solakon grid."""
    collector, _ = make_collector(
        house_error=RuntimeError("house offline"),
        solar=solar_reading(400.0),
        solakon=solakon_reading(meter_power_w=-120.0),
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 120.0
    assert sample["grid_source"] == "Solakon ONE Meter (Auto)"
    assert sample["house_power_w"] == 520.0
    assert sample["house_ok"] == 0
    assert sample["error_text"] == "Hausanschluss: house offline"


def test_explicit_failed_source_remains_unavailable() -> None:
    """Explicit source selection suppresses automatic fallback after a read error."""
    collector, _ = make_collector(
        solar_source="shelly_ac",
        house=house_reading(100.0),
        solar_error=RuntimeError("solar offline"),
        solakon=solakon_reading(
            ac_power_w=380.0,
            pv_power_w=500.0,
        ),
    )

    sample = collector.collect_once()

    assert sample["solar_power_w"] is None
    assert sample["solar_source"] == "Shelly AC"
    assert sample["house_power_w"] == 480.0
    assert sample["self_consumption_w"] == 380.0
    assert sample["error_text"] == "Shelly AC-Erzeugung: solar offline"
