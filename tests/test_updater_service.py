import json
from pathlib import Path
from unittest.mock import patch

from updater_service import (
    create_backup,
    read_request,
    run_update,
)


def test_read_request(tmp_path: Path):
    request_path = (
        tmp_path / "update-request.json"
    )

    request_path.write_text(
        json.dumps(
            {
                "version": "4.1.0",
                "archive_path": (
                    "/tmp/"
                    "SolarInspector-4.1.0.tar.gz"
                ),
            }
        ),
        encoding="utf-8",
    )

    payload = read_request(request_path)

    assert payload["version"] == "4.1.0"


@patch(
    "updater_service.activate_with_healthcheck"
)
@patch(
    "updater_service.prepare_release_environment"
)
def test_run_update(
    mock_prepare,
    mock_activate,
    tmp_path: Path,
):
    request_path = (
        tmp_path / "update-request.json"
    )
    status_path = (
        tmp_path / "update-status.json"
    )
    releases = tmp_path / "releases"
    current = tmp_path / "current"

    archive_path = (
        tmp_path
        / "SolarInspector-4.1.0.tar.gz"
    )

    request_path.write_text(
        json.dumps(
            {
                "version": "4.1.0",
                "archive_path": str(
                    archive_path
                ),
            }
        ),
        encoding="utf-8",
    )

    release_directory = (
        releases / "4.1.0"
    )

    app_directory = release_directory / "app"
    app_directory.mkdir(parents=True)

    config_path = tmp_path / "config.json"
    database_path = tmp_path / "solarinspector.db"

    config_path.write_text(
        '{"test": true}',
        encoding="utf-8",
    )

    database_path.write_bytes(
        b"sqlite-data"
    )

    mock_prepare.return_value = (
        release_directory
    )

    run_update(
        request_path=request_path,
        status_path=status_path,
        releases_directory=releases,
        current_link=current,
        healthcheck_url="http://127.0.0.1:8787/api/health",
        service_name="solarinspector.service",
        backup_directory=tmp_path / "backups",
        config_path=config_path,
        database_path=database_path,
    )

    assert not request_path.exists()

    payload = json.loads(
        status_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["state"] == "success"
    assert payload["progress"] == 100

    mock_prepare.assert_called_once()
    mock_activate.assert_called_once()

    config_link = release_directory / "app" / "config.json"
    data_link = release_directory / "app" / "data"

    assert config_link.is_symlink()
    assert data_link.is_symlink()

    assert config_link.resolve() == config_path.resolve()
    assert data_link.resolve() == database_path.parent.resolve()

def test_create_backup(tmp_path: Path):
    backup_directory = tmp_path / "backups"
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "solarinspector.db"

    releases = tmp_path / "releases"
    current_release = releases / "4.0.1"
    current_link = tmp_path / "current"

    current_release.mkdir(parents=True)
    current_link.symlink_to(current_release.resolve())

    config_path.write_text('{"test": true}', encoding="utf-8")
    database_path.write_bytes(b"sqlite-data")

    result = create_backup(
        backup_directory=backup_directory,
        version="4.1.0",
        config_path=config_path,
        database_path=database_path,
        current_link=current_link,
    )

    assert (result / "config.json").exists()
    assert (result / "solarinspector.db").exists()
    assert (result / "previous-release.txt").exists()
    assert (result / "backup.json").exists()
