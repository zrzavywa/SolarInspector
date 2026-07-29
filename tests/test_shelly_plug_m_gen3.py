"""Tests for the read-only Shelly Plug M Gen3 adapter."""

from __future__ import annotations

import math

from zrzavy_energy_monitor_core.adapters.shelly import ShellyReader


def _reader(payload: dict[str, object]) -> ShellyReader:
    reader = ShellyReader()
    reader._get_json = lambda _device, _path: payload  # type: ignore[method-assign]
    return reader


def _device() -> dict[str, object]:
    return {"type": "shelly_plug_m_gen3", "component_id": 0, "host": "test"}


def test_plug_m_uses_switch_status_and_preserves_zero() -> None:
    reading = _reader({"output": True, "apower": 0}).read(_device(), "solakon_meter")
    assert reading.power_w == 0.0
    assert reading.power_available is True
    assert reading.source == "Switch.GetStatus"


def test_plug_m_rejects_missing_bool_nan_and_infinity() -> None:
    for value in (None, True, math.nan, math.inf):
        payload = {"output": True}
        if value is not None:
            payload["apower"] = value
        reading = _reader(payload).read(_device(), "solakon_meter")
        assert reading.power_available is False
        assert "missing_active_power" in reading.errors


def test_plug_m_reports_relay_off_without_switching_it() -> None:
    reading = _reader({"output": False, "apower": 0}).read(_device(), "solakon_meter")
    assert reading.power_available is True
    assert reading.power_w == 0.0
    assert reading.errors == ("relay_off",)
