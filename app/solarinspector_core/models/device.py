"""Define configured measurement sources and device read snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole


class DeviceConnectionStatus(str, Enum):
    """Describe the connection status of a configured measurement device."""

    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MeasurementSource:
    """Describe the stable identity and roles of a configured source."""

    source_id: str
    name: str
    device_type: str
    roles: frozenset[MeasurementRole]

    def __post_init__(self) -> None:
        """Validate the minimal source identity contract."""

        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.device_type.strip():
            raise ValueError("device_type must not be empty")
        if not self.roles:
            raise ValueError("roles must not be empty")


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Contain measurements and connection status from one device read."""

    source_id: str
    status: DeviceConnectionStatus
    measurements: tuple[Measurement, ...]
    received_at: datetime
    error: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Validate snapshot consistency without applying quality decisions."""

        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        if (
            self.status
            in {
                DeviceConnectionStatus.OFFLINE,
                DeviceConnectionStatus.DISABLED,
            }
            and self.measurements
        ):
            raise ValueError(
                f"{self.status.value} snapshots cannot contain measurements"
            )

        metadata_keys: set[str] = set()
        for key, value in self.metadata:
            if not key.strip():
                raise ValueError("snapshot metadata keys must not be empty")
            if not value.strip():
                raise ValueError("snapshot metadata values must not be empty")
            if key in metadata_keys:
                raise ValueError("snapshot metadata keys must be unique")
            metadata_keys.add(key)

        identities: set[tuple[MeasurementRole, Metric]] = set()
        for measurement in self.measurements:
            if measurement.source_id != self.source_id:
                raise ValueError("snapshot and measurement source_id must match")
            identity = (measurement.role, measurement.metric)
            if identity in identities:
                raise ValueError(
                    "snapshot cannot contain duplicate role and metric measurements"
                )
            identities.add(identity)
