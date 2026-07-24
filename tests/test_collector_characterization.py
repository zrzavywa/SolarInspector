# Characterization tests for Collector lifecycle and error handling.

from copy import deepcopy
from typing import Any

import pytest
import solarinspector as si

pytestmark = pytest.mark.characterization


class StubConfigManager:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class StubDatabase:
    def __init__(self, initial: dict[str, Any] | None = None):
        self.initial = initial
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> dict[str, Any] | None:
        return deepcopy(self.initial)

    def insert_sample(self, sample: dict[str, Any]) -> int:
        self.samples.append(dict(sample))
        return len(self.samples)


class StubShellyReader:
    def __init__(
        self,
        readings: dict[str, si.MeterReading] | None = None,
        errors: dict[str, Exception] | None = None,
    ):
        self.readings = readings or {}
        self.errors = errors or {}

    def read(
        self,
        _config: dict[str, Any],
        role: str,
    ) -> si.MeterReading:
        if role in self.errors:
            raise self.errors[role]
        return self.readings[role]


class StubSolakonReader:
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
        assert self.reading is not None
        return self.reading


class FakeThread:
    created: list["FakeThread"] = []

    def __init__(
        self,
        *,
        target: Any,
        name: str,
        daemon: bool,
    ):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.start_called = False
        self.alive = False
        self.join_timeout: float | None = None
        self.created.append(self)

    def start(self) -> None:
        self.start_called = True
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout
        self.alive = False


class OneCycleEvent:
    def __init__(self):
        self.checks = 0
        self.waits: list[float] = []
        self.was_set = False

    def is_set(self) -> bool:
        self.checks += 1
        return self.checks > 1

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        return False

    def set(self) -> None:
        self.was_set = True

    def clear(self) -> None:
        self.was_set = False


def collector_config(
    *,
    enabled: bool = True,
    poll_interval_seconds: float = 10,
) -> dict[str, Any]:
    return si.deep_merge(
        deepcopy(si.DEFAULT_CONFIG),
        {
            "general": {
                "poll_interval_seconds": poll_interval_seconds,
                "solar_power_source": "auto",
                "grid_power_source": "auto",
            },
            "grid_meter": {
                "enabled": False,
            },
            "house_meter": {
                "enabled": enabled,
            },
            "solakon_meter": {
                "enabled": enabled,
            },
            "solakon_one": {
                "enabled": enabled,
                "simulation": False,
            },
        },
    )


def make_collector(
    config: dict[str, Any] | None = None,
    database: StubDatabase | None = None,
) -> tuple[si.Collector, StubDatabase]:
    actual_database = database or StubDatabase()
    collector = si.Collector(
        StubConfigManager(config or collector_config()),
        actual_database,
    )
    return collector, actual_database


def valid_house_reading() -> si.MeterReading:
    return si.MeterReading(
        power_w=100.0,
        voltage_v=230.0,
        current_a=0.5,
        power_factor=0.98,
        frequency_hz=50.0,
        source="House fixture",
    )


def valid_solar_reading() -> si.MeterReading:
    return si.MeterReading(
        power_w=400.0,
        voltage_v=230.0,
        current_a=1.8,
        power_factor=0.99,
        frequency_hz=50.0,
        source="Solar fixture",
    )


def valid_solakon_reading() -> si.SolakonOneReading:
    return si.SolakonOneReading(
        status="Betrieb",
        total_pv_power_w=500.0,
        active_power_w=380.0,
        battery_power_w=50.0,
        battery_soc_pct=65.0,
        load_power_w=500.0,
        meter_power_w=-100.0,
        power_factor=0.99,
        grid_frequency_hz=50.0,
    )


@pytest.mark.parametrize(
    ("enabled_role", "expected"),
    [
        (None, False),
        ("grid_meter", True),
        ("house_meter", True),
        ("solakon_meter", True),
        ("solakon_one", True),
    ],
)
def test_has_enabled_source(
    enabled_role: str | None,
    expected: bool,
) -> None:
    config = collector_config(enabled=False)
    if enabled_role is not None:
        config[enabled_role]["enabled"] = True

    assert si.Collector._has_enabled_source(config) is expected


def test_start_without_enabled_source_returns_false_and_sets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector(collector_config(enabled=False))

    started = collector.start()
    status = collector.status()

    assert started is False
    assert status["running"] is False
    assert status["last_error"] == (
        "Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen."
    )
    assert logs == [status["last_error"]]
    assert collector._thread is None


def test_start_creates_named_daemon_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeThread.created = []
    logs: list[str] = []
    monkeypatch.setattr(si.threading, "Thread", FakeThread)
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector()

    assert collector.start() is True

    assert len(FakeThread.created) == 1
    thread = FakeThread.created[0]
    assert thread.name == "SolarInspectorCollector"
    assert thread.daemon is True
    assert thread.start_called is True
    assert thread.target.__self__ is collector
    assert thread.target.__func__ is si.Collector._run
    assert collector.is_running() is True
    assert collector.status()["started_at"] is not None
    assert logs == ["Datenerfassung gestartet."]


def test_second_start_while_running_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeThread.created = []
    logs: list[str] = []
    monkeypatch.setattr(si.threading, "Thread", FakeThread)
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector()

    assert collector.start() is True
    assert collector.start() is False

    assert len(FakeThread.created) == 1
    assert logs == ["Datenerfassung gestartet."]


def test_stop_without_running_thread_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector()

    assert collector.stop() is False
    assert logs == []


def test_stop_sets_event_joins_thread_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeThread.created = []
    logs: list[str] = []
    monkeypatch.setattr(si.threading, "Thread", FakeThread)
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector()

    assert collector.start() is True
    thread = FakeThread.created[0]

    assert collector.stop() is True

    assert collector._stop_event.is_set() is True
    assert thread.join_timeout == 10
    assert collector.is_running() is False
    assert logs == [
        "Datenerfassung gestartet.",
        "Datenerfassung gestoppt.",
    ]


def test_status_returns_a_copy_of_latest_sample() -> None:
    database = StubDatabase(
        {
            "id": 7,
            "solar_power_w": 400.0,
        }
    )
    collector, _database = make_collector(database=database)
    collector._cycles = 3
    collector._last_error = "example"

    first_status = collector.status()
    assert first_status["last_sample"] is not None
    first_status["last_sample"]["solar_power_w"] = 999.0

    second_status = collector.status()

    assert second_status["last_sample"]["solar_power_w"] == 400.0
    assert second_status["cycles"] == 3
    assert second_status["last_error"] == "example"


def test_reset_state_clears_runtime_measurement_state() -> None:
    collector, _database = make_collector()
    collector._last_sample = {"id": 1}
    collector._last_error = "old error"
    collector._cycles = 4
    collector._started_at = "2026-07-23T12:00:00+02:00"
    collector._previous_power = {"solar_power_w": 400.0}
    collector._previous_epoch = 123.0
    collector._last_grid_meter_snapshot = object()
    collector._last_grid_meter_poll_monotonic = 456.0

    collector.reset_state()
    status = collector.status()

    assert status["last_sample"] is None
    assert status["last_error"] == ""
    assert status["cycles"] == 0
    assert status["started_at"] is None
    assert collector._previous_power is None
    assert collector._previous_epoch is None
    assert collector._last_grid_meter_snapshot is None
    assert collector._last_grid_meter_poll_monotonic is None


def test_collect_once_without_enabled_source_raises_without_insert() -> None:
    collector, database = make_collector(collector_config(enabled=False))

    with pytest.raises(
        ValueError,
        match="Keine Messstelle aktiviert",
    ):
        collector.collect_once()

    assert database.samples == []
    assert collector.status()["cycles"] == 0


def test_all_source_errors_are_collected_and_sample_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []
    monkeypatch.setattr(si, "log", logs.append)
    collector, database = make_collector()
    collector.reader = StubShellyReader(
        errors={
            "house_meter": RuntimeError("house failed"),
            "solakon_meter": RuntimeError("solar failed"),
        }
    )
    collector.solakon_reader = StubSolakonReader(error=RuntimeError("solakon failed"))

    sample = collector.collect_once()

    expected_error = (
        "Solakon ONE: solakon failed | "
        "Hausanschluss: house failed | "
        "Shelly AC-Erzeugung: solar failed"
    )
    assert sample["id"] == 1
    assert sample["grid_power_w"] is None
    assert sample["solar_power_w"] is None
    assert sample["house_power_w"] is None
    assert sample["house_ok"] == 0
    assert sample["solar_ok"] == 0
    assert sample["solakon_ok"] == 0
    assert sample["solar_source"] == "Keine Quelle"
    assert sample["grid_source"] == "Keine Quelle"
    assert sample["error_text"] == expected_error
    assert len(database.samples) == 1
    assert collector.status()["cycles"] == 1
    assert collector.status()["last_error"] == expected_error
    assert logs == ["Messzyklus mit Warnung: " + expected_error]


def test_successful_cycle_updates_sample_count_and_clears_old_error() -> None:
    collector, database = make_collector()
    collector.reader = StubShellyReader(
        readings={
            "house_meter": valid_house_reading(),
            "solakon_meter": valid_solar_reading(),
        }
    )
    collector.solakon_reader = StubSolakonReader(reading=valid_solakon_reading())
    collector._last_error = "old error"

    sample = collector.collect_once()
    status = collector.status()

    assert sample["id"] == 1
    assert sample["solar_power_w"] == 400.0
    assert sample["grid_power_w"] == 100.0
    assert len(database.samples) == 1
    assert status["cycles"] == 1
    assert status["last_error"] == ""
    assert status["last_sample"]["id"] == 1


@pytest.mark.parametrize(
    ("interval", "elapsed", "expected_wait"),
    [
        (0.1, 0.05, 0.2),
        (2.0, 0.5, 1.5),
    ],
)
def test_run_catches_cycle_error_and_waits_remaining_interval(
    monkeypatch: pytest.MonkeyPatch,
    interval: float,
    elapsed: float,
    expected_wait: float,
) -> None:
    logs: list[str] = []
    monkeypatch.setattr(si, "log", logs.append)
    collector, _database = make_collector(
        {
            "general": {
                "poll_interval_seconds": interval,
            }
        }
    )

    def fail_cycle() -> dict[str, Any]:
        raise RuntimeError("cycle failed")

    times = iter([100.0, 100.0 + elapsed])
    monkeypatch.setattr(
        si.time,
        "monotonic",
        lambda: next(times),
    )
    collector.collect_once = fail_cycle
    event = OneCycleEvent()
    collector._stop_event = event

    collector._run()

    assert collector.status()["last_error"] == "cycle failed"
    assert event.waits == [pytest.approx(expected_wait)]
    assert logs == ["Messzyklus fehlgeschlagen: cycle failed"]
