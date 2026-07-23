"""Characterization tests for stable error and fallback behavior."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import github_updater as gu
import pytest
import requests
import solarinspector as si
import update_status as us
from github_updater import (
    ReleaseInfo,
    UpdateCheckError,
    UpdateVerificationError,
)


class FrozenDateTime:
    """Provide a deterministic current date for fallback tests."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        value = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


class JsonResponse:
    """Minimal requests response used by update-check tests."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class DownloadResponse:
    """Minimal streaming response used by download limit tests."""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ):
        self.headers = headers or {}
        self.chunks = chunks or []

    def __enter__(self) -> "DownloadResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        assert chunk_size == 1024 * 1024
        return self.chunks


class StaticConfigManager:
    """Return a copy of one deterministic collector configuration."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


class FailingDatabase:
    """Reject persistence while exposing the Collector database interface."""

    def latest(self) -> None:
        return None

    def insert_sample(self, _sample: dict[str, Any]) -> int:
        raise RuntimeError("database unavailable")


def release_info(
    *,
    update_available: bool = True,
    asset_url: str | None = "https://example.invalid/archive",
    asset_name: str | None = "SolarInspector-4.2.0.tar.gz",
    checksum_url: str | None = "https://example.invalid/checksum",
    checksum_name: str | None = "SolarInspector-4.2.0.tar.gz.sha256",
) -> ReleaseInfo:
    """Create a deterministic release description."""

    return ReleaseInfo(
        installed_version="4.1.3",
        available_version="4.2.0",
        update_available=update_available,
        release_name="SolarInspector 4.2.0",
        release_notes="Test release",
        published_at="2026-07-23T10:00:00Z",
        html_url="https://example.invalid/release",
        asset_name=asset_name,
        asset_url=asset_url,
        checksum_name=checksum_name,
        checksum_url=checksum_url,
    )


def github_payload(
    *,
    tag_name: str = "v4.2.0",
    assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a minimal GitHub latest-release payload."""

    return {
        "tag_name": tag_name,
        "name": "SolarInspector 4.2.0",
        "body": "Test release",
        "published_at": "2026-07-23T10:00:00Z",
        "html_url": "https://example.invalid/release",
        "assets": assets or [],
    }


def test_installed_version_falls_back_when_version_file_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable VERSION file produces the historical neutral version."""

    def fail_read(_path: Path, encoding: str) -> str:
        raise OSError("not readable")

    monkeypatch.setattr(Path, "read_text", fail_read)

    assert si.get_installed_version() == "0.0.0"


def test_installed_version_falls_back_when_version_file_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty VERSION file also produces the neutral version."""

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _path, encoding: " \n",
    )

    assert si.get_installed_version() == "0.0.0"


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_parse_anchor_falls_back_to_current_local_date(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    """Missing and invalid date parameters resolve to today's date."""

    monkeypatch.setattr(si, "datetime", FrozenDateTime)

    assert si.parse_anchor(value) == datetime(2026, 7, 23).date()


def test_invalid_update_status_json_returns_defaults(tmp_path: Path) -> None:
    """A damaged update-status file is ignored instead of breaking the API."""

    path = tmp_path / "update-status.json"
    path.write_text("{invalid", encoding="utf-8")

    result = us.read_update_status(path)

    assert result == us.DEFAULT_STATUS
    assert result is not us.DEFAULT_STATUS


def test_partial_update_status_merges_defaults_and_preserves_unknown_fields(
    tmp_path: Path,
) -> None:
    """Status reads add missing defaults without discarding extra fields."""

    path = tmp_path / "update-status.json"
    path.write_text(
        '{"state": "failed", "custom": "preserved"}',
        encoding="utf-8",
    )

    result = us.read_update_status(path)

    assert result["state"] == "failed"
    assert result["progress"] == 0
    assert result["archive_path"] is None
    assert result["custom"] == "preserved"


def test_write_update_status_preserves_existing_values_and_replaces_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status writes merge fields and atomically replace the temporary file."""

    path = tmp_path / "state" / "update-status.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"installed_version": "4.1.3", "state": "checking"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        us,
        "utc_now_iso",
        lambda: "2026-07-23T10:30:00+00:00",
    )

    result = us.write_update_status(
        path,
        state="failed",
        message="offline",
    )

    assert result["installed_version"] == "4.1.3"
    assert result["state"] == "failed"
    assert result["message"] == "offline"
    assert result["updated_at"] == "2026-07-23T10:30:00+00:00"
    assert us.read_update_status(path) == result
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_update_check_wraps_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network failures are exposed as UpdateCheckError."""

    def fail_request(*_args: Any, **_kwargs: Any) -> None:
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(gu.requests, "get", fail_request)

    with pytest.raises(UpdateCheckError, match="offline"):
        gu.check_for_update("4.1.3")


def test_update_check_rejects_invalid_release_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid GitHub tag is translated into an update-check error."""

    monkeypatch.setattr(
        gu.requests,
        "get",
        lambda *_args, **_kwargs: JsonResponse(
            github_payload(tag_name="not-a-version")
        ),
    )

    with pytest.raises(
        UpdateCheckError,
        match="Invalid version returned by GitHub",
    ):
        gu.check_for_update("4.1.3")


def test_update_check_tolerates_missing_release_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A release without assets is reported but cannot be downloaded."""

    monkeypatch.setattr(
        gu.requests,
        "get",
        lambda *_args, **_kwargs: JsonResponse(github_payload()),
    )

    result = gu.check_for_update("4.1.3")

    assert result.update_available is True
    assert result.asset_name is None
    assert result.asset_url is None
    assert result.checksum_name is None
    assert result.checksum_url is None


def test_download_rejects_oversized_content_length_and_removes_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An oversized declared download is rejected before content is written."""

    destination = tmp_path / "release.tar.gz"
    response = DownloadResponse(
        headers={"Content-Length": "11"},
        chunks=[b"unused"],
    )
    monkeypatch.setattr(
        gu.requests,
        "get",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(
        UpdateVerificationError,
        match="überschreitet",
    ):
        gu.download_file(
            "https://example.invalid/archive",
            destination,
            maximum_size=10,
        )

    assert not destination.exists()


def test_download_rejects_stream_overflow_and_removes_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actual streamed bytes are limited even without Content-Length."""

    destination = tmp_path / "release.tar.gz"
    response = DownloadResponse(
        chunks=[b"123456", b"78901"],
    )
    monkeypatch.setattr(
        gu.requests,
        "get",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(
        UpdateVerificationError,
        match="überschreitet",
    ):
        gu.download_file(
            "https://example.invalid/archive",
            destination,
            maximum_size=10,
        )

    assert not destination.exists()


def test_download_wraps_request_error_and_removes_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure removes stale output and becomes UpdateCheckError."""

    destination = tmp_path / "release.tar.gz"
    destination.write_bytes(b"stale")

    def fail_request(*_args: Any, **_kwargs: Any) -> None:
        raise requests.Timeout("timed out")

    monkeypatch.setattr(gu.requests, "get", fail_request)

    with pytest.raises(UpdateCheckError, match="timed out"):
        gu.download_file(
            "https://example.invalid/archive",
            destination,
        )

    assert not destination.exists()


def test_checksum_parser_rejects_invalid_digest() -> None:
    """Non-SHA-256 text is rejected with the documented verification error."""

    with pytest.raises(
        UpdateVerificationError,
        match="Prüfsumme ist ungültig",
    ):
        gu.parse_checksum_file(
            "not-a-checksum  SolarInspector-4.2.0.tar.gz",
            "SolarInspector-4.2.0.tar.gz",
        )


def test_release_download_requires_archive_asset(tmp_path: Path) -> None:
    """Verification cannot begin when the release archive is missing."""

    with pytest.raises(
        UpdateVerificationError,
        match="kein Installationspaket",
    ):
        gu.download_and_verify_release(
            release_info(asset_url=None, asset_name=None),
            target_directory=tmp_path,
        )


def test_release_download_requires_checksum_asset(tmp_path: Path) -> None:
    """Verification cannot begin when the checksum asset is missing."""

    with pytest.raises(
        UpdateVerificationError,
        match="keine Prüfsummendatei",
    ):
        gu.download_and_verify_release(
            release_info(checksum_url=None, checksum_name=None),
            target_directory=tmp_path,
        )


def test_update_check_api_converts_check_error_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check endpoint retains its stable gateway-error response."""

    monkeypatch.setattr(si, "get_installed_version", lambda: "4.1.3")

    def fail_check(_version: str) -> ReleaseInfo:
        raise UpdateCheckError("GitHub offline")

    monkeypatch.setattr(si, "check_for_update", fail_check)

    response = si.app.test_client().get("/api/update/check")
    payload = response.get_json()

    assert response.status_code == 502
    assert payload == {
        "status": "error",
        "installed_version": "4.1.3",
        "message": "GitHub offline",
    }


def test_update_download_returns_409_when_no_newer_release_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-update is a conflict response and returns the status to idle."""

    status_path = tmp_path / "update-status.json"
    monkeypatch.setattr(si, "UPDATE_STATUS_PATH", status_path)
    monkeypatch.setattr(si, "UPDATE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(si, "get_installed_version", lambda: "4.1.3")
    monkeypatch.setattr(
        si,
        "check_for_update",
        lambda _version: release_info(update_available=False),
    )

    def unexpected_download(*_args: Any, **_kwargs: Any) -> Path:
        raise AssertionError("download must not be called")

    monkeypatch.setattr(
        si,
        "download_and_verify_release",
        unexpected_download,
    )

    response = si.app.test_client().post("/api/update/download")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["state"] == "idle"
    assert payload["progress"] == 0
    assert payload["message"] == "Keine neuere Version verfügbar."
    assert payload["available_version"] == "4.2.0"
    assert us.read_update_status(status_path)["state"] == "idle"


def test_update_download_persists_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verification failure becomes a persisted failed update status."""

    status_path = tmp_path / "update-status.json"
    monkeypatch.setattr(si, "UPDATE_STATUS_PATH", status_path)
    monkeypatch.setattr(si, "UPDATE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(si, "get_installed_version", lambda: "4.1.3")
    monkeypatch.setattr(
        si,
        "check_for_update",
        lambda _version: release_info(),
    )

    def fail_verification(
        _release: ReleaseInfo,
        *,
        target_directory: Path,
    ) -> Path:
        assert target_directory == tmp_path / "cache" / "4.2.0"
        raise UpdateVerificationError("checksum mismatch")

    monkeypatch.setattr(
        si,
        "download_and_verify_release",
        fail_verification,
    )

    response = si.app.test_client().post("/api/update/download")
    payload = response.get_json()

    assert response.status_code == 502
    assert payload["state"] == "failed"
    assert payload["progress"] == 0
    assert payload["message"] == "checksum mismatch"
    assert us.read_update_status(status_path)["state"] == "failed"


def test_update_install_rejects_unverified_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installation cannot be queued before verification succeeds."""

    monkeypatch.setattr(
        si,
        "UPDATE_STATUS_PATH",
        tmp_path / "missing-status.json",
    )
    monkeypatch.setattr(
        si,
        "UPDATE_REQUEST_PATH",
        tmp_path / "update-request.json",
    )

    response = si.app.test_client().post("/api/update/install")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["status"] == "error"
    assert "kein verifiziertes" in payload["message"]
    assert not si.UPDATE_REQUEST_PATH.exists()


@pytest.mark.parametrize(
    ("available_version", "archive_path"),
    [
        (None, "/tmp/SolarInspector-4.2.0.tar.gz"),
        ("4.2.0", None),
    ],
)
def test_update_install_rejects_incomplete_verified_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    available_version: str | None,
    archive_path: str | None,
) -> None:
    """Verified state still requires both version and archive path."""

    status_path = tmp_path / "update-status.json"
    request_path = tmp_path / "update-request.json"
    monkeypatch.setattr(si, "UPDATE_STATUS_PATH", status_path)
    monkeypatch.setattr(si, "UPDATE_REQUEST_PATH", request_path)
    us.write_update_status(
        status_path,
        state="verified",
        available_version=available_version,
        archive_path=archive_path,
    )

    response = si.app.test_client().post("/api/update/install")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["status"] == "error"
    assert "unvollständig" in payload["message"]
    assert not request_path.exists()


def test_database_insert_failure_does_not_advance_collector_state() -> None:
    """Persistence failure leaves cycle and integration state unchanged."""

    config = si.deep_merge(
        si.DEFAULT_CONFIG,
        {
            "house_meter": {
                "enabled": True,
                "type": "simulation",
            },
            "solakon_meter": {
                "enabled": False,
            },
            "solakon_one": {
                "enabled": False,
            },
        },
    )
    collector = si.Collector(
        StaticConfigManager(config),
        FailingDatabase(),
    )
    previous_power = {"grid_import_w": 123.0}
    collector._previous_power = dict(previous_power)
    collector._previous_epoch = 100.0

    with pytest.raises(RuntimeError, match="database unavailable"):
        collector.collect_once()

    status = collector.status()
    assert status["cycles"] == 0
    assert status["last_sample"] is None
    assert status["last_error"] == ""
    assert collector._previous_power == previous_power
    assert collector._previous_epoch == 100.0
