"""Read existing Shelly power meters.

This module preserves the HTTP access, response parsing, simulation,
direction handling, and error behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime
from typing import Any, Final, Optional

import requests
from requests.auth import HTTPDigestAuth

from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
    MeasurementSource,
)
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric


class ShellyReader:
    def __init__(self):
        self._session = requests.Session()
        self._simulation_start = time.monotonic()

    @staticmethod
    def _url(host: str, path: str) -> str:
        return f"http://{host}{path}"

    def _get_json(self, device: dict[str, Any], path: str) -> dict[str, Any]:
        if not device.get("host"):
            raise ValueError("Keine IP-Adresse oder kein Hostname konfiguriert.")
        auth = None
        if device.get("username"):
            auth = HTTPDigestAuth(device["username"], device.get("password", ""))
        response = self._session.get(
            self._url(device["host"], path),
            timeout=device.get("timeout_seconds", 3),
            auth=auth,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Das Gerät lieferte keine gültige JSON-Antwort.")
        return payload

    def read(self, device: dict[str, Any], role: str) -> MeterReading:
        device_type = device.get("type")
        factor = float(device.get("direction_factor", 1))

        if device_type == "simulation":
            reading = self._simulate(role)
        elif device_type == "shelly_pm_mini_gen3":
            reading = self._read_pm1(device)
        elif device_type == "shelly_3em_gen1":
            reading = self._read_3em_gen1(device)
        elif device_type == "shelly_pro_3em":
            reading = self._read_pro_3em(device)
        else:
            raise ValueError(f"Nicht unterstützter Gerätetyp: {device_type}")

        reading.power_w *= factor
        return reading

    def _read_pm1(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/rpc/PM1.GetStatus?id=0")
        return MeterReading(
            power_w=float(data.get("apower", 0.0)),
            voltage_v=_float_or_none(data.get("voltage")),
            current_a=_float_or_none(data.get("current")),
            power_factor=_float_or_none(data.get("pf")),
            frequency_hz=_float_or_none(data.get("freq")),
            energy_total_wh=_nested_float(data, "aenergy", "total"),
            returned_energy_total_wh=_nested_float(data, "ret_aenergy", "total"),
            source="PM1.GetStatus",
            power_available=data.get("apower") is not None,
        )

    def _read_3em_gen1(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/status")
        emeters = data.get("emeters") or []
        if not isinstance(emeters, list) or not emeters:
            raise ValueError("Keine emeters-Daten in der Shelly-3EM-Antwort.")
        power = data.get("total_power")
        power_available = power is not None or any(
            item.get("power") is not None for item in emeters
        )
        if power is None:
            power = sum(float(item.get("power", 0.0)) for item in emeters)
        voltages = [_float_or_none(item.get("voltage")) for item in emeters]
        valid_voltages = [item for item in voltages if item is not None]
        total_wh = sum(float(item.get("total", 0.0)) for item in emeters)
        returned_wh = sum(float(item.get("total_returned", 0.0)) for item in emeters)
        return MeterReading(
            power_w=float(power),
            voltage_v=(sum(valid_voltages) / len(valid_voltages))
            if valid_voltages
            else None,
            energy_total_wh=total_wh,
            returned_energy_total_wh=returned_wh,
            source="/status emeters",
            power_available=power_available,
        )

    def _read_pro_3em(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/rpc/EM.GetStatus?id=0")
        phase_power = [
            _float_or_none(data.get("a_act_power")),
            _float_or_none(data.get("b_act_power")),
            _float_or_none(data.get("c_act_power", data.get("c_active_power"))),
        ]
        power = _float_or_none(data.get("total_act_power"))
        power_available = power is not None or any(
            item is not None for item in phase_power
        )
        if power is None:
            power = sum(item or 0.0 for item in phase_power)
        voltages = [
            _float_or_none(data.get("a_voltage")),
            _float_or_none(data.get("b_voltage")),
            _float_or_none(data.get("c_voltage")),
        ]
        valid_voltages = [item for item in voltages if item is not None]
        currents = [
            _float_or_none(data.get("a_current")),
            _float_or_none(data.get("b_current")),
            _float_or_none(data.get("c_current")),
        ]
        valid_currents = [item for item in currents if item is not None]
        pfs = [
            _float_or_none(data.get("a_pf")),
            _float_or_none(data.get("b_pf")),
            _float_or_none(data.get("c_pf")),
        ]
        valid_pfs = [item for item in pfs if item is not None]
        freqs = [
            _float_or_none(data.get("a_freq")),
            _float_or_none(data.get("b_freq")),
            _float_or_none(data.get("c_freq")),
        ]
        valid_freqs = [item for item in freqs if item is not None]
        return MeterReading(
            power_w=float(power),
            voltage_v=(sum(valid_voltages) / len(valid_voltages))
            if valid_voltages
            else None,
            current_a=sum(valid_currents) if valid_currents else None,
            power_factor=(sum(valid_pfs) / len(valid_pfs)) if valid_pfs else None,
            frequency_hz=(sum(valid_freqs) / len(valid_freqs)) if valid_freqs else None,
            source="EM.GetStatus",
            power_available=power_available,
        )

    def _simulate(self, role: str) -> MeterReading:
        now = datetime.now().astimezone()
        seconds = now.hour * 3600 + now.minute * 60 + now.second
        daylight = max(0.0, math.sin(math.pi * (seconds - 6 * 3600) / (14 * 3600)))
        solar = 850.0 * daylight + random.uniform(-20, 20)
        solar = max(0.0, solar)
        household = 280 + 120 * math.sin(seconds / 2400.0) + random.uniform(-35, 35)
        household = max(90.0, household)
        if role == "solakon_meter":
            power = solar
            source = "Simulation Solakon"
        else:
            power = household - solar
            source = "Simulation Hausanschluss"
        return MeterReading(
            power_w=power,
            voltage_v=230 + random.uniform(-1.5, 1.5),
            current_a=abs(power) / 230.0,
            power_factor=0.97,
            frequency_hz=50 + random.uniform(-0.03, 0.03),
            source=source,
        )


class ShellyMeasurementAdapter:
    """Expose one configured Shelly source through the normalized contract."""

    def __init__(
        self,
        *,
        source_id: str,
        name: str,
        device: dict[str, Any],
        role: MeasurementRole,
        reader: ShellyReader | None = None,
    ) -> None:
        """Create an adapter without changing the existing ``ShellyReader`` API."""

        try:
            _power_metric, legacy_role = _ROLE_CONFIGURATION[role]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported Shelly measurement role: {role.value}"
            ) from exc

        self._source = MeasurementSource(
            source_id=source_id,
            name=name,
            device_type=str(device.get("type") or ""),
            roles=frozenset({role}),
        )
        self._device = dict(device)
        self._role = role
        self._legacy_role = legacy_role
        self._reader = reader if reader is not None else ShellyReader()

    @property
    def source(self) -> MeasurementSource:
        """Return stable metadata for the configured Shelly source."""

        return self._source

    def read_snapshot(self) -> DeviceSnapshot:
        """Read one Shelly value and map it to normalized measurements."""

        received_at = datetime.now().astimezone()
        try:
            reading = self._reader.read(self._device, self._legacy_role)
        except requests.RequestException as exc:
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
            if self._source.device_type == "simulation"
            else MeasurementQuality.REPORTED
        )
        measurements = tuple(
            _measurement(
                metric=metric,
                value=value,
                source_id=self._source.source_id,
                role=self._role,
                received_at=received_at,
                quality=quality,
            )
            for metric, value in _normalized_values(self._role, reading)
            if value is not None
        )
        status = (
            DeviceConnectionStatus.ONLINE
            if reading.power_available
            else DeviceConnectionStatus.DEGRADED
        )
        error = (
            None
            if reading.power_available
            else "Required power measurement is missing."
        )
        return DeviceSnapshot(
            source_id=self._source.source_id,
            status=status,
            measurements=measurements,
            received_at=received_at,
            error=error,
        )


_ROLE_CONFIGURATION: Final[dict[MeasurementRole, tuple[Metric, str]]] = {
    MeasurementRole.GRID_METER: (Metric.GRID_POWER, "house_meter"),
    MeasurementRole.PLANT_METER: (Metric.PLANT_AC_POWER, "solakon_meter"),
}


def _normalized_values(
    role: MeasurementRole,
    reading: MeterReading,
) -> tuple[tuple[Metric, Optional[float]], ...]:
    """Map available legacy fields to role-specific normalized metrics."""

    power_metric, _legacy_role = _ROLE_CONFIGURATION[role]
    values: list[tuple[Metric, Optional[float]]] = [
        (
            power_metric,
            reading.power_w if reading.power_available else None,
        )
    ]

    if role is MeasurementRole.GRID_METER:
        values.extend(
            [
                (Metric.GRID_IMPORT_TOTAL, reading.energy_total_wh),
                (Metric.GRID_EXPORT_TOTAL, reading.returned_energy_total_wh),
                (Metric.GRID_VOLTAGE, reading.voltage_v),
                (Metric.GRID_CURRENT, reading.current_a),
                (Metric.POWER_FACTOR, reading.power_factor),
            ]
        )
    else:
        values.extend(
            [
                (Metric.PLANT_AC_ENERGY_TOTAL, reading.energy_total_wh),
                (
                    Metric.PLANT_AC_RETURNED_ENERGY_TOTAL,
                    reading.returned_energy_total_wh,
                ),
                (Metric.PLANT_VOLTAGE, reading.voltage_v),
                (Metric.PLANT_CURRENT, reading.current_a),
                (Metric.PLANT_POWER_FACTOR, reading.power_factor),
            ]
        )

    values.append((Metric.FREQUENCY, reading.frequency_hz))
    return tuple(values)


def _measurement(
    *,
    metric: Metric,
    value: Optional[float],
    source_id: str,
    role: MeasurementRole,
    received_at: datetime,
    quality: MeasurementQuality,
) -> Measurement:
    """Build one normalized measurement using the canonical metric unit."""

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
    )


def _error_snapshot(
    *,
    source_id: str,
    status: DeviceConnectionStatus,
    received_at: datetime,
    error: Exception,
) -> DeviceSnapshot:
    """Create an unavailable snapshot while preserving a compact diagnostic."""

    return DeviceSnapshot(
        source_id=source_id,
        status=status,
        measurements=(),
        received_at=received_at,
        error=f"{type(error).__name__}: {error}",
    )


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_float(data: dict[str, Any], parent: str, child: str) -> Optional[float]:
    item = data.get(parent)
    if not isinstance(item, dict):
        return None
    return _float_or_none(item.get(child))
