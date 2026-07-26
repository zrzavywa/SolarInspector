"""Bounded, parameterized reads for persisted Zrzavy Energy Monitor time series."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Final

from zrzavy_energy_monitor_core.models.metrics import Metric

DEFAULT_MAXIMUM_QUERY_ROWS: Final = 5_000
HARD_MAXIMUM_QUERY_ROWS: Final = 50_000

_MEASUREMENT_COLUMNS: Final = """
    id, sample_id, source_id, role, metric, value, unit, measured_at,
    received_at, quality, device_status
"""
_PHASE_COLUMNS: Final = """
    p.sample_id, s.ts_epoch, s.ts_local, p.source_id, p.measurement_role,
    p.device_status, p.error_text, p.measured_at, p.received_at,
    p.l1_power_w, p.l1_voltage_v, p.l1_current_a, p.l1_power_factor,
    p.l1_quality, p.l2_power_w, p.l2_voltage_v, p.l2_current_a,
    p.l2_power_factor, p.l2_quality, p.l3_power_w, p.l3_voltage_v,
    p.l3_current_a, p.l3_power_factor, p.l3_quality,
    p.phase_power_available_count, p.phase_power_complete,
    p.phase_power_total_source, p.phase_power_sum_w, p.phase_power_spread_w,
    p.phase_power_share_l1_pct, p.phase_power_share_l2_pct,
    p.phase_power_share_l3_pct, p.phase_power_total_delta_w,
    p.phase_power_total_delta_pct, p.phase_power_total_consistent
"""
_GRID_COLUMNS: Final = """
    g.sample_id, s.ts_epoch, s.ts_local, g.source_id, g.source_name, g.adapter,
    g.active_source_id, g.device_status, g.quality, g.error_text, g.measured_at,
    g.received_at, g.grid_power_w, g.grid_power_quality,
    g.grid_import_power_w, g.grid_import_power_quality, g.grid_export_power_w,
    g.grid_export_power_quality, g.grid_import_total_kwh,
    g.grid_import_total_quality, g.grid_export_total_kwh,
    g.grid_export_total_quality
"""
_BALANCE_COLUMNS: Final = """
    b.sample_id, s.ts_epoch, s.ts_local, b.calculated_at, b.quality,
    b.house_power_w, b.grid_power_w, b.grid_import_power_w,
    b.grid_export_power_w, b.plant_ac_power_w, b.pv_power_w,
    b.battery_charge_power_w, b.battery_discharge_power_w,
    b.battery_soc_percent, b.self_consumed_power_w,
    b.self_consumption_rate_percent, b.autonomy_rate_percent,
    b.residual_power_w, b.fallback_used
"""
_VALIDATION_COLUMNS: Final = """
    id, first_seen_epoch, first_seen_local, last_seen_epoch, last_seen_local,
    source_id, role, metric, unit, rule_id, finding_code, severity, decision,
    quality, reason, raw_value_json, accepted_value, details_json,
    occurrence_count, minimum_value, maximum_value, first_sample_id,
    last_sample_id
"""
_SELECTION_COLUMNS: Final = """
    id, sample_id, selected_at, metric, selected_source_id,
    selected_source_role, selected_quality, fallback_used, selection_reason,
    rejected_candidates_json
"""


def get_latest_measurement(
    connection: sqlite3.Connection,
    source_id: str,
    metric: Metric | str,
) -> dict[str, object] | None:
    """Return the latest persisted value for one source and metric.

    Args:
        connection: Open SQLite connection. This function does not transact.
        source_id: Exact normalized source identifier.
        metric: Normalized or calculated metric identifier.

    Returns:
        The newest row as a dictionary, or ``None`` when no row matches.
    """

    row = connection.execute(
        f"""
        SELECT {_MEASUREMENT_COLUMNS}
        FROM measurements
        WHERE source_id = ? AND metric = ?
        ORDER BY measured_at DESC
        LIMIT 1
        """,
        (source_id, _metric_value(metric)),
    ).fetchone()
    return _dict_row(row)


def get_measurement_series(
    connection: sqlite3.Connection,
    metric: Metric | str,
    start: datetime,
    end: datetime,
    source_id: str | None = None,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return a bounded measurement series for the half-open UTC range.

    Raises:
        ValueError: If timestamps are naive, the range is empty/reversed, or
            the requested row limit is outside the supported bounds.
    """

    start_utc, end_utc, limit = _validated_range(start, end, maximum_rows)
    parameters: list[object] = [
        _metric_value(metric),
        start_utc,
        end_utc,
    ]
    source_clause = ""
    if source_id is not None:
        source_clause = "AND source_id = ?"
        parameters.append(source_id)
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT {_MEASUREMENT_COLUMNS}
        FROM measurements
        WHERE metric = ?
          AND measured_at >= ?
          AND measured_at < ?
          {source_clause}
        ORDER BY measured_at ASC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return _dict_rows(connection, rows)


def get_phase_series(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return bounded phase-detail rows for a half-open time range."""

    start_epoch, end_epoch, limit = _validated_epoch_range(start, end, maximum_rows)
    rows = connection.execute(
        f"""
        SELECT {_PHASE_COLUMNS}
        FROM samples AS s
        JOIN phase_samples AS p ON p.sample_id = s.id
        WHERE s.ts_epoch >= ? AND s.ts_epoch < ?
        ORDER BY s.ts_epoch ASC
        LIMIT ?
        """,
        (start_epoch, end_epoch, limit),
    ).fetchall()
    return _dict_rows(connection, rows)


def get_grid_series(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return bounded official-grid detail rows for a half-open time range."""

    start_epoch, end_epoch, limit = _validated_epoch_range(start, end, maximum_rows)
    rows = connection.execute(
        f"""
        SELECT {_GRID_COLUMNS}
        FROM samples AS s
        JOIN grid_meter_samples AS g ON g.sample_id = s.id
        WHERE s.ts_epoch >= ? AND s.ts_epoch < ?
        ORDER BY s.ts_epoch ASC
        LIMIT ?
        """,
        (start_epoch, end_epoch, limit),
    ).fetchall()
    return _dict_rows(connection, rows)


def get_energy_balance_series(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return bounded calculated energy-balance rows for a time range."""

    start_epoch, end_epoch, limit = _validated_epoch_range(start, end, maximum_rows)
    rows = connection.execute(
        f"""
        SELECT {_BALANCE_COLUMNS}
        FROM samples AS s
        JOIN energy_balance_samples AS b ON b.sample_id = s.id
        WHERE s.ts_epoch >= ? AND s.ts_epoch < ?
        ORDER BY s.ts_epoch ASC
        LIMIT ?
        """,
        (start_epoch, end_epoch, limit),
    ).fetchall()
    return _dict_rows(connection, rows)


def get_validation_events(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    source_id: str | None = None,
    metric: Metric | str | None = None,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return bounded validation events last observed in a time range."""

    start_epoch, end_epoch, limit = _validated_epoch_range(start, end, maximum_rows)
    clauses = ["last_seen_epoch >= ?", "last_seen_epoch < ?"]
    parameters: list[object] = [start_epoch, end_epoch]
    if source_id is not None:
        clauses.append("source_id = ?")
        parameters.append(source_id)
    if metric is not None:
        clauses.append("metric = ?")
        parameters.append(_metric_value(metric))
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT {_VALIDATION_COLUMNS}
        FROM validation_events
        WHERE {" AND ".join(clauses)}
        ORDER BY last_seen_epoch ASC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return _dict_rows(connection, rows)


def get_source_selection_events(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
    metric: Metric | str | None = None,
    *,
    maximum_rows: int = DEFAULT_MAXIMUM_QUERY_ROWS,
) -> list[dict[str, object]]:
    """Return bounded source-selection decisions for a half-open UTC range."""

    start_utc, end_utc, limit = _validated_range(start, end, maximum_rows)
    parameters: list[object] = [start_utc, end_utc]
    metric_clause = ""
    if metric is not None:
        metric_clause = "AND metric = ?"
        parameters.append(_metric_value(metric))
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT {_SELECTION_COLUMNS}
        FROM source_selection_events
        WHERE selected_at >= ? AND selected_at < ?
          {metric_clause}
        ORDER BY selected_at ASC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return _dict_rows(connection, rows)


def _validated_range(
    start: datetime,
    end: datetime,
    maximum_rows: int,
) -> tuple[str, str, int]:
    limit = _validated_limit(maximum_rows)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("time-series ranges require timezone-aware timestamps")
    if start >= end:
        raise ValueError("time-series range must have start before end")
    return (
        start.astimezone(timezone.utc).isoformat(),
        end.astimezone(timezone.utc).isoformat(),
        limit,
    )


def _validated_epoch_range(
    start: datetime,
    end: datetime,
    maximum_rows: int,
) -> tuple[float, float, int]:
    _start, _end, limit = _validated_range(start, end, maximum_rows)
    return start.timestamp(), end.timestamp(), limit


def _validated_limit(maximum_rows: int) -> int:
    if (
        isinstance(maximum_rows, bool)
        or not isinstance(maximum_rows, int)
        or maximum_rows < 1
        or maximum_rows > HARD_MAXIMUM_QUERY_ROWS
    ):
        raise ValueError(
            f"maximum_rows must be between 1 and {HARD_MAXIMUM_QUERY_ROWS}"
        )
    return maximum_rows


def _metric_value(metric: Metric | str) -> str:
    return metric.value if isinstance(metric, Metric) else metric


def _dict_row(
    row: sqlite3.Row | tuple[object, ...] | None,
) -> dict[str, object] | None:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    # Tuple rows are supported for callers that do not configure row_factory.
    raise TypeError("time-series queries require connection.row_factory = sqlite3.Row")


def _dict_rows(
    connection: sqlite3.Connection,
    rows: list[sqlite3.Row] | list[tuple[object, ...]],
) -> list[dict[str, object]]:
    return [result for row in rows if (result := _dict_row(row)) is not None]
