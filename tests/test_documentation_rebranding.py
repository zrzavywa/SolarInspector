"""Current documentation contracts for block R.8."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "TRADEMARKS.md",
    "docs/README.md",
    "docs/api.md",
    "docs/architecture.md",
    "docs/configuration.md",
    "docs/devices.md",
    "docs/installation-raspberry-pi.md",
    "docs/operation.md",
    "docs/security.md",
    "docs/shrdzm-grid-meter.md",
    "docs/troubleshooting.md",
    "docs/updates.md",
)
ARCHIVE_DIRECTORY = PROJECT_ROOT / "docs" / "development" / "4.5"


def test_current_documents_use_canonical_runtime_identifiers() -> None:
    """Exclude old runtime paths and services from active instructions."""

    prohibited = (
        "/opt/solarinspector",
        "/etc/solarinspector",
        "/var/lib/solarinspector",
        "/var/cache/solarinspector",
        "/var/log/solarinspector",
        "SolarInspector-<VERSION>",
        "SOLARINSPECTOR_CONFIG_PATH=",
        "systemctl status solarinspector.service",
        "systemctl start solarinspector.service",
        "systemctl stop solarinspector.service",
        "systemctl restart solarinspector.service",
    )

    for relative_path in CURRENT_DOCUMENTS:
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for old_identifier in prohibited:
            assert old_identifier not in content, (
                f"{relative_path} contains current legacy identifier {old_identifier}"
            )


def test_primary_documents_use_complete_name_and_description() -> None:
    """Keep the public name complete and ZEM supplementary."""

    for relative_path in ("README.md", "docs/README.md"):
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "Zrzavy Energy Monitor" in content
        assert "Open-source home energy monitoring and validation" in content
        assert content.splitlines()[0] != "# ZEM"


def test_legacy_name_is_explained_only_in_allowed_primary_contexts() -> None:
    """Document the former name without presenting it as current branding."""

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    trademarks = (PROJECT_ROOT / "TRADEMARKS.md").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "docs/migration-from-solarinspector.md").read_text(
        encoding="utf-8"
    )

    assert "Namenswechsel von SolarInspector" in readme
    assert "frühere Projektname" in trademarks
    assert "Direct migration from SolarInspector 4.1.3" in migration
    assert "Repository rename" in migration
    assert "Manual migration and healthcheck" in migration


def test_active_agent_instructions_use_canonical_identifiers() -> None:
    """Keep current instructions separate from temporary compatibility."""

    instructions = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert instructions.startswith("# Zrzavy Energy Monitor agent instructions")
    assert "app/zrzavy_energy_monitor_core/" in instructions
    assert "app/zrzavy_energy_monitor.py" in instructions
    assert "Temporary 4.5 compatibility" in instructions
    assert "app/solarinspector.py" in instructions
    assert "app/solarinspector_core/" in instructions


def test_development_archive_index_links_every_historical_file() -> None:
    """Make every pre-existing 4.5 development artifact discoverable."""

    index = (ARCHIVE_DIRECTORY / "README.md").read_text(encoding="utf-8")
    linked_targets = set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", index))
    archived_files = {
        path.name
        for path in ARCHIVE_DIRECTORY.iterdir()
        if path.is_file() and path.name != "README.md"
    }

    assert len(archived_files) == 42
    assert archived_files <= linked_targets


def test_changed_documentation_uses_valid_relative_links() -> None:
    """Resolve relative links introduced by the standards work package."""

    documents = (
        PROJECT_ROOT / "docs" / "README.md",
        PROJECT_ROOT / "docs" / "development" / "4.5" / "README.md",
    )

    for document in documents:
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            assert "://" not in target
            assert (document.parent / target).resolve().exists(), (
                f"{document.relative_to(PROJECT_ROOT)} contains broken link {target}"
            )
