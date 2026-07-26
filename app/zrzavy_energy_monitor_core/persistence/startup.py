"""Prepare and verify the SQLite schema before application services exist."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from zrzavy_energy_monitor_core.persistence.database import Database
from zrzavy_energy_monitor_core.persistence.maintenance import (
    DatabaseMaintenanceError,
    inspect_database,
    migrate_database_with_backup,
)
from zrzavy_energy_monitor_core.persistence.migrations import (
    DatabaseSchemaError,
    get_target_version,
    verify_schema,
)


class DatabaseStartupError(RuntimeError):
    """Report a fatal schema preparation failure before service startup."""


@dataclass(frozen=True)
class DatabaseStartupResult:
    """Describe a successfully prepared application database."""

    database_path: Path
    created: bool
    previous_schema_version: int
    current_schema_version: int
    applied_migration_versions: tuple[int, ...]
    backup_path: Path | None


def prepare_database_for_startup(
    database_path: Path,
    backup_directory: Path,
    *,
    application_version: str,
) -> DatabaseStartupResult:
    """Initialize or migrate SQLite before Collector and web startup.

    Args:
        database_path: Application database path.
        backup_directory: Destination for mandatory pre-migration backups.
        application_version: Version recorded in migration ledger rows.

    Returns:
        Created/migrated state and optional verified backup path.

    Raises:
        DatabaseStartupError: If creation, inspection, backup, migration,
            target verification, or integrity checking fails. The original
            exception is chained and no retry loop is started.

    Side Effects:
        A missing or zero-byte database receives the established Phase-09
        baseline. Every older schema, including that new baseline, is backed
        up and migrated before return. A verified target database is read-only
        checked and left byte-for-byte untouched.
    """

    path = database_path.expanduser().resolve()
    created = not path.exists() or path.stat().st_size == 0
    verified_backups: list[Path] = []
    try:
        if created:
            Database(path)
        before = inspect_database(path)
        if before.pending_migrations:
            migration = migrate_database_with_backup(
                path,
                backup_directory,
                application_version=application_version,
                backup_created=verified_backups.append,
            )
            applied_versions = tuple(
                item.version for item in migration.applied_migrations
            )
            backup_path = migration.backup_path
        else:
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                verify_schema(connection)
            applied_versions = ()
            backup_path = None
        after = inspect_database(path)
        if after.current_schema_version != get_target_version():
            raise DatabaseStartupError(
                "database startup did not reach the supported target schema"
            )
    except (
        DatabaseMaintenanceError,
        DatabaseSchemaError,
        sqlite3.DatabaseError,
        OSError,
        ValueError,
    ) as exc:
        backup_note = (
            f"; verified backup: {verified_backups[-1]}" if verified_backups else ""
        )
        raise DatabaseStartupError(
            f"database startup preparation failed for {path}: {exc}{backup_note}"
        ) from exc

    return DatabaseStartupResult(
        database_path=path,
        created=created,
        previous_schema_version=before.current_schema_version,
        current_schema_version=after.current_schema_version,
        applied_migration_versions=applied_versions,
        backup_path=backup_path,
    )
