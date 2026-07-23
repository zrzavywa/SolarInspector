"""Characterization tests for energy integration and dashboard aggregation."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

import pytest
import solarinspector as si

ENERGY_KEYS = (
    "grid_import_wh",
    "feed_in_wh",
    "solar_wh",
    "house_wh",
    "self_consumption_wh",
    "shelly_solar_wh",
    "solakon_pv_wh",
    "solakon_ac_wh",
    "battery_charge_wh",
    "battery_discharge_wh",
)


class FrozenDateTime(datetime):
    """Controllable replacement for solarinspector.datetime."""

    current = datetime(2026, 7, 23, 12, 0, 0).astimezone()

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current
        return cls.current.astimezone(tz)


class StubConfigManager:
    """Return a deterministic collector configuration."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class StubDatabase:
    """Capture inserted samples without using SQLite."""

    def __init__(self):
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> None:
        return None

    def insert_sample(self, sample: dict[str, Any]) -> int:
        self.samples.append(dict(sample))
        return len(self.samples)


class StubShellyReader:
    """Expose mutable house and solar readings."""

    def __init__(
        self,
        house: si.MeterReading,
        solar: si.MeterReading,
    ):
        self.house = house
        self.solar = solar

    def read(
        self,
        _config: dict[str, Any],
        role: str,
    ) -> si.MeterReading:
        if role == "house_meter":
            return self.house
        if role == "solakon_meter":
            return self.solar
        raise AssertionError(f"Unexpected role: {role}")


class StubSolakonReader:
    """Expose one mutable Solakon reading."""

    def __init__(self, reading: si.SolakonOneReading):
        self.reading = reading

    def read(
        self,
        _config: dict[str, Any],
    ) -> si.SolakonOneReading:
        return self.reading


class DashboardDatabase:
    """Return predefined rows to build_dashboard."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.requested_bounds: tuple[float, float] | None = None

    def rows_between(
        self,
        start_epoch: float,
        end_epoch: float,
    ) -> list[dict[str, Any]]:
        self.requested_bounds = (start_epoch, end_epoch)
        return self.rows


def collector_config(
    poll_interval_seconds: int = 10,
) -> dict[str, Any]:
    """Create a configuration with all measurement sources enabled."""
    return si.deep_merge(
        si.DEFAULT_CONFIG,
        {
            "general": {
                "poll_interval_seconds": poll_interval_seconds,
                "solar_power_source": "auto",
                "grid_power_source": "auto",
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


def house_reading(power_w: float) -> si.MeterReading:
    """Create a separate grid-meter reading."""
    return si.MeterReading(
        power_w=power_w,
        voltage_v=230.0,
        current_a=1.0,
        power_factor=0.98,
        frequency_hz=50.0,
        source="House fixture",
    )


def solar_reading(power_w: float) -> si.MeterReading:
    """Create a Shelly AC production reading."""
    return si.MeterReading(
        power_w=power_w,
        voltage_v=230.0,
        current_a=2.0,
        power_factor=0.99,
        frequency_hz=50.0,
        source="Solar fixture",
    )


def solakon_reading(
    *,
    pv_power_w: float | None = 500.0,
    ac_power_w: float | None = 380.0,
    battery_power_w: float | None = 200.0,
) -> si.SolakonOneReading:
    """Create a Solakon reading used by collector energy tests."""
    return si.SolakonOneReading(
        status="Betrieb",
        total_pv_power_w=pv_power_w,
        active_power_w=ac_power_w,
        battery_power_w=battery_power_w,
        battery_soc_pct=65.0,
        load_power_w=500.0,
        meter_power_w=-100.0,
    )


def make_collector(
    *,
    poll_interval_seconds: int = 10,
    grid_power_w: float = 100.0,
    solar_power_w: float = 400.0,
    pv_power_w: float | None = 500.0,
    ac_power_w: float | None = 380.0,
    battery_power_w: float | None = 200.0,
) -> tuple[
    si.Collector,
    StubDatabase,
    StubShellyReader,
    StubSolakonReader,
]:
    """Create a collector with mutable deterministic sources."""
    database = StubDatabase()
    shelly = StubShellyReader(
        house_reading(grid_power_w),
        solar_reading(solar_power_w),
    )
    solakon = StubSolakonReader(
        solakon_reading(
            pv_power_w=pv_power_w,
            ac_power_w=ac_power_w,
            battery_power_w=battery_power_w,
        )
    )
    collector = si.Collector(
        StubConfigManager(
            collector_config(
                poll_interval_seconds=poll_interval_seconds,
            )
        ),
        database,
    )
    collector.reader = shelly
    collector.solakon_reader = solakon
    return collector, database, shelly, solakon


def advance(seconds: float) -> None:
    """Advance the frozen collector clock."""
    FrozenDateTime.current += timedelta(seconds=seconds)


def test_first_sample_has_zero_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first measurement cannot integrate without previous power values."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, database, _shelly, _solakon = make_collector()

    sample = collector.collect_once()

    for key in ENERGY_KEYS:
        assert sample[key] == 0.0
    assert collector._previous_epoch == FrozenDateTime.current.timestamp()
    assert collector._previous_power is not None
    assert database.samples[0]["solar_wh"] == 0.0


def test_trapezoidal_energy_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Energy uses the average of previous and current power."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, shelly, solakon = make_collector()

    collector.collect_once()
    advance(10)

    shelly.house = house_reading(300.0)
    shelly.solar = solar_reading(600.0)
    solakon.reading = solakon_reading(
        pv_power_w=700.0,
        ac_power_w=580.0,
        battery_power_w=-100.0,
    )

    sample = collector.collect_once()

    assert sample["grid_import_wh"] == pytest.approx(200.0 * 10.0 / 3600.0)
    assert sample["feed_in_wh"] == 0.0
    assert sample["solar_wh"] == pytest.approx(500.0 * 10.0 / 3600.0)
    assert sample["house_wh"] == pytest.approx(700.0 * 10.0 / 3600.0)
    assert sample["self_consumption_wh"] == pytest.approx(500.0 * 10.0 / 3600.0)
    assert sample["shelly_solar_wh"] == pytest.approx(500.0 * 10.0 / 3600.0)
    assert sample["solakon_pv_wh"] == pytest.approx(600.0 * 10.0 / 3600.0)
    assert sample["solakon_ac_wh"] == pytest.approx(480.0 * 10.0 / 3600.0)
    assert sample["battery_charge_wh"] == pytest.approx(100.0 * 10.0 / 3600.0)
    assert sample["battery_discharge_wh"] == pytest.approx(50.0 * 10.0 / 3600.0)


def test_elapsed_time_is_limited_to_three_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long collection gaps are capped at poll interval times three."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, _shelly, _solakon = make_collector(
        poll_interval_seconds=10,
    )

    collector.collect_once()
    advance(100)

    sample = collector.collect_once()

    assert sample["solar_wh"] == pytest.approx(400.0 * 30.0 / 3600.0)
    assert sample["grid_import_wh"] == pytest.approx(100.0 * 30.0 / 3600.0)


def test_negative_elapsed_time_produces_zero_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clock moving backwards is clamped to a zero integration interval."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, _shelly, _solakon = make_collector()

    collector.collect_once()
    advance(-5)

    sample = collector.collect_once()

    for key in ENERGY_KEYS:
        assert sample[key] == 0.0


def test_missing_previous_power_produces_zero_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newly available measurement does not integrate against None."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, _shelly, solakon = make_collector(
        pv_power_w=None,
    )

    collector.collect_once()
    advance(10)
    solakon.reading = solakon_reading(pv_power_w=500.0)

    sample = collector.collect_once()

    assert sample["solakon_pv_power_w"] == 500.0
    assert sample["solakon_pv_wh"] == 0.0
    assert sample["solar_wh"] > 0.0


def test_missing_current_power_produces_zero_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disappearing measurement does not integrate its previous value."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, _shelly, solakon = make_collector(
        pv_power_w=500.0,
    )

    collector.collect_once()
    advance(10)
    solakon.reading = solakon_reading(pv_power_w=None)

    sample = collector.collect_once()

    assert sample["solakon_pv_power_w"] is None
    assert sample["solakon_pv_wh"] == 0.0
    assert sample["solar_wh"] > 0.0


def test_import_to_feed_in_transition_integrates_both_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import and export channels are integrated independently."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, shelly, _solakon = make_collector(
        grid_power_w=100.0,
    )

    collector.collect_once()
    advance(10)
    shelly.house = house_reading(-100.0)

    sample = collector.collect_once()

    expected = 50.0 * 10.0 / 3600.0
    assert sample["grid_import_w"] == 0.0
    assert sample["feed_in_w"] == 100.0
    assert sample["grid_import_wh"] == pytest.approx(expected)
    assert sample["feed_in_wh"] == pytest.approx(expected)


def test_charge_to_discharge_transition_integrates_both_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Battery charge and discharge energy remain separate during a sign change."""
    monkeypatch.setattr(si, "datetime", FrozenDateTime)
    collector, _database, _shelly, solakon = make_collector(
        battery_power_w=300.0,
    )

    collector.collect_once()
    advance(10)
    solakon.reading = solakon_reading(
        battery_power_w=-300.0,
    )

    sample = collector.collect_once()

    expected = 150.0 * 10.0 / 3600.0
    assert sample["battery_charge_wh"] == pytest.approx(expected)
    assert sample["battery_discharge_wh"] == pytest.approx(expected)


def dashboard_row(
    timestamp: datetime,
    *,
    solar_wh: float | None,
    house_wh: float | None,
    grid_import_wh: float | None,
    feed_in_wh: float | None,
    self_consumption_wh: float | None,
    shelly_solar_wh: float | None,
    solakon_pv_wh: float | None,
    solakon_ac_wh: float | None,
    battery_charge_wh: float | None,
    battery_discharge_wh: float | None,
    soc: float | None,
    difference_w: float | None,
    difference_pct: float | None,
    solar_source: str,
    grid_source: str,
) -> dict[str, Any]:
    """Create one persisted sample row for dashboard tests."""
    return {
        "ts_epoch": timestamp.timestamp(),
        "solar_wh": solar_wh,
        "house_wh": house_wh,
        "grid_import_wh": grid_import_wh,
        "feed_in_wh": feed_in_wh,
        "self_consumption_wh": self_consumption_wh,
        "shelly_solar_wh": shelly_solar_wh,
        "solakon_pv_wh": solakon_pv_wh,
        "solakon_ac_wh": solakon_ac_wh,
        "battery_charge_wh": battery_charge_wh,
        "battery_discharge_wh": battery_discharge_wh,
        "solakon_battery_soc_pct": soc,
        "solar_difference_w": difference_w,
        "solar_difference_pct": difference_pct,
        "solar_source": solar_source,
        "grid_source": grid_source,
    }


def test_dashboard_aggregates_energy_buckets_and_kpis() -> None:
    """Stored Wh values are summed into hourly series and period KPIs."""
    anchor = date(2026, 7, 23)
    start, end, _labels, _title = si.period_bounds("day", anchor)
    rows = [
        dashboard_row(
            start + timedelta(hours=1, minutes=5),
            solar_wh=1000.0,
            house_wh=2000.0,
            grid_import_wh=500.0,
            feed_in_wh=100.0,
            self_consumption_wh=800.0,
            shelly_solar_wh=950.0,
            solakon_pv_wh=1200.0,
            solakon_ac_wh=900.0,
            battery_charge_wh=200.0,
            battery_discharge_wh=50.0,
            soc=50.0,
            difference_w=10.0,
            difference_pct=2.0,
            solar_source="First solar",
            grid_source="First grid",
        ),
        dashboard_row(
            start + timedelta(hours=2, minutes=5),
            solar_wh=500.0,
            house_wh=1000.0,
            grid_import_wh=250.0,
            feed_in_wh=50.0,
            self_consumption_wh=400.0,
            shelly_solar_wh=475.0,
            solakon_pv_wh=600.0,
            solakon_ac_wh=450.0,
            battery_charge_wh=100.0,
            battery_discharge_wh=25.0,
            soc=70.0,
            difference_w=-5.0,
            difference_pct=-1.0,
            solar_source="Latest solar",
            grid_source="Latest grid",
        ),
    ]
    database = DashboardDatabase(rows)

    dashboard = si.build_dashboard(database, "day", anchor)

    assert database.requested_bounds == (
        start.timestamp(),
        end.timestamp(),
    )
    assert dashboard["series"]["solar_kwh"][1] == 1.0
    assert dashboard["series"]["solar_kwh"][2] == 0.5
    assert dashboard["series"]["house_kwh"][1] == 2.0
    assert dashboard["series"]["battery_charge_kwh"][2] == 0.1
    assert dashboard["series"]["battery_soc_avg"][1] == 50.0
    assert dashboard["series"]["battery_soc_avg"][2] == 70.0

    kpi = dashboard["kpi"]
    assert kpi["solar_kwh"] == 1.5
    assert kpi["house_kwh"] == 3.0
    assert kpi["grid_import_kwh"] == 0.75
    assert kpi["feed_in_kwh"] == 0.15
    assert kpi["self_consumption_kwh"] == 1.2
    assert kpi["self_consumption_pct"] == 80.0
    assert kpi["autarky_pct"] == 40.0
    assert kpi["shelly_ac_kwh"] == 1.425
    assert kpi["solakon_pv_kwh"] == 1.8
    assert kpi["solakon_ac_kwh"] == 1.35
    assert kpi["battery_charge_kwh"] == 0.3
    assert kpi["battery_discharge_kwh"] == 0.075
    assert kpi["battery_soc_avg"] == 60.0
    assert kpi["battery_soc_min"] == 50.0
    assert kpi["battery_soc_max"] == 70.0
    assert kpi["difference_avg_w"] == 2.5
    assert kpi["difference_avg_pct"] == 0.5
    assert kpi["sample_count"] == 2
    assert kpi["solar_source"] == "Latest solar"
    assert kpi["grid_source"] == "Latest grid"


def test_dashboard_treats_missing_energy_as_zero() -> None:
    """Missing and None energy fields contribute zero to dashboard totals."""
    anchor = date(2026, 7, 23)
    start, _end, _labels, _title = si.period_bounds("day", anchor)
    database = DashboardDatabase(
        [
            {
                "ts_epoch": (start + timedelta(hours=3)).timestamp(),
                "solar_wh": None,
                "house_wh": None,
                "solar_source": "No energy",
                "grid_source": "No grid",
            }
        ]
    )

    dashboard = si.build_dashboard(database, "day", anchor)
    kpi = dashboard["kpi"]

    assert kpi["solar_kwh"] == 0.0
    assert kpi["house_kwh"] == 0.0
    assert kpi["grid_import_kwh"] == 0.0
    assert kpi["battery_charge_kwh"] == 0.0
    assert kpi["self_consumption_pct"] is None
    assert kpi["autarky_pct"] is None
    assert kpi["battery_soc_avg"] is None
    assert kpi["difference_avg_w"] is None


@pytest.mark.parametrize(
    ("period", "offset", "expected"),
    [
        ("day", timedelta(hours=7), 7),
        ("week", timedelta(days=4), 4),
        ("year", timedelta(days=181), 6),
    ],
)
def test_bucket_index_uses_hour_weekday_or_month(
    period: str,
    offset: timedelta,
    expected: int,
) -> None:
    """Dashboard bucket selection depends on the requested period."""
    anchor = date(2026, 1, 1)
    start, _end, _labels, _title = si.period_bounds(period, anchor)

    assert si.bucket_index(period, start, start + offset) == expected
