from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from packaging.version import InvalidVersion, Version


GITHUB_OWNER = "zrzavywa"
GITHUB_REPOSITORY = "SolarInspector"

LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
)


class UpdateCheckError(RuntimeError):
    """Raised when the GitHub update check cannot be completed."""


@dataclass(frozen=True)
class ReleaseInfo:
    installed_version: str
    available_version: str
    update_available: bool
    release_name: str
    release_notes: str
    published_at: str | None
    html_url: str
    asset_name: str | None
    asset_url: str | None
    checksum_name: str | None
    checksum_url: str | None


def _find_asset(
    assets: list[dict[str, Any]],
    expected_name: str,
) -> dict[str, Any] | None:
    for asset in assets:
        if asset.get("name") == expected_name:
            return asset
    return None


def check_for_update(
    installed_version: str,
    timeout: int = 10,
) -> ReleaseInfo:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"SolarInspector/{installed_version}",
    }

    try:
        response = requests.get(
            LATEST_RELEASE_URL,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise UpdateCheckError(
            f"GitHub update check failed: {exc}"
        ) from exc

    payload = response.json()

    tag_name = str(payload.get("tag_name", "")).strip()
    available_version = tag_name.removeprefix("v")

    try:
        installed = Version(installed_version)
        available = Version(available_version)
    except InvalidVersion as exc:
        raise UpdateCheckError(
            f"Invalid version returned by GitHub: {tag_name}"
        ) from exc

    archive_name = f"SolarInspector-{available_version}.tar.gz"
    checksum_name = f"{archive_name}.sha256"

    assets = payload.get("assets", [])
    archive = _find_asset(assets, archive_name)
    checksum = _find_asset(assets, checksum_name)

    return ReleaseInfo(
        installed_version=installed_version,
        available_version=available_version,
        update_available=available > installed,
        release_name=str(payload.get("name") or tag_name),
        release_notes=str(payload.get("body") or ""),
        published_at=payload.get("published_at"),
        html_url=str(payload.get("html_url") or ""),
        asset_name=archive_name if archive else None,
        asset_url=archive.get("browser_download_url") if archive else None,
        checksum_name=checksum_name if checksum else None,
        checksum_url=checksum.get("browser_download_url") if checksum else None,
    )
