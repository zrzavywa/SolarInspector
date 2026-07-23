"""Tests for immutable metadata attached to device snapshots."""

from datetime import UTC, datetime

import pytest

from solarinspector_core.adapters.solakon import SolakonOneReading
from solarinspector_core.adapters.solakon_measurement import (
    SolakonMeasurementAdapter,
)
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)


class StubReader:
    """Return one deterministic Solakon reading."""

    def read(self, _config: dict[str, object]) -> SolakonOneReading:
        """Return device identity together with one numeric value."""

        return SolakonOneReading(
            model_name="Solakon ONE H3",
            serial_number="SYNTHETIC-001",
            status="Betrieb",
            total_pv_power_w=100.0,
        )


def test_snapshot_accepts_ordered_unique_metadata() -> None:
    snapshot = DeviceSnapshot(
        source_id="source",
        status=DeviceConnectionStatus.ONLINE,
        measurements=(),
        received_at=datetime(2026, 7, 23, tzinfo=UTC),
        metadata=(("model_name", "Example"), ("status", "Online")),
    )

    assert snapshot.metadata == (
        ("model_name", "Example"),
        ("status", "Online"),
    )


@pytest.mark.parametrize(
    "metadata",
    [
        (("", "value"),),
        (("key", ""),),
        (("key", "first"), ("key", "second")),
    ],
)
def test_snapshot_rejects_invalid_metadata(
    metadata: tuple[tuple[str, str], ...],
) -> None:
    with pytest.raises(ValueError, match="metadata"):
        DeviceSnapshot(
            source_id="source",
            status=DeviceConnectionStatus.ONLINE,
            measurements=(),
            received_at=datetime(2026, 7, 23, tzinfo=UTC),
            metadata=metadata,
        )


def test_solakon_adapter_preserves_non_numeric_device_details() -> None:
    adapter = SolakonMeasurementAdapter(
        source_id="solakon_one",
        name="Solakon ONE",
        config={"simulation": False},
        reader=StubReader(),
    )

    snapshot = adapter.read_snapshot()

    assert snapshot.metadata == (
        ("model_name", "Solakon ONE H3"),
        ("serial_number", "SYNTHETIC-001"),
        ("operating_status", "Betrieb"),
    )
