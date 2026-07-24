"""Contract tests for normalized measurement adapters."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes.measurement_adapter import FakeMeasurementAdapter
from solarinspector_core.adapters.base import MeasurementAdapter
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
    MeasurementSource,
)
from solarinspector_core.models.roles import MeasurementRole

NOW = datetime(2026, 7, 23, 18, 30, tzinfo=UTC)


def make_source(source_id: str = "plant_meter_shelly") -> MeasurementSource:
    """Build source metadata for focused adapter contract tests."""

    return MeasurementSource(
        source_id=source_id,
        name="Plant meter",
        device_type="shelly_pm_mini_gen3",
        roles=frozenset({MeasurementRole.PLANT_METER}),
    )


def make_snapshot(
    source_id: str = "plant_meter_shelly",
    *,
    status: DeviceConnectionStatus = DeviceConnectionStatus.ONLINE,
) -> DeviceSnapshot:
    """Build a valid snapshot without device-specific values."""

    return DeviceSnapshot(
        source_id=source_id,
        status=status,
        measurements=(),
        received_at=NOW,
    )


def test_fake_adapter_satisfies_runtime_protocol() -> None:
    adapter = FakeMeasurementAdapter(make_source(), (make_snapshot(),))

    assert isinstance(adapter, MeasurementAdapter)
    assert adapter.source.source_id == "plant_meter_shelly"


def test_adapter_returns_snapshots_in_configured_order() -> None:
    online = make_snapshot()
    degraded = make_snapshot(status=DeviceConnectionStatus.DEGRADED)
    adapter = FakeMeasurementAdapter(make_source(), (online, degraded))

    assert adapter.read_snapshot() is online
    assert adapter.read_snapshot() is degraded
    assert adapter.read_count == 2


def test_adapter_reports_exhausted_fake_snapshot_sequence() -> None:
    adapter = FakeMeasurementAdapter(make_source(), ())

    with pytest.raises(RuntimeError, match="no fake snapshot"):
        adapter.read_snapshot()

    assert adapter.read_count == 0


def test_fake_adapter_rejects_snapshot_from_another_source() -> None:
    with pytest.raises(ValueError, match="source_id"):
        FakeMeasurementAdapter(
            make_source("configured_source"),
            (make_snapshot("other_source"),),
        )
