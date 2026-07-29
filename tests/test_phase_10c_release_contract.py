from pathlib import Path

import pytest
from release_contract import (
    ReleaseContractError,
    extract_sha256,
    read_release_version,
)
from zrzavy_energy_monitor_core.direct_migration import (
    DirectMigrationError,
    resolve_legacy_installation,
)


def test_checksum_ignores_absolute_build_path() -> None:
    digest = "a" * 64
    assert extract_sha256(f"{digest}  /build/work/release.tar.gz\n") == digest


def test_checksum_rejects_ambiguous_content() -> None:
    with pytest.raises(ReleaseContractError):
        extract_sha256("a" * 64 + "\n" + "b" * 64 + "\n")


def test_release_version_is_exact(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("20260729T120000Z\n", encoding="utf-8")
    with pytest.raises(ReleaseContractError):
        read_release_version(tmp_path)


def _legacy_release(root: Path) -> Path:
    release = root / "releases" / "4.1.3"
    (release / "app").mkdir(parents=True)
    (release / ".venv/bin").mkdir(parents=True)
    (release / "VERSION").write_text("4.1.3\n", encoding="utf-8")
    (release / "app/solarinspector.py").write_text("# legacy\n", encoding="utf-8")
    (release / ".venv/bin/python").touch()
    return release


def test_legacy_current_symlink_is_repaired(tmp_path: Path) -> None:
    release = _legacy_release(tmp_path)
    (tmp_path / "current").symlink_to(tmp_path / "missing")
    assert resolve_legacy_installation(tmp_path) == release
    assert (tmp_path / "current").resolve() == release


def test_real_legacy_current_directory_is_never_replaced(tmp_path: Path) -> None:
    (tmp_path / "current").mkdir()
    with pytest.raises(DirectMigrationError):
        resolve_legacy_installation(tmp_path)
