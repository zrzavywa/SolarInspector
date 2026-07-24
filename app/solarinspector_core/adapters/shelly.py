"""Read existing Shelly power meters.

This module preserves the HTTP access, response parsing, simulation,
direction handling, and error behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Final, Optional

import requests
from requests.auth import HTTPDigestAuth

from solarinspector_core.config.shelly import (
    Phase,
    normalize_direction_factor,
    normalize_measurement_role,
    phase_direction_factor,
)
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
    MeasurementSource,
)
from solarinspector_core.models.legacy import MeterPhaseReading, MeterReading
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.services.phase_power import (
    PhasePowerAnalysis,
    analyze_phase_power,
)


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
        if reading.phases:
            reading.phases = tuple(
                replace(
                    phase,
                    power_w=(
                        phase.power_w
                        * phase_direction_factor(device, Phase(phase.phase))
                        if phase.power_w is not None
                        else None
                    ),
                )
                for phase in reading.phases
            )
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
            power_is_device_total=data.get("apower") is not None,
        )

    def _read_3em_gen1(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/status")
        emeters = data.get("emeters") or []
        if not isinstance(emeters, list) or not emeters:
            raise ValueError("Keine emeters-Daten in der Shelly-3EM-Antwort.")
        phases = tuple(
            _parse_gen1_phase(
                phase_index,
                emeters[phase_index] if phase_index < len(emeters) else {},
            )
            for phase_index in range(3)
        )
        power = data.get("total_power")
        power_is_device_total = power is not None
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
            power_is_device_total=power_is_device_total,
            phases=phases,
        )

    def _read_pro_3em(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/rpc/EM.GetStatus?id=0")
        phases = tuple(
            _parse_pro_phase(data, prefix, phase) for prefix, phase in _PRO_PHASES
        )
        phase_power = [phase.power_w for phase in phases]
        power = _float_or_none(data.get("total_act_power"))
        power_is_device_total = power is not None
        power_available = power is not None or any(
            item is not None for item in phase_power
        )
        if power is None:
            power = sum(item or 0.0 for item in phase_power)

        valid_voltages = [
            phase.voltage_v for phase in phases if phase.voltage_v is not None
        ]
        valid_currents = [
            phase.current_a for phase in phases if phase.current_a is not None
        ]
        valid_pfs = [
            phase.power_factor for phase in phases if phase.power_factor is not None
        ]
        valid_freqs = [
            phase.frequency_hz for phase in phases if phase.frequency_hz is not None
        ]

        device_errors = _string_tuple(data.get("errors"))
        raw_validity = data.get("is_valid")
        if isinstance(raw_validity, bool):
            is_valid = raw_validity
        elif device_errors or any(phase.is_valid is False for phase in phases):
            is_valid = False
        elif any(_phase_has_measurement(phase) for phase in phases):
            is_valid = True
        else:
            is_valid = None

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
            power_is_device_total=power_is_device_total,
            phases=phases,
            is_valid=is_valid,
            errors=device_errors,
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

        device_type = str(device.get("type") or "")
        source_roles = {role}
        if (
            role is MeasurementRole.GRID_METER
            and device_type in _MULTI_PHASE_DEVICE_TYPES
        ):
            source_roles.add(MeasurementRole.HOUSE_METER)

        self._source = MeasurementSource(
            source_id=source_id,
            name=name,
            device_type=device_type,
            roles=frozenset(source_roles),
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

        base_quality = (
            MeasurementQuality.CALCULATED
            if self._source.device_type == "simulation"
            else MeasurementQuality.REPORTED
        )
        analysis = _analyze_reading_phase_power(
            reading,
            self._role,
            self._device,
        )
        aggregate_quality = (
            MeasurementQuality.SUSPECT
            if _aggregate_is_suspect(reading, analysis)
            else base_quality
        )
        aggregate_measurements = tuple(
            _measurement(
                metric=metric,
                value=value,
                source_id=self._source.source_id,
                role=self._role,
                received_at=received_at,
                quality=aggregate_quality,
            )
            for metric, value in _normalized_values(self._role, reading)
            if value is not None
        )
        phase_measurements = _normalized_phase_measurements(
            reading=reading,
            source_id=self._source.source_id,
            received_at=received_at,
            base_quality=base_quality,
            enabled=self._role is MeasurementRole.GRID_METER,
        )
        diagnostics = _snapshot_diagnostics(reading, analysis)
        status = (
            DeviceConnectionStatus.ONLINE
            if reading.power_available and not diagnostics
            else DeviceConnectionStatus.DEGRADED
        )
        return DeviceSnapshot(
            source_id=self._source.source_id,
            status=status,
            measurements=aggregate_measurements + phase_measurements,
            received_at=received_at,
            error=" ".join(diagnostics) if diagnostics else None,
            metadata=_phase_metadata(self._device, reading, analysis),
        )


_MULTI_PHASE_DEVICE_TYPES: Final[frozenset[str]] = frozenset(
    {"shelly_3em_gen1", "shelly_pro_3em"}
)

_PHASE_METRICS: Final[dict[str, tuple[Metric, Metric, Metric, Metric]]] = {
    Phase.L1.value: (
        Metric.PHASE_POWER_L1,
        Metric.PHASE_VOLTAGE_L1,
        Metric.PHASE_CURRENT_L1,
        Metric.PHASE_POWER_FACTOR_L1,
    ),
    Phase.L2.value: (
        Metric.PHASE_POWER_L2,
        Metric.PHASE_VOLTAGE_L2,
        Metric.PHASE_CURRENT_L2,
        Metric.PHASE_POWER_FACTOR_L2,
    ),
    Phase.L3.value: (
        Metric.PHASE_POWER_L3,
        Metric.PHASE_VOLTAGE_L3,
        Metric.PHASE_CURRENT_L3,
        Metric.PHASE_POWER_FACTOR_L3,
    ),
}


def _analyze_reading_phase_power(
    reading: MeterReading,
    role: MeasurementRole,
    device: dict[str, Any],
) -> PhasePowerAnalysis | None:
    """Analyze phase power only for the compatible house/grid meter."""

    if role is not MeasurementRole.GRID_METER or not reading.phases:
        return None
    phase_by_name = {phase.phase: phase for phase in reading.phases}
    phase_power = tuple(
        phase_by_name[phase.value].power_w if phase.value in phase_by_name else None
        for phase in Phase
    )
    reported_total_w = (
        reading.power_w
        if reading.power_is_device_total and _phase_total_is_comparable(device)
        else None
    )
    return analyze_phase_power(
        phase_power,
        reported_total_w=reported_total_w,
    )


def _phase_total_is_comparable(device: dict[str, Any]) -> bool:
    """Return whether aggregate and phase signs use the same direction."""

    global_factor = normalize_direction_factor(device.get("direction_factor", 1))
    return all(
        phase_direction_factor(device, phase) == global_factor for phase in Phase
    )


def _normalized_phase_measurements(
    *,
    reading: MeterReading,
    source_id: str,
    received_at: datetime,
    base_quality: MeasurementQuality,
    enabled: bool,
) -> tuple[Measurement, ...]:
    """Map available phase values to HOUSE_METER metrics."""

    if not enabled:
        return ()

    measurements: list[Measurement] = []
    for phase in reading.phases:
        metrics = _PHASE_METRICS.get(phase.phase)
        if metrics is None:
            continue
        quality = (
            MeasurementQuality.SUSPECT
            if phase.is_valid is False or phase.errors
            else base_quality
        )
        for metric, value in zip(
            metrics,
            (
                phase.power_w,
                phase.voltage_v,
                phase.current_a,
                phase.power_factor,
            ),
            strict=True,
        ):
            if value is None:
                continue
            measurements.append(
                _measurement(
                    metric=metric,
                    value=value,
                    source_id=source_id,
                    role=MeasurementRole.HOUSE_METER,
                    received_at=received_at,
                    quality=quality,
                )
            )
    return tuple(measurements)


def _aggregate_is_suspect(
    reading: MeterReading,
    analysis: PhasePowerAnalysis | None,
) -> bool:
    """Return whether aggregate values carry known device diagnostics."""

    return bool(
        reading.is_valid is False
        or reading.errors
        or (analysis is not None and analysis.total_consistent is False)
    )


def _snapshot_diagnostics(
    reading: MeterReading,
    analysis: PhasePowerAnalysis | None,
) -> tuple[str, ...]:
    """Build stable diagnostics without discarding partial measurements."""

    diagnostics: list[str] = []
    if not reading.power_available:
        diagnostics.append("Required power measurement is missing.")
    if reading.is_valid is False:
        diagnostics.append("Shelly measurement reported invalid status.")
    if reading.errors:
        diagnostics.append(f"Device errors: {', '.join(reading.errors)}.")

    if analysis is not None:
        for phase in reading.phases:
            phase_name = phase.phase.upper()
            if phase.is_valid is False:
                detail = f" ({', '.join(phase.errors)})" if phase.errors else ""
                diagnostics.append(f"{phase_name} is invalid{detail}.")
            elif not phase.power_available:
                diagnostics.append(f"{phase_name} power measurement is missing.")
        if analysis.total_consistent is False:
            delta_w = abs(analysis.total_delta_w or 0.0)
            diagnostics.append(
                f"Device total differs from complete phase sum by {delta_w:.1f} W."
            )

    return tuple(dict.fromkeys(diagnostics))


def _phase_metadata(
    device: dict[str, Any],
    reading: MeterReading,
    analysis: PhasePowerAnalysis | None,
) -> tuple[tuple[str, str], ...]:
    """Expose deterministic phase analysis for later persistence and APIs."""

    if analysis is None:
        return ()

    metadata: list[tuple[str, str]] = [
        (
            "measurement_role",
            normalize_measurement_role(device.get("measurement_role")),
        ),
        ("phase_power_available_count", str(analysis.available_count)),
        ("phase_power_complete", _metadata_bool(analysis.complete)),
        (
            "phase_power_total_source",
            (
                "device"
                if reading.power_is_device_total and _phase_total_is_comparable(device)
                else (
                    "device_uncompared"
                    if reading.power_is_device_total
                    else "phase_sum"
                )
            ),
        ),
    ]
    if analysis.calculated_total_w is not None:
        metadata.append(
            (
                "phase_power_sum_w",
                _metadata_number(analysis.calculated_total_w),
            )
        )
    if analysis.spread_w is not None:
        metadata.append(("phase_power_spread_w", _metadata_number(analysis.spread_w)))
    for phase, share_pct in zip(Phase, analysis.shares_pct, strict=True):
        if share_pct is not None:
            metadata.append(
                (
                    f"phase_power_share_{phase.value}_pct",
                    _metadata_number(share_pct),
                )
            )
    if analysis.total_delta_w is not None:
        metadata.append(
            (
                "phase_power_total_delta_w",
                _metadata_number(analysis.total_delta_w),
            )
        )
    if analysis.total_delta_pct is not None:
        metadata.append(
            (
                "phase_power_total_delta_pct",
                _metadata_number(analysis.total_delta_pct),
            )
        )
    if analysis.total_consistent is not None:
        metadata.append(
            (
                "phase_power_total_consistent",
                _metadata_bool(analysis.total_consistent),
            )
        )
    return tuple(metadata)


def _metadata_number(value: float) -> str:
    """Format one finite number compactly and deterministically."""

    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return formatted if formatted and formatted != "-0" else "0"


def _metadata_bool(value: bool) -> str:
    """Format a boolean for string-only snapshot metadata."""

    return "true" if value else "false"


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


_PRO_PHASES: Final[tuple[tuple[str, Phase], ...]] = (
    ("a", Phase.L1),
    ("b", Phase.L2),
    ("c", Phase.L3),
)


def _parse_pro_phase(
    data: dict[str, Any],
    prefix: str,
    phase: Phase,
) -> MeterPhaseReading:
    """Parse one Pro 3EM phase and retain device diagnostics."""

    power_key = f"{prefix}_act_power"
    raw_power = data.get(power_key)
    if raw_power is None and prefix == "c":
        raw_power = data.get("c_active_power")

    raw_values: tuple[tuple[str, Any], ...] = (
        (power_key, raw_power),
        (f"{prefix}_voltage", data.get(f"{prefix}_voltage")),
        (f"{prefix}_current", data.get(f"{prefix}_current")),
        (f"{prefix}_pf", data.get(f"{prefix}_pf")),
        (f"{prefix}_freq", data.get(f"{prefix}_freq")),
    )
    parsed_values = tuple(
        (field_name, raw_value, _float_or_none(raw_value))
        for field_name, raw_value in raw_values
    )
    invalid_fields = tuple(
        f"invalid_value:{field_name}"
        for field_name, raw_value, parsed_value in parsed_values
        if raw_value is not None and parsed_value is None
    )
    parsed_by_name = {
        field_name: parsed_value
        for field_name, _raw_value, parsed_value in parsed_values
    }

    errors = _string_tuple(data.get(f"{prefix}_errors")) + invalid_fields
    flags = _string_tuple(data.get(f"{prefix}_flags"))
    has_measurement = any(
        parsed_value is not None
        for _field_name, _raw_value, parsed_value in parsed_values
    )
    if errors:
        is_valid = False
    elif has_measurement:
        is_valid = True
    else:
        is_valid = None

    return MeterPhaseReading(
        phase=phase.value,
        power_w=parsed_by_name[power_key],
        voltage_v=parsed_by_name[f"{prefix}_voltage"],
        current_a=parsed_by_name[f"{prefix}_current"],
        power_factor=parsed_by_name[f"{prefix}_pf"],
        frequency_hz=parsed_by_name[f"{prefix}_freq"],
        is_valid=is_valid,
        errors=errors,
        flags=flags,
    )


def _phase_has_measurement(phase: MeterPhaseReading) -> bool:
    """Return whether at least one instantaneous phase value is available."""

    return any(
        value is not None
        for value in (
            phase.power_w,
            phase.voltage_v,
            phase.current_a,
            phase.power_factor,
            phase.frequency_hz,
        )
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    """Normalize a JSON string array while preserving its order."""

    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )


_GEN1_PHASE_NAMES: Final[tuple[Phase, Phase, Phase]] = (
    Phase.L1,
    Phase.L2,
    Phase.L3,
)


def _parse_gen1_phase(
    phase_index: int,
    payload: Any,
) -> MeterPhaseReading:
    """Parse one positional Gen 1 emeter without affecting aggregate values."""

    if not isinstance(payload, dict):
        raise ValueError(
            f"Ungültige emeters-Daten für Phase "
            f"{_GEN1_PHASE_NAMES[phase_index].upper()}."
        )

    raw_validity = payload.get("is_valid")
    is_valid = raw_validity if isinstance(raw_validity, bool) else None

    return MeterPhaseReading(
        phase=_GEN1_PHASE_NAMES[phase_index],
        power_w=_float_or_none(payload.get("power")),
        voltage_v=_float_or_none(payload.get("voltage")),
        current_a=_float_or_none(payload.get("current")),
        power_factor=_float_or_none(payload.get("pf")),
        energy_total_wh=_float_or_none(payload.get("total")),
        returned_energy_total_wh=_float_or_none(payload.get("total_returned")),
        is_valid=is_valid,
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
