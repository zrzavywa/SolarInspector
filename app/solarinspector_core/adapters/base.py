"""Define the common contract for normalized measurement adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from solarinspector_core.models.device import DeviceSnapshot, MeasurementSource


@runtime_checkable
class MeasurementAdapter(Protocol):
    """Read one configured measurement source as normalized snapshots.

    Implementations remain device-specific internally, but expose stable source
    metadata and return only normalized ``DeviceSnapshot`` values. The protocol
    is structural, so adapters do not need to inherit from a framework base
    class.
    """

    @property
    def source(self) -> MeasurementSource:
        """Return stable metadata for the configured measurement source."""

        ...

    def read_snapshot(self) -> DeviceSnapshot:
        """Read the configured device once and return a normalized snapshot."""

        ...
