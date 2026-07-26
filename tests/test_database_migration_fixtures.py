"""Validate synthetic SQLite inputs for Phase 10 migration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from solarinspector_core.persistence.migrations import (
    apply_migrations,
    get_current_version,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "database"
FIXTURE_CHAINS = {
    "legacy_v3": ("legacy_v3",),
    "legacy_4_1": ("legacy_v3", "legacy_4_1"),
    "phase_05": ("legacy_v3", "legacy_4_1", "phase_05"),
    "phase_06_07": (
        "legacy_v3",
        "legacy_4_1",
        "phase_05",
        "phase_06_07",
    ),
    "phase_08": (
        "legacy_v3",
        "legacy_4_1",
        "phase_05",
        "phase_06_07",
        "phase_08",
    ),
    "phase_09": ("phase_09",),
}


@pytest.fixture(scope="module")
def expectations() -> dict[str, Any]:
    """Load the documented machine-readable fixture expectations."""

    return json.loads((FIXTURE_DIRECTORY / "expected.json").read_text(encoding="utf-8"))


def _build_database(tmp_path: Path, fixture_name: str) -> sqlite3.Connection:
    """Build an isolated SQLite database from a reviewed fixture script."""

    database_path = tmp_path / f"{fixture_name}.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    for script_name in FIXTURE_CHAINS[fixture_name]:
        script = (FIXTURE_DIRECTORY / f"{script_name}.sql").read_text(encoding="utf-8")
        connection.executescript(script)
    return connection


def _application_tables(connection: sqlite3.Connection) -> list[str]:
    """Return sorted application table names without SQLite internals."""

    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]


def _assert_integrity(connection: sqlite3.Connection) -> None:
    """Assert SQLite structural and foreign-key integrity."""

    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_legacy_v3_fixture_matches_characterized_schema_and_values(
    tmp_path: Path,
    expectations: dict[str, Any],
) -> None:
    expected = expectations["legacy_v3"]
    connection = _build_database(tmp_path, "legacy_v3")
    try:
        _assert_integrity(connection)
        columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        rows = connection.execute("SELECT * FROM samples ORDER BY ts_epoch").fetchall()
        schema_version = get_current_version(connection)
    finally:
        connection.close()

    assert (
        _application_tables_from_path(tmp_path / "legacy_v3.db") == expected["tables"]
    )
    assert len(columns) == expected["sample_columns"]
    assert len(rows) == expected["row_counts"]["samples"]
    assert schema_version == expected["schema_version"]
    values = expected["preserved_values"]
    assert rows[0]["grid_power_w"] == values["first_grid_power_w"]
    assert rows[1]["grid_power_w"] == values["second_grid_power_w"]
    assert rows[1]["voltage_v"] is values["second_voltage_v"]
    assert rows[1]["grid_import_wh"] == values["second_grid_import_wh"]
    assert rows[1]["feed_in_wh"] == values["second_feed_in_wh"]


def test_legacy_4_1_fixture_has_characterized_48_column_schema(
    tmp_path: Path,
    expectations: dict[str, Any],
) -> None:
    expected = expectations["legacy_4_1"]
    connection = _build_database(tmp_path, "legacy_4_1")
    try:
        _assert_integrity(connection)
        columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        second_row = connection.execute("SELECT * FROM samples WHERE id = 2").fetchone()
    finally:
        connection.close()

    assert len(columns) == expected["sample_columns"]
    assert second_row["solakon_pv_power_w"] is None
    assert (
        second_row["battery_charge_wh"]
        == expected["preserved_values"]["second_battery_charge_wh"]
    )


def test_phase_09_fixture_matches_all_tables_and_values(
    tmp_path: Path,
    expectations: dict[str, Any],
) -> None:
    expected = expectations["phase_09"]
    connection = _build_database(tmp_path, "phase_09")
    try:
        _assert_integrity(connection)
        assert _application_tables(connection) == expected["tables"]
        assert get_current_version(connection) == expected["schema_version"]
        assert (
            len(connection.execute("PRAGMA table_info(samples)").fetchall())
            == expected["sample_columns"]
        )
        for table_name, row_count in expected["row_counts"].items():
            actual_count = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            assert actual_count == row_count

        grid_row = connection.execute(
            """
            SELECT grid_import_total_kwh, grid_export_total_kwh
            FROM grid_meter_samples
            """
        ).fetchone()
        balance_row = connection.execute(
            """
            SELECT house_power_w, grid_export_power_w
            FROM energy_balance_samples
            """
        ).fetchone()
        validation_row = connection.execute(
            "SELECT accepted_value FROM validation_events"
        ).fetchone()
    finally:
        connection.close()

    values = expected["preserved_values"]
    assert grid_row["grid_import_total_kwh"] == values["grid_import_total_kwh"]
    assert grid_row["grid_export_total_kwh"] == values["grid_export_total_kwh"]
    assert balance_row["house_power_w"] == values["energy_balance_house_power_w"]
    assert (
        balance_row["grid_export_power_w"]
        == values["energy_balance_grid_export_power_w"]
    )
    assert validation_row["accepted_value"] == values["validation_accepted_value"]


def test_phase_09_fixture_can_be_stamped_without_domain_changes(
    tmp_path: Path,
    expectations: dict[str, Any],
) -> None:
    expected = expectations["phase_09"]
    connection = _build_database(tmp_path, "phase_09")
    try:
        before_counts = {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in expected["row_counts"]
        }

        applied = apply_migrations(
            connection,
            application_version="4.5.0",
        )

        after_counts = {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in expected["row_counts"]
        }
        integrity_result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()

    assert [migration.version for migration in applied] == [1, 2]
    assert before_counts == after_counts == expected["row_counts"]
    assert integrity_result == "ok"


def test_legacy_fixture_migrates_without_inventing_values(
    tmp_path: Path,
    expectations: dict[str, Any],
) -> None:
    expected = expectations["legacy_4_1"]
    connection = _build_database(tmp_path, "legacy_4_1")
    try:
        before_rows = connection.execute(
            """
            SELECT id, ts_epoch, ts_local, grid_power_w, grid_import_wh,
                   feed_in_wh
            FROM samples
            ORDER BY id
            """
        ).fetchall()

        applied = apply_migrations(
            connection,
            application_version="4.5.0",
        )

        after_rows = connection.execute(
            """
            SELECT id, ts_epoch, ts_local, grid_power_w, grid_import_wh,
                   feed_in_wh, solakon_pv_power_w, battery_charge_wh
            FROM samples
            ORDER BY id
            """
        ).fetchall()
        finding_count = connection.execute(
            "SELECT COUNT(*) FROM migration_findings"
        ).fetchone()[0]
        integrity_result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        migrated_tables = _application_tables(connection)
    finally:
        connection.close()

    assert [migration.version for migration in applied] == [1, 2]
    assert _get_current_version_from_path(tmp_path / "legacy_4_1.db") == 2
    assert len(after_rows) == expected["row_counts"]["samples"]
    for before_row, after_row in zip(before_rows, after_rows, strict=True):
        assert tuple(after_row[:6]) == tuple(before_row)
        assert after_row["solakon_pv_power_w"] is None
        assert (
            after_row["battery_charge_wh"]
            == expected["preserved_values"]["second_battery_charge_wh"]
        )
    assert finding_count == 0
    assert integrity_result == "ok"
    assert migrated_tables == [
        "energy_balance_samples",
        "grid_meter_samples",
        "measurements",
        "migration_findings",
        "phase_samples",
        "samples",
        "schema_migrations",
        "source_selection_events",
        "validation_events",
    ]


def test_legacy_v3_migration_adds_later_values_as_null(
    tmp_path: Path,
) -> None:
    connection = _build_database(tmp_path, "legacy_v3")
    try:
        apply_migrations(connection, application_version="4.5.0")
        row = connection.execute(
            """
            SELECT grid_power_w, grid_import_wh, solakon_pv_power_w,
                   battery_charge_wh
            FROM samples
            WHERE id = 1
            """
        ).fetchone()
    finally:
        connection.close()

    assert row["grid_power_w"] == 250.0
    assert row["grid_import_wh"] == 0.35
    assert row["solakon_pv_power_w"] is None
    assert row["battery_charge_wh"] is None


def test_legacy_migration_records_unknown_column_and_timestamp_findings(
    tmp_path: Path,
) -> None:
    connection = _build_database(tmp_path, "legacy_4_1")
    try:
        connection.execute("ALTER TABLE samples ADD COLUMN legacy_extra TEXT")
        connection.execute(
            "UPDATE samples SET ts_local = ? WHERE id = ?",
            ("legacy-local-time", 2),
        )
        connection.commit()

        apply_migrations(connection, application_version="4.5.0")

        findings = connection.execute(
            """
            SELECT finding_code, column_name, source_row_id, details_json
            FROM migration_findings
            ORDER BY finding_code
            """
        ).fetchall()
        preserved_value = connection.execute(
            "SELECT legacy_extra, ts_local FROM samples WHERE id = 2"
        ).fetchone()
    finally:
        connection.close()

    assert [row["finding_code"] for row in findings] == [
        "uninterpretable_legacy_timestamp",
        "unknown_legacy_column",
    ]
    assert findings[0]["column_name"] == "ts_local"
    assert findings[0]["source_row_id"] == 2
    assert findings[1]["column_name"] == "legacy_extra"
    assert findings[1]["source_row_id"] is None
    assert preserved_value["legacy_extra"] is None
    assert preserved_value["ts_local"] == "legacy-local-time"


def test_legacy_migration_rolls_back_all_changes_after_verification_failure(
    tmp_path: Path,
) -> None:
    connection = _build_database(tmp_path, "legacy_4_1")
    try:
        connection.execute("CREATE TABLE phase_samples (legacy INTEGER)")
        connection.commit()
        before_columns = connection.execute("PRAGMA table_info(samples)").fetchall()

        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            apply_migrations(connection, application_version="4.5.0")

        after_columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        migration_tables = connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table'
              AND name IN ('schema_migrations', 'migration_findings')
            """
        ).fetchall()
        sample_count = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    finally:
        connection.close()

    assert [row["name"] for row in after_columns] == [
        row["name"] for row in before_columns
    ]
    assert migration_tables == []
    assert sample_count == 2


@pytest.mark.parametrize("fixture_name", ("phase_05", "phase_06_07", "phase_08"))
def test_intermediate_fixture_migrates_idempotently_without_duplicate_rows(
    tmp_path: Path,
    expectations: dict[str, Any],
    fixture_name: str,
) -> None:
    expected = expectations[fixture_name]
    connection = _build_database(tmp_path, fixture_name)
    try:
        assert _application_tables(connection) == expected["tables"]
        before_counts = {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in expected["row_counts"]
        }

        first_applied = apply_migrations(
            connection,
            application_version="4.5.0",
        )
        second_applied = apply_migrations(
            connection,
            application_version="4.5.0",
        )

        after_counts = {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in expected["row_counts"]
        }
        migration_finding_count = connection.execute(
            "SELECT COUNT(*) FROM migration_findings"
        ).fetchone()[0]
        integrity_result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        schema_version = get_current_version(connection)
    finally:
        connection.close()

    assert [migration.version for migration in first_applied] == [1, 2]
    assert second_applied == ()
    assert before_counts == after_counts == expected["row_counts"]
    assert migration_finding_count == 0
    assert integrity_result == "ok"
    assert schema_version == 2


def test_empty_database_fixture_has_no_application_objects(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "empty.db"
    connection = sqlite3.connect(database_path)
    try:
        _assert_integrity(connection)
        assert _application_tables(connection) == []
    finally:
        connection.close()


def _application_tables_from_path(database_path: Path) -> list[str]:
    """Read application tables from a closed fixture database."""

    connection = sqlite3.connect(database_path)
    try:
        return _application_tables(connection)
    finally:
        connection.close()


def _get_current_version_from_path(database_path: Path) -> int:
    """Read the application schema version from a closed fixture database."""

    connection = sqlite3.connect(database_path)
    try:
        return get_current_version(connection)
    finally:
        connection.close()
