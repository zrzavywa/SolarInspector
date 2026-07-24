"""Optional integration test for a real local Hichi/Tasmota meter."""

from __future__ import annotations

import os
import time
from copy import deepcopy

import pytest
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.grid_meter import (
    DEFAULT_GRID_METER_CONFIG,
    normalize_grid_meter_config,
)
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
)
from solarinspector_core.models.metrics import Metric

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.integration,
]


def _environment_config() -> dict[str, object]:
    host = os.environ.get(
        "SOLARINSPECTOR_TEST_TASMOTA_HOST",
        "",
    ).strip()
    if not host:
        pytest.skip("SOLARINSPECTOR_TEST_TASMOTA_HOST is not set.")

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


def test_real_tasmota_grid_meter_is_repeatable() -> None:
    """Read several valid snapshots without exposing credentials."""

    config = _environment_config()
    samples = max(
        2,
        min(
            10,
            int(
                os.environ.get(
                    "SOLARINSPECTOR_TEST_TASMOTA_SAMPLES",
                    "3",
                )
            ),
        ),
    )
    interval = max(
        0.0,
        min(
            5.0,
            float(
                os.environ.get(
                    "SOLARINSPECTOR_TEST_TASMOTA_INTERVAL",
                    "0.2",
                )
            ),
        ),
    )
    timeout = float(config["timeout_seconds"])
    adapter = TasmotaHttpGridMeterAdapter(config)
    snapshots = []
    started = time.monotonic()

    for index in range(samples):
        snapshot = adapter.read_snapshot()
        snapshots.append(snapshot)

        assert snapshot.status in {
            DeviceConnectionStatus.ONLINE,
            DeviceConnectionStatus.DEGRADED,
        }, snapshot.error
        assert snapshot.measurements
        assert snapshot.received_at.tzinfo is not None

        metrics = {measurement.metric for measurement in snapshot.measurements}
        assert metrics.intersection(
            {
                Metric.GRID_POWER,
                Metric.GRID_IMPORT_TOTAL,
                Metric.GRID_EXPORT_TOTAL,
            }
        )

        password = str(config.get("password") or "")
        username = str(config.get("username") or "")
        representation = repr(snapshot)
        if password:
            assert password not in representation
        if username and username != "admin":
            assert username not in representation

        if index + 1 < samples:
            time.sleep(interval)

    elapsed = time.monotonic() - started
    assert elapsed <= samples * (timeout + 2.0) + (samples - 1) * interval
    assert len(snapshots) == samples
