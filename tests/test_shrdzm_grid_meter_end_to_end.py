"""End-to-end tests for the SHRDZM official grid-meter flow."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from solarinspector_core.adapters.grid_meter_factory import (
    create_grid_meter_adapter,
)
from solarinspector_core.adapters.shrdzm_grid_meter import (
    ShrdzmRestGridMeterAdapter,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.config.grid_meter import (
    DEFAULT_SHRDZM_REST_MAPPING,
)
from solarinspector_core.config.manager import ConfigManager
from solarinspector_core.services.collector import Collector
from solarinspector_core.web.api import (
    build_test_device_api_response,
)
from solarinspector_core.web.configuration import (
    apply_configuration_form,
)

ROOT = Path(__file__).parents[1]
FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "shrdzm" / "rest" / "grid_import_normal.json"
)


class FakeResponse:
    """Provide the response surface used by the REST adapter."""

    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        """Return the configured fixture object."""

        return self.payload


class FakeSession:
    """Record the local read-only request and return one fixture."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.response = FakeResponse(payload)
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
        """Return a deterministic response without network access."""

        self.calls.append((url, dict(params), timeout, auth))
        return self.response


class StubConfigManager:
    """Return isolated configuration copies to the collector."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get(self) -> dict[str, Any]:
        """Return one independent configuration copy."""

        return deepcopy(self.config)


class StubDatabase:
    """Capture compatible aggregate collector samples."""

    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> None:
        """Return no previous aggregate sample."""

        return None

    def insert_sample(self, sample: dict[str, Any]) -> int:
        """Capture one aggregate sample and return a stable ID."""

        self.samples.append(dict(sample))
        return len(self.samples)


def _fixture() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _form() -> dict[str, str]:
    return {
        "grid_meter_enabled": "on",
        "grid_meter_adapter": "shrdzm_rest",
        "grid_meter_source_id": "grid_meter_primary",
        "grid_meter_name": "Offizieller Netzstromzähler",
        "grid_meter_scheme": "http",
        "grid_meter_host": "192.0.2.60",
        "grid_meter_port": "80",
        "grid_meter_username": "reader",
        "grid_meter_password": "integration-secret",
        "grid_meter_timeout_seconds": "3",
        "grid_meter_poll_interval_seconds": "5",
        "grid_meter_direction_factor": "1",
        "grid_meter_shrdzm_endpoint": "/getLastData",
        "grid_meter_shrdzm_authentication_mode": "query",
        "grid_meter_shrdzm_username_parameter": "user",
        "grid_meter_shrdzm_password_parameter": "password",
        "grid_meter_shrdzm_energy_total_unit": "auto",
    }


def _configured_root() -> dict[str, Any]:
    current = apply_configuration_form(
        deepcopy(DEFAULT_CONFIG),
        _form(),
    )
    return ConfigManager.validate(current)


def test_form_validation_and_factory_select_shrdzm() -> None:
    """The browser form reaches the normalized concrete adapter."""

    config = _configured_root()["grid_meter"]

    assert config["enabled"] is True
    assert config["adapter"] == "shrdzm_rest"
    assert config["host"] == "192.0.2.60"
    assert config["shrdzm_rest"] == {
        "endpoint": "/getLastData",
        "authentication_mode": "query",
        "username_parameter": "user",
        "password_parameter": "password",
        "energy_total_unit": "auto",
    }
    assert config["mapping"] == DEFAULT_SHRDZM_REST_MAPPING
    assert isinstance(
        create_grid_meter_adapter(config),
        ShrdzmRestGridMeterAdapter,
    )


def test_connection_api_reads_fixture_without_exposing_secret() -> None:
    """The web diagnostic exercises the real adapter and safe metadata."""

    config = _configured_root()
    session = FakeSession(_fixture())

    def factory(
        adapter_config: dict[str, Any],
    ) -> ShrdzmRestGridMeterAdapter:
        return ShrdzmRestGridMeterAdapter(
            adapter_config,
            session=session,
        )

    response, status = build_test_device_api_response(
        config,
        "grid_meter",
        {
            "enabled": True,
            "adapter": "shrdzm_rest",
            "host": "192.0.2.60",
            "password": "",
            "shrdzm_rest": deepcopy(config["grid_meter"]["shrdzm_rest"]),
            "mapping": deepcopy(config["grid_meter"]["mapping"]),
        },
        reader=None,
        grid_meter_adapter_factory=factory,
    )

    assert status is None
    assert response["ok"] is True
    diagnostic = response["diagnostic"]
    assert diagnostic["adapter"] == "shrdzm_rest"
    assert diagnostic["transport"] == "shrdzm_rest"
    assert diagnostic["endpoint"] == "/getLastData"
    assert diagnostic["status"] == "online"
    assert diagnostic["values"]["grid_power_w"]["value"] == 568.0
    assert diagnostic["values"]["grid_import_power_w"]["value"] == 568.0
    assert diagnostic["values"]["grid_export_power_w"]["value"] == 0.0
    assert "1.7.0" in diagnostic["available_fields"]
    assert "integration-secret" not in repr(response)
    assert session.calls == [
        (
            "http://192.0.2.60:80/getLastData",
            {
                "user": "reader",
                "password": "integration-secret",
            },
            3.0,
            None,
        )
    ]


def test_collector_uses_shrdzm_as_official_primary_source() -> None:
    """The collector consumes the real adapter snapshot end to end."""

    config = _configured_root()
    database = StubDatabase()
    session = FakeSession(_fixture())
    collector = Collector(
        StubConfigManager(config),
        database,
    )
    collector._create_grid_meter_adapter = lambda adapter_config: (
        ShrdzmRestGridMeterAdapter(
            adapter_config,
            session=session,
        )
    )

    sample = collector.collect_once()

    assert sample["grid_power_w"] == 568.0
    assert sample["grid_import_w"] == 568.0
    assert sample["feed_in_w"] == 0.0
    assert sample["grid_source"] == "Offizieller Netzstromzähler"
    assert sample["error_text"] == ""
    assert len(database.samples) == 1
    assert len(session.calls) == 1


def test_ui_and_documentation_expose_completed_contract() -> None:
    """The operator surface and documentation remain linked."""

    template = (ROOT / "app" / "templates" / "configuration.html").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "shrdzm-grid-meter.md").read_text(encoding="utf-8")

    assert 'id="grid-meter-adapter"' in template
    assert 'id="shrdzm-rest-config"' in template
    assert "updateGridAdapterFields" in template
    assert "diagnostic.endpoint" in template
    assert "shrdzm-grid-meter.md" in readme
    assert "shrdzm-grid-meter.md" in docs_index
    assert "/getLastData" in guide
    assert "1.7.0" in guide
    assert "2.7.0" in guide
    assert "Hardwarevalidierung" in guide
    assert "integration-secret" not in guide
