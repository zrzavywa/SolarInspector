from unittest.mock import Mock, patch

from github_updater import check_for_update


@patch("github_updater.requests.get")
def test_newer_release_is_detected(mock_get):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "tag_name": "v4.1.0",
        "name": "SolarInspector 4.1.0",
        "body": "GitHub update support",
        "published_at": "2026-07-19T18:00:00Z",
        "html_url": "https://github.com/zrzavywa/SolarInspector/releases/tag/v4.1.0",
        "assets": [
            {
                "name": "SolarInspector-4.1.0.tar.gz",
                "browser_download_url": "https://example.invalid/archive",
            },
            {
                "name": "SolarInspector-4.1.0.tar.gz.sha256",
                "browser_download_url": "https://example.invalid/checksum",
            },
        ],
    }
    mock_get.return_value = response

    result = check_for_update("4.0.1")

    assert result.update_available is True
    assert result.available_version == "4.1.0"
    assert result.asset_name == "SolarInspector-4.1.0.tar.gz"
    assert result.checksum_name == "SolarInspector-4.1.0.tar.gz.sha256"
