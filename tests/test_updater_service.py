import json
from pathlib import Path
from unittest.mock import patch

from updater_service import (
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

    mock_prepare.return_value = (
        release_directory
    )

    run_update(
        request_path=request_path,
        status_path=status_path,
        releases_directory=releases,
        current_link=current,
        healthcheck_url=(
            "http://127.0.0.1:8787/api/health"
        ),
        service_name=(
            "solarinspector.service"
        ),
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
