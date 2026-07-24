#!/usr/bin/env python3
"""Run a bounded local Hichi/Tasmota stability check."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from solarinspector_core.adapters.tasmota_grid_meter import (  # noqa: E402
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.grid_meter import (  # noqa: E402
    DEFAULT_GRID_METER_CONFIG,
    normalize_grid_meter_config,
)
from solarinspector_core.models.device import (  # noqa: E402
    DeviceConnectionStatus,
)
from solarinspector_core.models.metrics import Metric  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Poll a local Hichi/Tasmota grid meter and write a credential-free summary."
        )
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=float(
            os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_SOAK_MINUTES",
                "120",
            )
        ),
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(
            os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_INTERVAL",
                "5",
            )
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def environment_config() -> dict[str, Any]:
    host = os.environ.get(
        "SOLARINSPECTOR_TEST_TASMOTA_HOST",
        "",
    ).strip()
    if not host:
        raise SystemExit("SOLARINSPECTOR_TEST_TASMOTA_HOST is not set.")

    config = deepcopy(DEFAULT_GRID_METER_CONFIG)
    config.update(
        {
            "enabled": True,
            "host": host,
            "port": os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_PORT",
                "80",
            ),
            "scheme": os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_SCHEME",
                "http",
            ),
            "username": os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_USERNAME",
                "",
            ),
            "password": os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_PASSWORD",
                "",
            ),
            "timeout_seconds": os.environ.get(
                "SOLARINSPECTOR_TEST_TASMOTA_TIMEOUT",
                "3",
            ),
        }
    )
    return normalize_grid_meter_config(config)


def metric_value(
    snapshot: Any,
    metric: Metric,
) -> float | None:
    for measurement in snapshot.measurements:
        if measurement.metric is metric:
            return float(measurement.value)
    return None


def main() -> int:
    args = parse_args()
    if args.duration_minutes <= 0:
        raise SystemExit("--duration-minutes must be positive.")
    if args.interval_seconds < 0.2:
        raise SystemExit("--interval-seconds must be at least 0.2.")

    config = environment_config()
    adapter = TasmotaHttpGridMeterAdapter(config)
    started_at = datetime.now().astimezone()
    deadline = time.monotonic() + (args.duration_minutes * 60.0)
    output = args.output or (
        Path(".phase06-capture")
        / ("tasmota-soak-" + started_at.strftime("%Y%m%d-%H%M%S") + ".json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    counts = {status.value: 0 for status in DeviceConnectionStatus}
    successful = 0
    errors: list[str] = []
    first_import_total: float | None = None
    last_import_total: float | None = None
    first_export_total: float | None = None
    last_export_total: float | None = None
    minimum_power: float | None = None
    maximum_power: float | None = None
    poll_durations: list[float] = []

    tracemalloc.start()
    while time.monotonic() < deadline:
        poll_started = time.monotonic()
        snapshot = adapter.read_snapshot()
        poll_durations.append(time.monotonic() - poll_started)
        counts[snapshot.status.value] += 1

        if (
            snapshot.status
            in {
                DeviceConnectionStatus.ONLINE,
                DeviceConnectionStatus.DEGRADED,
            }
            and snapshot.measurements
        ):
            successful += 1

        if snapshot.error and snapshot.error not in errors:
            errors.append(snapshot.error)
            errors = errors[-20:]

        power = metric_value(snapshot, Metric.GRID_POWER)
        if power is not None:
            minimum_power = (
                power if minimum_power is None else min(minimum_power, power)
            )
            maximum_power = (
                power if maximum_power is None else max(maximum_power, power)
            )

        import_total = metric_value(
            snapshot,
            Metric.GRID_IMPORT_TOTAL,
        )
        export_total = metric_value(
            snapshot,
            Metric.GRID_EXPORT_TOTAL,
        )
        if import_total is not None:
            if first_import_total is None:
                first_import_total = import_total
            last_import_total = import_total
        if export_total is not None:
            if first_export_total is None:
                first_export_total = export_total
            last_export_total = export_total

        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(args.interval_seconds, remaining))

    current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    finished_at = datetime.now().astimezone()

    report = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_minutes": args.duration_minutes,
        "interval_seconds": args.interval_seconds,
        "source_id": config["source_id"],
        "adapter": config["adapter"],
        "poll_count": sum(counts.values()),
        "successful_poll_count": successful,
        "status_counts": counts,
        "poll_seconds": {
            "minimum": (min(poll_durations) if poll_durations else None),
            "maximum": (max(poll_durations) if poll_durations else None),
            "average": (
                sum(poll_durations) / len(poll_durations) if poll_durations else None
            ),
        },
        "grid_power_w": {
            "minimum": minimum_power,
            "maximum": maximum_power,
        },
        "grid_import_total_wh": {
            "first": first_import_total,
            "last": last_import_total,
        },
        "grid_export_total_wh": {
            "first": first_export_total,
            "last": last_export_total,
        },
        "python_tracemalloc_bytes": {
            "current": current_memory,
            "peak": peak_memory,
        },
        "distinct_errors": errors,
    }
    output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
