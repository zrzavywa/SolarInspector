"""Web tests for official grid-meter configuration and display."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.web.api import (
    build_test_device_api_response,
)
from solarinspector_core.web.configuration import (
    apply_configuration_form,
)

APP_DIR = Path(__file__).parents[1] / "app"


class FakeResponse:
    """Provide one controlled Tasmota JSON response."""

    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    """Return one fake response and record the request."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.response = FakeResponse(payload)
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append((url, dict(params), timeout))
        return self.response


def _grid_form(**updates: str) -> dict[str, str]:
    form = {
        "grid_meter_enabled": "on",
        "grid_meter_adapter": "tasmota_http",
        "grid_meter_source_id": "grid_meter_primary",
        "grid_meter_name": "Hauptzähler",
        "grid_meter_scheme": "http",
        "grid_meter_host": "192.0.2.50",
        "grid_meter_port": "80",
        "grid_meter_username": "admin",
        "grid_meter_password": "",
        "grid_meter_timeout_seconds": "3",
        "grid_meter_poll_interval_seconds": "5",
        "grid_meter_direction_factor": "1",
        "grid_meter_mapping_grid_power_w": ("StatusSNS.strom.Pges"),
        "grid_meter_mapping_grid_import_power_w": "",
        "grid_meter_mapping_grid_export_power_w": "",
        "grid_meter_mapping_grid_import_total_kwh": ("StatusSNS.strom.VerbrauchT0"),
        "grid_meter_mapping_grid_export_total_kwh": ("StatusSNS.strom.RetourT0"),
        "grid_meter_mapping_frequency_hz": "",
    }
    form.update(updates)
    return form


def test_configuration_form_preserves_secret_and_unknown_mapping() -> None:
    """Blank password input does not erase stored credentials."""

    config = deepcopy(DEFAULT_CONFIG)
    config["grid_meter"]["password"] = "stored-secret"
    config["grid_meter"]["mapping"]["vendor_field"] = "StatusSNS.strom.Custom"

    result = apply_configuration_form(
        config,
        _grid_form(),
    )

    assert result["grid_meter"]["enabled"] is True
    assert result["grid_meter"]["name"] == "Hauptzähler"
    assert result["grid_meter"]["host"] == "192.0.2.50"
    assert result["grid_meter"]["password"] == ("stored-secret")
    assert result["grid_meter"]["mapping"]["vendor_field"] == "StatusSNS.strom.Custom"


def test_configuration_form_replaces_password_explicitly() -> None:
    """A supplied password intentionally replaces the old value."""

    config = deepcopy(DEFAULT_CONFIG)
    config["grid_meter"]["password"] = "old-secret"

    result = apply_configuration_form(
        config,
        _grid_form(
            grid_meter_password="new-secret",
        ),
    )

    assert result["grid_meter"]["password"] == "new-secret"


def test_grid_meter_connection_test_reports_mapping_without_secrets() -> None:
    """Diagnostic output contains fields and values, not credentials."""

    config = deepcopy(DEFAULT_CONFIG)
    config["grid_meter"]["password"] = "stored-secret"
    session = FakeSession(
        {
            "StatusSNS": {
                "Time": "2026-07-24T16:40:00",
                "strom": {
                    "Pges": -241,
                    "VerbrauchT0": "3456.782",
                    "RetourT0": "512.118",
                },
            }
        }
    )

    def factory(
        adapter_config: dict[str, Any],
    ) -> TasmotaHttpGridMeterAdapter:
        return TasmotaHttpGridMeterAdapter(
            adapter_config,
            session=session,
        )

    response, status = build_test_device_api_response(
        config,
        "grid_meter",
        {
            "enabled": True,
            "host": "192.0.2.50",
            "password": "",
            "mapping": deepcopy(config["grid_meter"]["mapping"]),
        },
        reader=None,
        grid_meter_adapter_factory=factory,
    )

    assert status is None
    assert response["ok"] is True
    diagnostic = response["diagnostic"]
    assert diagnostic["status"] == "online"
    assert diagnostic["values"]["grid_power_w"]["value"] == -241.0
    assert diagnostic["values"]["grid_export_power_w"]["value"] == 241.0
    assert diagnostic["values"]["grid_import_total_kwh"]["value"] == pytest.approx(
        3456.782
    )
    assert "StatusSNS.strom.Pges" in diagnostic["available_fields"]
    assert diagnostic["available_field_count"] == 4
    assert diagnostic["mapping"][0] == {
        "field": "grid_power_w",
        "path": "StatusSNS.strom.Pges",
        "status": "ok",
    }
    assert "stored-secret" not in repr(response)
    assert "password" not in repr(response).lower()
    assert session.calls[0][1]["password"] == ("stored-secret")


def test_grid_meter_connection_failure_is_controlled() -> None:
    """Unexpected factory errors do not expose implementation details."""

    class FailingFactory:
        def __call__(
            self,
            _config: dict[str, Any],
        ) -> Any:
            raise RuntimeError("secret request details")

    response, status = build_test_device_api_response(
        deepcopy(DEFAULT_CONFIG),
        "grid_meter",
        {
            "enabled": True,
            "host": "192.0.2.50",
        },
        reader=None,
        grid_meter_adapter_factory=FailingFactory(),
    )

    assert status == 502
    assert response == {
        "ok": False,
        "error": ("Unerwarteter Fehler beim Grid-Meter-Verbindungstest."),
    }
    assert "secret request details" not in repr(response)


def test_invalid_grid_adapter_is_rejected_without_network() -> None:
    """Invalid adapters return a controlled client error."""

    response, status = build_test_device_api_response(
        deepcopy(DEFAULT_CONFIG),
        "grid_meter",
        {
            "enabled": True,
            "adapter": "unsupported",
            "host": "192.0.2.50",
        },
        reader=None,
    )

    assert status == 400
    assert response["ok"] is False
    assert "Unbekannter Grid-Meter-Adapter" in response["error"]


def test_templates_contain_grid_configuration_and_dashboard_contract() -> None:
    """HTML and JavaScript expose the required public-grid fields."""

    configuration = (APP_DIR / "templates" / "configuration.html").read_text(
        encoding="utf-8"
    )
    dashboard = (APP_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
    javascript = (APP_DIR / "static" / "dashboard.js").read_text(encoding="utf-8")

    assert "Offizieller Netzstromzähler" in configuration
    assert 'name="grid_meter_source_id"' in configuration
    assert 'name="grid_meter_password"' in configuration
    assert 'value="shrdzm_rest"' in configuration
    assert 'name="grid_meter_shrdzm_endpoint"' in configuration
    assert 'name="grid_meter_shrdzm_authentication_mode"' in configuration
    assert 'value=""' in configuration
    assert 'id="test-grid-meter"' in configuration
    assert "/api/test-device/grid_meter" in configuration
    assert "Erkannte Felder" in configuration

    for element_id in (
        "grid-meter-import",
        "grid-meter-export",
        "grid-meter-import-total",
        "grid-meter-export-total",
        "grid-meter-source",
        "grid-meter-quality",
        "grid-meter-update",
        "grid-meter-age",
    ):
        assert f'id="{element_id}"' in dashboard
        assert element_id in javascript

    assert "activeSources?.grid_power_label" in javascript
    assert "gridMeter?.import_total_kwh" in javascript
