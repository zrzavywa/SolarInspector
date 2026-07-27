import json
from pathlib import Path
from unittest.mock import patch

import pytest
import zrzavy_energy_monitor as si
from github_updater import ReleaseInfo
from zrzavy_energy_monitor_core.services.update import perform_update_download

pytestmark = pytest.mark.release



@patch("zrzavy_energy_monitor.download_and_verify_release")
@patch("zrzavy_energy_monitor.check_for_update")
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


def test_download_returns_json_when_initial_status_write_fails(tmp_path: Path):
    def failing_writer(*_args, **_kwargs):
        raise PermissionError("/private/path")

    payload, status_code = perform_update_download(
        installed_version="4.5.1",
        status_path=tmp_path / "status.json",
        cache_directory=tmp_path / "updates",
        update_checker=lambda _version: pytest.fail("checker must not run"),
        release_downloader=lambda *_args, **_kwargs: pytest.fail("download must not run"),
        status_writer=failing_writer,
    )

    assert status_code == 502
    assert payload["state"] == "failed"
    assert payload["message"] == "Update konnte lokal nicht gespeichert werden."
    assert "/private/path" not in str(payload)


def test_download_returns_json_when_cache_write_fails(tmp_path: Path):
    release = ReleaseInfo(
        installed_version="4.5.1", available_version="4.5.2",
        update_available=True, release_name="Test", release_notes="",
        published_at="2026-07-27T00:00:00Z", html_url="", asset_name="a",
        asset_url="", checksum_name="a.sha256", checksum_url="",
    )

    def failing_download(*_args, **_kwargs):
        raise PermissionError("/secret/cache")

    payload, status_code = perform_update_download(
        installed_version="4.5.1", status_path=tmp_path / "status.json",
        cache_directory=tmp_path / "updates", update_checker=lambda _version: release,
        release_downloader=failing_download,
        status_writer=si.write_update_status,
    )

    assert status_code == 502
    assert payload["state"] == "failed"
    assert "/secret/cache" not in str(payload)


def test_status_temp_file_is_removed_after_write_failure(tmp_path: Path, monkeypatch):
    import update_status

    status_path = tmp_path / "status.json"
    temporary_path = status_path.with_suffix(".json.tmp")
    monkeypatch.setattr(temporary_path.__class__, "replace", lambda *_args: (_ for _ in ()).throw(OSError("no")))

    with pytest.raises(OSError):
        update_status.write_update_status(status_path, state="checking")

    assert not temporary_path.exists()
