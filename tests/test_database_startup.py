"""Test schema preparation before SolarInspector services are constructed."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import solarinspector_core.persistence.startup as startup
from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.maintenance import (
    DatabaseMaintenanceError,
    inspect_database,
)
from solarinspector_core.persistence.migrations import (
    apply_migrations,
    get_current_version,
)
from solarinspector_core.persistence.startup import (
    DatabaseStartupError,
    prepare_database_for_startup,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "database"


def _legacy_database(tmp_path: Path, name: str = "legacy") -> Path:
    path = tmp_path / f"{name}.db"
    with closing(sqlite3.connect(path)) as connection:
        for fixture in ("legacy_v3", "legacy_4_1"):
            connection.executescript(
                (FIXTURE_DIRECTORY / f"{fixture}.sql").read_text(encoding="utf-8")
            )
    return path


def _current_database(tmp_path: Path, name: str = "current") -> Path:
    path = tmp_path / f"{name}.db"
    database = Database(path)
    with database.connect() as connection:
        apply_migrations(connection, application_version="4.5.0")
    return path


def test_missing_database_is_initialized_backed_up_and_migrated(
    tmp_path: Path,
) -> None:
    database = tmp_path / "new" / "solarinspector.db"

    result = prepare_database_for_startup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
    )

    assert result.created is True
    assert result.previous_schema_version == 0
    assert result.current_schema_version == 2
    assert result.applied_migration_versions == (1, 2)
    assert result.backup_path is not None
    assert result.backup_path.is_file()
    assert inspect_database(database).table_counts["samples"] == 0


def test_legacy_database_is_backed_up_before_migration(tmp_path: Path) -> None:
    database = _legacy_database(tmp_path)

    result = prepare_database_for_startup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
    )

    assert result.created is False
    assert result.previous_schema_version == 0
    assert result.current_schema_version == 2
    assert result.backup_path is not None
    assert inspect_database(result.backup_path).current_schema_version == 0
    assert inspect_database(result.backup_path).table_counts["samples"] == 2
    assert inspect_database(database).table_counts["samples"] == 2


def test_current_database_is_verified_without_backup_or_writes(
    tmp_path: Path,
) -> None:
    database = _current_database(tmp_path)
    before = database.read_bytes()

    first = prepare_database_for_startup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
    )
    second = prepare_database_for_startup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
    )

    assert first.applied_migration_versions == ()
    assert first.backup_path is None
    assert second.applied_migration_versions == ()
    assert not (tmp_path / "backups").exists()
    assert database.read_bytes() == before


def test_phase_09_intermediate_schema_is_recognized(tmp_path: Path) -> None:
    database = tmp_path / "phase09.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            (FIXTURE_DIRECTORY / "phase_09.sql").read_text(encoding="utf-8")
        )

    result = prepare_database_for_startup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
    )

    assert result.applied_migration_versions == (1, 2)
    with closing(sqlite3.connect(database)) as connection:
        assert get_current_version(connection) == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM energy_balance_samples"
            ).fetchone()[0]
            == 1
        )


def test_unknown_newer_schema_refuses_startup_without_backup(
    tmp_path: Path,
) -> None:
    database = _current_database(tmp_path, "newer")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """
            INSERT INTO schema_migrations (
                version, applied_at, description, application_version, checksum
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (3, "2026-07-26T20:00:00+00:00", "future", "5.0.0", "future"),
        )
        connection.commit()

    with pytest.raises(DatabaseStartupError, match="newer than supported"):
        prepare_database_for_startup(
            database,
            tmp_path / "backups",
            application_version="4.5.0",
        )

    assert not (tmp_path / "backups").exists()
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[
                0
            ]
            == 3
        )


def test_failed_migration_is_reported_once_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _legacy_database(tmp_path, "failure")
    calls = 0

    def fail_once(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        callback = _kwargs.get("backup_created")
        assert callable(callback)
        callback(tmp_path / "backups" / "verified.db")
        raise DatabaseMaintenanceError("synthetic startup failure")

    monkeypatch.setattr(startup, "migrate_database_with_backup", fail_once)

    with pytest.raises(
        DatabaseStartupError,
        match=r"synthetic startup failure.*verified\.db",
    ):
        prepare_database_for_startup(
            database,
            tmp_path / "backups",
            application_version="4.5.0",
        )

    assert calls == 1
    assert inspect_database(database).current_schema_version == 0


def test_application_import_constructs_collector_only_after_target_schema() -> None:
    import solarinspector as application

    assert application.database_startup.current_schema_version == 2
    assert application.collector.database is application.database
    with application.database.connect() as connection:
        assert get_current_version(connection) == 2
