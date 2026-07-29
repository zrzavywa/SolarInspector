"""Shared release validation helpers used before application startup."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from packaging.version import Version


class ReleaseContractError(RuntimeError):
    """Raised when a release contract is not satisfied."""


def read_release_version(release_directory: Path) -> str:
    """Read and validate the semantic version declared by a release."""
    value = (release_directory / "VERSION").read_text(encoding="utf-8").strip()
    try:
        parsed = Version(value)
    except Exception as exc:
        raise ReleaseContractError(f"Ungültige Release-Version: {value!r}") from exc
    if str(parsed) != value or parsed != Version("4.5.5"):
        raise ReleaseContractError(f"Unerwartete Release-Version: {value!r}")
    return value


def find_python311(minimum: tuple[int, int] = (3, 11)) -> str:
    """Return the first usable Python >= 3.11, preferring /opt interpreters."""
    candidates = [Path("/opt/python-3.11.15/bin/python3.11")]
    candidates.extend(
        Path(item)
        for item in (
            shutil.which("python3.13"),
            shutil.which("python3.12"),
            shutil.which("python3.11"),
        )
        if item
    )
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
            continue
        result = subprocess.run(
            [
                str(candidate),
                "-c",
                "import sys; print('%d.%d' % sys.version_info[:2])",
            ],
            capture_output=True,
            text=True,
        )
        if (
            result.returncode == 0
            and tuple(map(int, result.stdout.strip().split("."))) >= minimum
        ):
            return str(candidate)
    raise ReleaseContractError("Kein Python 3.11+ Interpreter gefunden.")


def extract_sha256(checksum_text: str) -> str:
    """Extract exactly one plain SHA-256 value, ignoring stored paths."""
    matches = re.findall(
        r"(?m)^[ \t]*([0-9a-fA-F]{64})(?:[ \t]+\*?[^\r\n]*)?[ \t]*$",
        checksum_text,
    )
    if len(matches) != 1:
        raise ReleaseContractError(
            "Prüfsummendatei muss genau einen SHA-256-Wert enthalten."
        )
    return matches[0].lower()


def verify_sha256_archive(archive: Path, checksum_file: Path) -> None:
    """Verify an archive against a path-independent checksum file."""
    expected = extract_sha256(checksum_file.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ReleaseContractError(
            "SHA-256-Prüfung des Release-Archivs fehlgeschlagen."
        )
