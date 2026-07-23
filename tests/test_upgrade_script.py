"""Tests for the Raspberry Pi upgrade script package layout."""

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "Upgrade-SolarInspector-RaspberryPi.sh"


def run_help(script_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the upgrade script help command."""

    return subprocess.run(
        ["bash", str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_upgrade_script_uses_project_version() -> None:
    """Ensure the repository layout reads the canonical VERSION file."""

    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    result = run_help(SCRIPT_PATH)

    assert result.returncode == 0, result.stderr
    assert f"SolarInspector {version}" in result.stdout


def test_upgrade_script_supports_root_package_layout(
    tmp_path: Path,
) -> None:
    """Ensure the historical root-level package layout remains supported."""

    version = "4.5.0"
    package_script = tmp_path / "Upgrade-SolarInspector-RaspberryPi.sh"

    shutil.copy2(SCRIPT_PATH, package_script)
    (tmp_path / "VERSION").write_text(
        version + "\n",
        encoding="utf-8",
    )

    result = run_help(package_script)

    assert result.returncode == 0, result.stderr
    assert f"SolarInspector {version}" in result.stdout


def test_upgrade_script_rejects_missing_version(
    tmp_path: Path,
) -> None:
    """Ensure packages without a VERSION file are rejected."""

    scripts_directory = tmp_path / "scripts"
    scripts_directory.mkdir()

    package_script = scripts_directory / "Upgrade-SolarInspector-RaspberryPi.sh"
    shutil.copy2(SCRIPT_PATH, package_script)

    result = run_help(package_script)

    assert result.returncode != 0
    assert "VERSION-Datei wurde im Paket nicht gefunden." in result.stderr


def test_upgrade_script_rejects_invalid_version(
    tmp_path: Path,
) -> None:
    """Ensure malformed package versions are rejected."""

    package_script = tmp_path / "Upgrade-SolarInspector-RaspberryPi.sh"

    shutil.copy2(SCRIPT_PATH, package_script)
    (tmp_path / "VERSION").write_text(
        "4.5\n",
        encoding="utf-8",
    )

    result = run_help(package_script)

    assert result.returncode != 0
    assert "Ungültige Version" in result.stderr
