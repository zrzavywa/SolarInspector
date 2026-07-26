"""Resolve Zrzavy Energy Monitor runtime paths without filesystem mutation.

Importing this module derives path values only. It does not create, move,
copy, open, or delete configuration, databases, logs, PID files, or folders.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from zrzavy_energy_monitor_core.environment import (
    CONFIG_PATH_VARIABLE,
    DATABASE_PATH_VARIABLE,
    LEGACY_CONFIG_PATH_VARIABLE,
    LEGACY_DATABASE_PATH_VARIABLE,
    LEGACY_UPDATE_CACHE_DIR_VARIABLE,
    LEGACY_UPDATE_REQUEST_PATH_VARIABLE,
    LEGACY_UPDATE_STATUS_PATH_VARIABLE,
    UPDATE_CACHE_DIR_VARIABLE,
    UPDATE_REQUEST_PATH_VARIABLE,
    UPDATE_STATUS_PATH_VARIABLE,
    resolve_environment_variable,
    resolve_environment_variable_aliases,
)

CANONICAL_INSTALLATION_ROOT = Path("/opt/zrzavy-energy-monitor")
CANONICAL_CONFIG_PATH = Path("/etc/zrzavy-energy-monitor/config.json")
CANONICAL_DATA_DIR = Path("/var/lib/zrzavy-energy-monitor/data")
CANONICAL_DATABASE_PATH = CANONICAL_DATA_DIR / "zrzavy-energy-monitor.db"
CANONICAL_LOG_PATH = Path("/var/log/zrzavy-energy-monitor/zrzavy-energy-monitor.log")
CANONICAL_PID_PATH = CANONICAL_DATA_DIR / "zrzavy-energy-monitor.pid"
CANONICAL_UPDATE_STATUS_PATH = Path("/var/lib/zrzavy-energy-monitor/update-status.json")
CANONICAL_UPDATE_REQUEST_PATH = Path(
    "/var/lib/zrzavy-energy-monitor/update-request.json"
)
CANONICAL_UPDATE_CACHE_DIR = Path("/var/cache/zrzavy-energy-monitor/updates")

LEGACY_INSTALLATION_ROOT = Path("/opt/solarinspector")
LEGACY_CONFIG_PATH = Path("/etc/solarinspector/config.json")
LEGACY_DATA_DIR = Path("/var/lib/solarinspector/data")
LEGACY_DATABASE_PATH = LEGACY_DATA_DIR / "solarinspector.db"
LEGACY_LOG_PATH = Path("/var/log/solarinspector/solarinspector.log")
LEGACY_PID_PATH = LEGACY_DATA_DIR / "solarinspector.pid"
LEGACY_UPDATE_STATUS_PATH = Path("/var/lib/solarinspector/update-status.json")
LEGACY_UPDATE_REQUEST_PATH = Path("/var/lib/solarinspector/update-request.json")
LEGACY_UPDATE_CACHE_DIR = Path("/var/cache/solarinspector/updates")

HISTORICAL_UPDATE_STATUS_VARIABLE = "SOLARINSPECTOR_UPDATE_STATUS"
HISTORICAL_UPDATE_REQUEST_VARIABLE = "SOLARINSPECTOR_UPDATE_REQUEST"
HISTORICAL_UPDATE_CACHE_VARIABLE = "SOLARINSPECTOR_UPDATE_CACHE"


@dataclass(frozen=True)
class RuntimePaths:
    """Contain one internally consistent set of application runtime paths."""

    base_dir: Path
    config_path: Path
    data_dir: Path
    database_path: Path
    log_path: Path
    pid_path: Path
    update_status_path: Path
    update_request_path: Path
    update_cache_dir: Path
    legacy_installation: bool


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether ``path`` is located below ``parent``."""

    try:
        path.resolve(strict=False).relative_to(parent)
    except ValueError:
        return False
    return True


def _path_from_value(value: str | None, default: Path) -> Path:
    """Return a path from an optional environment value."""

    return default if value is None else Path(value)


def resolve_runtime_paths(
    base_dir: Path,
    *,
    environ: Mapping[str, str] | None = None,
    legacy_database_exists: bool | None = None,
) -> RuntimePaths:
    """Resolve runtime paths for source, canonical, or legacy installations.

    Args:
        base_dir: Directory containing the application entry points.
        environ: Optional environment mapping.
        legacy_database_exists: Optional explicit local-legacy detection
            result. When omitted, only the legacy database's existence is
            checked; its contents are never opened.

    Returns:
        An immutable, side-effect-free runtime path selection.
    """

    source = os.environ if environ is None else environ
    resolved_base_dir = base_dir.resolve(strict=False)
    local_data_dir = resolved_base_dir / "data"
    local_legacy_database = local_data_dir / "solarinspector.db"
    local_legacy_detected = (
        local_legacy_database.exists()
        if legacy_database_exists is None
        else legacy_database_exists
    )
    legacy_system_installation = _is_within(
        resolved_base_dir,
        LEGACY_INSTALLATION_ROOT,
    )
    canonical_system_installation = _is_within(
        resolved_base_dir,
        CANONICAL_INSTALLATION_ROOT,
    )
    canonical_path_environment = any(
        name in source
        for name in (
            CONFIG_PATH_VARIABLE,
            DATABASE_PATH_VARIABLE,
            UPDATE_STATUS_PATH_VARIABLE,
            UPDATE_REQUEST_PATH_VARIABLE,
            UPDATE_CACHE_DIR_VARIABLE,
        )
    )
    legacy_path_environment = any(
        canonical_name not in source
        and any(legacy_name in source for legacy_name in legacy_names)
        for canonical_name, legacy_names in (
            (CONFIG_PATH_VARIABLE, (LEGACY_CONFIG_PATH_VARIABLE,)),
            (DATABASE_PATH_VARIABLE, (LEGACY_DATABASE_PATH_VARIABLE,)),
            (
                UPDATE_STATUS_PATH_VARIABLE,
                (
                    LEGACY_UPDATE_STATUS_PATH_VARIABLE,
                    HISTORICAL_UPDATE_STATUS_VARIABLE,
                ),
            ),
            (
                UPDATE_REQUEST_PATH_VARIABLE,
                (
                    LEGACY_UPDATE_REQUEST_PATH_VARIABLE,
                    HISTORICAL_UPDATE_REQUEST_VARIABLE,
                ),
            ),
            (
                UPDATE_CACHE_DIR_VARIABLE,
                (
                    LEGACY_UPDATE_CACHE_DIR_VARIABLE,
                    HISTORICAL_UPDATE_CACHE_VARIABLE,
                ),
            ),
        )
    )
    legacy_installation = legacy_system_installation or (
        (local_legacy_detected or legacy_path_environment)
        and not canonical_system_installation
        and not canonical_path_environment
    )

    if legacy_system_installation:
        default_config_path = LEGACY_CONFIG_PATH
        default_data_dir = LEGACY_DATA_DIR
        default_database_path = LEGACY_DATABASE_PATH
        default_log_path = LEGACY_LOG_PATH
        default_pid_path = LEGACY_PID_PATH
        default_update_status_path = LEGACY_UPDATE_STATUS_PATH
        default_update_request_path = LEGACY_UPDATE_REQUEST_PATH
        default_update_cache_dir = LEGACY_UPDATE_CACHE_DIR
    elif canonical_system_installation:
        default_config_path = CANONICAL_CONFIG_PATH
        default_data_dir = CANONICAL_DATA_DIR
        default_database_path = CANONICAL_DATABASE_PATH
        default_log_path = CANONICAL_LOG_PATH
        default_pid_path = CANONICAL_PID_PATH
        default_update_status_path = CANONICAL_UPDATE_STATUS_PATH
        default_update_request_path = CANONICAL_UPDATE_REQUEST_PATH
        default_update_cache_dir = CANONICAL_UPDATE_CACHE_DIR
    else:
        default_config_path = resolved_base_dir / "config.json"
        default_data_dir = local_data_dir
        basename_prefix = (
            "solarinspector" if legacy_installation else "zrzavy-energy-monitor"
        )
        default_database_path = default_data_dir / f"{basename_prefix}.db"
        default_log_path = default_data_dir / f"{basename_prefix}.log"
        default_pid_path = default_data_dir / f"{basename_prefix}.pid"
        default_update_status_path = default_data_dir / "update-status.json"
        default_update_request_path = default_data_dir / "update-request.json"
        default_update_cache_dir = default_data_dir / "updates"

    config_path = _path_from_value(
        resolve_environment_variable(
            CONFIG_PATH_VARIABLE,
            LEGACY_CONFIG_PATH_VARIABLE,
            environ=source,
        ),
        default_config_path,
    )
    database_path = _path_from_value(
        resolve_environment_variable(
            DATABASE_PATH_VARIABLE,
            LEGACY_DATABASE_PATH_VARIABLE,
            environ=source,
        ),
        default_database_path,
    )
    update_status_path = _path_from_value(
        resolve_environment_variable_aliases(
            UPDATE_STATUS_PATH_VARIABLE,
            (
                LEGACY_UPDATE_STATUS_PATH_VARIABLE,
                HISTORICAL_UPDATE_STATUS_VARIABLE,
            ),
            environ=source,
        ),
        default_update_status_path,
    )
    update_request_path = _path_from_value(
        resolve_environment_variable_aliases(
            UPDATE_REQUEST_PATH_VARIABLE,
            (
                LEGACY_UPDATE_REQUEST_PATH_VARIABLE,
                HISTORICAL_UPDATE_REQUEST_VARIABLE,
            ),
            environ=source,
        ),
        default_update_request_path,
    )
    update_cache_dir = _path_from_value(
        resolve_environment_variable_aliases(
            UPDATE_CACHE_DIR_VARIABLE,
            (
                LEGACY_UPDATE_CACHE_DIR_VARIABLE,
                HISTORICAL_UPDATE_CACHE_VARIABLE,
            ),
            environ=source,
        ),
        default_update_cache_dir,
    )

    return RuntimePaths(
        base_dir=resolved_base_dir,
        config_path=config_path,
        data_dir=database_path.parent,
        database_path=database_path,
        log_path=default_log_path,
        pid_path=default_pid_path,
        update_status_path=update_status_path,
        update_request_path=update_request_path,
        update_cache_dir=update_cache_dir,
        legacy_installation=legacy_installation,
    )


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PATHS = resolve_runtime_paths(BASE_DIR)
CONFIG_PATH = RUNTIME_PATHS.config_path
DATA_DIR = RUNTIME_PATHS.data_dir
DB_PATH = RUNTIME_PATHS.database_path
LOG_PATH = RUNTIME_PATHS.log_path
PID_PATH = RUNTIME_PATHS.pid_path
UPDATE_STATUS_PATH = RUNTIME_PATHS.update_status_path
UPDATE_REQUEST_PATH = RUNTIME_PATHS.update_request_path
UPDATE_CACHE_DIR = RUNTIME_PATHS.update_cache_dir
