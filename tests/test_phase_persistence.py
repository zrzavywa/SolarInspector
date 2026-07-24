"""Tests for additive and atomic Shelly phase persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.persistence.database import Database


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
        source_id="house_meter",
        role=MeasurementRole.HOUSE_METER,
        measured_at=timestamp,
        received_at=timestamp,
        quality=quality,
    )


def _snapshot(timestamp: datetime) -> DeviceSnapshot:
    measurements = (
        _measurement(
            Metric.PHASE_POWER_L1,
            100.0,
            quality=MeasurementQuality.REPORTED,
            timestamp=timestamp,
        ),
        _measurement(
            Metric.PHASE_VOLTAGE_L1,
            229.0,
            quality=MeasurementQuality.REPORTED,
            timestamp=timestamp,
        ),
        _measurement(
            Metric.PHASE_POWER_L2,
            200.0,
            quality=MeasurementQuality.SUSPECT,
            timestamp=timestamp,
        ),
        _measurement(
            Metric.PHASE_CURRENT_L2,
            0.87,
            quality=MeasurementQuality.SUSPECT,
            timestamp=timestamp,
        ),
        _measurement(
            Metric.PHASE_POWER_L3,
            300.0,
            quality=MeasurementQuality.REPORTED,
            timestamp=timestamp,
        ),
        _measurement(
            Metric.PHASE_POWER_FACTOR_L3,
            0.97,
            quality=MeasurementQuality.REPORTED,
            timestamp=timestamp,
        ),
    )
    return DeviceSnapshot(
        source_id="house_meter",
        status=DeviceConnectionStatus.DEGRADED,
        measurements=measurements,
        received_at=timestamp,
        error="L2 is invalid.",
        metadata=(
            ("measurement_role", "distribution"),
            ("phase_power_available_count", "3"),
            ("phase_power_complete", "true"),
            ("phase_power_total_source", "device"),
            ("phase_power_sum_w", "600"),
            ("phase_power_spread_w", "200"),
            ("phase_power_share_l1_pct", "16.666667"),
            ("phase_power_share_l2_pct", "33.333333"),
            ("phase_power_share_l3_pct", "50"),
            ("phase_power_total_delta_w", "10"),
            ("phase_power_total_delta_pct", "1.639344"),
            ("phase_power_total_consistent", "true"),
        ),
    )


def _sample(timestamp: datetime) -> dict[str, object]:
    return {
        "ts_epoch": timestamp.timestamp(),
        "ts_local": timestamp.isoformat(),
        "grid_power_w": 610.0,
    }


def test_new_database_adds_phase_table_without_changing_samples(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "phase-schema.db")

    with database.connect() as connection:
        sample_columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        phase_columns = connection.execute(
            "PRAGMA table_info(phase_samples)"
        ).fetchall()
        phase_indexes = connection.execute(
            "PRAGMA index_list(phase_samples)"
        ).fetchall()

    assert len(sample_columns) == 48
    assert [row["name"] for row in phase_columns][:8] == [
        "sample_id",
        "source_id",
        "measurement_role",
        "device_status",
        "error_text",
        "measured_at",
        "received_at",
        "metadata_json",
    ]
    assert "l1_power_w" in [row["name"] for row in phase_columns]
    assert "phase_power_total_consistent" in [row["name"] for row in phase_columns]
    assert {row["name"] for row in phase_indexes} == {
        "idx_phase_samples_source_sample",
        "sqlite_autoindex_phase_samples_1",
    }


def test_atomic_insert_persists_phase_values_quality_and_analysis(
    tmp_path: Path,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T10:00:00+02:00")
    database = Database(tmp_path / "phase-values.db")

    sample_id = database.insert_sample_with_phase_snapshot(
        _sample(timestamp),
        _snapshot(timestamp),
        measurement_role="distribution",
    )
    row = database.latest_phase_sample()

    assert sample_id == 1
    assert row is not None
    assert row["sample_id"] == 1
    assert row["measurement_role"] == "distribution"
    assert row["device_status"] == "degraded"
    assert row["error_text"] == "L2 is invalid."
    assert row["l1_power_w"] == pytest.approx(100.0)
    assert row["l1_voltage_v"] == pytest.approx(229.0)
    assert row["l1_quality"] == "reported"
    assert row["l2_power_w"] == pytest.approx(200.0)
    assert row["l2_current_a"] == pytest.approx(0.87)
    assert row["l2_quality"] == "suspect"
    assert row["l3_power_factor"] == pytest.approx(0.97)
    assert row["phase_power_sum_w"] == pytest.approx(600.0)
    assert row["phase_power_spread_w"] == pytest.approx(200.0)
    assert row["phase_power_total_consistent"] == 1
    assert json.loads(row["metadata_json"])["measurement_role"] == ("distribution")


def test_phase_range_is_sorted_and_source_filtered(tmp_path: Path) -> None:
    database = Database(tmp_path / "phase-range.db")
    for minute in (2, 0, 1):
        timestamp = datetime.fromisoformat(f"2026-07-24T10:0{minute}:00+02:00")
        database.insert_sample_with_phase_snapshot(
            _sample(timestamp),
            _snapshot(timestamp),
        )

    start = datetime.fromisoformat("2026-07-24T10:00:00+02:00")
    end = datetime.fromisoformat("2026-07-24T10:02:00+02:00")
    rows = database.phase_rows_between(start.timestamp(), end.timestamp())

    assert [row["ts_local"] for row in rows] == [
        "2026-07-24T10:00:00+02:00",
        "2026-07-24T10:01:00+02:00",
    ]
    assert (
        database.phase_rows_between(
            start.timestamp(),
            end.timestamp(),
            source_id="unknown",
        )
        == []
    )


def test_phase_insert_failure_rolls_back_aggregate_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T10:00:00+02:00")
    database = Database(tmp_path / "phase-rollback.db")

    def fail_insert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("phase insert failed")

    monkeypatch.setattr(database, "_insert_phase_snapshot", fail_insert)

    with pytest.raises(RuntimeError, match="phase insert failed"):
        database.insert_sample_with_phase_snapshot(
            _sample(timestamp),
            _snapshot(timestamp),
        )

    assert database.latest() is None
    assert database.latest_phase_sample() is None


def test_delete_all_removes_aggregate_and_phase_rows(tmp_path: Path) -> None:
    timestamp = datetime.fromisoformat("2026-07-24T10:00:00+02:00")
    database = Database(tmp_path / "phase-delete.db")
    database.insert_sample_with_phase_snapshot(
        _sample(timestamp),
        _snapshot(timestamp),
    )

    database.delete_all()

    assert database.latest() is None
    assert database.latest_phase_sample() is None
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM phase_samples").fetchone()[0]
    assert count == 0


def test_initialization_adds_phase_table_to_existing_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing.db"
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
            WHERE type = 'table' AND name = 'phase_samples'
            """
        ).fetchone()
    assert table is not None
