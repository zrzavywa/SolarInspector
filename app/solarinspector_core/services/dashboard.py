"""Build the existing SolarInspector dashboard data.

This module preserves the energy aggregation, KPI calculation, series
formatting, and source reporting behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from solarinspector_core.persistence.database import Database
from solarinspector_core.services.periods import (
    bucket_index,
    period_bounds,
)


def build_dashboard(database: Database, period: str, anchor: date) -> dict[str, Any]:
    start, end, labels, title = period_bounds(period, anchor)
    rows = database.rows_between(start.timestamp(), end.timestamp())
    series_keys = [
        "solar_wh",
        "house_wh",
        "grid_import_wh",
        "feed_in_wh",
        "self_consumption_wh",
        "shelly_solar_wh",
        "solakon_pv_wh",
        "solakon_ac_wh",
        "battery_charge_wh",
        "battery_discharge_wh",
    ]
    buckets = {key: [0.0] * len(labels) for key in series_keys}
    totals = {key: 0.0 for key in series_keys}
    soc_buckets: list[list[float]] = [[] for _ in labels]
    all_soc: list[float] = []
    difference_values: list[float] = []
    difference_pct_values: list[float] = []

    for row in rows:
        sample_dt = datetime.fromtimestamp(float(row["ts_epoch"])).astimezone()
        index = bucket_index(period, start, sample_dt)
        if not (0 <= index < len(labels)):
            continue
        for key in series_keys:
            value = float(row.get(key) or 0.0)
            buckets[key][index] += value
            totals[key] += value
        soc = row.get("solakon_battery_soc_pct")
        if soc is not None:
            soc_value = float(soc)
            soc_buckets[index].append(soc_value)
            all_soc.append(soc_value)
        if row.get("solar_difference_w") is not None:
            difference_values.append(float(row["solar_difference_w"]))
        if row.get("solar_difference_pct") is not None:
            difference_pct_values.append(float(row["solar_difference_pct"]))

    solar = totals["solar_wh"]
    house = totals["house_wh"]
    self_use = totals["self_consumption_wh"]
    latest_row = rows[-1] if rows else None

    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "labels": labels,
        "series": {
            "solar_kwh": [round(v / 1000.0, 4) for v in buckets["solar_wh"]],
            "house_kwh": [round(v / 1000.0, 4) for v in buckets["house_wh"]],
            "grid_import_kwh": [
                round(v / 1000.0, 4) for v in buckets["grid_import_wh"]
            ],
            "feed_in_kwh": [round(v / 1000.0, 4) for v in buckets["feed_in_wh"]],
            "self_consumption_kwh": [
                round(v / 1000.0, 4) for v in buckets["self_consumption_wh"]
            ],
            "solakon_pv_kwh": [round(v / 1000.0, 4) for v in buckets["solakon_pv_wh"]],
            "solakon_ac_kwh": [round(v / 1000.0, 4) for v in buckets["solakon_ac_wh"]],
            "battery_charge_kwh": [
                round(v / 1000.0, 4) for v in buckets["battery_charge_wh"]
            ],
            "battery_discharge_kwh": [
                round(v / 1000.0, 4) for v in buckets["battery_discharge_wh"]
            ],
            "battery_soc_avg": [
                round(sum(values) / len(values), 1) if values else None
                for values in soc_buckets
            ],
        },
        "kpi": {
            "solar_kwh": round(solar / 1000.0, 3),
            "house_kwh": round(house / 1000.0, 3),
            "grid_import_kwh": round(totals["grid_import_wh"] / 1000.0, 3),
            "feed_in_kwh": round(totals["feed_in_wh"] / 1000.0, 3),
            "self_consumption_kwh": round(self_use / 1000.0, 3),
            "self_consumption_pct": round((self_use / solar * 100.0), 1)
            if solar > 0
            else None,
            "autarky_pct": round((self_use / house * 100.0), 1) if house > 0 else None,
            "sample_count": len(rows),
            "shelly_ac_kwh": round(totals["shelly_solar_wh"] / 1000.0, 3),
            "solakon_pv_kwh": round(totals["solakon_pv_wh"] / 1000.0, 3),
            "solakon_ac_kwh": round(totals["solakon_ac_wh"] / 1000.0, 3),
            "battery_charge_kwh": round(totals["battery_charge_wh"] / 1000.0, 3),
            "battery_discharge_kwh": round(totals["battery_discharge_wh"] / 1000.0, 3),
            "battery_soc_avg": round(sum(all_soc) / len(all_soc), 1)
            if all_soc
            else None,
            "battery_soc_min": round(min(all_soc), 1) if all_soc else None,
            "battery_soc_max": round(max(all_soc), 1) if all_soc else None,
            "difference_avg_w": round(
                sum(difference_values) / len(difference_values), 1
            )
            if difference_values
            else None,
            "difference_avg_pct": round(
                sum(difference_pct_values) / len(difference_pct_values), 1
            )
            if difference_pct_values
            else None,
            "solar_source": latest_row.get("solar_source") if latest_row else None,
            "grid_source": latest_row.get("grid_source") if latest_row else None,
        },
    }
