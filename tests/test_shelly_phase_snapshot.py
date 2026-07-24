"""Tests for normalized Shelly phase snapshots and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from solarinspector_core.adapters.shelly import (
    ShellyMeasurementAdapter,
    ShellyReader,
)
from solarinspector_core.models.device import DeviceConnectionStatus
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "shelly"


def _load_fixture(filename: str) -> dict[str, Any]:
    """Load one synthetic Shelly response fixture."""

    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def _read_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    *,
    device_type: str,
    payload: dict[str, Any],
    direction_factor: int = 1,
    phase_direction: dict[str, int] | None = None,
):
    """Read one GRID_METER snapshot through a real Shelly reader."""

    reader = ShellyReader()
    monkeypatch.setattr(reader, "_get_json", lambda _device, _path: payload)
    adapter = ShellyMeasurementAdapter(
        source_id="house-meter",
        name="House meter",
        device={
            "type": device_type,
            "host": "192.168.188.50",
            "username": "",
            "password": "",
            "timeout_seconds": 3,
            "direction_factor": direction_factor,
            "measurement_role": "house_total",
            "phase_direction": phase_direction or {},
        },
        role=MeasurementRole.GRID_METER,
        reader=reader,
    )
    return adapter, adapter.read_snapshot()


def _values(snapshot):
    """Index measurements by their role and metric."""

    return {
        (measurement.role, measurement.metric): measurement
        for measurement in snapshot.measurements
    }


def test_gen1_snapshot_emits_grid_total_and_house_phase_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregate compatibility and normalized phases coexist in one snapshot."""

    adapter, snapshot = _read_snapshot(
        monkeypatch,
        device_type="shelly_3em_gen1",
        payload=_load_fixture("3em_gen1_normal.json"),
    )
    values = _values(snapshot)
    metadata = dict(snapshot.metadata)

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert adapter.source.roles == frozenset(
        {MeasurementRole.GRID_METER, MeasurementRole.HOUSE_METER}
    )
    assert values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)].value == (
        pytest.approx(610.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L1)].value == (
        pytest.approx(100.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L2)].value == (
        pytest.approx(200.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L3)].value == (
        pytest.approx(300.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_VOLTAGE_L1)].value == (
        pytest.approx(229.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_CURRENT_L3)].value == (
        pytest.approx(1.3)
    )
    assert values[
        (MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_FACTOR_L2)
    ].value == pytest.approx(0.98)
    assert all(
        measurement.quality is MeasurementQuality.REPORTED
        for measurement in snapshot.measurements
    )

    assert metadata["measurement_role"] == "house_total"
    assert metadata["phase_power_available_count"] == "3"
    assert metadata["phase_power_complete"] == "true"
    assert metadata["phase_power_total_source"] == "device"
    assert float(metadata["phase_power_sum_w"]) == pytest.approx(600.0)
    assert float(metadata["phase_power_total_delta_w"]) == pytest.approx(10.0)
    assert metadata["phase_power_total_consistent"] == "true"
    assert float(metadata["phase_power_share_l3_pct"]) == pytest.approx(50.0)
    assert float(metadata["phase_power_spread_w"]) == pytest.approx(200.0)


def test_large_total_mismatch_degrades_snapshot_without_replacing_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The device total remains compatible while the mismatch is explicit."""

    _adapter, snapshot = _read_snapshot(
        monkeypatch,
        device_type="shelly_3em_gen1",
        payload={
            "total_power": 999.0,
            "emeters": [
                {"power": 100.0},
                {"power": 200.0},
                {"power": 300.0},
            ],
        },
    )
    values = _values(snapshot)
    metadata = dict(snapshot.metadata)

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert "differs from complete phase sum" in (snapshot.error or "")
    assert values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)].value == (
        pytest.approx(999.0)
    )
    assert (
        values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)].quality
        is MeasurementQuality.SUSPECT
    )
    assert metadata["phase_power_total_consistent"] == "false"
    assert float(metadata["phase_power_total_delta_w"]) == pytest.approx(399.0)


def test_pro_invalid_phase_keeps_partial_values_and_marks_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid phases survive while malformed phase B is diagnosed."""

    _adapter, snapshot = _read_snapshot(
        monkeypatch,
        device_type="shelly_pro_3em",
        payload=_load_fixture("pro_3em_invalid_phase.json"),
    )
    values = _values(snapshot)
    metadata = dict(snapshot.metadata)

    assert snapshot.status is DeviceConnectionStatus.DEGRADED
    assert "L2 is invalid" in (snapshot.error or "")
    assert values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)].value == (
        pytest.approx(80.0)
    )
    assert (
        values[(MeasurementRole.GRID_METER, Metric.GRID_POWER)].quality
        is MeasurementQuality.SUSPECT
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L1)].value == (
        pytest.approx(100.0)
    )
    assert values[(MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L3)].value == (
        pytest.approx(-20.0)
    )
    assert (MeasurementRole.HOUSE_METER, Metric.PHASE_POWER_L2) not in values
    assert metadata["phase_power_available_count"] == "2"
    assert metadata["phase_power_complete"] == "false"
    assert metadata["phase_power_total_source"] == "phase_sum"
    assert "phase_power_total_consistent" not in metadata


def test_phase_direction_overrides_skip_incomparable_total_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured phase sign corrections do not create a false mismatch."""

    _adapter, snapshot = _read_snapshot(
        monkeypatch,
        device_type="shelly_3em_gen1",
        payload=_load_fixture("3em_gen1_normal.json"),
        direction_factor=-1,
        phase_direction={"l1": 1, "l3": 1},
    )
    metadata = dict(snapshot.metadata)

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert metadata["phase_power_total_source"] == "device_uncompared"
    assert "phase_power_total_delta_w" not in metadata
    assert "phase_power_total_consistent" not in metadata


def test_phase_fallback_sum_is_not_misrepresented_as_device_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locally calculated fallback power has no artificial delta check."""

    _adapter, snapshot = _read_snapshot(
        monkeypatch,
        device_type="shelly_3em_gen1",
        payload=_load_fixture("3em_gen1_negative_phase.json"),
    )
    metadata = dict(snapshot.metadata)

    assert snapshot.status is DeviceConnectionStatus.ONLINE
    assert metadata["phase_power_total_source"] == "phase_sum"
    assert float(metadata["phase_power_sum_w"]) == pytest.approx(120.0)
    assert "phase_power_total_delta_w" not in metadata
    assert "phase_power_total_consistent" not in metadata
