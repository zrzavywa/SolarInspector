"""Tests for the normalized SolarInspector measurement model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
    MeasurementSource,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import METRIC_UNITS, Unit, unit_for_metric

NOW = datetime(2026, 7, 23, 16, 30, tzinfo=UTC)


def make_measurement(
    *,
    metric: Metric = Metric.PLANT_AC_POWER,
    value: float = 0.0,
    unit: Unit = Unit.WATT,
    role: MeasurementRole = MeasurementRole.PLANT_METER,
) -> Measurement:
    """Build a valid measurement for focused model tests."""

    return Measurement(
        metric=metric,
        value=value,
        unit=unit,
        source_id="plant_meter_shelly",
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.MEASURED,
        raw_value={"apower": value},
    )


def test_measurement_accepts_zero_as_a_valid_value() -> None:
    measurement = make_measurement(value=0.0)

    assert measurement.value == 0.0
    assert measurement.metric is Metric.PLANT_AC_POWER
    assert measurement.unit is Unit.WATT
    assert measurement.source_id == "plant_meter_shelly"
    assert measurement.measured_at == NOW
    assert measurement.received_at == NOW
    assert measurement.raw_value == {"apower": 0.0}


def test_measurement_is_immutable() -> None:
    measurement = make_measurement(value=125.0)

    with pytest.raises(FrozenInstanceError):
        measurement.value = 250.0  # type: ignore[misc]


def test_measurement_rejects_none_as_numeric_value() -> None:
    with pytest.raises(TypeError, match="real number"):
        make_measurement(value=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_measurement_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        make_measurement(value=value)


def test_measurement_rejects_an_empty_source_id() -> None:
    with pytest.raises(ValueError, match="source_id"):
        Measurement(
            metric=Metric.PLANT_AC_POWER,
            value=1.0,
            unit=Unit.WATT,
            source_id=" ",
            role=MeasurementRole.PLANT_METER,
            measured_at=NOW,
            received_at=NOW,
            quality=MeasurementQuality.MEASURED,
        )


def test_measurement_rejects_naive_timestamps() -> None:
    naive = datetime(2026, 7, 23, 16, 30)

    with pytest.raises(ValueError, match="measured_at"):
        Measurement(
            metric=Metric.PLANT_AC_POWER,
            value=1.0,
            unit=Unit.WATT,
            source_id="plant_meter_shelly",
            role=MeasurementRole.PLANT_METER,
            measured_at=naive,
            received_at=NOW,
            quality=MeasurementQuality.MEASURED,
        )


def test_measurement_rejects_a_noncanonical_unit() -> None:
    with pytest.raises(ValueError, match="requires unit W"):
        make_measurement(unit=Unit.WATT_HOUR)


def test_every_metric_has_one_canonical_unit() -> None:
    assert set(METRIC_UNITS) == set(Metric)
    assert unit_for_metric(Metric.PV_ENERGY_TOTAL) is Unit.WATT_HOUR
    assert unit_for_metric(Metric.BATTERY_SOC) is Unit.PERCENT
    assert unit_for_metric(Metric.POWER_FACTOR) is Unit.POWER_FACTOR


def test_measurement_source_supports_multiple_roles() -> None:
    source = MeasurementSource(
        source_id="solakon_one",
        name="Solakon ONE",
        device_type="solakon_one",
        roles=frozenset(
            {
                MeasurementRole.SOLAR_SYSTEM,
                MeasurementRole.BATTERY_SYSTEM,
            }
        ),
    )

    assert source.roles == {
        MeasurementRole.SOLAR_SYSTEM,
        MeasurementRole.BATTERY_SYSTEM,
    }


def test_measurement_source_requires_a_role() -> None:
    with pytest.raises(ValueError, match="roles"):
        MeasurementSource(
            source_id="solakon_one",
            name="Solakon ONE",
            device_type="solakon_one",
            roles=frozenset(),
        )


def test_online_snapshot_accepts_complete_measurements() -> None:
    measurement = make_measurement(value=412.0)

    snapshot = DeviceSnapshot(
        source_id="plant_meter_shelly",
        status=DeviceConnectionStatus.ONLINE,
        measurements=(measurement,),
        received_at=NOW,
    )

    assert snapshot.measurements == (measurement,)
    assert snapshot.error is None


def test_degraded_snapshot_accepts_partial_measurements_and_error() -> None:
    snapshot = DeviceSnapshot(
        source_id="plant_meter_shelly",
        status=DeviceConnectionStatus.DEGRADED,
        measurements=(make_measurement(value=0.0),),
        received_at=NOW,
        error="voltage field unavailable",
    )

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert snapshot.error == "voltage field unavailable"


@pytest.mark.parametrize(
    "status",
    [DeviceConnectionStatus.OFFLINE, DeviceConnectionStatus.DISABLED],
)
def test_unavailable_device_snapshot_contains_no_measurements(
    status: DeviceConnectionStatus,
) -> None:
    snapshot = DeviceSnapshot(
        source_id="plant_meter_shelly",
        status=status,
        measurements=(),
        received_at=NOW,
        error="connection failed" if status is DeviceConnectionStatus.OFFLINE else None,
    )

    assert snapshot.measurements == ()


def test_offline_snapshot_rejects_measurements() -> None:
    with pytest.raises(ValueError, match="offline"):
        DeviceSnapshot(
            source_id="plant_meter_shelly",
            status=DeviceConnectionStatus.OFFLINE,
            measurements=(make_measurement(value=0.0),),
            received_at=NOW,
        )


def test_snapshot_requires_matching_source_ids() -> None:
    measurement = make_measurement(value=1.0)

    with pytest.raises(ValueError, match="source_id"):
        DeviceSnapshot(
            source_id="different_source",
            status=DeviceConnectionStatus.ONLINE,
            measurements=(measurement,),
            received_at=NOW,
        )


def test_snapshot_rejects_duplicate_role_and_metric_values() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        DeviceSnapshot(
            source_id="plant_meter_shelly",
            status=DeviceConnectionStatus.ONLINE,
            measurements=(
                make_measurement(value=100.0),
                make_measurement(value=101.0),
            ),
            received_at=NOW,
        )
