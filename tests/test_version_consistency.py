"""Tests for consistent Zrzavy Energy Monitor release metadata."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.release


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "VERSION"
RELEASE_MANIFEST_FILE = PROJECT_ROOT / "release-manifest.json"


def read_project_version() -> str:
    """Read the canonical project version."""

    return VERSION_FILE.read_text(encoding="utf-8").strip()


def read_release_manifest() -> dict[str, object]:
    """Read the canonical release manifest."""

    return json.loads(RELEASE_MANIFEST_FILE.read_text(encoding="utf-8"))


def test_release_manifest_matches_project_version() -> None:
    """Ensure release metadata matches the canonical project version."""

    version = read_project_version()
    manifest = read_release_manifest()

    archive_name = f"zrzavy-energy-monitor-{version}.tar.gz"

    assert manifest["product"] == "Zrzavy Energy Monitor"
    assert manifest["product_id"] == "zrzavy-energy-monitor"
    assert manifest["version"] == version
    assert manifest["asset"] == archive_name
    assert manifest["checksum_asset"] == f"{archive_name}.sha256"
