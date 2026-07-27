"""Tests for the one-time direct 4.1.3 to 4.5.0 migration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from zrzavy_energy_monitor_core import direct_migration
from zrzavy_energy_monitor_core.direct_migration import (
    DirectMigrationError,
    DirectMigrationPaths,
    apply_direct_migration,
    main,
    plan_direct_migration,
    rollback_direct_migration,
)


def _create_legacy_installation(tmp_path: Path) -> DirectMigrationPaths:
    legacy_root = tmp_path / "legacy"
    target_root = tmp_path / "canonical"
    source_config = legacy_root / "etc/config.json"
    source_database = legacy_root / "state/data/solarinspector.db"
    source_log = legacy_root / "log/solarinspector.log"
    source_installation_root = legacy_root / "opt/solarinspector"
    systemd_directory = legacy_root / "systemd"
    source_config.parent.mkdir(parents=True)
    source_database.parent.mkdir(parents=True)
    source_log.parent.mkdir(parents=True)
    (source_installation_root / "current/app").mkdir(parents=True)
    systemd_directory.mkdir(parents=True)
    source_config.write_bytes(b'{"device": "synthetic", "zero": 0}\n')
    source_log.write_text("legacy audit log\n", encoding="utf-8")
    (source_installation_root / "current/VERSION").write_text(
        "4.1.3\n",
        encoding="utf-8",
    )
    (source_installation_root / "current/app/solarinspector.py").write_text(
        "# synthetic legacy application\n",
        encoding="utf-8",
    )
    source_systemd_units = tuple(
        systemd_directory / name
        for name in (
            "solarinspector.service",
            "solarinspector-updater.service",
            "solarinspector-updater.path",
        )
    )
    for unit_path in source_systemd_units:
        unit_path.write_text(
            f"[Unit]\nDescription=Synthetic {unit_path.name}\n",
            encoding="utf-8",
        )
    source_config.chmod(0o640)
    source_database.touch(mode=0o640)
    with closing(sqlite3.connect(source_database)) as connection:
        connection.execute(
            "CREATE TABLE samples (timestamp TEXT NOT NULL, grid_power REAL, note TEXT)"
        )
        connection.executemany(
            "INSERT INTO samples VALUES (?, ?, ?)",
            [
                ("2026-07-26T10:00:00+00:00", 0.0, None),
                ("2026-07-26T10:00:10+00:00", -125.5, "export"),
            ],
        )
        connection.commit()
    return DirectMigrationPaths(
        source_config=source_config,
        source_database=source_database,
        source_log=source_log,
        source_installation_root=source_installation_root,
        source_systemd_units=source_systemd_units,
        target_config=target_root / "etc/config.json",
        target_database=(target_root / "state/data/zrzavy-energy-monitor.db"),
        target_log=target_root / "log/zrzavy-energy-monitor.log",
        backup_root=target_root / "state/backups",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_rows(path: Path) -> list[tuple[str, float, str | None]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT timestamp, grid_power, note FROM samples ORDER BY timestamp"
        ).fetchall()


def test_dry_run_is_read_only_and_reports_integrity(tmp_path: Path) -> None:
    """Inspect the complete plan without creating target or backup paths."""

    paths = _create_legacy_installation(tmp_path)
    source_config_hash = _sha256(paths.source_config)
    source_database_hash = _sha256(paths.source_database)

    report = plan_direct_migration(paths)

    assert report.mode == "dry-run"
    assert report.status == "ready"
    assert report.source_integrity == "ok"
    assert report.source_table_counts["samples"] == 2
    assert not paths.target_config.exists()
    assert not paths.target_database.exists()
    assert not paths.backup_directory.exists()
    assert _sha256(paths.source_config) == source_config_hash
    assert _sha256(paths.source_database) == source_database_hash


def test_apply_requires_both_services_to_be_stopped(tmp_path: Path) -> None:
    """Refuse mutation while a collector may still write."""

    paths = _create_legacy_installation(tmp_path)

    with pytest.raises(DirectMigrationError, match="services must be stopped"):
        apply_direct_migration(paths, services_stopped=False)

    assert not paths.backup_directory.exists()
    assert not paths.target_database.exists()


def test_apply_backs_up_and_preserves_all_domain_values(tmp_path: Path) -> None:
    """Copy config and SQLite data with integrity, modes, and history intact."""

    paths = _create_legacy_installation(tmp_path)
    source_config_hash = _sha256(paths.source_config)
    source_database_hash = _sha256(paths.source_database)
    expected_rows = _sample_rows(paths.source_database)

    report = apply_direct_migration(paths, services_stopped=True)

    assert report.status == "applied"
    assert report.source_integrity == "ok"
    assert report.target_integrity == "ok"
    assert report.source_table_counts == report.target_table_counts
    assert _sha256(paths.source_config) == source_config_hash
    assert _sha256(paths.source_database) == source_database_hash
    assert _sha256(paths.target_config) == source_config_hash
    assert _sample_rows(paths.target_database) == expected_rows
    assert expected_rows[0] == ("2026-07-26T10:00:00+00:00", 0.0, None)
    assert paths.target_config.stat().st_mode & 0o777 == 0o640
    assert paths.target_database.stat().st_mode & 0o777 == 0o640
    assert not paths.target_log.exists()
    assert (paths.backup_directory / "solarinspector.log").read_text(
        encoding="utf-8"
    ) == "legacy audit log\n"
    assert (paths.backup_directory / "installation/current/VERSION").read_text(
        encoding="utf-8"
    ) == "4.1.3\n"
    assert sorted(
        path.name for path in (paths.backup_directory / "systemd").iterdir()
    ) == [
        "solarinspector-updater.path",
        "solarinspector-updater.service",
        "solarinspector.service",
    ]
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "applied"
    assert manifest["source_table_counts"]["samples"] == 2
    assert manifest["target_table_counts"]["samples"] == 2
    assert manifest["backup_installation_file_count"] == 2
    assert manifest["backup_systemd_unit_count"] == 3


def test_repeated_apply_refuses_to_overwrite_backup_or_target(
    tmp_path: Path,
) -> None:
    """Make one-time migration repeatable only through explicit rollback."""

    paths = _create_legacy_installation(tmp_path)
    apply_direct_migration(paths, services_stopped=True)

    with pytest.raises(DirectMigrationError, match="already exists"):
        apply_direct_migration(paths, services_stopped=True)


def test_rollback_restores_source_and_preserves_failed_target(
    tmp_path: Path,
) -> None:
    """Restore legacy data and retain only backed-up canonical evidence."""

    paths = _create_legacy_installation(tmp_path)
    original_config = paths.source_config.read_bytes()
    original_rows = _sample_rows(paths.source_database)
    apply_direct_migration(paths, services_stopped=True)
    Path(f"{paths.target_database}-wal").touch()
    Path(f"{paths.target_database}-shm").touch()
    paths.source_config.write_text('{"damaged": true}\n', encoding="utf-8")
    with closing(sqlite3.connect(paths.source_database)) as connection:
        connection.execute(
            "INSERT INTO samples VALUES (?, ?, ?)",
            ("2026-07-26T10:00:20+00:00", 999.0, "unexpected"),
        )
        connection.commit()

    report = rollback_direct_migration(paths, services_stopped=True)

    assert report.status == "rolled_back"
    assert report.source_integrity == "ok"
    assert paths.source_config.read_bytes() == original_config
    assert _sample_rows(paths.source_database) == original_rows
    assert (paths.backup_directory / "failed-target/config.json").is_file()
    failed_database = paths.backup_directory / "failed-target/zrzavy-energy-monitor.db"
    assert _sample_rows(failed_database) == original_rows
    assert not paths.target_config.exists()
    assert not paths.target_database.exists()
    assert not Path(f"{paths.target_database}-wal").exists()
    assert not Path(f"{paths.target_database}-shm").exists()
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "rolled_back"

    reapplied_paths = replace(
        paths,
        backup_root=paths.backup_root / "reapply",
    )
    reapplied = apply_direct_migration(
        reapplied_paths,
        services_stopped=True,
    )

    assert reapplied.status == "applied"
    assert _sample_rows(reapplied_paths.target_database) == original_rows


def test_failed_apply_keeps_source_unchanged_and_records_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail safely after backup without altering the only legacy database."""

    paths = _create_legacy_installation(tmp_path)
    source_hash = _sha256(paths.source_database)
    original_copy = direct_migration._atomic_sqlite_copy
    calls = 0

    def fail_target_copy(
        source: Path,
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic target failure")
        original_copy(source, destination, overwrite=overwrite)

    monkeypatch.setattr(
        direct_migration,
        "_atomic_sqlite_copy",
        fail_target_copy,
    )

    with pytest.raises(DirectMigrationError, match="legacy source remains"):
        apply_direct_migration(paths, services_stopped=True)

    assert _sha256(paths.source_database) == source_hash
    assert _sample_rows(paths.source_database)[0][1:] == (0.0, None)
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error_type"] == "OSError"
    assert "synthetic target failure" not in paths.manifest_path.read_text(
        encoding="utf-8"
    )


def test_cli_dry_run_and_service_guard(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expose safe CLI modes with controlled exit codes."""

    paths = _create_legacy_installation(tmp_path)
    common = [
        "--source-config",
        str(paths.source_config),
        "--source-database",
        str(paths.source_database),
        "--source-log",
        str(paths.source_log),
        "--source-installation-root",
        str(paths.source_installation_root),
        "--target-config",
        str(paths.target_config),
        "--target-database",
        str(paths.target_database),
        "--target-log",
        str(paths.target_log),
        "--backup-root",
        str(paths.backup_root),
    ]
    for unit_path in paths.source_systemd_units:
        common.extend(["--source-systemd-unit", str(unit_path)])

    assert main(["--dry-run", *common]) == 0
    dry_run_output = json.loads(capsys.readouterr().out)
    assert dry_run_output["status"] == "ready"
    assert main(["--apply", *common]) == 2
    assert "services must be stopped" in capsys.readouterr().err
