"""Tests for temporary normalized-to-legacy compatibility mappings."""

from datetime import UTC, datetime

import pytest

from solarinspector_core.adapters.compatibility import (
    meter_reading_from_snapshot,
    solakon_reading_from_snapshot,
)
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric

NOW = datetime(2026, 7, 23, 19, 0, tzinfo=UTC)


def measurement(
    role: MeasurementRole,
    metric: Metric,
    value: float,
) -> Measurement:
    """Build one valid normalized measurement."""

    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id="source",
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.REPORTED,
    )


def snapshot(
    *measurements: Measurement,
    metadata: tuple[tuple[str, str], ...] = (),
    error: str | None = None,
) -> DeviceSnapshot:
    """Build one normalized snapshot for compatibility tests."""

    return DeviceSnapshot(
        source_id="source",
        status=(
            DeviceConnectionStatus.DEGRADED
            if error
            else DeviceConnectionStatus.ONLINE
        ),
        measurements=tuple(measurements),
        received_at=NOW,
        error=error,
        metadata=metadata,
    )


def test_grid_snapshot_maps_to_legacy_meter_reading() -> None:
    reading = meter_reading_from_snapshot(
        snapshot(
            measurement(
                MeasurementRole.GRID_METER,
                Metric.GRID_POWER,
                -125.0,
            ),
            measurement(
                MeasurementRole.GRID_METER,
                Metric.GRID_IMPORT_TOTAL,
                12_345.0,
            ),
            measurement(
                MeasurementRole.GRID_METER,
                Metric.GRID_EXPORT_TOTAL,
                678.0,
            ),
            measurement(
                MeasurementRole.GRID_METER,
                Metric.POWER_FACTOR,
                0.98,
            ),
        ),
        MeasurementRole.GRID_METER,
    )

    assert reading is not None
    assert reading.power_w == pytest.approx(-125.0)
    assert reading.energy_total_wh == pytest.approx(12_345.0)
    assert reading.returned_energy_total_wh == pytest.approx(678.0)
    assert reading.power_factor == pytest.approx(0.98)


def test_plant_snapshot_maps_to_legacy_meter_reading() -> None:
    reading = meter_reading_from_snapshot(
        snapshot(
            measurement(
                MeasurementRole.PLANT_METER,
                Metric.PLANT_AC_POWER,
                610.0,
            ),
            measurement(
                MeasurementRole.PLANT_METER,
                Metric.PLANT_VOLTAGE,
                230.4,
            ),
            measurement(
                MeasurementRole.PLANT_METER,
                Metric.PLANT_CURRENT,
                2.65,
            ),
        ),
        MeasurementRole.PLANT_METER,
    )

    assert reading is not None
    assert reading.power_w == pytest.approx(610.0)
    assert reading.voltage_v == pytest.approx(230.4)
    assert reading.current_a == pytest.approx(2.65)


def test_meter_mapping_returns_none_without_required_power() -> None:
    reading = meter_reading_from_snapshot(
        snapshot(),
        MeasurementRole.GRID_METER,
    )

    assert reading is None


def test_meter_mapping_rejects_unsupported_role() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        meter_reading_from_snapshot(
            snapshot(),
            MeasurementRole.SOLAR_SYSTEM,
        )


def test_solakon_snapshot_restores_legacy_signs_units_and_metadata() -> None:
    reading = solakon_reading_from_snapshot(
        snapshot(
            measurement(
                MeasurementRole.GRID_METER,
                Metric.GRID_POWER,
                150.0,
            ),
            measurement(
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_POWER,
                960.0,
            ),
            measurement(
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PLANT_AC_POWER,
                740.0,
            ),
            measurement(
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_ENERGY_TOTAL,
                1_234_560.0,
            ),
            measurement(
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_ENERGY_TODAY,
                3_450.0,
            ),
            measurement(
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_CHARGE_POWER,
                220.0,
            ),
            measurement(
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_DISCHARGE_POWER,
                0.0,
            ),
            measurement(
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_SOC,
                76.0,
            ),
            metadata=(
                ("model_name", "Solakon ONE H3"),
                ("serial_number", "SYNTHETIC-001"),
                ("operating_status", "Betrieb"),
            ),
        )
    )

    assert reading is not None
    assert reading.model_name == "Solakon ONE H3"
    assert reading.serial_number == "SYNTHETIC-001"
    assert reading.status == "Betrieb"
    assert reading.meter_power_w == pytest.approx(-150.0)
    assert reading.total_pv_power_w == pytest.approx(960.0)
    assert reading.active_power_w == pytest.approx(740.0)
    assert reading.battery_power_w == pytest.approx(220.0)
    assert reading.battery_soc_pct == pytest.approx(76.0)
    assert reading.total_pv_energy_kwh == pytest.approx(1234.56)
    assert reading.daily_pv_energy_kwh == pytest.approx(3.45)


def test_solakon_discharge_restores_negative_legacy_battery_power() -> None:
    reading = solakon_reading_from_snapshot(
        snapshot(
            measurement(
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_CHARGE_POWER,
                0.0,
            ),
            measurement(
                MeasurementRole.BATTERY_SYSTEM,
                Metric.BATTERY_DISCHARGE_POWER,
                300.0,
            ),
        )
    )

    assert reading is not None
    assert reading.battery_power_w == pytest.approx(-300.0)


def test_empty_snapshot_maps_to_unavailable_solakon_reading() -> None:
    assert solakon_reading_from_snapshot(snapshot()) is None


def test_partial_snapshot_preserves_diagnostic_warning() -> None:
    reading = solakon_reading_from_snapshot(
        snapshot(
            measurement(
                MeasurementRole.SOLAR_SYSTEM,
                Metric.PV_POWER,
                100.0,
            ),
            error="Register block unavailable",
        )
    )

    assert reading is not None
    assert reading.total_pv_power_w == pytest.approx(100.0)
    assert reading.warnings == "Register block unavailable"
