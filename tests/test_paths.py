"""Tests for compatible Zrzavy Energy Monitor runtime path selection."""

from __future__ import annotations

import hashlib
import importlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from zrzavy_energy_monitor_core.environment import (
    DATABASE_PATH_VARIABLE,
    LEGACY_DATABASE_PATH_VARIABLE,
    UPDATE_STATUS_PATH_VARIABLE,
)
from zrzavy_energy_monitor_core.paths import (
    CANONICAL_CONFIG_PATH,
    CANONICAL_DATABASE_PATH,
    CANONICAL_LOG_PATH,
    CANONICAL_PID_PATH,
    CANONICAL_UPDATE_CACHE_DIR,
    HISTORICAL_UPDATE_STATUS_VARIABLE,
    LEGACY_CONFIG_PATH,
    LEGACY_DATABASE_PATH,
    LEGACY_LOG_PATH,
    LEGACY_PID_PATH,
    LEGACY_UPDATE_CACHE_DIR,
    resolve_runtime_paths,
)


def test_new_source_installation_uses_canonical_local_basenames(
    tmp_path: Path,
) -> None:
    """Use new names without creating any path in a clean source tree."""

    base_dir = tmp_path / "app"

    paths = resolve_runtime_paths(
        base_dir,
        environ={},
        legacy_database_exists=False,
    )

    assert paths.config_path == base_dir / "config.json"
    assert paths.data_dir == base_dir / "data"
    assert paths.database_path == base_dir / "data/zrzavy-energy-monitor.db"
    assert paths.log_path == base_dir / "data/zrzavy-energy-monitor.log"
    assert paths.pid_path == base_dir / "data/zrzavy-energy-monitor.pid"
    assert not paths.legacy_installation
    assert not base_dir.exists()


def test_canonical_system_installation_uses_approved_linux_paths() -> None:
    """Map a canonical release under /opt to persistent system paths."""

    paths = resolve_runtime_paths(
        Path("/opt/zrzavy-energy-monitor/current/app"),
        environ={},
        legacy_database_exists=False,
    )

    assert paths.config_path == CANONICAL_CONFIG_PATH
    assert paths.database_path == CANONICAL_DATABASE_PATH
    assert paths.log_path == CANONICAL_LOG_PATH
    assert paths.pid_path == CANONICAL_PID_PATH
    assert paths.update_cache_dir == CANONICAL_UPDATE_CACHE_DIR
    assert not paths.legacy_installation


def test_legacy_system_installation_remains_usable() -> None:
    """Recognize a release under the former installation root."""

    paths = resolve_runtime_paths(
        Path("/opt/solarinspector/current/app"),
        environ={},
        legacy_database_exists=False,
    )

    assert paths.config_path == LEGACY_CONFIG_PATH
    assert paths.database_path == LEGACY_DATABASE_PATH
    assert paths.log_path == LEGACY_LOG_PATH
    assert paths.pid_path == LEGACY_PID_PATH
    assert paths.update_cache_dir == LEGACY_UPDATE_CACHE_DIR
    assert paths.legacy_installation


def test_explicit_canonical_database_path_wins_over_legacy_state(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Select an explicit new path even while an old database still exists."""

    canonical_database = tmp_path / "new/zrzavy-energy-monitor.db"
    paths = resolve_runtime_paths(
        tmp_path / "app",
        environ={
            DATABASE_PATH_VARIABLE: str(canonical_database),
            LEGACY_DATABASE_PATH_VARIABLE: str(tmp_path / "old/solarinspector.db"),
        },
        legacy_database_exists=True,
    )

    assert paths.database_path == canonical_database
    assert paths.data_dir == canonical_database.parent
    assert not paths.legacy_installation
    assert len(caplog.records) == 1


def test_explicit_legacy_database_path_remains_supported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Use an explicitly configured old database without changing it."""

    legacy_database = tmp_path / "legacy/solarinspector.db"
    paths = resolve_runtime_paths(
        tmp_path / "app",
        environ={LEGACY_DATABASE_PATH_VARIABLE: str(legacy_database)},
        legacy_database_exists=False,
    )

    assert paths.database_path == legacy_database
    assert paths.legacy_installation
    assert len(caplog.records) == 1


def test_historical_updater_alias_is_last_compatibility_fallback(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Preserve the real pre-R.4 updater variable spelling."""

    historical_status = tmp_path / "legacy-update-status.json"
    paths = resolve_runtime_paths(
        tmp_path / "app",
        environ={
            HISTORICAL_UPDATE_STATUS_VARIABLE: str(historical_status),
        },
        legacy_database_exists=False,
    )

    assert paths.update_status_path == historical_status
    assert paths.legacy_installation
    assert len(caplog.records) == 1


def test_documented_canonical_updater_variable_overrides_historical_alias(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prefer the approved variable and emit one value-free warning."""

    canonical_status = tmp_path / "new-status.json"
    historical_status = tmp_path / "private-old-status.json"
    paths = resolve_runtime_paths(
        tmp_path / "app",
        environ={
            UPDATE_STATUS_PATH_VARIABLE: str(canonical_status),
            HISTORICAL_UPDATE_STATUS_VARIABLE: str(historical_status),
        },
        legacy_database_exists=False,
    )

    assert paths.update_status_path == canonical_status
    assert len(caplog.records) == 1
    assert str(canonical_status) not in caplog.text
    assert str(historical_status) not in caplog.text


def test_legacy_detection_and_rollback_preserve_sqlite_bytes(
    tmp_path: Path,
) -> None:
    """Switch path selection without mutating a synthetic legacy database."""

    base_dir = tmp_path / "app"
    legacy_database = base_dir / "data/solarinspector.db"
    legacy_database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(legacy_database)) as connection:
        connection.execute(
            "CREATE TABLE samples (timestamp TEXT NOT NULL, power_w REAL, note TEXT)"
        )
        connection.executemany(
            "INSERT INTO samples VALUES (?, ?, ?)",
            [
                ("2026-07-26T10:00:00+00:00", 0.0, None),
                ("2026-07-26T10:00:10+00:00", 125.5, "kept"),
            ],
        )
        connection.commit()

    before = hashlib.sha256(legacy_database.read_bytes()).hexdigest()
    with closing(sqlite3.connect(legacy_database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    legacy_paths = resolve_runtime_paths(
        base_dir,
        environ={},
        legacy_database_exists=True,
    )
    canonical_paths = resolve_runtime_paths(
        base_dir,
        environ={},
        legacy_database_exists=False,
    )
    rollback_paths = resolve_runtime_paths(
        base_dir,
        environ={},
        legacy_database_exists=True,
    )

    assert legacy_paths.database_path == legacy_database
    assert canonical_paths.database_path == (base_dir / "data/zrzavy-energy-monitor.db")
    assert rollback_paths.database_path == legacy_database
    assert not canonical_paths.database_path.exists()
    assert hashlib.sha256(legacy_database.read_bytes()).hexdigest() == before
    with closing(sqlite3.connect(legacy_database)) as connection:
        rows = connection.execute(
            "SELECT timestamp, power_w, note FROM samples ORDER BY timestamp"
        ).fetchall()
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert rows == [
        ("2026-07-26T10:00:00+00:00", 0.0, None),
        ("2026-07-26T10:00:10+00:00", 125.5, "kept"),
    ]


def test_paths_module_import_does_not_create_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload path constants without any filesystem write operation."""

    def unexpected_mkdir(*args, **kwargs) -> None:
        raise AssertionError("paths import attempted to create a directory")

    monkeypatch.setattr(Path, "mkdir", unexpected_mkdir)

    module = importlib.import_module("zrzavy_energy_monitor_core.paths")
    importlib.reload(module)

    assert isinstance(module.RUNTIME_PATHS.database_path, Path)
