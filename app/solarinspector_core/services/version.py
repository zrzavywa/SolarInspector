"""Read the installed SolarInspector version."""

from __future__ import annotations

from pathlib import Path


def read_installed_version(
    version_file: Path,
) -> str:
    """Read a VERSION file with the existing fallback behavior."""
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"

    return version or "0.0.0"
