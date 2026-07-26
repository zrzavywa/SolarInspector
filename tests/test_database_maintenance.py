"""Test safe Phase 10 database backup and migration orchestration."""

from __future__ import annotations

import hashlib
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import pytest
import solarinspector_core.persistence.maintenance as maintenance
from database_cli import EXIT_OPERATION_FAILED, main
from solarinspector_core.persistence.maintenance import (
    DatabaseMaintenanceError,
    create_database_backup,
    dry_run_database_migration,
    inspect_database,
    migrate_database_with_backup,
)
from solarinspector_core.persistence.migrations import get_current_version

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "database"
CREATED_AT = datetime(2026, 7, 26, 20, 15, 30, tzinfo=timezone.utc)


def _legacy_database(tmp_path: Path) -> Path:
    """Create an isolated synthetic SolarInspector 4.1.3 database."""

    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as connection:
        for name in ("legacy_v3", "legacy_4_1"):
            connection.executescript(
                (FIXTURE_DIRECTORY / f"{name}.sql").read_text(encoding="utf-8")
            )
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_only_inspection_reports_integrity_plan_and_counts(
    tmp_path: Path,
) -> None:
    database = _legacy_database(tmp_path)
    before = (_digest(database), database.stat().st_mtime_ns)

    inspection = inspect_database(database)

    assert inspection.integrity_check == "ok"
    assert inspection.current_schema_version == 0
    assert inspection.target_schema_version == 2
    assert [item.version for item in inspection.pending_migrations] == [1, 2]
    assert inspection.table_counts == {"samples": 2}
    assert (_digest(database), database.stat().st_mtime_ns) == before


def test_backup_is_consistent_private_and_never_overwritten(
    tmp_path: Path,
) -> None:
    database = _legacy_database(tmp_path)
    source_digest = _digest(database)
    backup_directory = tmp_path / "backups"

    backup = create_database_backup(
        database,
        backup_directory,
        target_schema_version=2,
        created_at=CREATED_AT,
    )

    assert backup.backup_path.name == (
        "solarinspector-before-schema-2-20260726T201530Z-from-0.db"
    )
    assert backup.integrity_check == "ok"
    assert backup.sample_count == 2
    backup_digest = _digest(backup.backup_path)
    assert stat.S_IMODE(backup_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup.backup_path.stat().st_mode) == 0o600
    assert _digest(database) == source_digest

    with pytest.raises(DatabaseMaintenanceError, match="already exists"):
        create_database_backup(
            database,
            backup_directory,
            target_schema_version=2,
            created_at=CREATED_AT,
        )
    assert _digest(backup.backup_path) == backup_digest


def test_dry_run_migrates_temporary_copy_without_touching_source(
    tmp_path: Path,
) -> None:
    database = _legacy_database(tmp_path)
    before = (_digest(database), database.stat().st_mtime_ns)

    result = dry_run_database_migration(
        database,
        application_version="4.5.0",
    )

    assert result.dry_run is True
    assert result.previous_schema_version == 0
    assert result.target_schema_version == 2
    assert [item.version for item in result.applied_migrations] == [1, 2]
    assert result.integrity_check == "ok"
    assert result.backup_path is None
    assert (_digest(database), database.stat().st_mtime_ns) == before


def test_migration_creates_verified_backup_before_source_changes(
    tmp_path: Path,
) -> None:
    database = _legacy_database(tmp_path)
    notifications: list[Path] = []

    result = migrate_database_with_backup(
        database,
        tmp_path / "backups",
        application_version="4.5.0",
        created_at=CREATED_AT,
        backup_created=notifications.append,
    )

    assert notifications == [result.backup_path]
    assert result.backup_path is not None
    assert [item.version for item in result.applied_migrations] == [1, 2]
    assert result.integrity_check == "ok"
    with closing(sqlite3.connect(database)) as connection:
        assert get_current_version(connection) == 2
        assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 2
    with closing(sqlite3.connect(result.backup_path)) as connection:
        assert get_current_version(connection) == 0
        assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 2


def test_corrupt_database_fails_before_backup_or_migration(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.db"
    database.write_bytes(b"not a sqlite database")
    backup_directory = tmp_path / "backups"

    with pytest.raises(DatabaseMaintenanceError, match="cannot be inspected"):
        create_database_backup(
            database,
            backup_directory,
            target_schema_version=2,
        )

    assert not backup_directory.exists()
    assert database.read_bytes() == b"not a sqlite database"


def test_migration_failure_leaves_verified_backup_and_source_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _legacy_database(tmp_path)
    before = _digest(database)
    backup_paths: list[Path] = []

    def fail_migration(*_args: object, **_kwargs: object) -> NoReturn:
        raise sqlite3.OperationalError("synthetic migration failure")

    monkeypatch.setattr(maintenance, "apply_migrations", fail_migration)

    with pytest.raises(sqlite3.OperationalError, match="synthetic"):
        migrate_database_with_backup(
            database,
            tmp_path / "backups",
            application_version="4.5.0",
            created_at=CREATED_AT,
            backup_created=backup_paths.append,
        )

    assert len(backup_paths) == 1
    assert backup_paths[0].is_file()
    assert inspect_database(backup_paths[0]).integrity_check == "ok"
    assert _digest(database) == before


def test_cli_info_dry_run_and_failure_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = _legacy_database(tmp_path)

    assert main(["--database-info", "--database", str(database)]) == 0
    info = capsys.readouterr()
    assert "Schema: 0; Ziel: 2; Migrationen: 1, 2" in info.out
    assert "Tabelle samples: 2" in info.out

    before = _digest(database)
    assert (
        main(
            [
                "--migrate-database",
                "--dry-run",
                "--database",
                str(database),
                "--application-version",
                "4.5.0",
            ]
        )
        == 0
    )
    dry_run = capsys.readouterr()
    assert "Dry Run: OK; Quelldatenbank unverändert" in dry_run.out
    assert _digest(database) == before

    missing = tmp_path / "missing.db"
    assert (
        main(["--check-database", "--database", str(missing)]) == EXIT_OPERATION_FAILED
    )
    failure = capsys.readouterr()
    assert "Datenbankoperation fehlgeschlagen" in failure.err
    assert not missing.exists()
