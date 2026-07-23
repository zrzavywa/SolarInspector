"""Coordinate SolarInspector software-update operations.

All paths and external operations are supplied by the compatible entry
module so existing runtime configuration and test monkeypatches remain
effective.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from github_updater import (
    UpdateCheckError,
    UpdateVerificationError,
)

UpdateChecker = Callable[[str], Any]
ReleaseDownloader = Callable[..., Path]
StatusReader = Callable[[Path], dict[str, Any]]
StatusWriter = Callable[..., dict[str, Any]]
RequestWriter = Callable[..., None]


def build_update_check_response(
    installed_version: str,
    update_checker: UpdateChecker,
) -> tuple[dict[str, Any], int | None]:
    """Build the existing update-check response."""
    try:
        release = update_checker(installed_version)
    except UpdateCheckError as exc:
        return {
            "status": "error",
            "installed_version": (installed_version),
            "message": str(exc),
        }, 502

    return {
        "status": "ok",
        "installed_version": (release.installed_version),
        "available_version": (release.available_version),
        "update_available": (release.update_available),
        "release_name": release.release_name,
        "release_notes": release.release_notes,
        "published_at": release.published_at,
        "release_url": release.html_url,
        "asset_name": release.asset_name,
        "asset_url": release.asset_url,
        "checksum_name": release.checksum_name,
        "checksum_url": release.checksum_url,
    }, None


def read_update_status_response(
    status_path: Path,
    status_reader: StatusReader,
) -> dict[str, Any]:
    """Read the existing persisted update status."""
    return status_reader(status_path)


def perform_update_download(
    installed_version: str,
    status_path: Path,
    cache_directory: Path,
    update_checker: UpdateChecker,
    release_downloader: ReleaseDownloader,
    status_writer: StatusWriter,
) -> tuple[dict[str, Any], int | None]:
    """Check, download, verify, and persist an update."""
    status_writer(
        status_path,
        state="checking",
        progress=10,
        message="GitHub Release wird geprüft.",
        installed_version=installed_version,
    )

    try:
        release = update_checker(installed_version)

        if not release.update_available:
            status = status_writer(
                status_path,
                state="idle",
                progress=0,
                message=("Keine neuere Version verfügbar."),
                available_version=(release.available_version),
            )
            return status, 409

        status_writer(
            status_path,
            state="downloading",
            progress=30,
            message=("Release-Paket wird heruntergeladen."),
            available_version=(release.available_version),
        )

        target_directory = cache_directory / release.available_version

        archive_path = release_downloader(
            release,
            target_directory=target_directory,
        )

        status = status_writer(
            status_path,
            state="verified",
            progress=100,
            message=("Release-Paket wurde erfolgreich heruntergeladen und geprüft."),
            archive_path=str(archive_path),
            available_version=(release.available_version),
        )

        return status, None

    except (
        UpdateCheckError,
        UpdateVerificationError,
    ) as exc:
        status = status_writer(
            status_path,
            state="failed",
            progress=0,
            message=str(exc),
        )
        return status, 502


def queue_update_installation(
    status_path: Path,
    status_reader: StatusReader,
    request_writer: RequestWriter,
    status_writer: StatusWriter,
) -> tuple[dict[str, Any], int]:
    """Queue installation of the verified update."""
    status = status_reader(status_path)

    if status.get("state") != "verified":
        return {
            "status": "error",
            "message": ("Es liegt kein verifiziertes Update-Paket vor."),
        }, 409

    version = status.get("available_version")
    archive_path = status.get("archive_path")

    if not version or not archive_path:
        return {
            "status": "error",
            "message": ("Updateinformationen sind unvollständig."),
        }, 409

    request_writer(
        version=version,
        archive_path=archive_path,
    )

    status_writer(
        status_path,
        state="queued",
        progress=0,
        message=("Update wurde zur Installation vorgemerkt."),
    )

    return {
        "status": "queued",
        "version": version,
    }, 202


def write_update_request_file(
    request_path: Path,
    version: str,
    archive_path: str,
) -> None:
    """Atomically persist an update installation request."""
    payload = {
        "version": version,
        "archive_path": archive_path,
    }

    request_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = request_path.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(request_path)
