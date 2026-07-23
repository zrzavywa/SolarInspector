"""Create SolarInspector CSV export content.

This module preserves the existing field order, delimiter, header names,
ignored-column behavior, output encoding, and filename convention.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any


def build_csv_export(
    rows: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[str, str]:
    """Build CSV content and its download filename."""
    fieldnames = [
        "ts_local",
        "grid_power_w",
        "solar_power_w",
        "house_power_w",
        "grid_import_w",
        "feed_in_w",
        "self_consumption_w",
        "solar_source",
        "grid_source",
        "shelly_solar_power_w",
        "solakon_pv_power_w",
        "solakon_ac_power_w",
        "solakon_battery_power_w",
        "solakon_battery_soc_pct",
        "solakon_load_power_w",
        "solakon_meter_power_w",
        "solakon_temperature_c",
        "solakon_daily_pv_kwh",
        "solakon_total_pv_kwh",
        "solakon_pv1_power_w",
        "solakon_pv2_power_w",
        "solakon_pv3_power_w",
        "solakon_pv4_power_w",
        "solar_difference_w",
        "solar_difference_pct",
        "solakon_model",
        "solakon_serial",
        "solakon_status",
        "voltage_v",
        "current_a",
        "power_factor",
        "frequency_hz",
        "grid_import_wh",
        "feed_in_wh",
        "solar_wh",
        "house_wh",
        "self_consumption_wh",
        "shelly_solar_wh",
        "solakon_pv_wh",
        "solakon_ac_wh",
        "battery_charge_wh",
        "battery_discharge_wh",
        "house_ok",
        "solar_ok",
        "solakon_ok",
        "error_text",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(rows)

    filename = f"solarinspector_{start_date.isoformat()}_{end_date.isoformat()}.csv"

    return output.getvalue(), filename
