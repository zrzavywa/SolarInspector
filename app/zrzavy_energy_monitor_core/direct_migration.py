"""Safely migrate SolarInspector 4.1.3 data to canonical 4.5.5 paths.

This module does not control services. Mutating callers must first stop the
legacy and canonical collectors and pass that verified precondition explicitly.
Systemd orchestration is layered on top in the dedicated Linux migration block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from zrzavy_energy_monitor_core.paths import (
    CANONICAL_CONFIG_PATH,
    CANONICAL_DATABASE_PATH,
    CANONICAL_LOG_PATH,
    LEGACY_CONFIG_PATH,
    LEGACY_DATABASE_PATH,
    LEGACY_LOG_PATH,
)
from zrzavy_energy_monitor_core.persistence.maintenance import inspect_database

TARGET_VERSION: Final = "4.5.5"
LEGACY_VERSION: Final = "4.1.3"
MIGRATION_ID: Final = f"solarinspector-4.1.3-to-zrzavy-energy-monitor-{TARGET_VERSION}"
MANIFEST_NAME: Final = "migration-manifest.json"
PRIVATE_DIRECTORY_MODE: Final = 0o700
DEFAULT_LEGACY_SYSTEMD_UNITS: Final = (
    Path("/etc/systemd/system/solarinspector.service"),
    Path("/etc/systemd/system/solarinspector-updater.service"),
    Path("/etc/systemd/system/solarinspector-updater.path"),
)


class DirectMigrationError(RuntimeError):
    """Report a failed or unsafe direct rebranding migration."""


def resolve_legacy_installation(root: Path) -> Path:
    """Resolve a safe SolarInspector 4.1.3 installation directory.

    A missing or broken ``current`` symlink may be repaired by selecting an
    exact validated release. Existing real files or directories are never
    replaced automatically.
    """
    current = root / "current"
    candidates: list[Path] = []
    if current.is_symlink():
        if current.exists():
            candidates.append(current.resolve())
    elif current.exists():
        raise DirectMigrationError(f"legacy current path is not a symlink: {current}")
    candidates.extend(sorted(root.glob(f"{LEGACY_VERSION}")))
    candidates.extend(sorted(root.glob(f"releases/{LEGACY_VERSION}")))
    for candidate in candidates:
        version_file = candidate / "VERSION"
        if (
            candidate.is_dir()
            and version_file.is_file()
            and version_file.read_text(encoding="utf-8").strip() == LEGACY_VERSION
            and (candidate / "app/solarinspector.py").is_file()
            and (candidate / ".venv/bin/python").is_file()
        ):
            if current.is_symlink() and not current.exists():
                current.unlink()
            if not current.exists():
                current.symlink_to(candidate, target_is_directory=True)
            return candidate
    raise DirectMigrationError(
        f"validated SolarInspector {LEGACY_VERSION} installation not found below {root}"
    )


@dataclass(frozen=True)
class DirectMigrationPaths:
    """Define explicit source, target, and backup paths for one migration."""

    source_config: Path
    source_database: Path
    source_log: Path
    source_installation_root: Path
    source_systemd_units: tuple[Path, ...]
    target_config: Path
    target_database: Path
    target_log: Path
    backup_root: Path

    @property
    def backup_directory(self) -> Path:
        """Return the deterministic backup directory for this migration."""

        return self.backup_root / MIGRATION_ID

    @property
    def manifest_path(self) -> Path:
        """Return the migration manifest path."""

        return self.backup_directory / MANIFEST_NAME


@dataclass(frozen=True)
class FileFingerprint:
    """Describe identity and permissions without exposing file contents."""

    sha256: str
    size_bytes: int
    mode: int
    uid: int
    gid: int


@dataclass(frozen=True)
class MigrationReport:
    """Describe a dry run, apply, or rollback result."""

    mode: str
    migration_id: str
    status: str
    backup_directory: Path
    source_integrity: str
    target_integrity: str | None
    source_table_counts: dict[str, int]
    target_table_counts: dict[str, int] | None


def plan_direct_migration(paths: DirectMigrationPaths) -> MigrationReport:
    """Validate a direct migration without writing to the filesystem.

    Args:
        paths: Explicit legacy, canonical, and backup locations.

    Returns:
        A read-only report containing database integrity and row counts.

    Raises:
        DirectMigrationError: If source or target preconditions are unsafe.
    """

    _validate_distinct_paths(paths)
    _require_regular_file(paths.source_config, "legacy configuration")
    _require_regular_file(paths.source_database, "legacy database")
    _require_directory(paths.source_installation_root, "legacy installation")
    for unit_path in paths.source_systemd_units:
        _require_regular_file(unit_path, "legacy systemd unit")
    if paths.target_config.exists() or paths.target_database.exists():
        raise DirectMigrationError(
            "canonical configuration or database already exists; "
            "refusing to overwrite it"
        )
    if paths.backup_directory.exists():
        raise DirectMigrationError(
            f"migration backup already exists: {paths.backup_directory}"
        )
    source = inspect_database(paths.source_database)
    return MigrationReport(
        mode="dry-run",
        migration_id=MIGRATION_ID,
        status="ready",
        backup_directory=paths.backup_directory,
        source_integrity=source.integrity_check,
        target_integrity=None,
        source_table_counts=source.table_counts,
        target_table_counts=None,
    )


def apply_direct_migration(
    paths: DirectMigrationPaths,
    *,
    services_stopped: bool,
) -> MigrationReport:
    """Back up and copy legacy configuration and SQLite data atomically.

    Args:
        paths: Explicit legacy, canonical, and backup locations.
        services_stopped: Confirmation that neither collector can write.

    Returns:
        Verified source and target integrity metadata.

    Raises:
        DirectMigrationError: If services are not stopped, preconditions fail,
            copying fails, or source and target data differ.

    Side Effects:
        Creates a private backup and canonical config/database files. Source
        files and old logs remain in place. Existing targets are never
        overwritten.
    """

    if not services_stopped:
        raise DirectMigrationError(
            "both legacy and canonical collector services must be stopped"
        )
    planned = plan_direct_migration(paths)
    backup_directory = paths.backup_directory
    backup_directory.mkdir(
        mode=PRIVATE_DIRECTORY_MODE,
        parents=True,
        exist_ok=False,
    )
    os.chmod(backup_directory, PRIVATE_DIRECTORY_MODE)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "migration_id": MIGRATION_ID,
        "source_version": "4.1.3",
        "target_version": TARGET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "backing_up",
        "paths": _serialized_paths(paths),
        "source_config": asdict(_fingerprint(paths.source_config)),
        "source_database": asdict(_fingerprint(paths.source_database)),
        "source_table_counts": planned.source_table_counts,
        "source_integrity": planned.source_integrity,
        "legacy_log_present": paths.source_log.is_file(),
        "source_installation_root": str(
            paths.source_installation_root.resolve(strict=False)
        ),
        "source_systemd_units": [
            str(path.resolve(strict=False)) for path in paths.source_systemd_units
        ],
    }
    _write_manifest(paths.manifest_path, manifest)

    try:
        _atomic_copy_file(
            paths.source_config,
            backup_directory / "config.json",
        )
        _atomic_sqlite_copy(
            paths.source_database,
            backup_directory / "solarinspector.db",
        )
        if paths.source_log.is_file():
            _atomic_copy_file(
                paths.source_log,
                backup_directory / "solarinspector.log",
            )
        _backup_directory_tree(
            paths.source_installation_root,
            backup_directory / "installation",
        )
        systemd_backup_directory = backup_directory / "systemd"
        for unit_path in paths.source_systemd_units:
            _atomic_copy_file(
                unit_path,
                systemd_backup_directory / unit_path.name,
            )
        _fsync_directory(backup_directory)

        backup_database = backup_directory / "solarinspector.db"
        backup_inspection = inspect_database(backup_database)
        _verify_database_equivalence(
            planned.source_table_counts,
            backup_inspection.table_counts,
            "backup",
        )

        _atomic_copy_file(paths.source_config, paths.target_config)
        _atomic_sqlite_copy(paths.source_database, paths.target_database)
        target = inspect_database(paths.target_database)
        _verify_database_equivalence(
            planned.source_table_counts,
            target.table_counts,
            "canonical target",
        )
        if (
            _fingerprint(paths.source_config).sha256
            != _fingerprint(paths.target_config).sha256
        ):
            raise DirectMigrationError(
                "canonical configuration differs from legacy source"
            )

        manifest.update(
            {
                "status": "applied",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "backup_config": asdict(_fingerprint(backup_directory / "config.json")),
                "backup_database": asdict(_fingerprint(backup_database)),
                "backup_installation_file_count": sum(
                    1
                    for path in (backup_directory / "installation").rglob("*")
                    if path.is_file()
                ),
                "backup_systemd_unit_count": len(paths.source_systemd_units),
                "target_config": asdict(_fingerprint(paths.target_config)),
                "target_database": asdict(_fingerprint(paths.target_database)),
                "target_table_counts": target.table_counts,
                "target_integrity": target.integrity_check,
            }
        )
        _write_manifest(paths.manifest_path, manifest)
        return MigrationReport(
            mode="apply",
            migration_id=MIGRATION_ID,
            status="applied",
            backup_directory=backup_directory,
            source_integrity=planned.source_integrity,
            target_integrity=target.integrity_check,
            source_table_counts=planned.source_table_counts,
            target_table_counts=target.table_counts,
        )
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
            }
        )
        _write_manifest(paths.manifest_path, manifest)
        raise DirectMigrationError(
            "direct migration failed; legacy source remains active and "
            f"unchanged, inspect {paths.manifest_path}"
        ) from exc


def rollback_direct_migration(
    paths: DirectMigrationPaths,
    *,
    services_stopped: bool,
) -> MigrationReport:
    """Restore legacy files from the verified migration backup.

    Args:
        paths: The same explicit paths used for apply.
        services_stopped: Confirmation that neither collector can write.

    Returns:
        Verified restored-source metadata.

    Raises:
        DirectMigrationError: If services are active or backup verification
            fails.

    Side Effects:
        Preserves any canonical target files in the backup directory before
        atomically restoring legacy config and database. Removes the inactive
        canonical files after their verified diagnostic copies exist so a
        later apply can use a fresh backup root.
    """

    if not services_stopped:
        raise DirectMigrationError(
            "both legacy and canonical collector services must be stopped"
        )
    manifest = _read_manifest(paths.manifest_path)
    if manifest.get("migration_id") != MIGRATION_ID:
        raise DirectMigrationError("migration manifest has an unexpected ID")
    backup_config = paths.backup_directory / "config.json"
    backup_database = paths.backup_directory / "solarinspector.db"
    _require_regular_file(backup_config, "backup configuration")
    _require_regular_file(backup_database, "backup database")
    backup_inspection = inspect_database(backup_database)
    expected_counts = manifest.get("source_table_counts")
    if not isinstance(expected_counts, dict):
        raise DirectMigrationError("migration manifest lacks source row counts")
    normalized_counts = {str(key): int(value) for key, value in expected_counts.items()}
    _verify_database_equivalence(
        normalized_counts,
        backup_inspection.table_counts,
        "rollback backup",
    )

    failed_target_directory = paths.backup_directory / "failed-target"
    failed_target_directory.mkdir(exist_ok=True)
    if paths.target_config.is_file():
        _atomic_copy_file(
            paths.target_config,
            failed_target_directory / "config.json",
            overwrite=True,
        )
    if paths.target_database.is_file():
        _atomic_sqlite_copy(
            paths.target_database,
            failed_target_directory / "zrzavy-energy-monitor.db",
            overwrite=True,
        )
    if paths.target_config.is_file():
        paths.target_config.unlink()
        _fsync_directory(paths.target_config.parent)
    if paths.target_database.is_file():
        paths.target_database.unlink()
        for suffix in ("-wal", "-shm"):
            Path(f"{paths.target_database}{suffix}").unlink(missing_ok=True)
        _fsync_directory(paths.target_database.parent)

    _atomic_copy_file(backup_config, paths.source_config, overwrite=True)
    _atomic_sqlite_copy(
        backup_database,
        paths.source_database,
        overwrite=True,
    )
    restored = inspect_database(paths.source_database)
    _verify_database_equivalence(
        normalized_counts,
        restored.table_counts,
        "restored legacy database",
    )
    manifest.update(
        {
            "status": "rolled_back",
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "restored_source_integrity": restored.integrity_check,
            "restored_source_table_counts": restored.table_counts,
        }
    )
    _write_manifest(paths.manifest_path, manifest)
    return MigrationReport(
        mode="rollback",
        migration_id=MIGRATION_ID,
        status="rolled_back",
        backup_directory=paths.backup_directory,
        source_integrity=restored.integrity_check,
        target_integrity=None,
        source_table_counts=restored.table_counts,
        target_table_counts=None,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the direct migration command-line interface.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Zero for a completed operation and two for a controlled refusal.
    """

    parser = argparse.ArgumentParser(
        description=(
            f"Direct SolarInspector 4.1.3 to Zrzavy Energy Monitor {TARGET_VERSION} "
            "configuration and SQLite migration"
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--services-stopped", action="store_true")
    parser.add_argument("--source-config", type=Path, default=LEGACY_CONFIG_PATH)
    parser.add_argument(
        "--source-database",
        type=Path,
        default=LEGACY_DATABASE_PATH,
    )
    parser.add_argument("--source-log", type=Path, default=LEGACY_LOG_PATH)
    parser.add_argument(
        "--source-installation-root",
        type=Path,
        default=Path("/opt/solarinspector"),
    )
    parser.add_argument(
        "--source-systemd-unit",
        action="append",
        type=Path,
        default=None,
        help=(
            "legacy unit to back up; repeat for multiple units "
            "(defaults to the three SolarInspector units)"
        ),
    )
    parser.add_argument("--target-config", type=Path, default=CANONICAL_CONFIG_PATH)
    parser.add_argument(
        "--target-database",
        type=Path,
        default=CANONICAL_DATABASE_PATH,
    )
    parser.add_argument("--target-log", type=Path, default=CANONICAL_LOG_PATH)
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path("/var/lib/zrzavy-energy-monitor/backups"),
    )
    args = parser.parse_args(argv)
    try:
        source_installation_root = args.source_installation_root
        if source_installation_root == Path("/opt/solarinspector"):
            source_installation_root = resolve_legacy_installation(
                source_installation_root
            )
    except DirectMigrationError as exc:
        print(f"Migration refused: {exc}", file=sys.stderr)
        return 2
    paths = DirectMigrationPaths(
        source_config=args.source_config,
        source_database=args.source_database,
        source_log=args.source_log,
        source_installation_root=source_installation_root,
        source_systemd_units=tuple(
            args.source_systemd_unit or DEFAULT_LEGACY_SYSTEMD_UNITS
        ),
        target_config=args.target_config,
        target_database=args.target_database,
        target_log=args.target_log,
        backup_root=args.backup_root,
    )
    try:
        if args.dry_run:
            report = plan_direct_migration(paths)
        elif args.apply:
            report = apply_direct_migration(
                paths,
                services_stopped=args.services_stopped,
            )
        else:
            report = rollback_direct_migration(
                paths,
                services_stopped=args.services_stopped,
            )
    except DirectMigrationError as exc:
        print(f"Migration refused: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                **asdict(report),
                "backup_directory": str(report.backup_directory),
            },
            sort_keys=True,
        )
    )
    return 0


def _validate_distinct_paths(paths: DirectMigrationPaths) -> None:
    resolved_sources = {
        paths.source_config.resolve(strict=False),
        paths.source_database.resolve(strict=False),
    }
    resolved_targets = {
        paths.target_config.resolve(strict=False),
        paths.target_database.resolve(strict=False),
    }
    if resolved_sources & resolved_targets:
        raise DirectMigrationError("source and target paths must be distinct")
    if Path("/") in resolved_sources | resolved_targets:
        raise DirectMigrationError("filesystem root cannot be a migration path")
    if paths.backup_directory.resolve(strict=False) in (
        resolved_sources | resolved_targets
    ):
        raise DirectMigrationError("backup directory cannot equal a data file")


def _require_regular_file(path: Path, description: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise DirectMigrationError(
            f"{description} is missing or not a regular file: {path}"
        )


def _require_directory(path: Path, description: str) -> None:
    if not path.is_dir() or path.is_symlink():
        raise DirectMigrationError(
            f"{description} is missing or not a real directory: {path}"
        )


def _fingerprint(path: Path) -> FileFingerprint:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return FileFingerprint(
        sha256=digest.hexdigest(),
        size_bytes=stat.st_size,
        mode=stat.st_mode & 0o777,
        uid=stat.st_uid,
        gid=stat.st_gid,
    )


def _atomic_copy_file(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> None:
    _require_regular_file(source, "copy source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise DirectMigrationError(f"destination already exists: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        _fsync_file(temporary)
        if destination.exists() and not destination.is_file():
            raise DirectMigrationError(
                f"destination is not a regular file: {destination}"
            )
        temporary.replace(destination)
        _preserve_owner_when_permitted(source, destination)
        _fsync_directory(destination.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_sqlite_copy(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> None:
    _require_regular_file(source, "SQLite source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise DirectMigrationError(f"destination already exists: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_uri = f"file:{source.resolve()}?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as source_connection,
            closing(sqlite3.connect(temporary)) as target_connection,
        ):
            source_connection.execute("PRAGMA query_only = ON")
            source_connection.backup(target_connection)
            target_connection.commit()
        source_mode = source.stat().st_mode & 0o777
        os.chmod(temporary, source_mode)
        _fsync_file(temporary)
        inspection = inspect_database(temporary)
        if inspection.integrity_check != "ok":
            raise DirectMigrationError("copied SQLite database is not integral")
        if destination.exists() and not destination.is_file():
            raise DirectMigrationError(
                f"destination is not a regular file: {destination}"
            )
        temporary.replace(destination)
        _preserve_owner_when_permitted(source, destination)
        _fsync_directory(destination.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _backup_directory_tree(source: Path, destination: Path) -> None:
    _require_directory(source, "directory backup source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise DirectMigrationError(
            f"directory backup destination already exists: {destination}"
        )
    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
    )
    temporary = temporary_parent / destination.name
    try:
        shutil.copytree(
            source,
            temporary,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        temporary.replace(destination)
        _fsync_directory(destination.parent)
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise
    shutil.rmtree(temporary_parent)


def _preserve_owner_when_permitted(source: Path, destination: Path) -> None:
    source_stat = source.stat()
    if os.geteuid() == 0:
        os.chown(destination, source_stat.st_uid, source_stat.st_gid)


def _verify_database_equivalence(
    expected_counts: dict[str, int],
    actual_counts: dict[str, int],
    description: str,
) -> None:
    if actual_counts != expected_counts:
        raise DirectMigrationError(
            f"{description} row counts differ from the legacy source"
        )


def _serialized_paths(paths: DirectMigrationPaths) -> dict[str, str]:
    return {
        "source_config": str(paths.source_config.resolve(strict=False)),
        "source_database": str(paths.source_database.resolve(strict=False)),
        "source_log": str(paths.source_log.resolve(strict=False)),
        "source_installation_root": str(
            paths.source_installation_root.resolve(strict=False)
        ),
        "source_systemd_units": ", ".join(
            str(path.resolve(strict=False)) for path in paths.source_systemd_units
        ),
        "target_config": str(paths.target_config.resolve(strict=False)),
        "target_database": str(paths.target_database.resolve(strict=False)),
        "target_log": str(paths.target_log.resolve(strict=False)),
        "backup_root": str(paths.backup_root.resolve(strict=False)),
    }


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(
        mode=PRIVATE_DIRECTORY_MODE,
        parents=True,
        exist_ok=True,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        _fsync_file(temporary)
        temporary.replace(path)
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_manifest(path: Path) -> dict[str, object]:
    _require_regular_file(path, "migration manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DirectMigrationError("migration manifest is invalid") from exc
    if not isinstance(payload, dict):
        raise DirectMigrationError("migration manifest must be an object")
    return payload


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
