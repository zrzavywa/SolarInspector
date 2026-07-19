from pathlib import Path
from unittest.mock import patch

import json
import solarinspector as si
from github_updater import ReleaseInfo


@patch("solarinspector.download_and_verify_release")
@patch("solarinspector.check_for_update")
def test_update_download_endpoint(
    mock_check,
    mock_download,
    tmp_path: Path,
    monkeypatch,
):
    status_path = tmp_path / "update-status.json"
    cache_path = tmp_path / "updates"

    monkeypatch.setattr(si, "UPDATE_STATUS_PATH", status_path)
    monkeypatch.setattr(si, "UPDATE_CACHE_DIR", cache_path)

    mock_check.return_value = ReleaseInfo(
        installed_version="4.1.0",
        available_version="4.2.0",
        update_available=True,
        release_name="SolarInspector 4.2.0",
        release_notes="Test",
        published_at="2026-07-19T18:00:00Z",
        html_url="https://example.invalid/release",
        asset_name="SolarInspector-4.2.0.tar.gz",
        asset_url="https://example.invalid/archive",
        checksum_name="SolarInspector-4.2.0.tar.gz.sha256",
        checksum_url="https://example.invalid/checksum",
    )

    archive_path = cache_path / "4.2.0" / "SolarInspector-4.2.0.tar.gz"
    mock_download.return_value = archive_path

    client = si.app.test_client()
    response = client.post("/api/update/download")

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["state"] == "verified"
    assert payload["progress"] == 100
    assert payload["available_version"] == "4.2.0"
    assert payload["archive_path"] == str(archive_path)


def test_update_status_endpoint(tmp_path: Path, monkeypatch):
    status_path = tmp_path / "update-status.json"
    monkeypatch.setattr(si, "UPDATE_STATUS_PATH", status_path)

    client = si.app.test_client()
    response = client.get("/api/update/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "idle"

def test_update_install_endpoint(
    tmp_path: Path,
    monkeypatch,
):
    status_path = (
        tmp_path / "update-status.json"
    )
    request_path = (
        tmp_path / "update-request.json"
    )

    monkeypatch.setattr(
        si,
        "UPDATE_STATUS_PATH",
        status_path,
    )
    monkeypatch.setattr(
        si,
        "UPDATE_REQUEST_PATH",
        request_path,
    )

    si.write_update_status(
        status_path,
        state="verified",
        progress=100,
        available_version="4.2.0",
        archive_path=(
            "/tmp/"
            "SolarInspector-4.2.0.tar.gz"
        ),
    )

    client = si.app.test_client()
    response = client.post(
        "/api/update/install"
    )

    assert response.status_code == 202
    assert request_path.exists()

    payload = json.loads(
        request_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["version"] == "4.2.0"
