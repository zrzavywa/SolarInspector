"""Local, dependency-free quality contracts for active documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "TRADEMARKS.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/api.md",
    "docs/architecture.md",
    "docs/configuration.md",
    "docs/devices.md",
    "docs/development.md",
    "docs/installation-raspberry-pi.md",
    "docs/migration-from-solarinspector.md",
    "docs/operation.md",
    "docs/security.md",
    "docs/shrdzm-grid-meter.md",
    "docs/troubleshooting.md",
    "docs/updates.md",
    "docs/development/4.5/README.md",
)
ARCHIVE_INDEX = PROJECT_ROOT / "docs/development/4.5/README.md"


def _markdown_without_fences(path: Path) -> str:
    """Return Markdown with fenced code blocks removed."""
    return re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def _relative_targets(path: Path) -> list[str]:
    """Collect local Markdown and image targets without network access."""
    content = _markdown_without_fences(path)
    return [
        target.split("#", 1)[0]
        for target in re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", content)
    ]


def _leaf_keys(value: object, prefix: str = "") -> list[str]:
    """Return leaf key paths from the canonical JSON example."""
    if not isinstance(value, dict):
        return [prefix]
    keys: list[str] = []
    for key, child in value.items():
        full = f"{prefix}.{key}" if prefix else key
        keys.extend(_leaf_keys(child, full))
    return keys


def test_active_relative_links_exist_without_network_access() -> None:
    """All active local links resolve relative to their Markdown document."""
    for relative in ACTIVE_DOCUMENTS:
        document = PROJECT_ROOT / relative
        for target in _relative_targets(document):
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (document.parent / target).resolve().exists(), (
                f"broken link: {relative} -> {target}"
            )


def test_documentation_indexes_are_complete() -> None:
    """Main and 4.5 archive indexes expose their required documents."""
    main_index = (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    for relative in ACTIVE_DOCUMENTS:
        if relative.startswith("docs/") and relative != "docs/README.md":
            assert (
                Path(relative).name in main_index
                or relative.removeprefix("docs/") in main_index
            )

    archive_files = {
        path.name
        for path in ARCHIVE_INDEX.parent.iterdir()
        if path.is_file() and path.name != "README.md"
    }
    archive_links = set(_relative_targets(ARCHIVE_INDEX))
    assert archive_files <= {Path(link).name for link in archive_links}


def test_central_versions_and_changelog_match_version_file() -> None:
    """Current documentation states the release version and has an Unreleased entry."""
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (PROJECT_ROOT / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == version
    assert f"{version}" in (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{version}" in (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert f"{version}" in (PROJECT_ROOT / "docs/architecture.md").read_text(
        encoding="utf-8"
    )
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog and f"## [{version}]" in changelog


def test_all_config_example_leaf_keys_are_documented() -> None:
    """Every canonical leaf key appears in the configuration reference."""
    example = json.loads(
        (PROJECT_ROOT / "app/config.example.json").read_text(encoding="utf-8")
    )
    documentation = (PROJECT_ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    for key_path in _leaf_keys(example):
        section, leaf = key_path.rsplit(".", 1)
        assert leaf in documentation, key_path
        if section == "general":
            section_heading = "## Abschnitt `general`"
        elif section == "persistence.retention":
            section_heading = "## Abschnitt `persistence.retention`"
        elif section.startswith("energy_balance"):
            section_heading = "## Abschnitt `energy_balance`"
        elif section.startswith("grid_meter"):
            section_heading = "## Abschnitt `grid_meter`"
        elif section.startswith("solakon_one"):
            section_heading = "## Abschnitt `solakon_one`"
        elif section.startswith("house_meter"):
            section_heading = "## Abschnitt `house_meter`"
        elif section.startswith("solakon_meter"):
            section_heading = "## Abschnitt `solakon_meter`"
        else:
            section_heading = ""
        assert section_heading in documentation, key_path


def test_current_architecture_repository_paths_exist() -> None:
    """Backticked current repository paths in architecture.md exist."""
    architecture = _markdown_without_fences(PROJECT_ROOT / "docs/architecture.md")
    for raw in re.findall(r"`([^`]+)`", architecture):
        if (
            raw.startswith(("/opt/", "/etc/", "/var/"))
            or raw in {"releases/", "current", "releases"}
            or "/" not in raw
        ):
            continue
        assert (PROJECT_ROOT / raw.rstrip("/")).exists(), raw


def test_mermaid_blocks_are_closed_and_typed() -> None:
    """Mermaid fences have balanced boundaries and recognized diagram types."""
    for relative in ("README.md", "docs/architecture.md", "docs/updates.md"):
        content = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        blocks = re.findall(r"```mermaid\n(.*?)```", content, flags=re.DOTALL)
        assert content.count("```mermaid") == content.count("```mermaid\n")
        for block in blocks:
            assert re.match(
                r"\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram)\b",
                block,
            )
