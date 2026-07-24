"""Tests for phase-level Shelly Pro 3EM parsing."""

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
    """Read one supplied Pro 3EM response through the public reader API."""

    reader = si.ShellyReader()
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: payload,
    )
    return reader.read(
        {
            "type": "shelly_pro_3em",
            "host": "192.168.188.51",
            "username": "",
            "password": "",
            "timeout_seconds": 3,
            "direction_factor": direction_factor,
            "phase_direction": phase_direction or {},
        },
        "house_meter",
    )


def test_pro_exposes_complete_phase_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All instantaneous A, B, and C fields are retained as L1, L2, L3."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("pro_3em_normal.json"),
    )

    assert reading.power_w == pytest.approx(620.0)
    assert reading.is_valid is True
    assert reading.errors == ()
    assert [phase.phase for phase in reading.phases] == ["l1", "l2", "l3"]

    l1, l2, l3 = reading.phases
    assert l1.power_w == pytest.approx(100.0)
    assert l1.voltage_v == pytest.approx(229.0)
    assert l1.current_a == pytest.approx(1.0)
    assert l1.power_factor == pytest.approx(0.95)
    assert l1.frequency_hz == pytest.approx(49.99)
    assert l1.is_valid is True
    assert l1.errors == ()
    assert l1.flags == ()

    assert l2.power_w == pytest.approx(200.0)
    assert l2.frequency_hz == pytest.approx(50.0)
    assert l2.is_valid is True

    assert l3.power_w == pytest.approx(300.0)
    assert l3.frequency_hz == pytest.approx(50.01)
    assert l3.is_valid is True


def test_pro_invalid_numeric_fields_mark_only_the_phase_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed B values are diagnosed without discarding A or C values."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("pro_3em_invalid_phase.json"),
    )

    assert reading.power_w == pytest.approx(80.0)
    assert reading.is_valid is False

    l1, l2, l3 = reading.phases
    assert l1.is_valid is True
    assert l1.power_w == pytest.approx(100.0)

    assert l2.is_valid is False
    assert l2.power_w is None
    assert l2.voltage_v is None
    assert l2.current_a is None
    assert l2.power_factor is None
    assert l2.frequency_hz is None
    assert l2.errors == (
        "invalid_value:b_act_power",
        "invalid_value:b_voltage",
        "invalid_value:b_current",
        "invalid_value:b_pf",
        "invalid_value:b_freq",
    )

    assert l3.is_valid is True
    assert l3.power_w == pytest.approx(-20.0)


def test_pro_preserves_reported_phase_flags_and_device_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reported phase diagnostics and component errors remain observable."""

    reading = _read_payload(
        monkeypatch,
        {
            "a_current": 1.0,
            "a_voltage": 255.0,
            "a_act_power": 250.0,
            "a_pf": 0.95,
            "a_freq": 50.0,
            "a_errors": ["out_of_range:voltage"],
            "a_flags": ["overvoltage"],
            "b_act_power": 20.0,
            "c_act_power": 30.0,
            "total_act_power": 300.0,
            "errors": ["phase_sequence"],
        },
    )

    assert reading.power_w == pytest.approx(300.0)
    assert reading.is_valid is False
    assert reading.errors == ("phase_sequence",)

    l1, l2, l3 = reading.phases
    assert l1.is_valid is False
    assert l1.errors == ("out_of_range:voltage",)
    assert l1.flags == ("overvoltage",)
    assert l2.is_valid is True
    assert l3.is_valid is True


def test_pro_incomplete_response_keeps_three_unavailable_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty status still has stable phase identities and validity."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("pro_3em_incomplete.json"),
    )

    assert reading.power_w == 0.0
    assert reading.power_available is False
    assert reading.is_valid is False
    assert [phase.phase for phase in reading.phases] == ["l1", "l2", "l3"]
    assert all(phase.is_valid is None for phase in reading.phases)
    assert all(phase.power_w is None for phase in reading.phases)


def test_pro_phase_direction_is_applied_per_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local phase overrides do not replace the legacy aggregate direction."""

    reading = _read_payload(
        monkeypatch,
        _load_fixture("pro_3em_normal.json"),
        direction_factor=-1,
        phase_direction={"l1": 1, "l3": 1},
    )

    assert reading.power_w == pytest.approx(-620.0)
    assert [phase.power_w for phase in reading.phases] == pytest.approx(
        [100.0, -200.0, 300.0]
    )
