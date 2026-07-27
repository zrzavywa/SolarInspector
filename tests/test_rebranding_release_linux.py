"""R.6 release, Linux, and systemd rebranding contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_release_pipeline_uses_canonical_artifact_names() -> None:
    """Keep manifest, build script, and workflow on one asset contract."""

    manifest = json.loads(
        (PROJECT_ROOT / "release-manifest.json").read_text(encoding="utf-8")
    )
    build_script = (PROJECT_ROOT / "scripts/build-release.sh").read_text(
        encoding="utf-8"
    )
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert manifest["product"] == "Zrzavy Energy Monitor"
    assert manifest["product_id"] == "zrzavy-energy-monitor"
    assert manifest["asset"] == f"zrzavy-energy-monitor-{VERSION}.tar.gz"
    assert 'PACKAGE_NAME="zrzavy-energy-monitor-${VERSION}"' in build_script
    assert "dist/zrzavy-energy-monitor-*.tar.gz" in workflow
    assert "dist/SolarInspector-" not in workflow
    assert "--exclude='Upgrade-SolarInspector-RaspberryPi.sh'" in build_script


def test_canonical_systemd_units_prevent_collector_conflicts() -> None:
    """Use only canonical paths while explicitly conflicting with the old app."""

    systemd_directory = PROJECT_ROOT / "systemd"
    application = (systemd_directory / "zrzavy-energy-monitor.service").read_text(
        encoding="utf-8"
    )
    updater = (systemd_directory / "zrzavy-energy-monitor-updater.service").read_text(
        encoding="utf-8"
    )
    updater_path = (systemd_directory / "zrzavy-energy-monitor-updater.path").read_text(
        encoding="utf-8"
    )

    assert "Description=Zrzavy Energy Monitor" in application
    assert "Conflicts=solarinspector.service" in application
    assert "User=solarinspector" in application
    assert "/opt/zrzavy-energy-monitor/current" in application
    assert "ZRZAVY_ENERGY_MONITOR_CONFIG_PATH=" in application
    assert "ZRZAVY_ENERGY_MONITOR_DATABASE_PATH=" in application
    assert "ReadWritePaths=/etc/zrzavy-energy-monitor" in application
    assert "/opt/solarinspector" not in application + updater + updater_path
    assert "Unit=zrzavy-energy-monitor-updater.service" in updater_path


def test_linux_scripts_are_syntactically_valid_and_safety_gated() -> None:
    """Keep privileged orchestration explicit and rollback-enabled."""

    migration = PROJECT_ROOT / "scripts/migrate-to-zrzavy-energy-monitor.sh"
    bootstrap = PROJECT_ROOT / "scripts/install-updater-bootstrap.sh"

    for script in (migration, bootstrap):
        subprocess.run(
            ["bash", "-n", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    content = migration.read_text(encoding="utf-8")
    assert "--orchestrate-systemd" in content
    assert "--keep-legacy-paths" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content
    assert '"$EUID" -ne 0' in content
    assert 'systemctl_is_active "$NEW_SERVICE"' in content
    assert 'systemctl stop "$OLD_SERVICE"' in content
    assert 'systemctl stop "$OLD_SERVICE" "$OLD_UPDATER_PATH"' in content
    assert "Rollback refused: a collector is still active." in content
    assert "trap restore_legacy_service ERR" in content
    assert "DATA_MIGRATION_APPLIED=false" in content
    assert 'if [[ "$DATA_MIGRATION_APPLIED" == true ]]' in content
    assert "wait_for_healthcheck" in content
    assert 'systemctl disable "$OLD_SERVICE" "$OLD_UPDATER_PATH"' in content
