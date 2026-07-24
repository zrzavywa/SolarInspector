"""Tests for the read-only SHRDZM REST grid-meter adapter."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import requests
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.shrdzm_grid_meter import (
    ShrdzmRestGridMeterAdapter,
    lookup_shrdzm_path,
    parse_shrdzm_grid_meter_payload,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.config.grid_meter import (
    DEFAULT_SHRDZM_REST_MAPPING,
)
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "shrdzm" / "rest"


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
        self.calls: list[
            tuple[
                str,
                dict[str, str],
                float,
                tuple[str, str] | None,
            ]
        ] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
        auth: tuple[str, str] | None,
    ) -> FakeResponse:
        self.calls.append((url, dict(params), timeout, auth))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("Fake response is not configured.")
        return self.response


def _fixture(filename: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _config(**updates: object) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config.update(
        {
            "enabled": True,
            "adapter": "shrdzm_rest",
            "host": "192.0.2.60",
            "mapping": deepcopy(DEFAULT_SHRDZM_REST_MAPPING),
        }
    )
    config.update(updates)
    return config


def _snapshot(
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
):
    adapter = ShrdzmRestGridMeterAdapter(
        config or _config(),
        session=FakeSession(FakeResponse(payload=payload)),
    )
    snapshot = adapter.read_snapshot()
    values = {measurement.metric: measurement for measurement in snapshot.measurements}
    return snapshot, values


def test_import_fixture_produces_online_snapshot() -> None:
    """A complete public-format OBIS payload normalizes import."""

    adapter = ShrdzmRestGridMeterAdapter(
        _config(),
        session=FakeSession(FakeResponse(payload=_fixture("grid_import_normal.json"))),
    )

    snapshot = adapter.read_snapshot()
    values = {measurement.metric: measurement for measurement in snapshot.measurements}
    metadata = dict(snapshot.metadata)

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.source_id == "grid_meter_primary"
    assert adapter.source.roles == frozenset({MeasurementRole.GRID_METER})
    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert snapshot.error is None
    assert values[Metric.GRID_POWER].value == 568.0
    assert values[Metric.GRID_POWER].quality is MeasurementQuality.CALCULATED
    assert values[Metric.GRID_IMPORT_POWER].value == 568.0
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0
    assert values[Metric.GRID_IMPORT_TOTAL].value == 5_853_648.0
    assert values[Metric.GRID_EXPORT_TOTAL].value == 15_317.0
    assert values[Metric.GRID_IMPORT_TOTAL].unit is Unit.WATT_HOUR
    assert values[Metric.PHASE_VOLTAGE_L1].value == 238.0
    assert values[Metric.PHASE_CURRENT_L3].value == 1.57
    assert metadata["transport"] == "shrdzm_rest"
    assert metadata["rest_endpoint"] == "/getLastData"
    assert metadata["device_time"] == "2024-10-20T19:51:25"


def test_export_fixture_normalizes_negative_grid_power() -> None:
    """Export remains a positive magnitude and a negative net value."""

    snapshot, values = _snapshot(_fixture("grid_export_normal.json"))

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_POWER].value == -245.0
    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 245.0


def test_zero_fixture_retains_real_zero() -> None:
    """A reported zero is never treated as a missing value."""

    snapshot, values = _snapshot(_fixture("grid_zero_power.json"))

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_POWER].value == 0.0
    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0


def test_query_authentication_uses_parameters_not_url() -> None:
    """Documented REST credentials remain outside the URL string."""

    session = FakeSession(FakeResponse(payload=_fixture("grid_import_normal.json")))
    config = _config(
        scheme="https",
        port=8443,
        timeout_seconds=7,
        username="device-user",
        password="very-secret",
    )
    adapter = ShrdzmRestGridMeterAdapter(
        config,
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert session.calls == [
        (
            "https://192.0.2.60:8443/getLastData",
            {
                "user": "device-user",
                "password": "very-secret",
            },
            7.0,
            None,
        )
    ]
    assert "very-secret" not in repr(snapshot)
    assert "device-user" not in repr(snapshot)


def test_custom_query_parameter_names_are_supported() -> None:
    """Firmware-specific parameter names remain configurable."""

    session = FakeSession(FakeResponse(payload=_fixture("grid_import_normal.json")))
    config = _config(
        username="reader",
        password="secret",
    )
    config["shrdzm_rest"].update(
        {
            "username_parameter": "login",
            "password_parameter": "key",
        }
    )

    ShrdzmRestGridMeterAdapter(
        config,
        session=session,
    ).read_snapshot()

    assert session.calls[0][1] == {
        "login": "reader",
        "key": "secret",
    }


def test_basic_authentication_uses_documented_admin_fallback() -> None:
    """A web password can use the documented admin account."""

    session = FakeSession(FakeResponse(payload=_fixture("grid_import_normal.json")))
    config = _config(
        username="",
        password="secret",
    )
    config["shrdzm_rest"]["authentication_mode"] = "basic"

    ShrdzmRestGridMeterAdapter(
        config,
        session=session,
    ).read_snapshot()

    assert session.calls[0][1] == {}
    assert session.calls[0][3] == ("admin", "secret")


def test_no_authentication_ignores_stored_credentials() -> None:
    """The explicit none mode sends neither query nor basic auth."""

    session = FakeSession(FakeResponse(payload=_fixture("grid_import_normal.json")))
    config = _config(
        username="stored-user",
        password="stored-secret",
    )
    config["shrdzm_rest"]["authentication_mode"] = "none"

    ShrdzmRestGridMeterAdapter(
        config,
        session=session,
    ).read_snapshot()

    assert session.calls[0][1] == {}
    assert session.calls[0][3] is None


def test_partial_payload_is_degraded_without_invented_power() -> None:
    """Missing mapped values remain absent and visible as diagnostics."""

    snapshot, values = _snapshot(_fixture("grid_partial_values.json"))

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert Metric.GRID_POWER not in values
    assert values[Metric.GRID_IMPORT_POWER].value == 125.0
    assert Metric.GRID_EXPORT_POWER not in values
    assert values[Metric.GRID_IMPORT_TOTAL].value == 1000.0
    assert Metric.GRID_EXPORT_TOTAL not in values
    assert "Required grid power measurement is missing" in (snapshot.error or "")


def test_invalid_values_do_not_become_zero() -> None:
    """Malformed numbers remain absent while valid values survive."""

    snapshot, values = _snapshot(_fixture("grid_invalid_values.json"))

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert Metric.GRID_POWER not in values
    assert Metric.GRID_IMPORT_POWER not in values
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0
    assert values[Metric.GRID_IMPORT_TOTAL].value == 5000.0
    assert "not numeric for grid power" in (snapshot.error or "")
    assert "not numeric for grid import power" in (snapshot.error or "")


def test_net_power_is_used_when_directional_paths_are_disabled() -> None:
    """The confirmed 16.7.0 field remains a supported fallback."""

    config = _config()
    config["mapping"]["grid_import_power_w"] = ""
    config["mapping"]["grid_export_power_w"] = ""

    snapshot, values = _snapshot(
        _fixture("grid_export_normal.json"),
        config=config,
    )

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_POWER].value == -245.0
    assert values[Metric.GRID_POWER].quality is MeasurementQuality.REPORTED
    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 245.0
    assert values[Metric.GRID_EXPORT_POWER].quality is MeasurementQuality.CALCULATED


def test_explicit_kwh_total_unit_converts_to_canonical_wh() -> None:
    """A configured kWh response is converted to watt-hours."""

    config = _config()
    config["shrdzm_rest"]["energy_total_unit"] = "kwh"
    payload = _fixture("grid_import_normal.json")
    payload["1.8.0"] = "12.5"
    payload["2.8.0"] = "1.25"

    snapshot, values = _snapshot(payload, config=config)

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_IMPORT_TOTAL].value == 12_500.0
    assert values[Metric.GRID_EXPORT_TOTAL].value == 1250.0


def test_auto_unit_rejects_ambiguous_custom_total_path() -> None:
    """Auto scaling never guesses a unit for custom counter fields."""

    config = _config()
    config["mapping"]["grid_import_total_kwh"] = "custom.import_total"
    payload = _fixture("grid_import_normal.json")
    payload["custom"] = {"import_total": "12.5"}

    snapshot, values = _snapshot(payload, config=config)

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert Metric.GRID_IMPORT_TOTAL not in values
    assert "Energy unit is ambiguous" in (snapshot.error or "")


def test_exact_obis_key_precedes_dotted_path_traversal() -> None:
    """Direct keys such as 1.7.0 are addressable without JSONPath."""

    payload = {
        "1.7.0": "250",
        "nested": {"1.7.0": "300"},
    }

    direct_found, direct_value = lookup_shrdzm_path(
        payload,
        "1.7.0",
    )
    nested_found, nested_value = lookup_shrdzm_path(
        payload,
        "nested.1.7.0",
    )

    assert direct_found is True
    assert direct_value == "250"
    assert nested_found is True
    assert nested_value == "300"


def test_parser_accepts_numeric_strings_and_records_paths() -> None:
    """The published string-valued format parses deterministically."""

    reading = parse_shrdzm_grid_meter_payload(
        _fixture("grid_import_normal.json"),
        DEFAULT_SHRDZM_REST_MAPPING,
    )
    values = {item.mapping_key: item.value for item in reading.values}

    assert values["grid_import_power_w"] == 568.0
    assert values["grid_export_power_w"] == 0.0
    assert values["grid_import_total_kwh"] == 5_853_648.0
    assert "1.7.0" in reading.available_paths
    assert reading.device_time == "2024-10-20T19:51:25"
    assert reading.diagnostics == ()


def test_diagnostic_paths_are_optional_and_credential_free() -> None:
    """Connection-test metadata can expose paths but never secrets."""

    config = _config(
        username="reader",
        password="do-not-leak",
        _include_diagnostic_paths=True,
    )
    snapshot, _values = _snapshot(
        _fixture("grid_import_normal.json"),
        config=config,
    )
    metadata = dict(snapshot.metadata)

    paths = json.loads(metadata["available_scalar_paths_json"])
    assert "1.7.0" in paths
    assert "do-not-leak" not in repr(snapshot)
    assert "reader" not in repr(snapshot)


def test_disabled_source_does_not_call_http() -> None:
    """A disabled source returns the structural disabled status."""

    session = FakeSession()
    adapter = ShrdzmRestGridMeterAdapter(
        _config(enabled=False),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DISABLED
    assert snapshot.measurements == ()
    assert session.calls == []


def test_missing_host_returns_offline_without_network_call() -> None:
    """An incomplete active configuration remains controlled."""

    session = FakeSession()
    adapter = ShrdzmRestGridMeterAdapter(
        _config(host=""),
        session=session,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert "host is not configured" in (snapshot.error or "")
    assert session.calls == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            requests.Timeout("URL contains password=do-not-leak"),
            "SHRDZM request timed out.",
        ),
        (
            requests.ConnectionError("URL contains password=do-not-leak"),
            "SHRDZM device is unreachable.",
        ),
        (
            requests.RequestException("URL contains password=do-not-leak"),
            "SHRDZM HTTP request failed.",
        ),
    ],
)
def test_transport_failures_are_credential_safe(
    error: requests.RequestException,
    message: str,
) -> None:
    """Network diagnostics never reuse exception URLs."""

    adapter = ShrdzmRestGridMeterAdapter(
        _config(password="do-not-leak"),
        session=FakeSession(error=error),
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
    """HTTP failures retain the code without exposing the URL."""

    adapter = ShrdzmRestGridMeterAdapter(
        _config(password="do-not-leak"),
        session=FakeSession(
            FakeResponse(
                status_code=status_code,
                payload={"status": "error"},
            )
        ),
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
            payload={},
            text="not-json",
            json_error=ValueError("invalid"),
        ),
        FakeResponse(payload=[1, 2, 3]),
    ],
)
def test_unusable_responses_are_offline(
    response: FakeResponse,
) -> None:
    """Empty, malformed, and non-object JSON are controlled."""

    adapter = ShrdzmRestGridMeterAdapter(
        _config(),
        session=FakeSession(response),
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()
