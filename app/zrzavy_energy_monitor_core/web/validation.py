"""Build public API payloads for persisted validation events."""

from __future__ import annotations

import json
import sqlite3
from contextlib import AbstractContextManager
from typing import Any, Protocol


class ValidationQueryDatabase(Protocol):
    """Provide configured SQLite connections for validation queries."""

    def connect(self) -> AbstractContextManager[sqlite3.Connection]:
        """Return one short-lived SQLite connection context manager."""

        ...


def build_validation_events_api_response(
    database: ValidationQueryDatabase,
    *,
    limit_value: object = 100,
    source_id: str | None = None,
    decision: str | None = None,
    severity: str | None = None,
    hours_value: object = 24,
    now_epoch: float,
) -> dict[str, Any]:
    """Return filtered, decoded, and bounded validation events."""

    limit = _bounded_int(limit_value, default=100, minimum=1, maximum=500)
    hours = _bounded_float(
        hours_value,
        default=24.0,
        minimum=0.25,
        maximum=24.0 * 365.0,
    )
    normalized_source = _optional_text(source_id)
    normalized_decision = _choice(
        decision,
        allowed={"accept_with_warning", "reject"},
    )
    normalized_severity = _choice(
        severity,
        allowed={"warning", "error"},
    )
    cutoff = now_epoch - hours * 3600.0

    clauses = ["last_seen_epoch >= ?"]
    parameters: list[object] = [cutoff]

    if normalized_source is not None:
        clauses.append("source_id = ?")
        parameters.append(normalized_source)
    if normalized_decision is not None:
        clauses.append("decision = ?")
        parameters.append(normalized_decision)
    if normalized_severity is not None:
        clauses.append("severity = ?")
        parameters.append(normalized_severity)

    query = (
        "SELECT * FROM validation_events WHERE "
        + " AND ".join(clauses)
        + " ORDER BY last_seen_epoch DESC, id DESC LIMIT ?"
    )
    parameters.append(limit)

    with database.connect() as conn:
        rows = conn.execute(query, parameters).fetchall()

    return {
        "window_hours": hours,
        "filters": {
            "source_id": normalized_source,
            "decision": normalized_decision,
            "severity": normalized_severity,
            "limit": limit,
        },
        "events": [_event_row(row) for row in rows],
    }


def build_validation_summary_api_response(
    database: ValidationQueryDatabase,
    *,
    enabled: bool,
    hours_value: object = 24,
    recent_limit_value: object = 8,
    now_epoch: float,
) -> dict[str, Any]:
    """Return an operational summary and newest validation events."""

    hours = _bounded_float(
        hours_value,
        default=24.0,
        minimum=0.25,
        maximum=24.0 * 365.0,
    )
    recent_limit = _bounded_int(
        recent_limit_value,
        default=8,
        minimum=1,
        maximum=50,
    )
    cutoff = now_epoch - hours * 3600.0

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS event_group_count,
                   COALESCE(SUM(occurrence_count), 0) AS occurrence_count,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN decision = 'accept_with_warning'
                               THEN 1 ELSE 0
                           END
                       ),
                       0
                   ) AS warning_group_count,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN decision = 'accept_with_warning'
                               THEN occurrence_count ELSE 0
                           END
                       ),
                       0
                   ) AS warning_occurrence_count,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN decision = 'reject'
                               THEN 1 ELSE 0
                           END
                       ),
                       0
                   ) AS rejection_group_count,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN decision = 'reject'
                               THEN occurrence_count ELSE 0
                           END
                       ),
                       0
                   ) AS rejection_occurrence_count,
                   MAX(last_seen_epoch) AS latest_event_epoch,
                   MAX(last_seen_local) AS latest_event_local
            FROM validation_events
            WHERE last_seen_epoch >= ?
            """,
            (cutoff,),
        ).fetchone()
        source_rows = conn.execute(
            """
            SELECT source_id,
                   COUNT(*) AS event_group_count,
                   COALESCE(SUM(occurrence_count), 0) AS occurrence_count,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN decision = 'reject'
                               THEN occurrence_count ELSE 0
                           END
                       ),
                       0
                   ) AS rejection_occurrence_count
            FROM validation_events
            WHERE last_seen_epoch >= ?
            GROUP BY source_id
            ORDER BY occurrence_count DESC, source_id
            """,
            (cutoff,),
        ).fetchall()

    summary = _summary_row(row)
    recent = build_validation_events_api_response(
        database,
        limit_value=recent_limit,
        hours_value=hours,
        now_epoch=now_epoch,
    )["events"]

    if not enabled:
        status = "disabled"
    elif summary["rejection_occurrence_count"]:
        status = "error"
    elif summary["warning_occurrence_count"]:
        status = "warning"
    else:
        status = "ok"

    return {
        "enabled": enabled,
        "status": status,
        "window_hours": hours,
        "summary": summary,
        "sources": [
            {
                "source_id": str(source["source_id"]),
                "event_group_count": int(source["event_group_count"]),
                "occurrence_count": int(source["occurrence_count"]),
                "rejection_occurrence_count": int(source["rejection_occurrence_count"]),
            }
            for source in source_rows
        ],
        "recent_events": recent,
    }


def _summary_row(row: sqlite3.Row | None) -> dict[str, Any]:
    """Convert the aggregate SQL row to stable public JSON."""

    if row is None:
        return {
            "event_group_count": 0,
            "occurrence_count": 0,
            "warning_group_count": 0,
            "warning_occurrence_count": 0,
            "rejection_group_count": 0,
            "rejection_occurrence_count": 0,
            "latest_event_epoch": None,
            "latest_event_local": None,
        }
    return {
        "event_group_count": int(row["event_group_count"]),
        "occurrence_count": int(row["occurrence_count"]),
        "warning_group_count": int(row["warning_group_count"]),
        "warning_occurrence_count": int(row["warning_occurrence_count"]),
        "rejection_group_count": int(row["rejection_group_count"]),
        "rejection_occurrence_count": int(row["rejection_occurrence_count"]),
        "latest_event_epoch": _optional_float(row["latest_event_epoch"]),
        "latest_event_local": (
            str(row["latest_event_local"])
            if row["latest_event_local"] is not None
            else None
        ),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    """Decode one already-sanitized persisted event row."""

    first_epoch = float(row["first_seen_epoch"])
    last_epoch = float(row["last_seen_epoch"])
    return {
        "id": int(row["id"]),
        "first_seen_epoch": first_epoch,
        "first_seen_local": str(row["first_seen_local"]),
        "last_seen_epoch": last_epoch,
        "last_seen_local": str(row["last_seen_local"]),
        "duration_seconds": max(0.0, last_epoch - first_epoch),
        "source_id": str(row["source_id"]),
        "role": str(row["role"]),
        "metric": str(row["metric"]),
        "unit": str(row["unit"]),
        "rule_id": str(row["rule_id"]),
        "code": str(row["finding_code"]),
        "severity": str(row["severity"]),
        "decision": str(row["decision"]),
        "quality": str(row["quality"]),
        "reason": str(row["reason"]),
        "raw_value": _decoded_json(row["raw_value_json"]),
        "accepted_value": _optional_float(row["accepted_value"]),
        "details": _decoded_mapping(row["details_json"]),
        "occurrence_count": int(row["occurrence_count"]),
        "minimum_value": _optional_float(row["minimum_value"]),
        "maximum_value": _optional_float(row["maximum_value"]),
        "first_sample_id": _optional_int(row["first_sample_id"]),
        "last_sample_id": _optional_int(row["last_sample_id"]),
    }


def _decoded_json(value: object) -> object:
    """Decode bounded persisted JSON without raising through the API."""

    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _decoded_mapping(value: object) -> dict[str, object]:
    """Decode safe finding details as a JSON object."""

    decoded = _decoded_json(value)
    return decoded if isinstance(decoded, dict) else {}


def _optional_text(value: str | None) -> str | None:
    """Return a stripped optional filter value."""

    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _choice(
    value: str | None,
    *,
    allowed: set[str],
) -> str | None:
    """Return a supported filter value or no filter."""

    normalized = _optional_text(value)
    return normalized if normalized in allowed else None


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse one bounded integer query parameter."""

    if isinstance(value, bool):
        return default
    try:
        normalized = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, normalized))


def _bounded_float(
    value: object,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Parse one bounded floating-point query parameter."""

    if isinstance(value, bool):
        return default
    try:
        normalized = float(str(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, normalized))


def _optional_float(value: object) -> float | None:
    """Convert a nullable SQLite numeric field safely."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    """Convert a nullable SQLite integer field safely."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
