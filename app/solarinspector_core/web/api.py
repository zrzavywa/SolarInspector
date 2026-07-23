"""Build responses for the basic SolarInspector HTTP APIs.

Flask route registration, JSON conversion, global dependency lookup, and
the patchable application clock remain in the compatible entry module.
"""

from __future__ import annotations

from typing import Any, Protocol


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

    return {
        "latest": latest,
        "collector": status,
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
