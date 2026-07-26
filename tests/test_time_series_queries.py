"""Tests for bounded and indexed time-series reads."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from zrzavy_energy_monitor_core.persistence.database import Database
from zrzavy_energy_monitor_core.persistence.migrations import apply_migrations
from zrzavy_energy_monitor_core.persistence.queries import (
    HARD_MAXIMUM_QUERY_ROWS,
    get_energy_balance_series,
    get_grid_series,
    get_latest_measurement,
    get_measurement_series,
    get_phase_series,
    get_source_selection_events,
    get_validation_events,
)

START = datetime(2026, 7, 26, 8, tzinfo=timezone.utc)


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    """Create a migrated database containing representative history."""

    database = Database(tmp_path / "queries.db")
    with database.connect() as setup:
        apply_migrations(setup, application_version="4.5.0")
        for offset in range(3):
            measured_at = START + timedelta(minutes=offset)
            cursor = setup.execute(
                """
                INSERT INTO samples (ts_epoch, ts_local)
                VALUES (?, ?)
                """,
                (measured_at.timestamp(), measured_at.isoformat()),
            )
            sample_id = int(cursor.lastrowid or 0)
            setup.execute(
                """
                INSERT INTO measurements (
                    sample_id, source_id, role, metric, value, unit,
                    measured_at, received_at, quality, device_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    "grid-main",
                    "grid",
                    "grid_power",
                    float(offset),
                    "W",
                    measured_at.isoformat(),
                    measured_at.isoformat(),
                    "measured",
                    "available",
                ),
            )
            setup.execute(
                """
                INSERT INTO phase_samples (
                    sample_id, source_id, measurement_role, device_status,
                    measured_at, received_at, l1_power_w
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    "shelly",
                    "house_total",
                    "available",
                    measured_at.isoformat(),
                    measured_at.isoformat(),
                    float(offset),
                ),
            )
            setup.execute(
                """
                INSERT INTO grid_meter_samples (
                    sample_id, source_id, source_name, adapter, device_status,
                    measured_at, received_at, grid_power_w
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    "grid-main",
                    "Grid",
                    "test",
                    "available",
                    measured_at.isoformat(),
                    measured_at.isoformat(),
                    float(offset),
                ),
            )
            setup.execute(
                """
                INSERT INTO energy_balance_samples (
                    sample_id, calculated_at, quality, house_power_w
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    sample_id,
                    measured_at.isoformat(),
                    "complete",
                    float(offset),
                ),
            )
            setup.execute(
                """
                INSERT INTO source_selection_events (
                    sample_id, selected_at, metric, selected_source_id,
                    selected_source_role, selected_quality, fallback_used,
                    selection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    measured_at.isoformat(),
                    "grid_power",
                    "grid-main",
                    "grid",
                    "measured",
                    0,
                    "preferred_source",
                ),
            )
        setup.execute(
            """
            INSERT INTO validation_events (
                first_seen_epoch, first_seen_local, last_seen_epoch,
                last_seen_local, source_id, role, metric, unit, rule_id,
                finding_code, severity, decision, quality, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                START.timestamp(),
                START.isoformat(),
                (START + timedelta(minutes=1)).timestamp(),
                (START + timedelta(minutes=1)).isoformat(),
                "grid-main",
                "grid",
                "grid_power",
                "W",
                "range",
                "high",
                "warning",
                "accept",
                "suspect",
                "test",
            ),
        )
        setup.commit()
    opened = sqlite3.connect(database.path)
    opened.row_factory = sqlite3.Row
    try:
        yield opened
    finally:
        opened.close()


def test_measurement_queries_are_ordered_bounded_and_half_open(
    connection: sqlite3.Connection,
) -> None:
    rows = get_measurement_series(
        connection,
        "grid_power",
        START,
        START + timedelta(minutes=2),
        maximum_rows=1,
    )

    assert [row["value"] for row in rows] == [0.0]
    assert get_latest_measurement(connection, "grid-main", "grid_power")["value"] == 2.0  # type: ignore[index]
    assert get_latest_measurement(connection, "missing", "grid_power") is None


def test_detail_and_event_queries_return_controlled_results(
    connection: sqlite3.Connection,
) -> None:
    end = START + timedelta(minutes=2)

    assert len(get_phase_series(connection, START, end)) == 2
    assert len(get_grid_series(connection, START, end)) == 2
    assert len(get_energy_balance_series(connection, START, end)) == 2
    assert (
        len(
            get_validation_events(
                connection,
                START,
                end,
                source_id="grid-main",
                metric="grid_power",
            )
        )
        == 1
    )
    assert (
        len(get_source_selection_events(connection, START, end, metric="grid_power"))
        == 2
    )
    assert get_source_selection_events(connection, START, end, metric="pv_power") == []


@pytest.mark.parametrize(
    ("start", "end", "maximum_rows"),
    [
        (START.replace(tzinfo=None), START + timedelta(minutes=1), 10),
        (START, START, 10),
        (START + timedelta(minutes=1), START, 10),
        (START, START + timedelta(minutes=1), 0),
        (START, START + timedelta(minutes=1), HARD_MAXIMUM_QUERY_ROWS + 1),
        (START, START + timedelta(minutes=1), True),
    ],
)
def test_invalid_ranges_and_limits_are_rejected(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    maximum_rows: int,
) -> None:
    with pytest.raises(ValueError):
        get_measurement_series(
            connection,
            "grid_power",
            start,
            end,
            maximum_rows=maximum_rows,
        )


def test_representative_queries_use_time_series_indexes(
    connection: sqlite3.Connection,
) -> None:
    measurement_plan = _query_plan(
        connection,
        """
        SELECT id FROM measurements
        WHERE source_id = ? AND metric = ?
        ORDER BY measured_at DESC LIMIT 1
        """,
        ("grid-main", "grid_power"),
    )
    selection_plan = _query_plan(
        connection,
        """
        SELECT id FROM source_selection_events
        WHERE metric = ? AND selected_at >= ? AND selected_at < ?
        ORDER BY selected_at LIMIT ?
        """,
        (
            "grid_power",
            START.isoformat(),
            (START + timedelta(hours=1)).isoformat(),
            100,
        ),
    )
    balance_plan = _query_plan(
        connection,
        """
        SELECT b.sample_id FROM samples AS s
        JOIN energy_balance_samples AS b ON b.sample_id = s.id
        WHERE s.ts_epoch >= ? AND s.ts_epoch < ?
        ORDER BY s.ts_epoch LIMIT ?
        """,
        (START.timestamp(), (START + timedelta(hours=1)).timestamp(), 100),
    )

    assert "idx_measurements_source_metric_measured_at" in measurement_plan
    assert "idx_source_selection_events_metric_selected_at" in selection_plan
    assert "idx_samples_ts_epoch" in balance_plan


def _query_plan(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...],
) -> str:
    rows = connection.execute(f"EXPLAIN QUERY PLAN {sql}", parameters).fetchall()
    return "\n".join(str(row["detail"]) for row in rows)
