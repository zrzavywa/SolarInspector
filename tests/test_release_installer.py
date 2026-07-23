import io
import tarfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from release_installer import (
    ReleaseInstallError,
    activate_release,
    activate_with_healthcheck,
    prepare_release,
    prepare_release_environment,
    read_current_release,
    rollback_release,
    validate_release_archive,
    wait_for_healthcheck,
)

pytestmark = pytest.mark.release



@patch("release_installer.requests.get")
def test_healthcheck_accepts_expected_version(mock_get):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": "ok",
        "version": "4.1.0",
    }
    mock_get.return_value = response

    payload = wait_for_healthcheck(
        url="http://127.0.0.1:8787/api/health",
        expected_version="4.1.0",
        timeout_seconds=1,
        interval_seconds=0.01,
    )

    assert payload["status"] == "ok"

@patch("release_installer.requests.get")
def test_healthcheck_rejects_wrong_version(mock_get):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": "ok",
        "version": "4.0.1",
    }
    mock_get.return_value = response

    with pytest.raises(ReleaseInstallError):
        wait_for_healthcheck(
            url="http://127.0.0.1:8787/api/health",
            expected_version="4.1.0",
            timeout_seconds=0.05,
            interval_seconds=0.01,
        )

@patch("release_installer.wait_for_healthcheck")
def test_failed_healthcheck_rolls_back(
    mock_healthcheck,
    tmp_path: Path,
):
    releases = tmp_path / "releases"
    old_release = releases / "4.0.1"
    new_release = releases / "4.1.0"
    current = tmp_path / "current"

    old_release.mkdir(parents=True)
    new_release.mkdir(parents=True)
    current.symlink_to(old_release.resolve())

    mock_healthcheck.side_effect = ReleaseInstallError("boom")

    restart_calls = []

    def restart_service():
        restart_calls.append(True)

    with pytest.raises(ReleaseInstallError):
        activate_with_healthcheck(
            release_directory=new_release,
            current_link=current,
            healthcheck_url="http://127.0.0.1:8787/api/health",
            expected_version="4.1.0",
            restart_service=restart_service,
            timeout_seconds=1,
        )

    assert current.resolve() == old_release.resolve()
    assert len(restart_calls) == 2

@patch("release_installer.run_release_smoke_test")
@patch("release_installer.install_release_dependencies")
@patch("release_installer.create_release_venv")
def test_prepare_release_environment(
    mock_create_venv,
    mock_install_dependencies,
    mock_smoke_test,
    tmp_path: Path,
):
    archive_path = tmp_path / "SolarInspector-4.1.0.tar.gz"
    releases_directory = tmp_path / "releases"

    create_valid_archive(archive_path)

    expected_release = releases_directory / "4.1.0"
    expected_venv = expected_release / ".venv"

    mock_create_venv.return_value = expected_venv

    result = prepare_release_environment(
        archive_path=archive_path,
        version="4.1.0",
        releases_directory=releases_directory,
    )

    assert result == expected_release

    mock_create_venv.assert_called_once_with(
        expected_release,
        python_executable=None,
    )
    mock_install_dependencies.assert_called_once_with(
        expected_release,
        expected_venv,
    )
    mock_smoke_test.assert_called_once_with(
        expected_release,
        expected_venv,
    )


def create_valid_archive(path: Path, version: str = "4.1.0") -> None:
    root = f"SolarInspector-{version}"

    files = {
        f"{root}/VERSION": version.encode(),
        f"{root}/release-manifest.json": b"{}",
        f"{root}/app/solarinspector.py": b"print('ok')",
        f"{root}/app/requirements.txt": b"Flask>=3",
    }

    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_valid_release_archive(tmp_path: Path):
    archive_path = tmp_path / "SolarInspector-4.1.0.tar.gz"
    create_valid_archive(archive_path)

    members = validate_release_archive(
        archive_path,
        "SolarInspector-4.1.0",
    )

    assert len(members) == 4


def test_prepare_release(tmp_path: Path):
    archive_path = tmp_path / "SolarInspector-4.1.0.tar.gz"
    releases_directory = tmp_path / "releases"

    create_valid_archive(archive_path)

    result = prepare_release(
        archive_path=archive_path,
        version="4.1.0",
        releases_directory=releases_directory,
    )

    assert result == releases_directory / "4.1.0"
    assert (result / "VERSION").read_text() == "4.1.0"
    assert (result / "app" / "solarinspector.py").exists()


def test_path_traversal_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "malicious.tar.gz"

    with tarfile.open(archive_path, "w:gz") as archive:
        content = b"bad"
        info = tarfile.TarInfo(
            name="SolarInspector-4.1.0/../../evil.txt"
        )
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    with pytest.raises(ReleaseInstallError):
        validate_release_archive(
            archive_path,
            "SolarInspector-4.1.0",
        )


def test_symlink_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "symlink.tar.gz"

    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(
            name="SolarInspector-4.1.0/app/link"
        )
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)

    with pytest.raises(ReleaseInstallError):
        validate_release_archive(
            archive_path,
            "SolarInspector-4.1.0",
        )


def test_runtime_config_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "config.tar.gz"
    root = "SolarInspector-4.1.0"

    with tarfile.open(archive_path, "w:gz") as archive:
        content = b"{}"
        info = tarfile.TarInfo(
            name=f"{root}/app/config.json"
        )
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    with pytest.raises(ReleaseInstallError):
        validate_release_archive(
            archive_path,
            root,
        )


def test_activate_release_creates_current_symlink(tmp_path: Path):
    releases = tmp_path / "releases"
    release = releases / "4.1.0"
    current = tmp_path / "current"

    release.mkdir(parents=True)

    previous = activate_release(release, current)

    assert previous is None
    assert current.is_symlink()
    assert current.resolve() == release.resolve()

def test_activate_release_returns_previous_release(tmp_path: Path):
    releases = tmp_path / "releases"
    old_release = releases / "4.0.1"
    new_release = releases / "4.1.0"
    current = tmp_path / "current"

    old_release.mkdir(parents=True)
    new_release.mkdir(parents=True)

    current.symlink_to(old_release.resolve())

    previous = activate_release(new_release, current)

    assert previous == old_release.resolve()
    assert current.resolve() == new_release.resolve()

def test_rollback_restores_previous_release(tmp_path: Path):
    releases = tmp_path / "releases"
    old_release = releases / "4.0.1"
    new_release = releases / "4.1.0"
    current = tmp_path / "current"

    old_release.mkdir(parents=True)
    new_release.mkdir(parents=True)

    current.symlink_to(new_release.resolve())

    result = rollback_release(old_release, current)

    assert result == old_release.resolve()
    assert current.resolve() == old_release.resolve()

def test_non_symlink_current_path_is_rejected(tmp_path: Path):
    current = tmp_path / "current"
    current.mkdir()

    with pytest.raises(ReleaseInstallError):
        read_current_release(current)
