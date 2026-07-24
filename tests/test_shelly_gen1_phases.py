"""Tests for phase-level Shelly 3EM Gen 1 parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import solarinspector as si

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "shelly"


def _load_fixture(filename: str) -> dict[str, Any]:
    """Load one synthetic Shelly response fixture."""

    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def _read_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    *,
    direction_factor: int = 1,
    phase_direction: dict[str, int] | None = None,
) -> si.MeterReading:
    """Read one supplied Gen 1 response through the public reader API."""

    reader = si.ShellyReader()
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: payload,
    )
    return reader.read(
        {
            "type": "shelly_3em_gen1",
            "host": "192.168.188.50",
            "username": "",
            "password": "",
            "timeout_seconds": 3,
            "direction_factor": direction_factor,
            "phase_direction": phase_direction or {},
        },
        "house_meter",
    )


def test_gen1_exposes_complete_phase_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All documented Gen 1 phase values remain available after parsing."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("3em_gen1_normal.json"),
    )

    assert [phase.phase for phase in reading.phases] == ["l1", "l2", "l3"]

    l1, l2, l3 = reading.phases
    assert l1.power_w == pytest.approx(100.0)
    assert l1.voltage_v == pytest.approx(229.0)
    assert l1.current_a == pytest.approx(0.44)
    assert l1.power_factor == pytest.approx(0.99)
    assert l1.energy_total_wh == pytest.approx(1000.0)
    assert l1.returned_energy_total_wh == pytest.approx(10.0)
    assert l1.is_valid is None
    assert l1.power_available is True

    assert l2.power_w == pytest.approx(200.0)
    assert l2.voltage_v == pytest.approx(230.0)
    assert l2.current_a == pytest.approx(0.87)
    assert l2.power_factor == pytest.approx(0.98)

    assert l3.power_w == pytest.approx(300.0)
    assert l3.voltage_v == pytest.approx(231.0)
    assert l3.current_a == pytest.approx(1.3)
    assert l3.power_factor == pytest.approx(0.97)


def test_gen1_phase_direction_overrides_inherit_global_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing phase overrides inherit the validated global direction."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("3em_gen1_normal.json"),
        direction_factor=-1,
        phase_direction={"l1": 1, "l3": 1},
    )

    assert reading.power_w == pytest.approx(-610.0)
    assert [phase.power_w for phase in reading.phases] == pytest.approx(
        [100.0, -200.0, 300.0]
    )


def test_gen1_missing_phase_values_remain_explicitly_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial emeter still produces stable L1, L2, and L3 phase slots."""

    reading = _read_payload(
        monkeypatch,
        {
            "total_power": 15.0,
            "emeters": [
                {
                    "power": 15.0,
                    "voltage": 230.0,
                    "current": 0.07,
                    "pf": 0.95,
                    "is_valid": True,
                },
                {
                    "voltage": "not-a-number",
                    "is_valid": False,
                },
            ],
        },
    )

    assert reading.power_w == pytest.approx(15.0)
    assert len(reading.phases) == 3

    l1, l2, l3 = reading.phases
    assert l1.is_valid is True
    assert l1.power_available is True

    assert l2.power_w is None
    assert l2.voltage_v is None
    assert l2.current_a is None
    assert l2.power_factor is None
    assert l2.is_valid is False
    assert l2.power_available is False

    assert l3.phase == "l3"
    assert l3.power_w is None
    assert l3.is_valid is None
    assert l3.power_available is False


def test_gen1_phase_parsing_does_not_replace_reported_device_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing aggregate total remains authoritative in Block 05.3."""

    reading = _read_payload(
        monkeypatch,
        {
            "total_power": 999.0,
            "emeters": [
                {"power": 100.0},
                {"power": 200.0},
                {"power": 300.0},
            ],
        },
    )

    assert reading.power_w == pytest.approx(999.0)
    assert [phase.power_w for phase in reading.phases] == pytest.approx(
        [100.0, 200.0, 300.0]
    )
