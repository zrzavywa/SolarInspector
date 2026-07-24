"""Tests for controlled official grid-meter adapter selection."""

from __future__ import annotations

from copy import deepcopy

import pytest
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.grid_meter_factory import (
    GridMeterAdapterConfigurationError,
    create_grid_meter_adapter,
)
from solarinspector_core.adapters.shrdzm_grid_meter import (
    ShrdzmRestGridMeterAdapter,
)
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.config.grid_meter import (
    DEFAULT_SHRDZM_REST_MAPPING,
)


def test_factory_selects_existing_tasmota_adapter() -> None:
    """Existing installations retain their concrete transport."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    adapter = create_grid_meter_adapter(config)

    assert isinstance(adapter, TasmotaHttpGridMeterAdapter)
    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.device_type == "tasmota_http"


def test_factory_selects_shrdzm_rest_adapter() -> None:
    """The known SHRDZM selection creates the read-only adapter."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config["adapter"] = "shrdzm_rest"
    config["mapping"] = deepcopy(DEFAULT_SHRDZM_REST_MAPPING)

    adapter = create_grid_meter_adapter(config)

    assert isinstance(adapter, ShrdzmRestGridMeterAdapter)
    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.device_type == "shrdzm_rest"


def test_factory_rejects_unknown_adapter_explicitly() -> None:
    """Invalid names are not silently redirected to Tasmota."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config["adapter"] = "unsupported-secret-transport"

    with pytest.raises(
        GridMeterAdapterConfigurationError,
        match="Unbekannter Grid-Meter-Adapter",
    ) as error:
        create_grid_meter_adapter(config)

    assert "password" not in str(error.value).lower()
    assert "tasmota_http" in str(error.value)
    assert "shrdzm_rest" in str(error.value)
