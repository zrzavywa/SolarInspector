"""Create Zrzavy Energy Monitor CSV export content.

This module preserves the existing field order, delimiter, header names,
ignored-column behavior, output encoding, and filename convention.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Final

from zrzavy_energy_monitor_core.persistence.queries import (
    HARD_MAXIMUM_QUERY_ROWS,
    get_energy_balance_series,
    get_grid_series,
    get_measurement_series,
    get_phase_series,
    get_source_selection_events,
    get_validation_events,
)

DEFAULT_MAXIMUM_EXPORT_ROWS: Final = 50_000
SUPPORTED_TIME_SERIES_EXPORTS: Final = frozenset(
    {
        "measurements",
        "phases",
        "grid",
        "energy_balance",
        "validation_events",
        "source_selection_events",
    }
)


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

    filename = (
        f"zrzavy-energy-monitor_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    )

    return output.getvalue(), filename


def build_time_series_csv_export(
    connection: sqlite3.Connection,
    dataset: str,
    start: datetime,
    end: datetime,
    *,
    metric: str | None = None,
    source_id: str | None = None,
    maximum_rows: int = DEFAULT_MAXIMUM_EXPORT_ROWS,
) -> tuple[str, str]:
    """Build one bounded Phase-10 CSV export.

    Args:
        connection: Open SQLite connection configured with ``sqlite3.Row``.
            The export performs read-only queries and no transaction.
        dataset: One value from ``SUPPORTED_TIME_SERIES_EXPORTS``.
        start: Inclusive timezone-aware range start.
        end: Exclusive timezone-aware range end.
        metric: Optional metric filter for measurements and diagnostic events.
            Measurement exports require this value.
        source_id: Optional source filter for measurements and validation.
        maximum_rows: Maximum exported rows, from 1 through 50,000.

    Returns:
        Semicolon-separated UTF-8 text and a safe deterministic filename.
        Missing database values become empty fields; real zeros remain zero.

    Raises:
        ValueError: If the dataset, filter, range, or limit is invalid.

    Security:
        Raw validation values, metadata JSON, rejected-candidate JSON, device
        serials, addresses, and credentials are never part of these exports.
        Text cells that spreadsheet programs could execute are escaped.
    """

    if dataset not in SUPPORTED_TIME_SERIES_EXPORTS:
        raise ValueError(f"unsupported CSV dataset: {dataset}")
    if (
        isinstance(maximum_rows, bool)
        or not isinstance(maximum_rows, int)
        or not 1 <= maximum_rows <= HARD_MAXIMUM_QUERY_ROWS
    ):
        raise ValueError(
            f"maximum_rows must be between 1 and {HARD_MAXIMUM_QUERY_ROWS}"
        )

    fieldnames, rows = _time_series_export_rows(
        connection,
        dataset=dataset,
        start=start,
        end=end,
        metric=metric,
        source_id=source_id,
        maximum_rows=maximum_rows,
    )
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(
        {field: _safe_csv_value(row.get(field)) for field in fieldnames} for row in rows
    )
    filename = (
        f"zrzavy-energy-monitor_{dataset}_"
        f"{start.astimezone(timezone.utc).date().isoformat()}_"
        f"{end.astimezone(timezone.utc).date().isoformat()}.csv"
    )
    return output.getvalue(), filename


def _time_series_export_rows(
    connection: sqlite3.Connection,
    *,
    dataset: str,
    start: datetime,
    end: datetime,
    metric: str | None,
    source_id: str | None,
    maximum_rows: int,
) -> tuple[list[str], list[dict[str, object]]]:
    normalized_metric = metric.strip() if metric is not None else None
    normalized_source = source_id.strip() if source_id is not None else None
    normalized_metric = normalized_metric or None
    normalized_source = normalized_source or None
    if dataset == "measurements":
        if normalized_metric is None:
            raise ValueError("measurement CSV export requires a metric")
        rows = get_measurement_series(
            connection,
            normalized_metric,
            start,
            end,
            source_id=normalized_source,
            maximum_rows=maximum_rows,
        )
        return (
            [
                "measured_at_utc",
                "received_at_utc",
                "source_id",
                "role",
                "metric",
                "value",
                "unit",
                "quality",
                "device_status",
            ],
            [
                {
                    **row,
                    "measured_at_utc": row["measured_at"],
                    "received_at_utc": row["received_at"],
                }
                for row in rows
            ],
        )
    if dataset == "phases":
        return _phase_export(
            get_phase_series(connection, start, end, maximum_rows=maximum_rows)
        )
    if dataset == "grid":
        return _grid_export(
            get_grid_series(connection, start, end, maximum_rows=maximum_rows)
        )
    if dataset == "energy_balance":
        return _balance_export(
            get_energy_balance_series(connection, start, end, maximum_rows=maximum_rows)
        )
    if dataset == "validation_events":
        rows = get_validation_events(
            connection,
            start,
            end,
            source_id=normalized_source,
            metric=normalized_metric,
            maximum_rows=maximum_rows,
        )
        fields = [
            "last_seen_at_utc",
            "source_id",
            "role",
            "metric",
            "unit",
            "rule_id",
            "finding_code",
            "severity",
            "decision",
            "quality",
            "reason",
            "accepted_value",
            "occurrence_count",
            "minimum_value",
            "maximum_value",
        ]
        return fields, [
            {
                **row,
                "last_seen_at_utc": _epoch_utc(row["last_seen_epoch"]),
            }
            for row in rows
        ]

    rows = get_source_selection_events(
        connection,
        start,
        end,
        metric=normalized_metric,
        maximum_rows=maximum_rows,
    )
    fields = [
        "selected_at_utc",
        "metric",
        "selected_source_id",
        "selected_source_role",
        "selected_quality",
        "fallback_used",
        "selection_reason",
    ]
    return fields, [{**row, "selected_at_utc": row["selected_at"]} for row in rows]


def _phase_export(
    rows: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]]]:
    fields = [
        "timestamp_utc",
        "source_id",
        "measurement_role",
        "device_status",
        "measured_at",
        "l1_power_w",
        "l1_voltage_v",
        "l1_current_a",
        "l1_power_factor",
        "l1_quality",
        "l2_power_w",
        "l2_voltage_v",
        "l2_current_a",
        "l2_power_factor",
        "l2_quality",
        "l3_power_w",
        "l3_voltage_v",
        "l3_current_a",
        "l3_power_factor",
        "l3_quality",
        "phase_power_available_count",
        "phase_power_complete",
        "phase_power_sum_w",
        "phase_power_spread_w",
        "phase_power_total_delta_w",
        "phase_power_total_delta_pct",
        "phase_power_total_consistent",
    ]
    return fields, [
        {**row, "timestamp_utc": _epoch_utc(row["ts_epoch"])} for row in rows
    ]


def _grid_export(
    rows: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]]]:
    fields = [
        "timestamp_utc",
        "source_id",
        "source_name",
        "adapter",
        "device_status",
        "quality",
        "measured_at",
        "grid_power_w",
        "grid_power_quality",
        "grid_import_power_w",
        "grid_import_power_quality",
        "grid_export_power_w",
        "grid_export_power_quality",
        "grid_import_total_kwh",
        "grid_import_total_quality",
        "grid_export_total_kwh",
        "grid_export_total_quality",
    ]
    return fields, [
        {**row, "timestamp_utc": _epoch_utc(row["ts_epoch"])} for row in rows
    ]


def _balance_export(
    rows: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]]]:
    fields = [
        "timestamp_utc",
        "calculated_at",
        "quality",
        "house_power_w",
        "grid_power_w",
        "grid_import_power_w",
        "grid_export_power_w",
        "plant_ac_power_w",
        "pv_power_w",
        "battery_charge_power_w",
        "battery_discharge_power_w",
        "battery_soc_percent",
        "self_consumed_power_w",
        "self_consumption_rate_percent",
        "autonomy_rate_percent",
        "residual_power_w",
        "fallback_used",
    ]
    return fields, [
        {**row, "timestamp_utc": _epoch_utc(row["ts_epoch"])} for row in rows
    ]


def _epoch_utc(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("export timestamp epoch must be numeric")
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def _safe_csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
