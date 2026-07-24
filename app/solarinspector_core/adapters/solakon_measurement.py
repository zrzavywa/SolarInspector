"""Expose Solakon ONE values through the normalized measurement contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Optional, Protocol

from solarinspector_core.adapters.solakon import (
    ModbusError,
    SolakonOneReader,
    SolakonOneReading,
)
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
    MeasurementSource,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric


class _SolakonReader(Protocol):
    """Describe the existing reader method used by the normalized adapter."""

    def read(self, config: dict[str, Any]) -> SolakonOneReading:
        """Return one legacy Solakon reading."""


_SOLAKON_ROLES: Final[frozenset[MeasurementRole]] = frozenset(
    {
        MeasurementRole.GRID_METER,
        MeasurementRole.SOLAR_SYSTEM,
        MeasurementRole.BATTERY_SYSTEM,
    }
)


class SolakonMeasurementAdapter:
    """Expose one configured Solakon ONE through normalized snapshots."""

    def __init__(
        self,
        *,
        source_id: str,
        name: str,
        config: dict[str, Any],
        reader: _SolakonReader | None = None,
    ) -> None:
        """Create an adapter without changing ``SolakonOneReader.read``."""

        self._source = MeasurementSource(
            source_id=source_id,
            name=name,
            device_type="solakon_one",
            roles=_SOLAKON_ROLES,
        )
        self._config = dict(config)
        self._simulation = bool(config.get("simulation"))
        self._reader = reader if reader is not None else SolakonOneReader()

    @property
    def source(self) -> MeasurementSource:
        """Return stable metadata for the configured Solakon source."""

        return self._source

    def read_snapshot(self) -> DeviceSnapshot:
        """Read Solakon once and normalize all available values."""

        received_at = datetime.now().astimezone()
        try:
            reading = self._reader.read(self._config)
        except ModbusError as exc:
            status = (
                DeviceConnectionStatus.OFFLINE
                if _has_os_error_cause(exc)
                else DeviceConnectionStatus.DEGRADED
            )
            return _error_snapshot(
                source_id=self._source.source_id,
                status=status,
                received_at=received_at,
                error=exc,
            )
        except OSError as exc:
            return _error_snapshot(
                source_id=self._source.source_id,
                status=DeviceConnectionStatus.OFFLINE,
                received_at=received_at,
                error=exc,
            )
        except (TypeError, ValueError) as exc:
            return _error_snapshot(
                source_id=self._source.source_id,
                status=DeviceConnectionStatus.DEGRADED,
                received_at=received_at,
                error=exc,
            )

        quality = (
            MeasurementQuality.CALCULATED
            if self._simulation
            else MeasurementQuality.REPORTED
        )
        measurements = tuple(
            _measurement(
                role=role,
                metric=metric,
                value=value,
                raw_value=raw_value,
                source_id=self._source.source_id,
                received_at=received_at,
                quality=quality,
            )
            for role, metric, value, raw_value in _normalized_values(reading)
            if value is not None
        )
        status = (
            DeviceConnectionStatus.DEGRADED
            if reading.warnings
            else DeviceConnectionStatus.ONLINE
        )
        return DeviceSnapshot(
            source_id=self._source.source_id,
            status=status,
            measurements=measurements,
            received_at=received_at,
            error=reading.warnings or None,
            metadata=_snapshot_metadata(reading),
        )


def _snapshot_metadata(
    reading: SolakonOneReading,
) -> tuple[tuple[str, str], ...]:
    """Preserve non-numeric device details needed by legacy consumers."""

    values = (
        ("model_name", reading.model_name),
        ("serial_number", reading.serial_number),
        ("operating_status", reading.status),
    )
    return tuple(
        (key, value) for key, value in values if value is not None and value.strip()
    )


def _normalized_values(
    reading: SolakonOneReading,
) -> tuple[
    tuple[MeasurementRole, Metric, Optional[float], object | None],
    ...,
]:
    """Map legacy Solakon fields to canonical metrics and units."""

    values: list[tuple[MeasurementRole, Metric, Optional[float], object | None]] = [
        (
            MeasurementRole.GRID_METER,
            Metric.GRID_POWER,
            _reverse_sign(reading.meter_power_w),
            reading.meter_power_w,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PV_POWER,
            reading.total_pv_power_w,
            reading.total_pv_power_w,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PLANT_AC_POWER,
            reading.active_power_w,
            reading.active_power_w,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.SYSTEM_LOAD_POWER,
            reading.load_power_w,
            reading.load_power_w,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.FREQUENCY,
            reading.grid_frequency_hz,
            reading.grid_frequency_hz,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.POWER_FACTOR,
            reading.power_factor,
            reading.power_factor,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.DEVICE_TEMPERATURE,
            reading.internal_temperature_c,
            reading.internal_temperature_c,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PV_ENERGY_TOTAL,
            _kilowatt_hours_to_watt_hours(reading.total_pv_energy_kwh),
            reading.total_pv_energy_kwh,
        ),
        (
            MeasurementRole.SOLAR_SYSTEM,
            Metric.PV_ENERGY_TODAY,
            _kilowatt_hours_to_watt_hours(reading.daily_pv_energy_kwh),
            reading.daily_pv_energy_kwh,
        ),
        (
            MeasurementRole.BATTERY_SYSTEM,
            Metric.BATTERY_SOC,
            reading.battery_soc_pct,
            reading.battery_soc_pct,
        ),
        (
            MeasurementRole.BATTERY_SYSTEM,
            Metric.BATTERY_CHARGE_TOTAL,
            _kilowatt_hours_to_watt_hours(reading.battery_total_charge_kwh),
            reading.battery_total_charge_kwh,
        ),
        (
            MeasurementRole.BATTERY_SYSTEM,
            Metric.BATTERY_DISCHARGE_TOTAL,
            _kilowatt_hours_to_watt_hours(reading.battery_total_discharge_kwh),
            reading.battery_total_discharge_kwh,
        ),
    ]

    if reading.battery_power_w is not None:
        values.extend(
            [
                (
                    MeasurementRole.BATTERY_SYSTEM,
                    Metric.BATTERY_CHARGE_POWER,
                    max(0.0, reading.battery_power_w),
                    reading.battery_power_w,
                ),
                (
                    MeasurementRole.BATTERY_SYSTEM,
                    Metric.BATTERY_DISCHARGE_POWER,
                    max(0.0, -reading.battery_power_w),
                    reading.battery_power_w,
                ),
            ]
        )

    pv_values = (
        (
            Metric.PV_INPUT_VOLTAGE_1,
            Metric.PV_INPUT_CURRENT_1,
            Metric.PV_INPUT_POWER_1,
            reading.pv1_voltage_v,
            reading.pv1_current_a,
            reading.pv1_power_w,
        ),
        (
            Metric.PV_INPUT_VOLTAGE_2,
            Metric.PV_INPUT_CURRENT_2,
            Metric.PV_INPUT_POWER_2,
            reading.pv2_voltage_v,
            reading.pv2_current_a,
            reading.pv2_power_w,
        ),
        (
            Metric.PV_INPUT_VOLTAGE_3,
            Metric.PV_INPUT_CURRENT_3,
            Metric.PV_INPUT_POWER_3,
            reading.pv3_voltage_v,
            reading.pv3_current_a,
            reading.pv3_power_w,
        ),
        (
            Metric.PV_INPUT_VOLTAGE_4,
            Metric.PV_INPUT_CURRENT_4,
            Metric.PV_INPUT_POWER_4,
            reading.pv4_voltage_v,
            reading.pv4_current_a,
            reading.pv4_power_w,
        ),
    )
    for (
        voltage_metric,
        current_metric,
        power_metric,
        voltage,
        current,
        power,
    ) in pv_values:
        values.extend(
            [
                (
                    MeasurementRole.SOLAR_SYSTEM,
                    voltage_metric,
                    voltage,
                    voltage,
                ),
                (
                    MeasurementRole.SOLAR_SYSTEM,
                    current_metric,
                    current,
                    current,
                ),
                (
                    MeasurementRole.SOLAR_SYSTEM,
                    power_metric,
                    power,
                    power,
                ),
            ]
        )

    return tuple(values)


def _measurement(
    *,
    role: MeasurementRole,
    metric: Metric,
    value: Optional[float],
    raw_value: object | None,
    source_id: str,
    received_at: datetime,
    quality: MeasurementQuality,
) -> Measurement:
    """Build one normalized measurement using its canonical unit."""

    if value is None:
        raise ValueError("missing values must be filtered before normalization")
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=received_at,
        received_at=received_at,
        quality=quality,
        raw_value=raw_value,
    )


def _reverse_sign(value: Optional[float]) -> Optional[float]:
    """Convert Solakon feed-in-positive grid power to import-positive."""

    return None if value is None else -value


def _kilowatt_hours_to_watt_hours(value: Optional[float]) -> Optional[float]:
    """Convert legacy Solakon kWh counters to canonical watt-hours."""

    return None if value is None else value * 1000.0


def _has_os_error_cause(error: BaseException) -> bool:
    """Return whether a wrapped Modbus error originated in the transport."""

    cause = error.__cause__
    while cause is not None:
        if isinstance(cause, OSError):
            return True
        cause = cause.__cause__
    return False


def _error_snapshot(
    *,
    source_id: str,
    status: DeviceConnectionStatus,
    received_at: datetime,
    error: Exception,
) -> DeviceSnapshot:
    """Create a snapshot without measurements and retain a diagnostic."""

    return DeviceSnapshot(
        source_id=source_id,
        status=status,
        measurements=(),
        received_at=received_at,
        error=f"{type(error).__name__}: {error}",
    )
