"""Build responses for the basic SolarInspector HTTP APIs.

Flask route registration, JSON conversion, global dependency lookup, and
the patchable application clock remain in the compatible entry module.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Protocol

from solarinspector_core.config.manager import ConfigManager
from solarinspector_core.persistence.database import Database
from solarinspector_core.services.dashboard import build_dashboard
from solarinspector_core.services.periods import (
    bucket_index,
    parse_anchor,
    period_bounds,
)


class CollectorApi(Protocol):
    """Collector operations used by the basic HTTP APIs."""

    def start(self) -> bool:
        """Start measurement collection."""

    def stop(self) -> bool:
        """Stop measurement collection."""

    def status(self) -> dict[str, Any]:
        """Return the current collector status."""

    def collect_once(self) -> dict[str, Any]:
        """Collect and persist one sample."""

    def reset_state(self) -> None:
        """Reset the current runtime state."""


class DatabaseApi(Protocol):
    """Database operations used by the basic HTTP APIs."""

    def latest(self) -> dict[str, Any] | None:
        """Return the most recent sample."""

    def delete_all(self) -> None:
        """Delete all persisted samples."""


class PhaseDatabaseApi(Protocol):
    """Database operations used by the additive phase APIs."""

    def latest_phase_sample(
        self,
        source_id: str = "house_meter",
    ) -> dict[str, Any] | None:
        """Return the most recent persisted phase sample."""

    def phase_rows_between(
        self,
        start_epoch: float,
        end_epoch: float,
        *,
        source_id: str = "house_meter",
    ) -> list[dict[str, Any]]:
        """Return persisted phase rows for one source and time range."""


def build_start_api_response(
    collector: CollectorApi,
) -> tuple[dict[str, Any], int | None]:
    """Build the existing start API payload and optional error status."""
    started = collector.start()
    status = collector.status()

    if not started and not status["running"]:
        return {
            "ok": False,
            "started": False,
            "error": status["last_error"],
            "status": status,
        }, 400

    return {
        "ok": True,
        "started": started,
        "status": status,
    }, None


def build_stop_api_response(
    collector: CollectorApi,
) -> dict[str, Any]:
    """Build the existing stop API payload."""
    stopped = collector.stop()
    return {
        "ok": True,
        "stopped": stopped,
        "status": collector.status(),
    }


def build_collect_once_api_response(
    collector: CollectorApi,
) -> tuple[dict[str, Any], int | None]:
    """Build the existing single-collection payload."""
    try:
        sample = collector.collect_once()
        return {
            "ok": True,
            "sample": sample,
        }, None
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }, 500


def build_status_api_response(
    collector: CollectorApi,
) -> dict[str, Any]:
    """Return the existing collector status payload."""
    return collector.status()


def build_health_api_response(
    installed_version: str,
) -> dict[str, Any]:
    """Build the existing health payload."""
    return {
        "status": "ok",
        "version": installed_version,
        "config_schema": 5,
        "database": "ok",
        "web": "ok",
    }


def build_live_api_response(
    database: DatabaseApi,
    collector: CollectorApi,
    now_epoch: float,
) -> dict[str, Any]:
    """Build the existing live measurement payload."""
    latest = database.latest()
    status = collector.status()

    if latest:
        latest["age_seconds"] = max(
            0,
            int(now_epoch - float(latest["ts_epoch"])),
        )

    grid_meter = _latest_grid_meter_api_row(
        database,
        now_epoch=now_epoch,
    )
    active_source_id = (
        grid_meter.get("active_source_id")
        if grid_meter is not None
        else _legacy_active_grid_source_id(latest)
    )

    return {
        "latest": latest,
        "collector": status,
        "grid_meter": grid_meter,
        "active_sources": {
            "grid_power": active_source_id,
            "grid_power_label": (latest.get("grid_source") if latest else None),
        },
    }


def build_delete_all_api_response(
    collector: CollectorApi,
    database: DatabaseApi,
) -> dict[str, bool]:
    """Stop collection, delete samples, and reset runtime state."""
    collector.stop()
    database.delete_all()
    collector.reset_state()
    return {"ok": True}


def build_system_version_api_response(
    installed_version: str,
) -> dict[str, Any]:
    """Build the existing system version payload."""
    return {
        "product": "SolarInspector",
        "version": installed_version,
        "config_schema": 5,
    }


def _latest_grid_meter_api_row(
    database: DatabaseApi,
    *,
    now_epoch: float,
) -> dict[str, Any] | None:
    """Read and serialize an optional persisted grid-meter row."""

    latest_method = getattr(
        database,
        "latest_grid_meter_sample",
        None,
    )
    if not callable(latest_method):
        return None
    row = latest_method()
    return _grid_meter_api_row(
        row,
        now_epoch=now_epoch,
    )


def _grid_meter_api_row(
    row: dict[str, Any] | None,
    *,
    now_epoch: float,
) -> dict[str, Any] | None:
    """Convert one persisted grid-meter row to public JSON."""

    if row is None:
        return None

    metadata: dict[str, Any] = {}
    raw_metadata = row.get("metadata_json")
    if isinstance(raw_metadata, str) and raw_metadata:
        try:
            parsed = json.loads(raw_metadata)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError:
            metadata = {}

    last_update = row.get("received_at")
    age_seconds: int | None = None
    if isinstance(last_update, str):
        try:
            age_seconds = max(
                0,
                int(now_epoch - datetime.fromisoformat(last_update).timestamp()),
            )
        except ValueError:
            age_seconds = None

    return {
        "sample_id": row.get("sample_id"),
        "source_id": row.get("source_id"),
        "name": row.get("source_name"),
        "adapter": row.get("adapter"),
        "status": row.get("device_status"),
        "quality": row.get("quality"),
        "last_update": last_update,
        "measured_at": row.get("measured_at"),
        "age_seconds": age_seconds,
        "power_w": _optional_float(row.get("grid_power_w")),
        "import_power_w": _optional_float(row.get("grid_import_power_w")),
        "export_power_w": _optional_float(row.get("grid_export_power_w")),
        "import_total_kwh": _optional_float(row.get("grid_import_total_kwh")),
        "export_total_kwh": _optional_float(row.get("grid_export_total_kwh")),
        "active_source_id": row.get("active_source_id"),
        "error": row.get("error_text"),
        "metadata": metadata,
    }


def _legacy_active_grid_source_id(
    latest: dict[str, Any] | None,
) -> str | None:
    """Map established source labels to stable identifiers."""

    if not latest:
        return None
    label = latest.get("grid_source")
    if not isinstance(label, str):
        return None
    if label.startswith("Separate Hausmessung"):
        return "house_meter"
    if label.startswith("Solakon ONE Meter"):
        return "solakon_one"
    return None


def build_dashboard_api_response(
    database: Database,
    period: str,
    anchor_value: str | None,
) -> dict[str, Any]:
    """Build the existing dashboard API payload."""
    if period not in {"day", "week", "year"}:
        period = "day"

    anchor = parse_anchor(anchor_value)

    return build_dashboard(
        database,
        period,
        anchor,
    )


def build_phase_live_api_response(
    database: PhaseDatabaseApi,
    source_id: str = "house_meter",
) -> dict[str, Any]:
    """Return the newest phase snapshot in a browser-friendly structure."""

    normalized_source = _phase_source_id(source_id)
    return {
        "source_id": normalized_source,
        "latest": _phase_api_row(database.latest_phase_sample(normalized_source)),
    }


def build_phase_dashboard_api_response(
    database: PhaseDatabaseApi,
    period: str,
    anchor_value: str | None,
    source_id: str = "house_meter",
) -> dict[str, Any]:
    """Aggregate persisted phase power into dashboard period buckets."""

    if period not in {"day", "week", "year"}:
        period = "day"
    normalized_source = _phase_source_id(source_id)
    anchor = parse_anchor(anchor_value)
    start, end, labels, title = period_bounds(period, anchor)
    rows = database.phase_rows_between(
        start.timestamp(),
        end.timestamp(),
        source_id=normalized_source,
    )

    sums = {phase: [0.0] * len(labels) for phase in _PHASE_NAMES}
    counts = {phase: [0] * len(labels) for phase in _PHASE_NAMES}
    total_sums = {phase: 0.0 for phase in _PHASE_NAMES}
    total_counts = {phase: 0 for phase in _PHASE_NAMES}
    suspect_samples = 0
    max_spread_w: float | None = None

    for row in rows:
        sample_time = datetime.fromtimestamp(
            float(row["ts_epoch"]),
            tz=start.tzinfo,
        )
        index = bucket_index(period, start, sample_time)
        if not 0 <= index < len(labels):
            continue

        if any(
            row.get(f"{phase}_quality")
            in {"suspect", "rejected", "stale", "unavailable"}
            for phase in _PHASE_NAMES
        ):
            suspect_samples += 1

        spread = _optional_float(row.get("phase_power_spread_w"))
        if spread is not None:
            max_spread_w = spread if max_spread_w is None else max(max_spread_w, spread)

        for phase in _PHASE_NAMES:
            value = _optional_float(row.get(f"{phase}_power_w"))
            if value is None:
                continue
            sums[phase][index] += value
            counts[phase][index] += 1
            total_sums[phase] += value
            total_counts[phase] += 1

    series = {
        f"{phase}_power_w": [
            round(sums[phase][index] / counts[phase][index], 3)
            if counts[phase][index]
            else None
            for index in range(len(labels))
        ]
        for phase in _PHASE_NAMES
    }
    averages = {
        phase: (
            round(total_sums[phase] / total_counts[phase], 3)
            if total_counts[phase]
            else None
        )
        for phase in _PHASE_NAMES
    }

    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "title": title,
        "source_id": normalized_source,
        "labels": labels,
        "series": series,
        "summary": {
            "sample_count": len(rows),
            "suspect_sample_count": suspect_samples,
            "average_power_w": averages,
            "max_spread_w": max_spread_w,
            "latest": _phase_api_row(rows[-1]) if rows else None,
        },
    }


def _phase_api_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert one flattened persistence row to the public phase shape."""

    if row is None:
        return None

    metadata: dict[str, Any] = {}
    metadata_json = row.get("metadata_json")
    if isinstance(metadata_json, str) and metadata_json:
        try:
            parsed = json.loads(metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError:
            metadata = {"invalid_metadata_json": metadata_json}

    phases = {
        phase: {
            "power_w": _optional_float(row.get(f"{phase}_power_w")),
            "voltage_v": _optional_float(row.get(f"{phase}_voltage_v")),
            "current_a": _optional_float(row.get(f"{phase}_current_a")),
            "power_factor": _optional_float(row.get(f"{phase}_power_factor")),
            "quality": row.get(f"{phase}_quality"),
        }
        for phase in _PHASE_NAMES
    }

    return {
        "sample_id": row.get("sample_id"),
        "source_id": row.get("source_id"),
        "measurement_role": row.get("measurement_role"),
        "device_status": row.get("device_status"),
        "error": row.get("error_text"),
        "ts_epoch": _optional_float(row.get("ts_epoch")),
        "ts_local": row.get("ts_local"),
        "measured_at": row.get("measured_at"),
        "received_at": row.get("received_at"),
        "phases": phases,
        "analysis": {
            "available_count": _optional_int(row.get("phase_power_available_count")),
            "complete": _optional_bool(row.get("phase_power_complete")),
            "total_source": row.get("phase_power_total_source"),
            "sum_w": _optional_float(row.get("phase_power_sum_w")),
            "spread_w": _optional_float(row.get("phase_power_spread_w")),
            "share_pct": {
                phase: _optional_float(row.get(f"phase_power_share_{phase}_pct"))
                for phase in _PHASE_NAMES
            },
            "total_delta_w": _optional_float(row.get("phase_power_total_delta_w")),
            "total_delta_pct": _optional_float(row.get("phase_power_total_delta_pct")),
            "total_consistent": _optional_bool(row.get("phase_power_total_consistent")),
        },
        "metadata": metadata,
    }


def _phase_source_id(value: str | None) -> str:
    """Return a compact source identifier without accepting empty values."""

    normalized = (value or "house_meter").strip()
    return normalized[:120] or "house_meter"


def _optional_float(value: object) -> float | None:
    """Convert supported SQLite scalar values to float."""

    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(value: object) -> int | None:
    """Convert supported SQLite scalar values to int."""

    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if value in {0, "0", "false", "False"}:
        return False
    if value in {1, "1", "true", "True"}:
        return True
    return None


_PHASE_NAMES = ("l1", "l2", "l3")


def build_test_device_api_response(
    root_config: dict[str, Any],
    role: str,
    payload: dict[str, Any],
    reader: Any,
) -> tuple[dict[str, Any], int | None]:
    """Build the existing Shelly device-test payload."""
    if role not in {
        "house_meter",
        "solakon_meter",
    }:
        return {
            "ok": False,
            "error": "Unbekannte Messstelle.",
        }, 404

    if payload:
        updates: dict[str, Any] = {
            "enabled": bool(payload.get("enabled", True)),
            "type": payload.get(
                "type",
                root_config[role]["type"],
            ),
            "host": payload.get("host", ""),
            "username": payload.get(
                "username",
                "",
            ),
            "password": payload.get(
                "password",
                "",
            ),
            "timeout_seconds": payload.get(
                "timeout_seconds",
                3,
            ),
            "direction_factor": payload.get(
                "direction_factor",
                1,
            ),
        }
        if role == "house_meter":
            updates.update(
                {
                    "measurement_role": payload.get(
                        "measurement_role",
                        root_config[role].get("measurement_role"),
                    ),
                    "phase_direction": payload.get(
                        "phase_direction",
                        root_config[role].get("phase_direction", {}),
                    ),
                }
            )
        root_config[role].update(updates)

        root_config = ConfigManager.validate(root_config)

    config = root_config[role]

    if not config.get("enabled"):
        return {
            "ok": False,
            "error": "Messstelle ist deaktiviert.",
        }, 400

    try:
        reading = reader.read(config, role)

        return {
            "ok": True,
            "reading": asdict(reading),
        }, None
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }, 502


def build_test_solakon_one_api_response(
    root_config: dict[str, Any],
    payload: dict[str, Any],
    reader: Any,
) -> tuple[dict[str, Any], int | None]:
    """Build the existing Solakon ONE test payload."""
    root_config["solakon_one"].update(
        {
            "enabled": bool(payload.get("enabled", True)),
            "host": payload.get("host", ""),
            "port": payload.get("port", 502),
            "device_id": payload.get(
                "device_id",
                1,
            ),
            "timeout_seconds": payload.get(
                "timeout_seconds",
                5,
            ),
            "simulation": bool(payload.get("simulation", False)),
        }
    )

    try:
        root_config = ConfigManager.validate(root_config)
        config = root_config["solakon_one"]

        if not config.get("enabled"):
            return {
                "ok": False,
                "error": ("Solakon ONE ist deaktiviert."),
            }, 400

        reading = reader.test(config)

        return {
            "ok": True,
            "reading": reading.to_dict(),
        }, None
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }, 502
