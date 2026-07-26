"""Tests for the additive Phase-09 live API and dashboard contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zrzavy_energy_monitor_core.web.api import build_live_api_response


class _Database:
    """Expose predefined legacy and energy-balance rows."""

    def __init__(self, balance: dict[str, Any] | None) -> None:
        self.balance = balance

    def latest(self) -> None:
        return None

    def latest_energy_balance_sample(self) -> dict[str, Any] | None:
        return self.balance


class _Collector:
    """Provide the minimum live API collector contract."""

    def status(self) -> dict[str, Any]:
        return {"running": True}


def _row() -> dict[str, Any]:
    return {
        "sample_id": 12,
        "calculated_at": "2026-07-26T18:00:00+02:00",
        "quality": "calculated",
        "house_power_w": 1500.0,
        "grid_power_w": 900.0,
        "grid_import_power_w": 900.0,
        "grid_export_power_w": 0.0,
        "plant_ac_power_w": 600.0,
        "pv_power_w": 720.0,
        "battery_charge_power_w": 100.0,
        "battery_discharge_power_w": 0.0,
        "battery_soc_percent": 74.0,
        "self_consumed_power_w": 600.0,
        "self_consumption_rate_percent": 100.0,
        "autonomy_rate_percent": 40.0,
        "residual_power_w": 0.0,
        "fallback_used": 1,
        "source_metadata_json": json.dumps(
            {
                "grid_power": {
                    "selected_source_id": "house_meter",
                    "selected_measurement_timestamp": ("2026-07-26T17:59:55+02:00"),
                    "fallback_used": True,
                }
            }
        ),
        "findings_json": json.dumps([{"severity": "warning", "code": "fallback_used"}]),
    }


def test_live_api_exposes_nested_current_energy_balance() -> None:
    payload = build_live_api_response(
        _Database(_row()),
        _Collector(),
        now_epoch=1_785_081_610.0,
    )

    balance = payload["energy_balance"]
    assert balance["sample_id"] == 12
    assert balance["quality"] == "calculated"
    assert balance["values"]["house_power_w"] == 1500.0
    assert balance["values"]["grid_export_power_w"] == 0.0
    assert balance["fallback_used"] is True
    assert balance["sources"]["grid_power"]["selected_source_id"] == "house_meter"
    assert balance["sources"]["grid_power"]["age_seconds"] == 15
    assert balance["findings"][0]["code"] == "fallback_used"


def test_live_api_preserves_null_and_zero_and_handles_invalid_json() -> None:
    row = _row()
    row["self_consumption_rate_percent"] = None
    row["source_metadata_json"] = "invalid"
    row["findings_json"] = "{}"

    balance = build_live_api_response(
        _Database(row),
        _Collector(),
        now_epoch=1_785_081_610.0,
    )["energy_balance"]

    assert balance["values"]["grid_export_power_w"] == 0.0
    assert balance["values"]["self_consumption_rate_percent"] is None
    assert balance["sources"] == {}
    assert balance["findings"] == []


def test_live_api_returns_null_without_energy_balance_support_or_row() -> None:
    assert (
        build_live_api_response(
            _Database(None),
            _Collector(),
            now_epoch=0.0,
        )["energy_balance"]
        is None
    )


def test_dashboard_contains_energy_balance_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    template = (root / "app/templates/dashboard.html").read_text(encoding="utf-8")
    script = (root / "app/static/dashboard.js").read_text(encoding="utf-8")

    for element_id in (
        "balance-pv",
        "balance-plant-ac",
        "balance-house",
        "balance-grid-import",
        "balance-grid-export",
        "balance-battery-charge",
        "balance-battery-discharge",
        "balance-self-consumed",
        "balance-self-consumption-rate",
        "balance-autonomy-rate",
        "energy-balance-sources",
        "energy-balance-fallback",
        "energy-balance-age",
        "energy-balance-warning",
    ):
        assert f'id="{element_id}"' in template
        assert element_id in script
    assert "Anlagen-AC-Leistung" in template
    assert "Netzeinspeisung" in template
    assert "data.energy_balance" in script
