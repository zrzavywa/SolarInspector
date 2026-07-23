"""Fake implementation of the normalized measurement adapter contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from solarinspector_core.models.device import DeviceSnapshot, MeasurementSource


@dataclass(slots=True)
class FakeMeasurementAdapter:
    """Return configured snapshots in order without device communication."""

    source: MeasurementSource
    snapshots: tuple[DeviceSnapshot, ...]
    read_count: int = field(default=0, init=False)
    _next_snapshot_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Reject fake snapshots that belong to a different source."""

        if any(
            snapshot.source_id != self.source.source_id for snapshot in self.snapshots
        ):
            raise ValueError("fake snapshots must match the adapter source_id")

    def read_snapshot(self) -> DeviceSnapshot:
        """Return the next configured snapshot and count the read operation."""

        if self._next_snapshot_index >= len(self.snapshots):
            raise RuntimeError("no fake snapshot configured for the next read")

        snapshot = self.snapshots[self._next_snapshot_index]
        self._next_snapshot_index += 1
        self.read_count += 1
        return snapshot
