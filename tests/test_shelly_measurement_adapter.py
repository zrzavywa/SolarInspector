"""Tests for normalized snapshots produced by the Shelly adapter."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests
from solarinspector_core.adapters import MeasurementAdapter
from solarinspector_core.adapters.shelly import (
    ShellyMeasurementAdapter,
    ShellyReader,
)
from solarinspector_core.models.device import DeviceConnectionStatus, DeviceSnapshot
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric


def device_config(
    device_type: str = "shelly_pm_mini_gen3",
    *,
    direction_factor: int = 1,
) -> dict[str, object]:
    """Return a minimal configured Shelly device."""

    return {
        "type": device_type,
        "host": "192.168.188.50",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": direction_factor,
    }


def make_adapter(
    *,
    role: MeasurementRole,
    device: dict[str, object] | None = None,
    reader: ShellyReader | None = None,
) -> ShellyMeasurementAdapter:
    """Build one configured normalized Shelly adapter."""

    return ShellyMeasurementAdapter(
        source_id="shelly-test",
        name="Shelly test meter",
        device=dict(device or device_config()),
        role=role,
        reader=reader,
    )


def measurement_values(
    adapter: ShellyMeasurementAdapter,
) -> tuple[DeviceSnapshot, dict[Metric, float]]:
    """Read one snapshot and index its values by metric."""

    snapshot = adapter.read_snapshot()
    values = {
        measurement.metric: measurement.value for measurement in snapshot.measurements
    }
    return snapshot, values


def test_shelly_adapter_satisfies_runtime_protocol() -> None:
    adapter = make_adapter(role=MeasurementRole.GRID_METER)

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.source_id == "shelly-test"
    assert adapter.source.roles == frozenset({MeasurementRole.GRID_METER})


def test_plant_meter_snapshot_maps_available_legacy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "apower": 412.7,
        "voltage": 230.4,
        "current": 1.79,
        "pf": 0.99,
        "freq": 50.01,
        "aenergy": {"total": 12345.6},
        "ret_aenergy": {"total": 78.9},
    }
    reader = ShellyReader()
    monkeypatch.setattr(reader, "_get_json", lambda _device, _path: payload)
    adapter = make_adapter(role=MeasurementRole.PLANT_METER, reader=reader)

    snapshot, values = measurement_values(adapter)

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values == {
        Metric.PLANT_AC_POWER: pytest.approx(412.7),
        Metric.PLANT_AC_ENERGY_TOTAL: pytest.approx(12345.6),
        Metric.PLANT_AC_RETURNED_ENERGY_TOTAL: pytest.approx(78.9),
        Metric.PLANT_VOLTAGE: pytest.approx(230.4),
        Metric.PLANT_CURRENT: pytest.approx(1.79),
        Metric.PLANT_POWER_FACTOR: pytest.approx(0.99),
        Metric.FREQUENCY: pytest.approx(50.01),
    }
    for measurement in snapshot.measurements:
        assert measurement.source_id == snapshot.source_id
        assert measurement.role is MeasurementRole.PLANT_METER
        assert measurement.unit is unit_for_metric(measurement.metric)
        assert measurement.quality is MeasurementQuality.REPORTED
        assert measurement.measured_at == snapshot.received_at
        assert measurement.received_at == snapshot.received_at


def test_grid_snapshot_preserves_normalized_power_sign_and_energy_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "apower": 412.7,
        "pf": 0.99,
        "freq": 50.01,
        "aenergy": {"total": 12345.6},
        "ret_aenergy": {"total": 78.9},
    }
    reader = ShellyReader()
    monkeypatch.setattr(reader, "_get_json", lambda _device, _path: payload)
    adapter = make_adapter(
        role=MeasurementRole.GRID_METER,
        device=device_config(direction_factor=-1),
        reader=reader,
    )

    _snapshot, values = measurement_values(adapter)

    assert values == {
        Metric.GRID_POWER: pytest.approx(-412.7),
        Metric.GRID_IMPORT_TOTAL: pytest.approx(12345.6),
        Metric.GRID_EXPORT_TOTAL: pytest.approx(78.9),
        Metric.POWER_FACTOR: pytest.approx(0.99),
        Metric.FREQUENCY: pytest.approx(50.01),
    }


def test_simulated_grid_values_are_marked_as_calculated() -> None:
    reader = Mock(spec=ShellyReader)
    reader.read.return_value = MeterReading(power_w=250.0, source="Simulation")
    device = device_config("simulation")
    adapter = make_adapter(
        role=MeasurementRole.GRID_METER,
        device=device,
        reader=reader,
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert len(snapshot.measurements) == 1
    assert snapshot.measurements[0].metric is Metric.GRID_POWER
    assert snapshot.measurements[0].quality is MeasurementQuality.CALCULATED
    reader.read.assert_called_once_with(device, "house_meter")


def test_missing_required_power_returns_degraded_partial_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "voltage": 229.8,
        "pf": 0.97,
        "freq": 50.0,
    }
    reader = ShellyReader()
    monkeypatch.setattr(reader, "_get_json", lambda _device, _path: payload)
    adapter = make_adapter(
        role=MeasurementRole.GRID_METER,
        reader=reader,
    )

    snapshot, values = measurement_values(adapter)

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert snapshot.error == "Required power measurement is missing."
    assert Metric.GRID_POWER not in values
    assert values[Metric.GRID_VOLTAGE] == pytest.approx(229.8)
    assert values[Metric.POWER_FACTOR] == pytest.approx(0.97)
    assert values[Metric.FREQUENCY] == pytest.approx(50.0)


def test_network_error_returns_offline_snapshot() -> None:
    reader = Mock(spec=ShellyReader)
    reader.read.side_effect = requests.Timeout("timed out")
    adapter = make_adapter(role=MeasurementRole.GRID_METER, reader=reader)

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.OFFLINE
    assert snapshot.measurements == ()
    assert snapshot.error == "Timeout: timed out"


def test_parse_error_returns_degraded_snapshot() -> None:
    reader = Mock(spec=ShellyReader)
    reader.read.side_effect = ValueError("invalid power")
    adapter = make_adapter(role=MeasurementRole.PLANT_METER, reader=reader)

    snapshot = adapter.read_snapshot()

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert snapshot.measurements == ()
    assert snapshot.error == "ValueError: invalid power"


@pytest.mark.parametrize(
    "role",
    [
        MeasurementRole.HOUSE_METER,
        MeasurementRole.SOLAR_SYSTEM,
        MeasurementRole.BATTERY_SYSTEM,
    ],
)
def test_adapter_rejects_roles_not_supported_by_shelly_meter_mapping(
    role: MeasurementRole,
) -> None:
    with pytest.raises(ValueError, match="Unsupported Shelly measurement role"):
        make_adapter(role=role)
