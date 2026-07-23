"""Characterization tests for the SolarInspector SQLite persistence layer."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import solarinspector as si

EXPECTED_COLUMNS = [
    "id",
    "ts_epoch",
    "ts_local",
    "grid_power_w",
    "solar_power_w",
    "house_power_w",
    "grid_import_w",
    "feed_in_w",
    "self_consumption_w",
    "voltage_v",
    "current_a",
    "power_factor",
    "frequency_hz",
    "grid_import_wh",
    "feed_in_wh",
    "solar_wh",
    "house_wh",
    "self_consumption_wh",
    "house_ok",
    "solar_ok",
    "error_text",
    "shelly_solar_power_w",
    "solakon_pv_power_w",
    "solakon_ac_power_w",
    "solakon_battery_power_w",
    "solakon_battery_soc_pct",
    "solakon_load_power_w",
    "solakon_meter_power_w",
    "solakon_temperature_c",
    "solakon_daily_pv_kwh",
    "solakon_total_pv_kwh",
    "solakon_pv1_power_w",
    "solakon_pv2_power_w",
    "solakon_pv3_power_w",
    "solakon_pv4_power_w",
    "solar_difference_w",
    "solar_difference_pct",
    "solar_source",
    "grid_source",
    "solakon_model",
    "solakon_serial",
    "solakon_status",
    "solakon_ok",
    "shelly_solar_wh",
    "solakon_pv_wh",
    "solakon_ac_wh",
    "battery_charge_wh",
    "battery_discharge_wh",
]

ENERGY_DEFAULT_COLUMNS = [
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
]

STATUS_DEFAULT_COLUMNS = [
    "house_ok",
    "solar_ok",
    "solakon_ok",
]


def minimal_sample(
    ts_epoch: float,
    ts_local: str,
    **values: Any,
) -> dict[str, Any]:
    """Create the smallest sample accepted by the current schema."""
    sample: dict[str, Any] = {
        "ts_epoch": ts_epoch,
        "ts_local": ts_local,
    }
    sample.update(values)
    return sample


def test_new_database_has_current_schema_index_and_wal(
    tmp_path: Path,
) -> None:
    """A new database is initialized with 48 columns and the timestamp index."""
    database = si.Database(tmp_path / "schema.db")

    with database.connect() as connection:
        columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        indexes = connection.execute("PRAGMA index_list(samples)").fetchall()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert [row["name"] for row in columns] == EXPECTED_COLUMNS
    assert len(columns) == 48
    assert journal_mode == "wal"
    assert [row["name"] for row in indexes] == ["idx_samples_ts_epoch"]


def test_energy_and_status_columns_have_zero_defaults(
    tmp_path: Path,
) -> None:
    """Energy counters and status flags are non-null columns defaulting to zero."""
    database = si.Database(tmp_path / "defaults.db")

    with database.connect() as connection:
        schema = {
            row["name"]: row for row in connection.execute("PRAGMA table_info(samples)")
        }

    for name in ENERGY_DEFAULT_COLUMNS + STATUS_DEFAULT_COLUMNS:
        assert schema[name]["notnull"] == 1
        assert schema[name]["dflt_value"] == "0"


def test_minimal_insert_uses_schema_defaults(
    tmp_path: Path,
) -> None:
    """A sample containing only required timestamps receives database defaults."""
    database = si.Database(tmp_path / "minimal.db")

    sample_id = database.insert_sample(
        minimal_sample(
            100.0,
            "2026-07-23T12:00:00+02:00",
        )
    )
    row = database.latest()

    assert sample_id == 1
    assert row is not None
    assert row["id"] == 1
    assert row["ts_epoch"] == 100.0
    assert row["grid_power_w"] is None

    for name in ENERGY_DEFAULT_COLUMNS + STATUS_DEFAULT_COLUMNS:
        assert row[name] == 0


def test_insert_returns_incrementing_ids(
    tmp_path: Path,
) -> None:
    """Each successful insert returns SQLite's generated row identifier."""
    database = si.Database(tmp_path / "ids.db")

    first = database.insert_sample(
        minimal_sample(
            100.0,
            "2026-07-23T12:00:00+02:00",
        )
    )
    second = database.insert_sample(
        minimal_sample(
            200.0,
            "2026-07-23T12:01:00+02:00",
        )
    )

    assert first == 1
    assert second == 2


def test_latest_uses_timestamp_not_insert_order(
    tmp_path: Path,
) -> None:
    """latest selects the greatest ts_epoch even when inserted earlier."""
    database = si.Database(tmp_path / "latest.db")
    database.insert_sample(
        minimal_sample(
            300.0,
            "2026-07-23T12:03:00+02:00",
            solar_source="Newest timestamp",
        )
    )
    database.insert_sample(
        minimal_sample(
            100.0,
            "2026-07-23T12:01:00+02:00",
            solar_source="Last inserted",
        )
    )

    latest = database.latest()

    assert latest is not None
    assert latest["ts_epoch"] == 300.0
    assert latest["solar_source"] == "Newest timestamp"


def test_rows_between_is_lower_inclusive_upper_exclusive_and_sorted(
    tmp_path: Path,
) -> None:
    """Range reads include the lower bound, exclude the upper, and sort by time."""
    database = si.Database(tmp_path / "range.db")

    for timestamp in (30.0, 10.0, 20.0, 40.0):
        database.insert_sample(
            minimal_sample(
                timestamp,
                f"sample-{timestamp}",
            )
        )

    rows = database.rows_between(10.0, 40.0)

    assert [row["ts_epoch"] for row in rows] == [
        10.0,
        20.0,
        30.0,
    ]


def test_empty_database_latest_rows_and_stats(
    tmp_path: Path,
) -> None:
    """Empty persistence queries return neutral current results."""
    database = si.Database(tmp_path / "empty.db")

    assert database.latest() is None
    assert database.rows_between(0.0, 100.0) == []

    stats = database.stats()
    assert stats["count"] == 0
    assert stats["first_epoch"] is None
    assert stats["last_epoch"] is None
    assert stats["db_size_bytes"] > 0


def test_stats_report_count_time_bounds_and_file_size(
    tmp_path: Path,
) -> None:
    """Statistics use minimum and maximum timestamps across all rows."""
    database = si.Database(tmp_path / "stats.db")

    for timestamp in (300.0, 100.0, 200.0):
        database.insert_sample(
            minimal_sample(
                timestamp,
                f"sample-{timestamp}",
            )
        )

    stats = database.stats()

    assert stats["count"] == 3
    assert stats["first_epoch"] == 100.0
    assert stats["last_epoch"] == 300.0
    assert stats["db_size_bytes"] > 0


def test_v3_style_schema_migration_preserves_existing_row(
    tmp_path: Path,
) -> None:
    """Adding current columns does not remove data from a prior base schema."""
    path = tmp_path / "legacy.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_epoch REAL NOT NULL,
                ts_local TEXT NOT NULL,
                grid_power_w REAL,
                solar_power_w REAL,
                house_power_w REAL,
                grid_import_w REAL,
                feed_in_w REAL,
                self_consumption_w REAL,
                voltage_v REAL,
                current_a REAL,
                power_factor REAL,
                frequency_hz REAL,
                grid_import_wh REAL NOT NULL DEFAULT 0,
                feed_in_wh REAL NOT NULL DEFAULT 0,
                solar_wh REAL NOT NULL DEFAULT 0,
                house_wh REAL NOT NULL DEFAULT 0,
                self_consumption_wh REAL NOT NULL DEFAULT 0,
                house_ok INTEGER NOT NULL DEFAULT 0,
                solar_ok INTEGER NOT NULL DEFAULT 0,
                error_text TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO samples (
                ts_epoch,
                ts_local,
                grid_power_w,
                solar_wh
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                123.0,
                "legacy-row",
                456.0,
                7.5,
            ),
        )
        connection.commit()

    database = si.Database(path)
    row = database.latest()

    assert row is not None
    assert row["ts_local"] == "legacy-row"
    assert row["grid_power_w"] == 456.0
    assert row["solar_wh"] == 7.5
    assert row["solakon_pv_power_w"] is None
    assert row["solakon_pv_wh"] == 0
    assert row["battery_discharge_wh"] == 0

    with database.connect() as connection:
        columns = [
            item["name"] for item in connection.execute("PRAGMA table_info(samples)")
        ]

    assert columns == EXPECTED_COLUMNS


def test_initialize_is_idempotent(
    tmp_path: Path,
) -> None:
    """Reopening the same database preserves rows and does not duplicate schema."""
    path = tmp_path / "idempotent.db"
    first = si.Database(path)
    first.insert_sample(
        minimal_sample(
            100.0,
            "persisted",
        )
    )

    second = si.Database(path)

    assert second.stats()["count"] == 1
    assert second.latest() is not None

    with second.connect() as connection:
        columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        indexes = connection.execute("PRAGMA index_list(samples)").fetchall()

    assert len(columns) == 48
    assert [row["name"] for row in indexes] == ["idx_samples_ts_epoch"]


def test_delete_all_empties_database_and_keeps_it_reusable(
    tmp_path: Path,
) -> None:
    """delete_all removes samples but leaves the schema usable for new inserts."""
    database = si.Database(tmp_path / "delete.db")
    database.insert_sample(
        minimal_sample(
            100.0,
            "first",
        )
    )
    database.insert_sample(
        minimal_sample(
            200.0,
            "second",
        )
    )

    database.delete_all()

    assert database.latest() is None
    assert database.stats()["count"] == 0

    new_id = database.insert_sample(
        minimal_sample(
            300.0,
            "after-delete",
        )
    )

    assert new_id == 3
    assert database.stats()["count"] == 1
    assert database.latest()["ts_local"] == "after-delete"


def test_insert_missing_required_timestamp_raises_integrity_error(
    tmp_path: Path,
) -> None:
    """SQLite rejects samples that omit a required timestamp column."""
    database = si.Database(tmp_path / "invalid.db")

    with pytest.raises(sqlite3.IntegrityError):
        database.insert_sample(
            {
                "ts_epoch": 100.0,
            }
        )
