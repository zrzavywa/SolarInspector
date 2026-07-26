#!/usr/bin/env python3
"""Measure validation-cycle runtime, bounded history, and Python allocations."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def parse_args() -> argparse.Namespace:
    """Parse deterministic benchmark options."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=5000)
    parser.add_argument("--max-average-ms", type=float, default=5.0)
    parser.add_argument("--max-peak-mib", type=float, default=64.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("validation-replay-performance.json"),
    )
    return parser.parse_args()


def _snapshot(index: int, at: datetime) -> DeviceSnapshot:
    measurement = Measurement(
        metric=Metric.PLANT_AC_POWER,
        value=float(index % 801),
        unit=unit_for_metric(Metric.PLANT_AC_POWER),
        source_id="solakon_one",
        role=MeasurementRole.SOLAR_SYSTEM,
        measured_at=at,
        received_at=at,
        quality=MeasurementQuality.REPORTED,
        raw_value=index % 801,
    )
    return DeviceSnapshot(
        source_id="solakon_one",
        status=DeviceConnectionStatus.ONLINE,
        measurements=(measurement,),
        received_at=at,
    )


def main() -> int:
    """Run a no-wait validation benchmark and write one JSON report."""

    args = parse_args()
    if args.cycles < 1:
        raise SystemExit("--cycles must be at least 1")
    if args.max_average_ms <= 0 or args.max_peak_mib <= 0:
        raise SystemExit("performance limits must be greater than zero")

    bridge = CollectorValidationBridge()
    config = {
        "validation": {
            "enabled": True,
            "profiles": {},
            "sources": {},
        }
    }
    base_time = datetime(2026, 7, 25, 14, 0, tzinfo=timezone.utc)
    event_count = 0
    accepted_count = 0

    tracemalloc.start()
    started = time.perf_counter()
    for index in range(args.cycles):
        at = base_time + timedelta(seconds=index)
        result = bridge.validate_cycle(
            (_snapshot(index, at),),
            config=config,
            now=at,
        )
        event_count += len(result.events)
        accepted_count += sum(
            len(snapshot.measurements) for snapshot in result.snapshots
        )
    elapsed_seconds = time.perf_counter() - started
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    average_ms = elapsed_seconds * 1000.0 / args.cycles
    peak_mib = peak_bytes / 1024.0 / 1024.0
    report = {
        "cycles": args.cycles,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "average_cycle_ms": round(average_ms, 6),
        "accepted_measurements": accepted_count,
        "validation_events": event_count,
        "history_size": len(bridge._history),
        "tracemalloc_current_mib": round(
            current_bytes / 1024.0 / 1024.0,
            6,
        ),
        "tracemalloc_peak_mib": round(peak_mib, 6),
        "limits": {
            "max_average_ms": args.max_average_ms,
            "max_peak_mib": args.max_peak_mib,
        },
        "passed": (
            average_ms <= args.max_average_ms
            and peak_mib <= args.max_peak_mib
            and len(bridge._history) <= 512
            and event_count == 0
            and accepted_count == args.cycles
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
