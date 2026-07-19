from unittest.mock import patch

import solarinspector as si
from github_updater import ReleaseInfo



def test_health_endpoint():
    client = si.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["version"] == si.get_installed_version()

def test_system_version_endpoint():
    client = si.app.test_client()

    response = client.get("/api/system/version")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["product"] == "SolarInspector"
    assert payload["version"] == si.get_installed_version()

def test_update_page():
    client = si.app.test_client()

    response = client.get("/update")

    assert response.status_code == 200
    assert b"Software-Update" in response.data
    assert b"Update herunterladen und pr" in response.data
    assert b"Downloadstatus" in response.data

@patch("solarinspector.check_for_update")
def test_update_check_endpoint(mock_check):
    mock_check.return_value = ReleaseInfo(
        installed_version="4.1.0",
        available_version="4.2.0",
        update_available=True,
        release_name="SolarInspector 4.2.0",
        release_notes="Test release",
        published_at="2026-07-19T18:00:00Z",
        html_url="https://example.invalid/release",
        asset_name="SolarInspector-4.2.0.tar.gz",
        asset_url="https://example.invalid/archive",
        checksum_name="SolarInspector-4.2.0.tar.gz.sha256",
        checksum_url="https://example.invalid/checksum",
    )

    client = si.app.test_client()
    response = client.get("/api/update/check")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["update_available"] is True
    assert payload["available_version"] == "4.2.0"
