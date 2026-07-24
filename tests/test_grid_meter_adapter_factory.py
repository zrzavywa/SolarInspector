"""Tests for controlled grid-meter adapter selection."""

from __future__ import annotations

from copy import deepcopy

import pytest
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.grid_meter_factory import (
    GridMeterAdapterConfigurationError,
    create_grid_meter_adapter,
)
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG


def test_factory_selects_existing_tasmota_adapter() -> None:
    """Existing installations retain their transport."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    adapter = create_grid_meter_adapter(config)

    assert isinstance(adapter, TasmotaHttpGridMeterAdapter)
    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.device_type == "tasmota_http"


def test_factory_rejects_unknown_adapter_explicitly() -> None:
    """Unknown adapter names are not redirected to Tasmota."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config["adapter"] = "unsupported"

    with pytest.raises(
        GridMeterAdapterConfigurationError,
        match="Unbekannter Grid-Meter-Adapter",
    ) as error:
        create_grid_meter_adapter(config)

    assert "tasmota_http" in str(error.value)
    assert "shrdzm_rest" in str(error.value)


def test_factory_reports_staged_shrdzm_adapter() -> None:
    """Known SHRDZM selection fails safely before Block 07.3."""

    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config["adapter"] = "shrdzm_rest"

    with pytest.raises(
        GridMeterAdapterConfigurationError,
        match="Block 07.3",
    ):
        create_grid_meter_adapter(config)
