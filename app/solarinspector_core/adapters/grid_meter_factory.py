"""Create official grid-meter adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.grid_meter import (
    GridMeterAdapter,
    normalize_grid_meter_adapter,
)


class GridMeterAdapterConfigurationError(ValueError):
    """Report a safe adapter-selection failure."""


def create_grid_meter_adapter(
    config: Mapping[str, Any],
) -> MeasurementAdapter:
    """Create the selected adapter without network access."""

    adapter_name = normalize_grid_meter_adapter(config.get("adapter"))

    if adapter_name == GridMeterAdapter.TASMOTA_HTTP.value:
        return TasmotaHttpGridMeterAdapter(config)

    if adapter_name == GridMeterAdapter.SHRDZM_REST.value:
        raise GridMeterAdapterConfigurationError(
            "SHRDZM REST ist konfiguriert; der eigentliche "
            "REST-Adapter folgt in Block 07.3."
        )

    supported = ", ".join(adapter.value for adapter in GridMeterAdapter)
    raise GridMeterAdapterConfigurationError(
        f"Unbekannter Grid-Meter-Adapter {adapter_name!r}. Unterstützt: {supported}."
    )
