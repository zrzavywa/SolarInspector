"""Integration tests for official grid-meter collector priority."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from solarinspector_core.adapters.solakon import SolakonOneReading
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.services.collector import Collector


class StubConfigManager:
    """Return isolated collector configuration copies."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class StubDatabase:
    """Capture compatible aggregate samples."""

    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> None:
        return None

    def insert_sample(self, sample: dict[str, Any]) -> int:
        self.samples.append(dict(sample))
        return len(self.samples)


class StubShellyReader:
    """Return role-specific compatible Shelly readings."""

    def __init__(
        self,
        readings: dict[str, MeterReading],
    ) -> None:
        self.readings = readings

    def read(
        self,
        _config: dict[str, Any],
        role: str,
    ) -> MeterReading:
        return self.readings[role]


class StubSolakonReader:
    """Return one compatible Solakon reading."""

    def __init__(self, reading: SolakonOneReading) -> None:
        self.reading = reading

    def read(
        self,
        _config: dict[str, Any],
    ) -> SolakonOneReading:
        return self.reading


class SnapshotAdapter:
    """Return one prepared grid-meter snapshot."""

    def __init__(self, snapshot: DeviceSnapshot) -> None:
        self.snapshot = snapshot

    def read_snapshot(self) -> DeviceSnapshot:
        return self.snapshot


class SnapshotFactory:
    """Return snapshots sequentially and count real polls."""

    def __init__(
        self,
        snapshots: list[DeviceSnapshot],
    ) -> None:
        self.snapshots = snapshots
        self.calls = 0

    def __call__(
        self,
        _config: dict[str, Any],
    ) -> SnapshotAdapter:
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return SnapshotAdapter(self.snapshots[index])


class FailingFactory:
    """Raise an unexpected adapter-construction error."""

    def __call__(self, _config: dict[str, Any]) -> Any:
        raise RuntimeError("adapter construction failed")


def _config(
    *,
    grid_enabled: bool,
    house_enabled: bool = False,
    solar_enabled: bool = False,
    solakon_enabled: bool = False,
    fallback_source: str = "auto",
    grid_poll_interval: int = 5,
) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    config["general"]["grid_power_source"] = fallback_source
    config["grid_meter"].update(
        {
            "enabled": grid_enabled,
            "host": "192.0.2.50",
            "poll_interval_seconds": grid_poll_interval,
        }
    )
    config["house_meter"]["enabled"] = house_enabled
    config["solakon_meter"]["enabled"] = solar_enabled
    config["solakon_one"]["enabled"] = solakon_enabled
    return config


def _measurement(
    metric: Metric,
    value: float,
    timestamp: datetime,
) -> Measurement:
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id="grid_meter_primary",
        role=MeasurementRole.GRID_METER,
        measured_at=timestamp,
        received_at=timestamp,
        quality=MeasurementQuality.REPORTED,
    )


def _grid_snapshot(
    *,
    power_w: float | None,
    import_power_w: float | None = None,
    export_power_w: float | None = None,
    status: DeviceConnectionStatus = (DeviceConnectionStatus.ONLINE),
    error: str | None = None,
) -> DeviceSnapshot:
    timestamp = datetime.fromisoformat("2026-07-24T15:55:00+02:00")
    values = (
        (Metric.GRID_POWER, power_w),
        (Metric.GRID_IMPORT_POWER, import_power_w),
        (Metric.GRID_EXPORT_POWER, export_power_w),
    )
    measurements = tuple(
        _measurement(metric, value, timestamp)
        for metric, value in values
        if value is not None
    )
    return DeviceSnapshot(
        source_id="grid_meter_primary",
        status=status,
        measurements=measurements,
        received_at=timestamp,
        error=error,
    )


def _collector(
    config: dict[str, Any],
    *,
    grid_factory: Any | None = None,
    shelly_readings: dict[str, MeterReading] | None = None,
    solakon_reading: SolakonOneReading | None = None,
) -> tuple[Collector, StubDatabase]:
    database = StubDatabase()
    collector = Collector(
        StubConfigManager(config),
        database,
    )
    if grid_factory is not None:
        collector._create_grid_meter_adapter = grid_factory
    if shelly_readings is not None:
        collector.reader = StubShellyReader(shelly_readings)
    if solakon_reading is not None:
        collector.solakon_reader = StubSolakonReader(solakon_reading)
    return collector, database


def _house_reading(power_w: float) -> MeterReading:
    return MeterReading(
        power_w=power_w,
        source="House fixture",
    )


def _solar_reading(power_w: float) -> MeterReading:
    return MeterReading(
        power_w=power_w,
        source="Solar fixture",
    )


def test_official_meter_precedes_explicit_legacy_source() -> None:
    """A valid official value overrides the configured legacy source."""

    config = _config(
        grid_enabled=True,
        house_enabled=True,
        solar_enabled=True,
        fallback_source="house_meter",
    )
    factory = SnapshotFactory([_grid_snapshot(power_w=-200.0)])
    collector, _database = _collector(
        config,
        grid_factory=factory,
        shelly_readings={
            "house_meter": _house_reading(900.0),
            "solakon_meter": _solar_reading(500.0),
        },
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == -200.0
    assert sample["grid_import_w"] == 0.0
    assert sample["feed_in_w"] == 200.0
    assert sample["house_power_w"] == 300.0
    assert sample["self_consumption_w"] == 300.0
    assert sample["grid_source"] == ("Offizieller Netzstromzähler")
    assert factory.calls == 1


def test_official_zero_power_does_not_trigger_fallback() -> None:
    """A real zero remains authoritative over a non-zero Shelly."""

    config = _config(
        grid_enabled=True,
        house_enabled=True,
    )
    collector, _database = _collector(
        config,
        grid_factory=SnapshotFactory([_grid_snapshot(power_w=0.0)]),
        shelly_readings={
            "house_meter": _house_reading(800.0),
        },
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 0.0
    assert sample["grid_import_w"] == 0.0
    assert sample["feed_in_w"] == 0.0
    assert sample["grid_source"] == ("Offizieller Netzstromzähler")


def test_degraded_snapshot_with_power_remains_primary() -> None:
    """Partial optional values do not invalidate core power."""

    config = _config(
        grid_enabled=True,
        house_enabled=True,
    )
    collector, _database = _collector(
        config,
        grid_factory=SnapshotFactory(
            [
                _grid_snapshot(
                    power_w=125.0,
                    status=(DeviceConnectionStatus.DEGRADED),
                    error="Export total is unavailable.",
                )
            ]
        ),
        shelly_readings={
            "house_meter": _house_reading(999.0),
        },
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 125.0
    assert sample["grid_source"] == ("Offizieller Netzstromzähler")
    assert (
        "Offizieller Netzstromzähler: "
        "Export total is unavailable." in sample["error_text"]
    )


def test_offline_official_meter_uses_marked_house_fallback() -> None:
    """An offline official source does not stop the cycle."""

    config = _config(
        grid_enabled=True,
        house_enabled=True,
    )
    offline = _grid_snapshot(
        power_w=None,
        status=DeviceConnectionStatus.OFFLINE,
        error="Tasmota device is unreachable.",
    )
    collector, database = _collector(
        config,
        grid_factory=SnapshotFactory([offline]),
        shelly_readings={
            "house_meter": _house_reading(100.0),
        },
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 100.0
    assert sample["grid_import_w"] == 100.0
    assert sample["feed_in_w"] == 0.0
    assert sample["grid_source"] == ("Separate Hausmessung (Auto) (Fallback)")
    assert "Tasmota device is unreachable" in (sample["error_text"])
    assert len(database.samples) == 1


def test_unexpected_adapter_error_uses_solakon_fallback() -> None:
    """Unexpected adapter errors retain compatible fallback."""

    config = _config(
        grid_enabled=True,
        solakon_enabled=True,
        fallback_source="solakon_one",
    )
    collector, database = _collector(
        config,
        grid_factory=FailingFactory(),
        solakon_reading=SolakonOneReading(
            meter_power_w=-70.0,
        ),
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 70.0
    assert sample["grid_source"] == ("Solakon ONE Meter (Fallback)")
    assert "Unexpected grid-meter adapter failure." in sample["error_text"]
    assert "adapter construction failed" not in (sample["error_text"])
    assert len(database.samples) == 1


def test_disabled_official_meter_preserves_legacy_behavior() -> None:
    """Existing installations keep their old source labels."""

    config = _config(
        grid_enabled=False,
        house_enabled=True,
    )
    collector, _database = _collector(
        config,
        shelly_readings={
            "house_meter": _house_reading(100.0),
        },
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 100.0
    assert sample["grid_source"] == ("Separate Hausmessung (Auto)")
    assert sample["error_text"] == ""


def test_missing_official_and_fallback_values_stay_missing() -> None:
    """Missing power is not converted to an invented zero."""

    config = _config(grid_enabled=True)
    degraded = _grid_snapshot(
        power_w=None,
        status=DeviceConnectionStatus.DEGRADED,
        error="Required grid power is missing.",
    )
    collector, database = _collector(
        config,
        grid_factory=SnapshotFactory([degraded]),
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] is None
    assert sample["grid_import_w"] is None
    assert sample["feed_in_w"] is None
    assert sample["grid_source"] == (
        "Keine Quelle (offizieller Netzstromzähler nicht verfügbar)"
    )
    assert len(database.samples) == 1


def test_reported_direction_values_are_used_by_collector() -> None:
    """Collector retains adapter-provided directional metrics."""

    config = _config(grid_enabled=True)
    snapshot = _grid_snapshot(
        power_w=-50.0,
        import_power_w=12.0,
        export_power_w=34.0,
    )
    collector, _database = _collector(
        config,
        grid_factory=SnapshotFactory([snapshot]),
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == -50.0
    assert sample["grid_import_w"] == 12.0
    assert sample["feed_in_w"] == 34.0


def test_grid_meter_poll_interval_reuses_recent_snapshot() -> None:
    """Collector does not poll faster than the source interval."""

    config = _config(
        grid_enabled=True,
        grid_poll_interval=5,
    )
    factory = SnapshotFactory(
        [
            _grid_snapshot(power_w=100.0),
            _grid_snapshot(power_w=200.0),
        ]
    )
    collector, _database = _collector(
        config,
        grid_factory=factory,
    )
    times = iter([100.0, 102.0])
    collector._monotonic = lambda: next(times)

    first = collector.collect_once()
    second = collector.collect_once()

    assert first["grid_power_w"] == 100.0
    assert second["grid_power_w"] == 100.0
    assert factory.calls == 1


def test_grid_meter_is_polled_again_after_interval() -> None:
    """A due source poll replaces the cached snapshot."""

    config = _config(
        grid_enabled=True,
        grid_poll_interval=5,
    )
    factory = SnapshotFactory(
        [
            _grid_snapshot(power_w=100.0),
            _grid_snapshot(power_w=200.0),
        ]
    )
    collector, _database = _collector(
        config,
        grid_factory=factory,
    )
    times = iter([100.0, 105.0])
    collector._monotonic = lambda: next(times)

    first = collector.collect_once()
    second = collector.collect_once()

    assert first["grid_power_w"] == 100.0
    assert second["grid_power_w"] == 200.0
    assert factory.calls == 2
