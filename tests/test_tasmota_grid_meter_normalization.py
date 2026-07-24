"""Tests for canonical Tasmota grid-meter measurement semantics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.units import Unit


class FakeResponse:
    """Return one deterministic JSON payload."""

    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.text = "json"

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    """Return one supplied fake HTTP response."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.response = FakeResponse(payload)

    def get(
        self,
        _url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        assert params["cmnd"] == "Status 10"
        assert timeout > 0
        return self.response


def _config(
    *,
    direction_factor: int = 1,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG["grid_meter"])
    config.update(
        {
            "enabled": True,
            "host": "192.0.2.50",
            "direction_factor": direction_factor,
        }
    )
    if mapping is not None:
        config["mapping"].update(mapping)
    return config


def _snapshot(
    payload: dict[str, Any],
    *,
    direction_factor: int = 1,
    mapping: dict[str, str] | None = None,
):
    adapter = TasmotaHttpGridMeterAdapter(
        _config(
            direction_factor=direction_factor,
            mapping=mapping,
        ),
        session=FakeSession(payload),
    )
    snapshot = adapter.read_snapshot()
    values = {measurement.metric: measurement for measurement in snapshot.measurements}
    return snapshot, values


def _payload(
    *,
    power_w: object,
    import_total_kwh: object = 12.5,
    export_total_kwh: object = 1.25,
    **extra: object,
) -> dict[str, Any]:
    meter = {
        "Pges": power_w,
        "VerbrauchT0": import_total_kwh,
        "RetourT0": export_total_kwh,
        **extra,
    }
    return {
        "StatusSNS": {
            "Time": "2026-07-24T15:45:00",
            "strom": meter,
        }
    }


def test_positive_grid_power_is_import_positive() -> None:
    """Positive signed power means grid import after normalization."""

    snapshot, values = _snapshot(_payload(power_w=250.0))

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_POWER].value == 250.0
    assert values[Metric.GRID_IMPORT_POWER].value == 250.0
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0
    assert values[Metric.GRID_IMPORT_POWER].quality is MeasurementQuality.CALCULATED
    assert values[Metric.GRID_EXPORT_POWER].quality is MeasurementQuality.CALCULATED


def test_negative_grid_power_is_export_positive() -> None:
    """Negative signed power becomes a positive export magnitude."""

    _snapshot_value, values = _snapshot(_payload(power_w=-175.0))

    assert values[Metric.GRID_POWER].value == -175.0
    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 175.0


def test_direction_factor_is_applied_before_power_split() -> None:
    """The configured sign correction controls all derived powers."""

    _snapshot_value, values = _snapshot(
        _payload(power_w=125.0),
        direction_factor=-1,
    )

    assert values[Metric.GRID_POWER].value == -125.0
    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 125.0


def test_energy_totals_are_converted_from_kwh_to_wh() -> None:
    """Tasmota counters use canonical watt-hours in measurements."""

    _snapshot_value, values = _snapshot(
        _payload(
            power_w=0.0,
            import_total_kwh="12627.640",
            export_total_kwh="19.895",
        )
    )

    imported = values[Metric.GRID_IMPORT_TOTAL]
    exported = values[Metric.GRID_EXPORT_TOTAL]

    assert imported.value == pytest.approx(12_627_640.0)
    assert exported.value == pytest.approx(19_895.0)
    assert imported.unit is Unit.WATT_HOUR
    assert exported.unit is Unit.WATT_HOUR
    assert imported.quality is MeasurementQuality.REPORTED
    assert exported.quality is MeasurementQuality.REPORTED
    assert imported.raw_value == "12627.640"
    assert exported.raw_value == "19.895"


def test_direct_import_and_export_power_override_calculation() -> None:
    """Configured magnitude fields remain reported device values."""

    snapshot, values = _snapshot(
        _payload(
            power_w=-50.0,
            ImportP=12.0,
            ExportP=34.0,
        ),
        mapping={
            "grid_import_power_w": "StatusSNS.strom.ImportP",
            "grid_export_power_w": "StatusSNS.strom.ExportP",
        },
    )

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert values[Metric.GRID_POWER].value == -50.0
    assert values[Metric.GRID_IMPORT_POWER].value == 12.0
    assert values[Metric.GRID_EXPORT_POWER].value == 34.0
    assert values[Metric.GRID_IMPORT_POWER].quality is MeasurementQuality.REPORTED
    assert values[Metric.GRID_EXPORT_POWER].quality is MeasurementQuality.REPORTED


def test_direct_zero_power_is_not_replaced_by_calculation() -> None:
    """A reported zero remains authoritative over the signed total."""

    _snapshot_value, values = _snapshot(
        _payload(
            power_w=500.0,
            ImportP=0,
            ExportP=0,
        ),
        mapping={
            "grid_import_power_w": "StatusSNS.strom.ImportP",
            "grid_export_power_w": "StatusSNS.strom.ExportP",
        },
    )

    assert values[Metric.GRID_IMPORT_POWER].value == 0.0
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0
    assert values[Metric.GRID_IMPORT_POWER].quality is MeasurementQuality.REPORTED


def test_negative_reported_magnitude_is_rejected_explicitly() -> None:
    """Negative direct magnitudes are not silently converted or clamped."""

    snapshot, values = _snapshot(
        _payload(
            power_w=100.0,
            ImportP=-10.0,
        ),
        mapping={
            "grid_import_power_w": "StatusSNS.strom.ImportP",
        },
    )

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert Metric.GRID_IMPORT_POWER not in values
    assert values[Metric.GRID_EXPORT_POWER].value == 0.0
    assert "grid import power must not be negative" in (snapshot.error or "")


def test_each_metric_occurs_only_once_in_snapshot() -> None:
    """Canonical splitting cannot create duplicate metric identities."""

    snapshot, _values = _snapshot(_payload(power_w=0.0))

    metrics = [measurement.metric for measurement in snapshot.measurements]

    assert len(metrics) == len(set(metrics))
    assert set(metrics) == {
        Metric.GRID_POWER,
        Metric.GRID_IMPORT_POWER,
        Metric.GRID_EXPORT_POWER,
        Metric.GRID_IMPORT_TOTAL,
        Metric.GRID_EXPORT_TOTAL,
    }
