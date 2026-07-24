"""Integration tests for collector-managed phase persistence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import requests
from solarinspector_core.adapters.shelly import ShellyReader
from solarinspector_core.config.defaults import DEFAULT_CONFIG
from solarinspector_core.persistence.database import Database
from solarinspector_core.services.collector import Collector


class StubConfigManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)


def _config(device_type: str) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    config["general"]["grid_power_source"] = "house_meter"
    config["house_meter"].update(
        {
            "enabled": True,
            "type": device_type,
            "host": "192.168.188.50",
            "measurement_role": "house_total",
            "phase_direction": {},
        }
    )
    config["solakon_meter"]["enabled"] = False
    config["solakon_one"]["enabled"] = False
    return config


def _collector(
    tmp_path: Path,
    device_type: str,
) -> tuple[Collector, Database, ShellyReader]:
    database = Database(tmp_path / f"{device_type}.db")
    collector = Collector(
        StubConfigManager(_config(device_type)),
        database,
    )
    reader = ShellyReader()
    collector.reader = reader
    collector._now = lambda: datetime.fromisoformat("2026-07-24T10:00:00+02:00")
    return collector, database, reader


def test_collector_persists_gen1_phases_with_aggregate_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector, database, reader = _collector(tmp_path, "shelly_3em_gen1")
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: {
            "total_power": 610.0,
            "emeters": [
                {"power": 100.0, "voltage": 229.0},
                {"power": 200.0, "voltage": 230.0},
                {"power": 300.0, "voltage": 231.0},
            ],
        },
    )

    sample = collector.collect_once()
    phase = database.latest_phase_sample()

    assert sample["id"] == 1
    assert sample["grid_power_w"] == pytest.approx(610.0)
    assert phase is not None
    assert phase["sample_id"] == sample["id"]
    assert phase["l1_power_w"] == pytest.approx(100.0)
    assert phase["l2_power_w"] == pytest.approx(200.0)
    assert phase["l3_power_w"] == pytest.approx(300.0)
    assert phase["phase_power_sum_w"] == pytest.approx(600.0)
    assert phase["device_status"] == "online"


def test_collector_does_not_create_phase_row_for_single_phase_meter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector, database, reader = _collector(
        tmp_path,
        "shelly_pm_mini_gen3",
    )
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: {
            "apower": 120.0,
            "voltage": 230.0,
        },
    )

    sample = collector.collect_once()

    assert sample["id"] == 1
    assert sample["grid_power_w"] == pytest.approx(120.0)
    assert database.latest_phase_sample() is None


def test_collector_persists_offline_multiphase_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector, database, reader = _collector(tmp_path, "shelly_pro_3em")

    def timeout(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise requests.Timeout("timed out")

    monkeypatch.setattr(reader, "_get_json", timeout)

    sample = collector.collect_once()
    phase = database.latest_phase_sample()

    assert sample["id"] == 1
    assert sample["house_ok"] == 0
    assert "Hausanschluss: timed out" in sample["error_text"]
    assert phase is not None
    assert phase["device_status"] == "offline"
    assert phase["error_text"] == "Timeout: timed out"
    assert phase["l1_power_w"] is None
