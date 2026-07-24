"Shared contract tests for production measurement adapters."

from __future__ import annotations

from typing import Any

import pytest
import requests
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.adapters.shelly import ShellyMeasurementAdapter
from solarinspector_core.adapters.solakon import SolakonOneReading
from solarinspector_core.adapters.solakon_measurement import (
    SolakonMeasurementAdapter,
)
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric


class StubShellyReader:
    "Return or raise one deterministic legacy Shelly result."

    def __init__(
        self,
        *,
        reading: MeterReading | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reading = reading
        self.error = error

    def read(
        self,
        _device: dict[str, Any],
        _role: str,
    ) -> MeterReading:
        "Return the configured result without network communication."

        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("stub has no reading")
        return self.reading


class StubSolakonReader:
    "Return or raise one deterministic legacy Solakon result."

    def __init__(
        self,
        *,
        reading: SolakonOneReading | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reading = reading
        self.error = error

    def read(self, _config: dict[str, Any]) -> SolakonOneReading:
        "Return the configured result without Modbus communication."

        if self.error is not None:
            raise self.error
        if self.reading is None:
            raise AssertionError("stub has no reading")
        return self.reading


def production_adapters() -> tuple[
    tuple[MeasurementAdapter, Metric],
    ...,
]:
    "Build representative production adapters with valid zero power."

    return (
        (
            ShellyMeasurementAdapter(
                source_id="grid_meter",
                name="Grid meter",
                device={"type": "shelly_pro_3em"},
                role=MeasurementRole.GRID_METER,
                reader=StubShellyReader(
                    reading=MeterReading(
                        power_w=0.0,
                        voltage_v=230.0,
                        current_a=0.0,
                    )
                ),
            ),
            Metric.GRID_POWER,
        ),
        (
            ShellyMeasurementAdapter(
                source_id="plant_meter",
                name="Plant meter",
                device={"type": "shelly_pm_mini_gen3"},
                role=MeasurementRole.PLANT_METER,
                reader=StubShellyReader(
                    reading=MeterReading(
                        power_w=0.0,
                        voltage_v=230.0,
                        current_a=0.0,
                    )
                ),
            ),
            Metric.PLANT_AC_POWER,
        ),
        (
            SolakonMeasurementAdapter(
                source_id="solakon_one",
                name="Solakon ONE",
                config={"simulation": False},
                reader=StubSolakonReader(
                    reading=SolakonOneReading(
                        total_pv_power_w=0.0,
                        active_power_w=0.0,
                        battery_power_w=0.0,
                        battery_soc_pct=0.0,
                        meter_power_w=0.0,
                    )
                ),
            ),
            Metric.PV_POWER,
        ),
    )


@pytest.mark.parametrize(
    ("adapter", "zero_metric"),
    production_adapters(),
)
def test_production_adapter_obeys_normalized_contract(
    adapter: MeasurementAdapter,
    zero_metric: Metric,
) -> None:
    "Production adapters expose stable sources and valid snapshots."

    source = adapter.source

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source is source

    snapshot = adapter.read_snapshot()

    assert snapshot.source_id == source.source_id
    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert snapshot.measurements
    assert any(
        measurement.metric is zero_metric and measurement.value == 0.0
        for measurement in snapshot.measurements
    )

    for measurement in snapshot.measurements:
        assert measurement.source_id == snapshot.source_id
        assert measurement.role in source.roles
        assert measurement.unit is unit_for_metric(measurement.metric)
        assert measurement.measured_at.tzinfo is not None
        assert measurement.received_at.tzinfo is not None


@pytest.mark.parametrize(
    "adapter",
    [
        ShellyMeasurementAdapter(
            source_id="grid_meter_error",
            name="Grid meter",
            device={"type": "shelly_pro_3em"},
            role=MeasurementRole.GRID_METER,
            reader=StubShellyReader(
                error=requests.Timeout("timed out"),
            ),
        ),
        SolakonMeasurementAdapter(
            source_id="solakon_error",
            name="Solakon ONE",
            config={"simulation": False},
            reader=StubSolakonReader(
                error=OSError("network down"),
            ),
        ),
    ],
)
def test_production_adapter_contains_transport_failure(
    adapter: MeasurementAdapter,
) -> None:
    "Communication failures return offline snapshots instead of escaping."

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()
    assert snapshot.error
