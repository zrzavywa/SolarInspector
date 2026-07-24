"""Tests for official grid-meter persistence and live API output."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import (
    MeasurementQuality,
)
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.persistence.database import Database
from solarinspector_core.services.collector import Collector
from solarinspector_core.web.api import build_live_api_response


def _measurement(
    metric: Metric,
    value: float,
    *,
    quality: MeasurementQuality,
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
        quality=quality,
    )


def _snapshot(
    timestamp: datetime,
    *,
    power_w: float | None = -241.0,
    import_power_w: float | None = 0.0,
    export_power_w: float | None = 241.0,
    import_total_wh: float | None = 3_456_782.0,
    export_total_wh: float | None = 512_118.0,
    status: DeviceConnectionStatus = (DeviceConnectionStatus.ONLINE),
    error: str | None = None,
    metadata: tuple[tuple[str, str], ...] = (),
) -> DeviceSnapshot:
    values = (
        (
            Metric.GRID_POWER,
            power_w,
            MeasurementQuality.REPORTED,
        ),
        (
            Metric.GRID_IMPORT_POWER,
            import_power_w,
            MeasurementQuality.CALCULATED,
        ),
        (
            Metric.GRID_EXPORT_POWER,
            export_power_w,
            MeasurementQuality.CALCULATED,
        ),
        (
            Metric.GRID_IMPORT_TOTAL,
            import_total_wh,
            MeasurementQuality.REPORTED,
        ),
        (
            Metric.GRID_EXPORT_TOTAL,
            export_total_wh,
            MeasurementQuality.REPORTED,
        ),
    )
    measurements = tuple(
        _measurement(
            metric,
            value,
            quality=quality,
            timestamp=timestamp,
        )
        for metric, value, quality in values
        if value is not None
    )
    return DeviceSnapshot(
        source_id="grid_meter_primary",
        status=status,
        measurements=measurements,
        received_at=timestamp,
        error=error,
        metadata=metadata,
    )


def _sample(timestamp: datetime) -> dict[str, object]:
    return {
        "ts_epoch": timestamp.timestamp(),
        "ts_local": timestamp.isoformat(),
        "grid_power_w": -241.0,
        "grid_source": "Offizieller Netzstromzähler",
    }


def _context_snapshot(
    timestamp: datetime,
    **kwargs: Any,
) -> DeviceSnapshot:
    base = _snapshot(timestamp, **kwargs)
    return DeviceSnapshot(
        source_id=base.source_id,
        status=base.status,
        measurements=base.measurements,
        received_at=base.received_at,
        error=base.error,
        metadata=(
            ("source_name", "Offizieller Netzstromzähler"),
            ("adapter", "tasmota_http"),
            ("active_source_id", "grid_meter_primary"),
            ("device_time", "2026-07-24T16:20:00"),
        ),
    )


def test_schema_adds_grid_table_without_changing_samples(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "grid-schema.db")

    with database.connect() as connection:
        sample_columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        grid_columns = connection.execute(
            "PRAGMA table_info(grid_meter_samples)"
        ).fetchall()
        indexes = connection.execute("PRAGMA index_list(grid_meter_samples)").fetchall()

    assert len(sample_columns) == 48
    names = [row["name"] for row in grid_columns]
    assert names[:11] == [
        "sample_id",
        "source_id",
        "source_name",
        "adapter",
        "active_source_id",
        "device_status",
        "quality",
        "error_text",
        "measured_at",
        "received_at",
        "metadata_json",
    ]
    assert "grid_import_total_kwh" in names
    assert "grid_export_total_kwh" in names
    assert {row["name"] for row in indexes} == {
        "idx_grid_meter_samples_source_sample",
    }


def test_atomic_insert_persists_values_status_and_quality(
    tmp_path: Path,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T16:20:00+02:00")
    database = Database(tmp_path / "grid-values.db")

    sample_id = database.insert_sample_with_snapshots(
        _sample(timestamp),
        grid_meter_snapshot=_context_snapshot(timestamp),
    )
    row = database.latest_grid_meter_sample()

    assert sample_id == 1
    assert row is not None
    assert row["sample_id"] == 1
    assert row["source_id"] == "grid_meter_primary"
    assert row["source_name"] == ("Offizieller Netzstromzähler")
    assert row["adapter"] == "tasmota_http"
    assert row["active_source_id"] == ("grid_meter_primary")
    assert row["device_status"] == "online"
    assert row["quality"] == "reported"
    assert row["grid_power_w"] == pytest.approx(-241.0)
    assert row["grid_import_power_w"] == 0.0
    assert row["grid_export_power_w"] == 241.0
    assert row["grid_import_total_kwh"] == pytest.approx(3456.782)
    assert row["grid_export_total_kwh"] == pytest.approx(512.118)
    assert row["grid_import_power_quality"] == ("calculated")
    assert json.loads(row["metadata_json"])["device_time"] == "2026-07-24T16:20:00"


def test_zero_is_persisted_and_missing_values_remain_null(
    tmp_path: Path,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T16:21:00+02:00")
    database = Database(tmp_path / "grid-zero.db")
    snapshot = _context_snapshot(
        timestamp,
        power_w=0.0,
        import_power_w=0.0,
        export_power_w=0.0,
        import_total_wh=0.0,
        export_total_wh=None,
        status=DeviceConnectionStatus.DEGRADED,
        error="Export total is unavailable.",
    )

    database.insert_sample_with_snapshots(
        _sample(timestamp),
        grid_meter_snapshot=snapshot,
    )
    row = database.latest_grid_meter_sample()

    assert row is not None
    assert row["grid_power_w"] == 0.0
    assert row["grid_import_power_w"] == 0.0
    assert row["grid_export_power_w"] == 0.0
    assert row["grid_import_total_kwh"] == 0.0
    assert row["grid_export_total_kwh"] is None
    assert row["device_status"] == "degraded"
    assert row["error_text"] == ("Export total is unavailable.")


def test_grid_detail_failure_rolls_back_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T16:22:00+02:00")
    database = Database(tmp_path / "grid-rollback.db")

    def fail_insert(
        *_args: object,
        **_kwargs: object,
    ) -> None:
        raise RuntimeError("grid detail insert failed")

    monkeypatch.setattr(
        database,
        "_insert_grid_meter_snapshot",
        fail_insert,
    )

    with pytest.raises(
        RuntimeError,
        match="grid detail insert failed",
    ):
        database.insert_sample_with_snapshots(
            _sample(timestamp),
            grid_meter_snapshot=_context_snapshot(timestamp),
        )

    assert database.latest() is None
    assert database.latest_grid_meter_sample() is None


def test_delete_all_removes_grid_details(
    tmp_path: Path,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T16:23:00+02:00")
    database = Database(tmp_path / "grid-delete.db")
    database.insert_sample_with_snapshots(
        _sample(timestamp),
        grid_meter_snapshot=_context_snapshot(timestamp),
    )

    database.delete_all()

    assert database.latest() is None
    assert database.latest_grid_meter_sample() is None


class StubConfigManager:
    """Return deep copies of one collector configuration."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class SnapshotAdapter:
    """Return one prepared snapshot."""

    def __init__(self, snapshot: DeviceSnapshot) -> None:
        self.snapshot = snapshot

    def read_snapshot(self) -> DeviceSnapshot:
        return self.snapshot


class StatusCollector:
    """Expose one stable API status."""

    def __init__(self, sample: dict[str, Any]) -> None:
        self.sample = sample

    def status(self) -> dict[str, Any]:
        return {
            "running": True,
            "started_at": None,
            "cycles": 1,
            "last_error": "",
            "last_sample": dict(self.sample),
        }


def test_collector_persists_official_snapshot_context(
    tmp_path: Path,
) -> None:
    meter_time = datetime.fromisoformat("2026-07-24T16:20:00+02:00")
    collector_time = datetime.fromisoformat("2026-07-24T16:25:00+02:00")
    config = deepcopy(DEFAULT_CONFIG)
    config["grid_meter"].update(
        {
            "enabled": True,
            "host": "192.0.2.50",
            "name": "Hauptzähler",
            "adapter": "tasmota_http",
        }
    )
    database = Database(tmp_path / "collector-grid.db")
    collector = Collector(
        StubConfigManager(config),
        database,
    )
    snapshot = _snapshot(meter_time)
    collector._create_grid_meter_adapter = lambda _config: SnapshotAdapter(snapshot)
    collector._now = lambda: collector_time
    collector._monotonic = lambda: 100.0

    sample = collector.collect_once()
    row = database.latest_grid_meter_sample()

    assert sample["grid_power_w"] == -241.0
    assert row is not None
    assert row["source_name"] == "Hauptzähler"
    assert row["adapter"] == "tasmota_http"
    assert row["active_source_id"] == ("grid_meter_primary")
    assert row["received_at"] == meter_time.isoformat()


def test_live_api_exposes_grid_meter_and_active_source(
    tmp_path: Path,
) -> None:
    meter_time = datetime.fromisoformat("2026-07-24T16:20:00+02:00")
    now = datetime.fromisoformat("2026-07-24T16:25:05+02:00")
    database = Database(tmp_path / "grid-api.db")
    database.insert_sample_with_snapshots(
        _sample(meter_time),
        grid_meter_snapshot=_context_snapshot(meter_time),
    )

    payload = build_live_api_response(
        database,
        StatusCollector(_sample(meter_time)),
        now.timestamp(),
    )

    assert payload["latest"]["grid_power_w"] == -241.0
    assert payload["grid_meter"] == {
        "sample_id": 1,
        "source_id": "grid_meter_primary",
        "name": "Offizieller Netzstromzähler",
        "adapter": "tasmota_http",
        "status": "online",
        "quality": "reported",
        "last_update": meter_time.isoformat(),
        "measured_at": meter_time.isoformat(),
        "age_seconds": 305,
        "power_w": -241.0,
        "import_power_w": 0.0,
        "export_power_w": 241.0,
        "import_total_kwh": pytest.approx(3456.782),
        "export_total_kwh": pytest.approx(512.118),
        "active_source_id": "grid_meter_primary",
        "error": None,
        "metadata": {
            "active_source_id": "grid_meter_primary",
            "adapter": "tasmota_http",
            "device_time": "2026-07-24T16:20:00",
            "source_name": ("Offizieller Netzstromzähler"),
        },
    }
    assert payload["active_sources"] == {
        "grid_power": "grid_meter_primary",
        "grid_power_label": ("Offizieller Netzstromzähler"),
    }


def test_initialization_migrates_existing_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing-grid.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_epoch REAL NOT NULL,
                ts_local TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
            (100.0, "existing"),
        )
        connection.commit()

    database = Database(path)

    assert database.latest()["ts_local"] == "existing"
    with database.connect() as connection:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name = 'grid_meter_samples'
            """
        ).fetchone()
    assert table is not None
