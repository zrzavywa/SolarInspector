from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from packaging.version import InvalidVersion, Version
import hashlib
import re
import tempfile
from pathlib import Path

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

class UpdateVerificationError(RuntimeError):
    """Raised when a downloaded release cannot be verified."""

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

SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def download_file(
    url: str,
    destination: Path,
    timeout: int = 60,
    maximum_size: int = 100 * 1024 * 1024,
) -> Path:
    """Download a release asset with a maximum size limit."""

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(
            url,
            stream=True,
            timeout=timeout,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "SolarInspector-Updater",
            },
        ) as response:
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > maximum_size:
                raise UpdateVerificationError(
                    "Das Release-Paket überschreitet die erlaubte Größe."
                )

            downloaded = 0

            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue

                    downloaded += len(chunk)

                    if downloaded > maximum_size:
                        raise UpdateVerificationError(
                            "Das Release-Paket überschreitet die erlaubte Größe."
                        )

                    handle.write(chunk)

    except requests.RequestException as exc:
        destination.unlink(missing_ok=True)
        raise UpdateCheckError(
            f"Download fehlgeschlagen: {exc}"
        ) from exc
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def parse_checksum_file(content: str, expected_filename: str) -> str:
    """Read a standard sha256 checksum file."""

    first_line = content.strip().splitlines()[0]
    parts = first_line.split()

    if not parts:
        raise UpdateVerificationError(
            "Die Prüfsummendatei ist leer."
        )

    checksum = parts[0].strip()

    if not SHA256_PATTERN.fullmatch(checksum):
        raise UpdateVerificationError(
            "Die SHA-256-Prüfsumme ist ungültig."
        )

    if len(parts) > 1:
        checksum_filename = parts[-1].lstrip("*")

        if Path(checksum_filename).name != expected_filename:
            raise UpdateVerificationError(
                "Die Prüfsumme gehört nicht zum erwarteten Release-Paket."
            )

    return checksum.lower()


def verify_sha256(path: Path, expected_checksum: str) -> None:
    actual_checksum = calculate_sha256(path)

    if actual_checksum.lower() != expected_checksum.lower():
        raise UpdateVerificationError(
            "Die SHA-256-Prüfung des Release-Pakets ist fehlgeschlagen."
        )


def download_and_verify_release(
    release: ReleaseInfo,
    target_directory: Path | None = None,
) -> Path:
    if not release.asset_url or not release.asset_name:
        raise UpdateVerificationError(
            "Das Release enthält kein Installationspaket."
        )

    if not release.checksum_url or not release.checksum_name:
        raise UpdateVerificationError(
            "Das Release enthält keine Prüfsummendatei."
        )

    if target_directory is None:
        target_directory = Path(
            tempfile.mkdtemp(prefix="solarinspector-update-")
        )

    archive_path = target_directory / release.asset_name
    checksum_path = target_directory / release.checksum_name

    download_file(release.asset_url, archive_path)
    download_file(
        release.checksum_url,
        checksum_path,
        maximum_size=64 * 1024,
    )

    checksum_content = checksum_path.read_text(encoding="utf-8")
    expected_checksum = parse_checksum_file(
        checksum_content,
        release.asset_name,
    )

    verify_sha256(archive_path, expected_checksum)

    return archive_path
