"""Read official grid-meter values from Tasmota over local HTTP."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, cast

import requests

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
    """Describe the requests session operation used by the adapter."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> _HttpResponse:
        """Perform one HTTP GET request."""


class TasmotaGridMeterError(RuntimeError):
    """Base class for controlled Tasmota grid-meter failures."""


class TasmotaTransportError(TasmotaGridMeterError):
    """Report local network or timeout failures without exposing credentials."""


class TasmotaResponseError(TasmotaGridMeterError):
    """Report unusable HTTP or JSON responses."""


class TasmotaHttpStatusError(TasmotaResponseError):
    """Report one non-successful HTTP status code."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Tasmota returned HTTP status {status_code}.")


@dataclass(frozen=True, slots=True)
class TasmotaGridMeterReading:
    """Contain parsed raw core values before Phase-06 normalization."""

    grid_power_w: float | None
    grid_import_total_kwh: float | None
    grid_export_total_kwh: float | None
    raw_grid_power: object | None
    raw_grid_import_total: object | None
    raw_grid_export_total: object | None
    device_time: str | None
    diagnostics: tuple[str, ...]
    available_paths: tuple[str, ...]


_CORE_MAPPING: Final[tuple[tuple[str, str], ...]] = (
    ("grid_power_w", "grid power"),
    ("grid_import_total_kwh", "grid import total"),
    ("grid_export_total_kwh", "grid export total"),
)


class TasmotaHttpGridMeterAdapter:
    """Read one configured Hichi/Tasmota official grid meter."""

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
        adapter_name = str(self._config.get("adapter") or "tasmota_http").strip()

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
        """Return stable metadata for the configured official grid meter."""

        return self._source

    def read_snapshot(self) -> DeviceSnapshot:
        """Read and parse one Tasmota ``Status 10`` response."""

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
            payload = self._read_status_10()
        except TasmotaGridMeterError as exc:
            return _error_snapshot(
                source_id=self._source.source_id,
                received_at=received_at,
                error=exc,
            )

        mapping = self._config.get("mapping")
        normalized_mapping = (
            cast(Mapping[str, Any], mapping) if isinstance(mapping, Mapping) else {}
        )
        reading = parse_tasmota_grid_meter_payload(
            payload,
            normalized_mapping,
        )

        measurements: tuple[Measurement, ...] = ()
        if reading.grid_power_w is not None:
            measurements = (
                Measurement(
                    metric=Metric.GRID_POWER,
                    value=reading.grid_power_w,
                    unit=unit_for_metric(Metric.GRID_POWER),
                    source_id=self._source.source_id,
                    role=MeasurementRole.GRID_METER,
                    measured_at=received_at,
                    received_at=received_at,
                    quality=MeasurementQuality.REPORTED,
                    raw_value=reading.raw_grid_power,
                ),
            )

        diagnostics = list(reading.diagnostics)
        if reading.grid_power_w is None:
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
            metadata=_snapshot_metadata(reading),
        )

    def _read_status_10(self) -> dict[str, Any]:
        """Request and decode the Tasmota smart-meter status payload."""

        host = str(self._config.get("host") or "").strip()
        if not host:
            raise TasmotaTransportError("Tasmota host is not configured.")

        scheme = str(self._config.get("scheme") or "http").strip()
        port = int(self._config.get("port") or 80)
        timeout = float(self._config.get("timeout_seconds") or 3)
        url = f"{scheme}://{host}:{port}/cm"

        params = {"cmnd": "Status 10"}
        username = str(self._config.get("username") or "").strip()
        password = str(self._config.get("password") or "")
        if username or password:
            params["user"] = username or "admin"
            params["password"] = password

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise TasmotaTransportError("Tasmota request timed out.") from exc
        except requests.ConnectionError as exc:
            raise TasmotaTransportError("Tasmota device is unreachable.") from exc
        except requests.RequestException as exc:
            raise TasmotaTransportError("Tasmota HTTP request failed.") from exc

        if response.status_code != 200:
            raise TasmotaHttpStatusError(response.status_code)
        if not response.text.strip():
            raise TasmotaResponseError("Tasmota returned an empty response.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise TasmotaResponseError("Tasmota returned invalid JSON.") from exc

        if not isinstance(payload, Mapping):
            raise TasmotaResponseError("Tasmota JSON root must be an object.")
        return {str(key): value for key, value in payload.items()}


def parse_tasmota_grid_meter_payload(
    payload: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> TasmotaGridMeterReading:
    """Extract configured raw core values from nested Tasmota JSON."""

    parsed: dict[str, float | None] = {}
    raw_values: dict[str, object | None] = {}
    diagnostics: list[str] = []

    for mapping_key, label in _CORE_MAPPING:
        configured_path = str(mapping.get(mapping_key) or "").strip()
        if not configured_path:
            parsed[mapping_key] = None
            raw_values[mapping_key] = None
            continue

        found, raw_value = lookup_tasmota_path(
            payload,
            configured_path,
        )
        raw_values[mapping_key] = raw_value if found else None
        if not found:
            parsed[mapping_key] = None
            diagnostics.append(
                f"Mapping path not found for {label}: {configured_path}."
            )
            continue

        numeric_value = _numeric_value(raw_value)
        parsed[mapping_key] = numeric_value
        if numeric_value is None:
            diagnostics.append(
                f"Mapped value is not numeric for {label}: {configured_path}."
            )

    device_time_found, raw_device_time = lookup_tasmota_path(
        payload,
        "StatusSNS.Time",
    )
    device_time = (
        str(raw_device_time).strip()
        if device_time_found
        and isinstance(raw_device_time, (str, int, float))
        and str(raw_device_time).strip()
        else None
    )

    return TasmotaGridMeterReading(
        grid_power_w=parsed["grid_power_w"],
        grid_import_total_kwh=parsed["grid_import_total_kwh"],
        grid_export_total_kwh=parsed["grid_export_total_kwh"],
        raw_grid_power=raw_values["grid_power_w"],
        raw_grid_import_total=raw_values["grid_import_total_kwh"],
        raw_grid_export_total=raw_values["grid_export_total_kwh"],
        device_time=device_time,
        diagnostics=tuple(diagnostics),
        available_paths=tuple(iter_scalar_paths(payload)),
    )


def lookup_tasmota_path(
    payload: Mapping[str, Any],
    path: str,
) -> tuple[bool, object | None]:
    """Resolve a simple dotted path with support for dotted OBIS keys."""

    normalized = path.strip().strip(".")
    if not normalized:
        return False, None

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
            paths.extend(iter_scalar_paths(value[raw_key], child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            paths.extend(iter_scalar_paths(child, child_prefix))
    elif prefix:
        paths.append(prefix)
    return tuple(paths)


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


def _snapshot_metadata(
    reading: TasmotaGridMeterReading,
) -> tuple[tuple[str, str], ...]:
    """Retain non-secret parser information for later diagnostics."""

    metadata: list[tuple[str, str]] = [
        ("transport", "tasmota_http"),
        ("tasmota_command", "Status 10"),
        (
            "available_scalar_path_count",
            str(len(reading.available_paths)),
        ),
    ]
    if reading.device_time:
        metadata.append(("device_time", reading.device_time))
    if reading.grid_import_total_kwh is not None:
        metadata.append(
            (
                "raw_grid_import_total_kwh",
                _metadata_number(reading.grid_import_total_kwh),
            )
        )
    if reading.grid_export_total_kwh is not None:
        metadata.append(
            (
                "raw_grid_export_total_kwh",
                _metadata_number(reading.grid_export_total_kwh),
            )
        )
    return tuple(metadata)


def _metadata_number(value: float) -> str:
    """Format one finite number compactly for string-only metadata."""

    formatted = f"{value:.12f}".rstrip("0").rstrip(".")
    return formatted if formatted and formatted != "-0" else "0"


def _error_snapshot(
    *,
    source_id: str,
    received_at: datetime,
    error: TasmotaGridMeterError,
) -> DeviceSnapshot:
    """Create one credential-safe offline snapshot."""

    return DeviceSnapshot(
        source_id=source_id,
        status=DeviceConnectionStatus.OFFLINE,
        measurements=(),
        received_at=received_at,
        error=f"{type(error).__name__}: {error}",
    )
