"""Guard bounded validation history and non-blocking replay performance."""

from __future__ import annotations

import time
import tracemalloc
from datetime import datetime, timedelta, timezone

from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.validation import CollectorValidationBridge

BASE_TIME = datetime(2026, 7, 25, 14, 0, tzinfo=timezone.utc)


def _snapshot(index: int) -> DeviceSnapshot:
    now = BASE_TIME + timedelta(seconds=index)
    measurement = Measurement(
        metric=Metric.PLANT_AC_POWER,
        value=float(index % 801),
        unit=unit_for_metric(Metric.PLANT_AC_POWER),
        source_id="solakon_one",
        role=MeasurementRole.SOLAR_SYSTEM,
        measured_at=now,
        received_at=now,
        quality=MeasurementQuality.REPORTED,
        raw_value=index % 801,
    )
    return DeviceSnapshot(
        source_id="solakon_one",
        status=DeviceConnectionStatus.ONLINE,
        measurements=(measurement,),
        received_at=now,
    )


def test_validation_replay_stays_bounded_and_non_blocking() -> None:
    bridge = CollectorValidationBridge()
    config = {
        "validation": {
            "enabled": True,
            "profiles": {},
            "sources": {},
        }
    }
    cycle_count = 750

    tracemalloc.start()
    started = time.perf_counter()
    for index in range(cycle_count):
        now = BASE_TIME + timedelta(seconds=index)
        result = bridge.validate_cycle(
            (_snapshot(index),),
            config=config,
            now=now,
        )
        assert result.events == ()
        assert len(result.snapshots[0].measurements) == 1
    elapsed = time.perf_counter() - started
    _current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert elapsed < 5.0
    assert peak_memory < 32 * 1024 * 1024
    assert len(bridge._history) <= 512
