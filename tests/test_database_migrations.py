"""Test version planning and verification for the Phase 10 SQLite schema."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.migrations import (
    SchemaVerificationError,
    UnsupportedSchemaVersionError,
    apply_migrations,
    get_current_version,
    get_target_version,
    plan_migrations,
    verify_schema,
)

APPLIED_AT = datetime(2026, 7, 26, 18, 0, tzinfo=timezone.utc)


def test_unversioned_phase_09_schema_is_stamped_and_verified(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "phase-09.db")

    with database.connect() as connection:
        assert get_current_version(connection) == 0

        applied = apply_migrations(
            connection,
            application_version="4.5.0",
            applied_at=APPLIED_AT,
        )

        verify_schema(connection)
        rows = connection.execute(
            """
            SELECT version, applied_at, description, application_version,
                   length(checksum)
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()

    assert [migration.version for migration in applied] == [1, 2]
    assert [tuple(row) for row in rows] == [
        (
            1,
            "2026-07-26T18:00:00+00:00",
            "Migrate known unversioned schemas to the Phase 09 baseline.",
            "4.5.0",
            64,
        ),
        (
            2,
            "2026-07-26T18:00:00+00:00",
            "Add normalized measurements and source-selection events.",
            "4.5.0",
            64,
        ),
    ]


def test_migration_is_idempotent_for_verified_schema(tmp_path: Path) -> None:
    database = Database(tmp_path / "current.db")

    with database.connect() as connection:
        first = apply_migrations(connection, application_version="4.5.0")
        second = apply_migrations(connection, application_version="4.5.0")
        row_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

    assert len(first) == 2
    assert second == ()
    assert row_count == 2


def test_incomplete_schema_rolls_back_version_ledger() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(
            SchemaVerificationError,
            match="missing columns",
        ):
            apply_migrations(connection, application_version="4.5.0")

        table = connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
    finally:
        connection.close()

    assert table is None


def test_unknown_newer_version_is_rejected_without_changes(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "newer.db")

    with database.connect() as connection:
        apply_migrations(connection, application_version="4.5.0")
        connection.execute(
            """
            INSERT INTO schema_migrations (
                version, applied_at, description, application_version, checksum
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (3, APPLIED_AT.isoformat(), "Future schema", "4.6.0", "future"),
        )
        connection.commit()

        with pytest.raises(
            UnsupportedSchemaVersionError,
            match="newer than supported",
        ):
            get_current_version(connection)

        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]

    assert versions == [1, 2, 3]


def test_tampered_migration_checksum_is_rejected(tmp_path: Path) -> None:
    database = Database(tmp_path / "tampered.db")

    with database.connect() as connection:
        apply_migrations(connection, application_version="4.5.0")
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
            ("changed",),
        )
        connection.commit()

        with pytest.raises(
            SchemaVerificationError,
            match="does not match",
        ):
            verify_schema(connection)


def test_planner_validates_version_range() -> None:
    assert get_target_version() == 2
    assert [migration.version for migration in plan_migrations(0)] == [1, 2]
    assert [migration.version for migration in plan_migrations(1)] == [2]
    assert plan_migrations(2) == ()

    with pytest.raises(ValueError, match="must not be negative"):
        plan_migrations(-1)
    with pytest.raises(
        UnsupportedSchemaVersionError,
        match="newer than supported",
    ):
        plan_migrations(3)


def test_migration_rejects_naive_timestamp_before_writing(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "naive.db")

    with database.connect() as connection:
        with pytest.raises(ValueError, match="timezone-aware"):
            apply_migrations(
                connection,
                application_version="4.5.0",
                applied_at=datetime(2026, 7, 26, 18, 0),
            )

        assert get_current_version(connection) == 0
