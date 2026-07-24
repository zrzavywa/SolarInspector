"""Read an official grid meter from the local SHRDZM REST API."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, cast

import requests

from solarinspector_core.config.shelly import normalize_direction_factor
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


class _HttpResponse(Protocol):
    """Describe the response attributes used by the local HTTP client."""

    status_code: int
    text: str

    def json(self) -> Any:
        """Decode and return the response JSON."""


class _HttpSession(Protocol):
    """Describe the requests operation used by the adapter."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
        auth: tuple[str, str] | None,
    ) -> _HttpResponse:
        """Perform one local HTTP GET request."""


class ShrdzmGridMeterError(RuntimeError):
    """Base class for controlled SHRDZM grid-meter failures."""


class ShrdzmTransportError(ShrdzmGridMeterError):
    """Report local network failures without exposing credentials."""


class ShrdzmResponseError(ShrdzmGridMeterError):
    """Report an unusable HTTP or JSON response."""


class ShrdzmHttpStatusError(ShrdzmResponseError):
    """Report one non-successful HTTP status code."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"SHRDZM returned HTTP status {status_code}.")


@dataclass(frozen=True, slots=True)
class ShrdzmParsedValue:
    """Retain one configured numeric value and its raw representation."""

    mapping_key: str
    path: str
    value: float
    raw_value: object


@dataclass(frozen=True, slots=True)
class ShrdzmGridMeterReading:
    """Contain parsed values before canonical normalization."""

    values: tuple[ShrdzmParsedValue, ...]
    device_time: str | None
    diagnostics: tuple[str, ...]
    available_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DirectMetricSpec:
    """Describe a mapped value that converts directly to one metric."""

    mapping_key: str
    label: str
    metric: Metric


_MAPPED_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("grid_power_w", "grid power"),
    ("grid_import_power_w", "grid import power"),
    ("grid_export_power_w", "grid export power"),
    ("grid_import_total_kwh", "grid import total"),
    ("grid_export_total_kwh", "grid export total"),
    ("frequency_hz", "frequency"),
    ("phase_voltage_l1_v", "phase L1 voltage"),
    ("phase_voltage_l2_v", "phase L2 voltage"),
    ("phase_voltage_l3_v", "phase L3 voltage"),
    ("phase_current_l1_a", "phase L1 current"),
    ("phase_current_l2_a", "phase L2 current"),
    ("phase_current_l3_a", "phase L3 current"),
    ("phase_power_l1_w", "phase L1 power"),
    ("phase_power_l2_w", "phase L2 power"),
    ("phase_power_l3_w", "phase L3 power"),
)

_DIRECT_METRICS: Final[tuple[_DirectMetricSpec, ...]] = (
    _DirectMetricSpec("frequency_hz", "frequency", Metric.FREQUENCY),
    _DirectMetricSpec(
        "phase_voltage_l1_v",
        "phase L1 voltage",
        Metric.PHASE_VOLTAGE_L1,
    ),
    _DirectMetricSpec(
        "phase_voltage_l2_v",
        "phase L2 voltage",
        Metric.PHASE_VOLTAGE_L2,
    ),
    _DirectMetricSpec(
        "phase_voltage_l3_v",
        "phase L3 voltage",
        Metric.PHASE_VOLTAGE_L3,
    ),
    _DirectMetricSpec(
        "phase_current_l1_a",
        "phase L1 current",
        Metric.PHASE_CURRENT_L1,
    ),
    _DirectMetricSpec(
        "phase_current_l2_a",
        "phase L2 current",
        Metric.PHASE_CURRENT_L2,
    ),
    _DirectMetricSpec(
        "phase_current_l3_a",
        "phase L3 current",
        Metric.PHASE_CURRENT_L3,
    ),
    _DirectMetricSpec(
        "phase_power_l1_w",
        "phase L1 power",
        Metric.PHASE_POWER_L1,
    ),
    _DirectMetricSpec(
        "phase_power_l2_w",
        "phase L2 power",
        Metric.PHASE_POWER_L2,
    ),
    _DirectMetricSpec(
        "phase_power_l3_w",
        "phase L3 power",
        Metric.PHASE_POWER_L3,
    ),
)


class ShrdzmRestGridMeterAdapter:
    """Read one configured SHRDZM official grid meter over local REST."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        session: _HttpSession | None = None,
    ) -> None:
        """Create the adapter without performing network access."""

        self._config = dict(config)
        source_id = str(self._config.get("source_id") or "grid_meter_primary").strip()
        name = str(self._config.get("name") or "Offizieller Netzstromzähler").strip()
        adapter_name = str(self._config.get("adapter") or "shrdzm_rest").strip()

        self._source = MeasurementSource(
            source_id=source_id,
            name=name,
            device_type=adapter_name,
            roles=frozenset({MeasurementRole.GRID_METER}),
        )
        concrete_session = session if session is not None else requests.Session()
        self._session = cast(_HttpSession, concrete_session)

    @property
    def source(self) -> MeasurementSource:
        """Return stable metadata for the configured official meter."""

        return self._source

    def read_snapshot(self) -> DeviceSnapshot:
        """Read and normalize one SHRDZM ``getLastData`` response."""

        received_at = datetime.now().astimezone()
        if not bool(self._config.get("enabled", False)):
            return DeviceSnapshot(
                source_id=self._source.source_id,
                status=DeviceConnectionStatus.DISABLED,
                measurements=(),
                received_at=received_at,
                error="Grid meter is disabled.",
            )

        try:
            payload = self._read_last_data()
        except ShrdzmGridMeterError as exc:
            return _error_snapshot(
                source_id=self._source.source_id,
                received_at=received_at,
                error=exc,
            )

        raw_mapping = self._config.get("mapping")
        mapping = (
            cast(Mapping[str, Any], raw_mapping)
            if isinstance(raw_mapping, Mapping)
            else {}
        )
        reading = parse_shrdzm_grid_meter_payload(
            payload,
            mapping,
        )
        rest_config = _rest_config(self._config)
        energy_total_unit = (
            str(rest_config.get("energy_total_unit") or "auto").strip().lower()
        )

        normalized_values, normalization_diagnostics = _normalized_measurement_values(
            reading,
            mapping=mapping,
            direction_factor=normalize_direction_factor(
                self._config.get("direction_factor", 1)
            ),
            energy_total_unit=energy_total_unit,
        )
        measurements = tuple(
            _measurement(
                metric=metric,
                value=value,
                raw_value=raw_value,
                source_id=self._source.source_id,
                received_at=received_at,
                quality=quality,
            )
            for metric, value, quality, raw_value in normalized_values
        )

        diagnostics = [
            *reading.diagnostics,
            *normalization_diagnostics,
        ]
        if not any(
            measurement.metric is Metric.GRID_POWER for measurement in measurements
        ):
            diagnostics.append("Required grid power measurement is missing.")

        status = (
            DeviceConnectionStatus.ONLINE
            if measurements and not diagnostics
            else DeviceConnectionStatus.DEGRADED
        )
        return DeviceSnapshot(
            source_id=self._source.source_id,
            status=status,
            measurements=measurements,
            received_at=received_at,
            error=" ".join(dict.fromkeys(diagnostics)) or None,
            metadata=_snapshot_metadata(
                reading,
                endpoint=str(rest_config.get("endpoint") or "/getLastData"),
                energy_total_unit=energy_total_unit,
                include_paths=bool(
                    self._config.get(
                        "_include_diagnostic_paths",
                        False,
                    )
                ),
            ),
        )

    def _read_last_data(self) -> dict[str, Any]:
        """Request and decode the documented SHRDZM REST response."""

        host = str(self._config.get("host") or "").strip()
        if not host:
            raise ShrdzmTransportError("SHRDZM host is not configured.")

        scheme = str(self._config.get("scheme") or "http").strip()
        port = int(self._config.get("port") or 80)
        timeout = float(self._config.get("timeout_seconds") or 3)
        rest_config = _rest_config(self._config)
        endpoint = str(rest_config.get("endpoint") or "/getLastData").strip()
        endpoint = "/" + endpoint.lstrip("/")
        url = f"{scheme}://{host}:{port}{endpoint}"

        authentication_mode = (
            str(rest_config.get("authentication_mode") or "query").strip().lower()
        )
        username = str(self._config.get("username") or "").strip()
        password = str(self._config.get("password") or "")
        params: dict[str, str] = {}
        auth: tuple[str, str] | None = None

        if authentication_mode == "query" and (username or password):
            username_parameter = str(
                rest_config.get("username_parameter") or "user"
            ).strip()
            password_parameter = str(
                rest_config.get("password_parameter") or "password"
            ).strip()
            params[username_parameter] = username
            params[password_parameter] = password
        elif authentication_mode == "basic" and (username or password):
            auth = (username or "admin", password)

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=timeout,
                auth=auth,
            )
        except requests.Timeout as exc:
            raise ShrdzmTransportError("SHRDZM request timed out.") from exc
        except requests.ConnectionError as exc:
            raise ShrdzmTransportError("SHRDZM device is unreachable.") from exc
        except requests.RequestException as exc:
            raise ShrdzmTransportError("SHRDZM HTTP request failed.") from exc

        if response.status_code != 200:
            raise ShrdzmHttpStatusError(response.status_code)
        if not response.text.strip():
            raise ShrdzmResponseError("SHRDZM returned an empty response.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ShrdzmResponseError("SHRDZM returned invalid JSON.") from exc

        if not isinstance(payload, Mapping):
            raise ShrdzmResponseError("SHRDZM JSON root must be an object.")
        return {str(key): value for key, value in payload.items()}


_NormalizedMeasurementValue = tuple[
    Metric,
    float,
    MeasurementQuality,
    object | None,
]


def parse_shrdzm_grid_meter_payload(
    payload: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> ShrdzmGridMeterReading:
    """Extract configured numeric values from SHRDZM OBIS JSON."""

    values: list[ShrdzmParsedValue] = []
    diagnostics: list[str] = []

    for mapping_key, label in _MAPPED_FIELDS:
        configured_path = str(mapping.get(mapping_key) or "").strip()
        if not configured_path:
            continue

        found, raw_value = lookup_shrdzm_path(
            payload,
            configured_path,
        )
        if not found:
            diagnostics.append(
                f"Mapping path not found for {label}: {configured_path}."
            )
            continue

        numeric_value = _numeric_value(raw_value)
        if numeric_value is None:
            diagnostics.append(
                f"Mapped value is not numeric for {label}: {configured_path}."
            )
            continue

        values.append(
            ShrdzmParsedValue(
                mapping_key=mapping_key,
                path=configured_path,
                value=numeric_value,
                raw_value=raw_value,
            )
        )

    device_time = _device_time(payload)
    return ShrdzmGridMeterReading(
        values=tuple(values),
        device_time=device_time,
        diagnostics=tuple(diagnostics),
        available_paths=tuple(iter_scalar_paths(payload)),
    )


def lookup_shrdzm_path(
    payload: Mapping[str, Any],
    path: str,
) -> tuple[bool, object | None]:
    """Resolve exact OBIS keys before traversing a dotted path."""

    normalized = path.strip().strip(".")
    if not normalized:
        return False, None
    if normalized in payload:
        return True, payload[normalized]

    parts = normalized.split(".")
    current: object = payload
    for index, part in enumerate(parts):
        if not isinstance(current, Mapping):
            return False, None

        current_mapping = cast(Mapping[str, Any], current)
        remaining = ".".join(parts[index:])
        if remaining in current_mapping:
            return True, current_mapping[remaining]
        if part not in current_mapping:
            return False, None
        current = current_mapping[part]

    return True, current


def iter_scalar_paths(
    value: object,
    prefix: str = "",
) -> Sequence[str]:
    """Return deterministic paths for scalar JSON values."""

    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key in sorted(value, key=lambda item: str(item)):
            key = str(raw_key)
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(
                iter_scalar_paths(
                    value[raw_key],
                    child_prefix,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            paths.extend(iter_scalar_paths(child, child_prefix))
    elif prefix:
        paths.append(prefix)
    return tuple(paths)


def _normalized_measurement_values(
    reading: ShrdzmGridMeterReading,
    *,
    mapping: Mapping[str, Any],
    direction_factor: int,
    energy_total_unit: str,
) -> tuple[
    tuple[_NormalizedMeasurementValue, ...],
    tuple[str, ...],
]:
    """Convert SHRDZM raw values to canonical metrics and units."""

    parsed = {value.mapping_key: value for value in reading.values}
    values: list[_NormalizedMeasurementValue] = []
    diagnostics: list[str] = []

    reported_import = _non_negative_power(
        parsed.get("grid_import_power_w"),
        label="grid import power",
        diagnostics=diagnostics,
    )
    reported_export = _non_negative_power(
        parsed.get("grid_export_power_w"),
        label="grid export power",
        diagnostics=diagnostics,
    )
    reported_grid = parsed.get("grid_power_w")

    signed_grid_power: float | None = None
    signed_quality = MeasurementQuality.REPORTED
    signed_raw: object | None = None

    if reported_import is not None and reported_export is not None:
        signed_grid_power = (
            reported_import.value - reported_export.value
        ) * direction_factor
        signed_quality = MeasurementQuality.CALCULATED
        signed_raw = {
            "import": reported_import.raw_value,
            "export": reported_export.raw_value,
        }
    elif reported_grid is not None:
        signed_grid_power = reported_grid.value * direction_factor
        signed_raw = reported_grid.raw_value

    if signed_grid_power is not None:
        values.append(
            (
                Metric.GRID_POWER,
                signed_grid_power,
                signed_quality,
                signed_raw,
            )
        )

    import_value = _directional_power_value(
        reported=reported_import,
        calculated=(
            max(0.0, signed_grid_power) if signed_grid_power is not None else None
        ),
    )
    if import_value is not None:
        values.append(
            (
                Metric.GRID_IMPORT_POWER,
                import_value[0],
                import_value[1],
                import_value[2],
            )
        )

    export_value = _directional_power_value(
        reported=reported_export,
        calculated=(
            max(0.0, -signed_grid_power) if signed_grid_power is not None else None
        ),
    )
    if export_value is not None:
        values.append(
            (
                Metric.GRID_EXPORT_POWER,
                export_value[0],
                export_value[1],
                export_value[2],
            )
        )

    for mapping_key, metric, label in (
        (
            "grid_import_total_kwh",
            Metric.GRID_IMPORT_TOTAL,
            "grid import total",
        ),
        (
            "grid_export_total_kwh",
            Metric.GRID_EXPORT_TOTAL,
            "grid export total",
        ),
    ):
        parsed_total = parsed.get(mapping_key)
        if parsed_total is None:
            continue
        path = str(mapping.get(mapping_key) or "").strip()
        normalized_total, diagnostic = _energy_total_to_wh(
            parsed_total.value,
            path=path,
            configured_unit=energy_total_unit,
            label=label,
        )
        if diagnostic:
            diagnostics.append(diagnostic)
        if normalized_total is not None:
            values.append(
                (
                    metric,
                    normalized_total,
                    MeasurementQuality.REPORTED,
                    parsed_total.raw_value,
                )
            )

    for spec in _DIRECT_METRICS:
        parsed_value = parsed.get(spec.mapping_key)
        if parsed_value is None:
            continue
        values.append(
            (
                spec.metric,
                parsed_value.value,
                MeasurementQuality.REPORTED,
                parsed_value.raw_value,
            )
        )

    return tuple(values), tuple(diagnostics)


def _non_negative_power(
    value: ShrdzmParsedValue | None,
    *,
    label: str,
    diagnostics: list[str],
) -> ShrdzmParsedValue | None:
    """Reject negative directional magnitudes without inventing zero."""

    if value is None:
        return None
    if value.value < 0.0:
        diagnostics.append(f"Mapped {label} must not be negative.")
        return None
    return value


def _directional_power_value(
    *,
    reported: ShrdzmParsedValue | None,
    calculated: float | None,
) -> (
    tuple[
        float,
        MeasurementQuality,
        object | None,
    ]
    | None
):
    """Prefer a reported magnitude over a value derived from net power."""

    if reported is not None:
        return (
            reported.value,
            MeasurementQuality.REPORTED,
            reported.raw_value,
        )
    if calculated is None:
        return None
    return (
        calculated,
        MeasurementQuality.CALCULATED,
        None,
    )


def _energy_total_to_wh(
    value: float,
    *,
    path: str,
    configured_unit: str,
    label: str,
) -> tuple[float | None, str | None]:
    """Convert a configured SHRDZM energy counter to watt-hours."""

    unit = configured_unit.strip().lower()
    if unit == "auto":
        unit = _standard_obis_energy_unit(path) or ""
        if not unit:
            return (
                None,
                f"Energy unit is ambiguous for {label}: {path}. "
                "Configure wh, kwh, or mwh.",
            )

    factors = {
        "wh": 1.0,
        "kwh": 1000.0,
        "mwh": 1_000_000.0,
    }
    factor = factors.get(unit)
    if factor is None:
        return (
            None,
            f"Unsupported energy unit for {label}: {unit}.",
        )
    return value * factor, None


def _standard_obis_energy_unit(path: str) -> str | None:
    """Return the documented raw unit for standard SHRDZM totals."""

    normalized = path.strip().strip(".")
    if normalized.endswith(("1.8.0", "2.8.0")):
        return "wh"
    return None


def _measurement(
    *,
    metric: Metric,
    value: float,
    raw_value: object | None,
    source_id: str,
    received_at: datetime,
    quality: MeasurementQuality,
) -> Measurement:
    """Build one normalized SHRDZM grid-meter measurement."""

    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=MeasurementRole.GRID_METER,
        measured_at=received_at,
        received_at=received_at,
        quality=quality,
        raw_value=raw_value,
    )


def _numeric_value(value: object) -> float | None:
    """Parse a finite number without treating booleans as measurements."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            result = float(candidate)
        except ValueError:
            return None
    else:
        return None
    return result if math.isfinite(result) else None


def _device_time(payload: Mapping[str, Any]) -> str | None:
    """Return one non-secret device timestamp when present."""

    for key in ("timestamp", "UTC"):
        value = payload.get(key)
        if isinstance(value, (str, int, float)):
            candidate = str(value).strip()
            if candidate:
                return candidate
    return None


def _rest_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the normalized SHRDZM-specific configuration mapping."""

    value = config.get("shrdzm_rest")
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _snapshot_metadata(
    reading: ShrdzmGridMeterReading,
    *,
    endpoint: str,
    energy_total_unit: str,
    include_paths: bool,
) -> tuple[tuple[str, str], ...]:
    """Retain credential-free parser information for diagnostics."""

    metadata: list[tuple[str, str]] = [
        ("transport", "shrdzm_rest"),
        ("rest_endpoint", "/" + endpoint.lstrip("/")),
        ("energy_total_unit", energy_total_unit),
        (
            "available_scalar_path_count",
            str(len(reading.available_paths)),
        ),
    ]
    if reading.device_time:
        metadata.append(("device_time", reading.device_time))
    if include_paths:
        metadata.append(
            (
                "available_scalar_paths_json",
                json.dumps(
                    reading.available_paths,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
    return tuple(metadata)


def _error_snapshot(
    *,
    source_id: str,
    received_at: datetime,
    error: ShrdzmGridMeterError,
) -> DeviceSnapshot:
    """Create one credential-safe offline snapshot."""

    return DeviceSnapshot(
        source_id=source_id,
        status=DeviceConnectionStatus.OFFLINE,
        measurements=(),
        received_at=received_at,
        error=f"{type(error).__name__}: {error}",
    )
