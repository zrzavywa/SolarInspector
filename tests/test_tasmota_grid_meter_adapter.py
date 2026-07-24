"""Tests for Tasmota HTTP communication and core JSON parsing."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import requests
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
    lookup_tasmota_path,
    parse_tasmota_grid_meter_payload,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tasmota"


class FakeResponse:
    """Provide the subset of a requests response used by the adapter."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object = None,
        text: str | None = None,
        json_error: ValueError | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.text = text if text is not None else json.dumps(payload)
        self.json_error = json_error

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    """Record HTTP calls and return or raise a configured result."""

    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        error: requests.RequestException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append((url, dict(params), timeout))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("Fake response is not configured.")
        return self.response


def _fixture(filename: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def _config(**updates: object) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config["enabled"] = True
    config["host"] = "192.0.2.50"
    config.update(updates)
    return config


def _measurements_by_metric(
    adapter: TasmotaHttpGridMeterAdapter,
):
    snapshot = adapter.read_snapshot()
    return snapshot, {
        measurement.metric: measurement for measurement in snapshot.measurements
    }


def test_real_fixture_produces_online_core_grid_power() -> None:
    """The captured Hichi response yields one normalized core metric."""

    payload = _fixture("grid_meter_status10_sample_01.json")
    status_sns = payload["StatusSNS"]
    meter_values = status_sns["strom"]

    raw_power = meter_values["Pges"]
    raw_import_total = meter_values["VerbrauchT0"]
    raw_export_total = meter_values["RetourT0"]
    raw_device_time = status_sns["Time"]

    session = FakeSession(FakeResponse(payload=payload))
    adapter = TasmotaHttpGridMeterAdapter(
        _config(),
        session=session,
    )

    snapshot, values = _measurements_by_metric(adapter)
    metadata = dict(snapshot.metadata)

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.source_id == "grid_meter_primary"
    assert adapter.source.roles == frozenset({MeasurementRole.GRID_METER})
    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert snapshot.error is None

    assert values[Metric.GRID_POWER].value == pytest.approx(float(raw_power))
    assert values[Metric.GRID_POWER].quality is MeasurementQuality.REPORTED
    assert values[Metric.GRID_POWER].raw_value == raw_power

    assert metadata["device_time"] == str(raw_device_time)
    assert float(metadata["raw_grid_import_total_kwh"]) == pytest.approx(
        float(raw_import_total)
    )
    assert float(metadata["raw_grid_export_total_kwh"]) == pytest.approx(
        float(raw_export_total)
    )


def test_http_request_uses_status_10_and_configured_authentication() -> None:
    """Tasmota query credentials are applied but never embedded in the URL."""

    session = FakeSession(
        FakeResponse(
            payload={
                "StatusSNS": {
                    "strom": {
                        "Pges": 123,
                        "VerbrauchT0": 10.0,
                        "RetourT0": 2.0,
                    }
                }
            }
        )
    )
    adapter = TasmotaHttpGridMeterAdapter(
        _config(
            scheme="https",
            port=8443,
            timeout_seconds=7,
            username="admin",
            password="very-secret",
        ),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert session.calls == [
        (
            "https://192.0.2.50:8443/cm",
            {
                "cmnd": "Status 10",
                "user": "admin",
                "password": "very-secret",
            },
            7.0,
        )
    ]
    assert "very-secret" not in (snapshot.error or "")


def test_password_without_username_uses_tasmota_admin_user() -> None:
    """The documented Tasmota default admin user is used when needed."""

    session = FakeSession(
        FakeResponse(
            payload={
                "StatusSNS": {
                    "strom": {
                        "Pges": 0,
                        "VerbrauchT0": 1,
                        "RetourT0": 0,
                    }
                }
            }
        )
    )
    adapter = TasmotaHttpGridMeterAdapter(
        _config(username="", password="secret"),
        session=session,
    )

    adapter.read_snapshot()

    assert session.calls[0][1]["user"] == "admin"
    assert session.calls[0][1]["password"] == "secret"


def test_numeric_strings_and_zero_are_valid_values() -> None:
    """Numeric strings are parsed and a real zero is not treated as absent."""

    reading = parse_tasmota_grid_meter_payload(
        {
            "StatusSNS": {
                "strom": {
                    "Pges": "0",
                    "VerbrauchT0": "12627.640",
                    "RetourT0": "19.895",
                }
            }
        },
        DEFAULT_CONFIG["grid_meter"]["mapping"],
    )

    assert reading.grid_power_w == 0.0
    assert reading.grid_import_total_kwh == pytest.approx(12627.64)
    assert reading.grid_export_total_kwh == pytest.approx(19.895)
    assert reading.diagnostics == ()


def test_dotted_obis_key_is_resolved_without_jsonpath() -> None:
    """A leaf key such as 1.8.0 remains addressable by a simple path."""

    payload = {
        "StatusSNS": {
            "SML": {
                "1.8.0": "3456.782",
            }
        }
    }

    found, value = lookup_tasmota_path(
        payload,
        "StatusSNS.SML.1.8.0",
    )
    reading = parse_tasmota_grid_meter_payload(
        payload,
        {
            "grid_power_w": "",
            "grid_import_total_kwh": ("StatusSNS.SML.1.8.0"),
            "grid_export_total_kwh": "",
        },
    )

    assert found is True
    assert value == "3456.782"
    assert reading.grid_import_total_kwh == pytest.approx(3456.782)
    assert reading.diagnostics == ()


def test_missing_optional_mapped_value_degrades_but_keeps_power() -> None:
    """Successful JSON retains valid power while reporting mapping gaps."""

    session = FakeSession(
        FakeResponse(
            payload={
                "StatusSNS": {
                    "strom": {
                        "Pges": 0,
                        "VerbrauchT0": 10.0,
                    }
                }
            }
        )
    )
    adapter = TasmotaHttpGridMeterAdapter(
        _config(),
        session=session,
    )

    snapshot, values = _measurements_by_metric(adapter)

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert values[Metric.GRID_POWER].value == 0.0
    assert "grid export total" in (snapshot.error or "")
    assert "Required grid power" not in (snapshot.error or "")


def test_invalid_power_is_not_converted_to_zero() -> None:
    """Malformed power is absent while valid counters remain available."""

    session = FakeSession(
        FakeResponse(
            payload={
                "StatusSNS": {
                    "strom": {
                        "Pges": "not-a-number",
                        "VerbrauchT0": 10.0,
                        "RetourT0": 2.0,
                    }
                }
            }
        )
    )
    adapter = TasmotaHttpGridMeterAdapter(
        _config(),
        session=session,
    )

    snapshot = adapter.read_snapshot()
    values = {measurement.metric: measurement for measurement in snapshot.measurements}

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert Metric.GRID_POWER not in values
    assert Metric.GRID_IMPORT_POWER not in values
    assert Metric.GRID_EXPORT_POWER not in values
    assert values[Metric.GRID_IMPORT_TOTAL].value == 10_000.0
    assert values[Metric.GRID_EXPORT_TOTAL].value == 2_000.0
    assert "not numeric for grid power" in (snapshot.error or "")
    assert "Required grid power measurement is missing" in (snapshot.error or "")


def test_disabled_source_does_not_call_http() -> None:
    """A disabled source returns the structural disabled status."""

    session = FakeSession()
    adapter = TasmotaHttpGridMeterAdapter(
        _config(enabled=False),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DISABLED
    assert snapshot.measurements == ()
    assert session.calls == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            requests.Timeout("URL contains password=do-not-leak"),
            "Tasmota request timed out.",
        ),
        (
            requests.ConnectionError("URL contains password=do-not-leak"),
            "Tasmota device is unreachable.",
        ),
        (
            requests.RequestException("URL contains password=do-not-leak"),
            "Tasmota HTTP request failed.",
        ),
    ],
)
def test_transport_failures_are_offline_and_credential_safe(
    error: requests.RequestException,
    message: str,
) -> None:
    """Network diagnostics never reuse exception URLs containing secrets."""

    session = FakeSession(error=error)
    adapter = TasmotaHttpGridMeterAdapter(
        _config(password="do-not-leak"),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()
    assert message in (snapshot.error or "")
    assert "do-not-leak" not in (snapshot.error or "")


@pytest.mark.parametrize("status_code", [401, 403, 404, 500])
def test_http_error_statuses_are_offline(
    status_code: int,
) -> None:
    """HTTP failures retain the status code without exposing the URL."""

    session = FakeSession(
        FakeResponse(
            status_code=status_code,
            payload={"Status": "error"},
        )
    )
    adapter = TasmotaHttpGridMeterAdapter(
        _config(password="do-not-leak"),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert f"HTTP status {status_code}" in (snapshot.error or "")
    assert "do-not-leak" not in (snapshot.error or "")


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(payload={}, text=""),
        FakeResponse(
            payload=None,
            text="{broken",
            json_error=ValueError("invalid json"),
        ),
        FakeResponse(payload=[1, 2, 3]),
    ],
)
def test_unusable_responses_are_offline(
    response: FakeResponse,
) -> None:
    """Empty, invalid, and non-object responses are not treated as zero."""

    adapter = TasmotaHttpGridMeterAdapter(
        _config(),
        session=FakeSession(response),
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()


def test_missing_host_returns_offline_without_network_call() -> None:
    """An incomplete active configuration remains a controlled failure."""

    session = FakeSession()
    adapter = TasmotaHttpGridMeterAdapter(
        _config(host=""),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert "host is not configured" in (snapshot.error or "")
    assert session.calls == []
