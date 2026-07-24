"""Tests for additive phase APIs and dashboard integration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import solarinspector as si
from solarinspector_core.web.api import (
    build_phase_dashboard_api_response,
    build_phase_live_api_response,
)


class PhaseDatabaseStub:
    """Provide deterministic phase rows and record requested ranges."""

    def __init__(self) -> None:
        self.latest: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []
        self.latest_source: str | None = None
        self.range_request: tuple[float, float, str] | None = None

    def latest_phase_sample(
        self,
        source_id: str = "house_meter",
    ) -> dict[str, Any] | None:
        self.latest_source = source_id
        return None if self.latest is None else dict(self.latest)

    def phase_rows_between(
        self,
        start_epoch: float,
        end_epoch: float,
        *,
        source_id: str = "house_meter",
    ) -> list[dict[str, Any]]:
        self.range_request = (start_epoch, end_epoch, source_id)
        return [dict(row) for row in self.rows]


def _timestamp(hour: int) -> float:
    timezone = datetime.now().astimezone().tzinfo
    return datetime(2026, 7, 24, hour, tzinfo=timezone).timestamp()


def _row(
    hour: int,
    *,
    l1: float | None = 100.0,
    l2: float | None = 200.0,
    l3: float | None = 300.0,
    l2_quality: str = "reported",
) -> dict[str, Any]:
    return {
        "sample_id": hour + 1,
        "source_id": "house_meter",
        "measurement_role": "distribution",
        "device_status": "online",
        "error_text": None,
        "ts_epoch": _timestamp(hour),
        "ts_local": f"2026-07-24T{hour:02d}:00:00+02:00",
        "measured_at": f"2026-07-24T{hour:02d}:00:00+02:00",
        "received_at": f"2026-07-24T{hour:02d}:00:00+02:00",
        "metadata_json": json.dumps({"device_errors": []}),
        "l1_power_w": l1,
        "l1_voltage_v": 229.0,
        "l1_current_a": 0.44,
        "l1_power_factor": 0.98,
        "l1_quality": "reported",
        "l2_power_w": l2,
        "l2_voltage_v": 230.0,
        "l2_current_a": 0.87,
        "l2_power_factor": 0.97,
        "l2_quality": l2_quality,
        "l3_power_w": l3,
        "l3_voltage_v": 231.0,
        "l3_current_a": 1.30,
        "l3_power_factor": 0.96,
        "l3_quality": "reported",
        "phase_power_available_count": 3,
        "phase_power_complete": 1,
        "phase_power_total_source": "device",
        "phase_power_sum_w": 600.0,
        "phase_power_spread_w": 200.0,
        "phase_power_share_l1_pct": 16.6667,
        "phase_power_share_l2_pct": 33.3333,
        "phase_power_share_l3_pct": 50.0,
        "phase_power_total_delta_w": 10.0,
        "phase_power_total_delta_pct": 1.6393,
        "phase_power_total_consistent": 1,
    }


def test_phase_live_returns_null_without_persisted_snapshot() -> None:
    database = PhaseDatabaseStub()

    assert build_phase_live_api_response(database) == {
        "source_id": "house_meter",
        "latest": None,
    }
    assert database.latest_source == "house_meter"


def test_phase_live_builds_nested_values_analysis_and_metadata() -> None:
    database = PhaseDatabaseStub()
    database.latest = _row(10, l2_quality="suspect")

    payload = build_phase_live_api_response(database, " house_meter ")
    latest = payload["latest"]

    assert latest["phases"]["l1"]["power_w"] == pytest.approx(100.0)
    assert latest["phases"]["l2"]["quality"] == "suspect"
    assert latest["analysis"]["complete"] is True
    assert latest["analysis"]["total_consistent"] is True
    assert latest["analysis"]["share_pct"]["l3"] == pytest.approx(50.0)
    assert latest["metadata"] == {"device_errors": []}


def test_phase_dashboard_averages_values_in_period_buckets() -> None:
    database = PhaseDatabaseStub()
    database.rows = [
        _row(10, l1=100.0, l2=200.0, l3=300.0),
        _row(10, l1=300.0, l2=400.0, l3=500.0),
        _row(11, l1=-50.0, l2=None, l3=150.0),
    ]

    payload = build_phase_dashboard_api_response(
        database,
        "day",
        "2026-07-24",
    )

    assert payload["labels"][10] == "10:00"
    assert payload["series"]["l1_power_w"][10] == pytest.approx(200.0)
    assert payload["series"]["l1_power_w"][11] == pytest.approx(-50.0)
    assert payload["series"]["l2_power_w"][11] is None
    assert payload["summary"]["sample_count"] == 3
    assert payload["summary"]["average_power_w"]["l3"] == pytest.approx(
        316.667,
    )


def test_phase_dashboard_counts_suspect_samples_and_spread() -> None:
    database = PhaseDatabaseStub()
    first = _row(9, l2_quality="suspect")
    second = _row(10)
    second["phase_power_spread_w"] = 350.0
    database.rows = [first, second]

    payload = build_phase_dashboard_api_response(
        database,
        "day",
        "2026-07-24",
    )

    assert payload["summary"]["suspect_sample_count"] == 1
    assert payload["summary"]["max_spread_w"] == pytest.approx(350.0)
    assert payload["summary"]["latest"]["sample_id"] == 11


def test_phase_dashboard_unknown_period_falls_back_and_forwards_source() -> None:
    database = PhaseDatabaseStub()

    payload = build_phase_dashboard_api_response(
        database,
        "quarter",
        "2026-07-24",
        "distribution_meter",
    )

    assert payload["period"] == "day"
    assert payload["source_id"] == "distribution_meter"
    assert database.range_request is not None
    assert database.range_request[2] == "distribution_meter"


def test_phase_live_route_uses_configured_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = PhaseDatabaseStub()
    database.latest = _row(10)
    monkeypatch.setattr(si, "database", database)
    si.app.config.update(TESTING=True)

    response = si.app.test_client().get("/api/phases/live?source=house_meter")

    assert response.status_code == 200
    assert response.get_json()["latest"]["phases"]["l3"]["power_w"] == 300.0


def test_phase_dashboard_route_returns_period_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = PhaseDatabaseStub()
    database.rows = [_row(10)]
    monkeypatch.setattr(si, "database", database)
    si.app.config.update(TESTING=True)

    response = si.app.test_client().get(
        "/api/phases/dashboard?period=day&anchor=2026-07-24"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["series"]["l1_power_w"][10] == 100.0


def test_dashboard_template_contains_phase_live_and_history_elements() -> None:
    root = Path(__file__).parents[1]
    template = (root / "app/templates/dashboard.html").read_text(encoding="utf-8")

    assert 'id="phase-panel"' in template
    assert 'id="phase-{{ phase }}-power"' in template
    assert 'id="phase-power-chart"' in template


def test_dashboard_script_loads_both_phase_endpoints() -> None:
    root = Path(__file__).parents[1]
    script = (root / "app/static/dashboard.js").read_text(encoding="utf-8")

    assert "/api/phases/live" in script
    assert "/api/phases/dashboard" in script
    assert "drawPhaseChart" in script
