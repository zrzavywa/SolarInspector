"""Persist, deduplicate, sanitize, and retain validation events in SQLite."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real
from typing import Protocol

from zrzavy_energy_monitor_core.models.units import unit_for_metric
from zrzavy_energy_monitor_core.validation.engine import ValidationEvent
from zrzavy_energy_monitor_core.validation.result import ValidationFinding

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "passwd",
    "payload",
    "raw_response",
    "response_body",
    "secret",
    "token",
    "url",
    "uri",
)
_SENSITIVE_TEXT_MARKERS = (
    "authorization:",
    "password=",
    "passwd=",
    "secret=",
    "token=",
)


class ValidationEventConnectionProvider(Protocol):
    """Provide short-lived SQLite connections for event persistence."""

    def connect(self) -> AbstractContextManager[sqlite3.Connection]:
        """Return one configured SQLite connection context manager."""

        ...


@dataclass(frozen=True, slots=True)
class ValidationEventPersistencePolicy:
    """Configure bounded event aggregation and safe serialization."""

    dedup_window_seconds: float = 300.0
    retention_days: float = 90.0
    prune_interval_seconds: float = 3600.0
    max_reason_chars: int = 512
    max_details_chars: int = 4096
    max_raw_value_chars: int = 512

    def __post_init__(self) -> None:
        """Require useful, finite, and bounded policy values."""

        object.__setattr__(
            self,
            "dedup_window_seconds",
            _non_negative_float(
                self.dedup_window_seconds,
                "dedup_window_seconds",
            ),
        )
        object.__setattr__(
            self,
            "retention_days",
            _positive_float(self.retention_days, "retention_days"),
        )
        object.__setattr__(
            self,
            "prune_interval_seconds",
            _positive_float(
                self.prune_interval_seconds,
                "prune_interval_seconds",
            ),
        )
        for field_name in (
            "max_reason_chars",
            "max_details_chars",
            "max_raw_value_chars",
        ):
            object.__setattr__(
                self,
                field_name,
                _bounded_positive_int(
                    getattr(self, field_name),
                    field_name,
                    minimum=64,
                    maximum=65536,
                ),
            )

    @classmethod
    def from_config(
        cls,
        value: object,
    ) -> ValidationEventPersistencePolicy:
        """Build one policy while accepting an absent legacy configuration."""

        raw = dict(value) if isinstance(value, Mapping) else {}
        return cls(
            dedup_window_seconds=_non_negative_float(
                raw.get("dedup_window_seconds", 300.0),
                "dedup_window_seconds",
            ),
            retention_days=_positive_float(
                raw.get("retention_days", 90.0),
                "retention_days",
            ),
            prune_interval_seconds=_positive_float(
                raw.get("prune_interval_seconds", 3600.0),
                "prune_interval_seconds",
            ),
            max_reason_chars=_bounded_positive_int(
                raw.get("max_reason_chars", 512),
                "max_reason_chars",
                minimum=64,
                maximum=65536,
            ),
            max_details_chars=_bounded_positive_int(
                raw.get("max_details_chars", 4096),
                "max_details_chars",
                minimum=64,
                maximum=65536,
            ),
            max_raw_value_chars=_bounded_positive_int(
                raw.get("max_raw_value_chars", 512),
                "max_raw_value_chars",
                minimum=64,
                maximum=65536,
            ),
        )


class ValidationEventStore:
    """Persist actionable validation findings without unbounded event spam."""

    def __init__(
        self,
        database: ValidationEventConnectionProvider,
    ) -> None:
        """Create one store using the application's SQLite connection provider."""

        self._database = database
        self._lock = threading.RLock()
        self._last_prune_epoch: float | None = None

    def persist(
        self,
        events: Iterable[ValidationEvent],
        *,
        sample_id: int | None = None,
        policy: ValidationEventPersistencePolicy | None = None,
        reference_time: datetime | None = None,
    ) -> tuple[int, ...]:
        """Persist findings and aggregate identical recent occurrences.

        One row represents one source, role, metric, rule, finding code, and
        measurement-level decision within the configured deduplication window.
        """

        active_policy = policy or ValidationEventPersistencePolicy()
        event_tuple = tuple(events)
        reference = _reference_time(event_tuple, reference_time)
        reference_epoch = reference.timestamp()
        should_prune = self._prune_due(
            reference_epoch,
            active_policy.prune_interval_seconds,
        )
        if not event_tuple and not should_prune:
            return ()

        persisted_ids: list[int] = []
        with self._lock:
            with self._database.connect() as conn:
                try:
                    for event in event_tuple:
                        for finding in event.findings:
                            persisted_ids.append(
                                self._persist_finding(
                                    conn,
                                    event=event,
                                    finding=finding,
                                    sample_id=sample_id,
                                    policy=active_policy,
                                )
                            )
                    if should_prune:
                        self._delete_expired(
                            conn,
                            reference_epoch=reference_epoch,
                            retention_days=active_policy.retention_days,
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            if should_prune:
                self._last_prune_epoch = reference_epoch

        return tuple(persisted_ids)

    def latest(
        self,
        *,
        limit: int = 100,
        source_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return newest aggregated events with decoded safe JSON fields."""

        normalized_limit = _bounded_positive_int(
            limit,
            "limit",
            minimum=1,
            maximum=1000,
        )
        query = "SELECT * FROM validation_events"
        parameters: list[object] = []
        if source_id is not None:
            normalized_source = source_id.strip()
            if not normalized_source:
                raise ValueError("source_id must not be empty")
            query += " WHERE source_id = ?"
            parameters.append(normalized_source)
        query += " ORDER BY last_seen_epoch DESC, id DESC LIMIT ?"
        parameters.append(normalized_limit)

        with self._database.connect() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [_decoded_row(row) for row in rows]

    def count(self) -> int:
        """Return the number of aggregated validation-event rows."""

        with self._database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM validation_events"
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def prune_expired(
        self,
        *,
        reference_time: datetime,
        retention_days: float = 90.0,
    ) -> int:
        """Delete rows whose last occurrence is older than retention."""

        _require_aware(reference_time, "reference_time")
        normalized_days = _positive_float(
            retention_days,
            "retention_days",
        )
        with self._lock:
            with self._database.connect() as conn:
                try:
                    deleted = self._delete_expired(
                        conn,
                        reference_epoch=reference_time.timestamp(),
                        retention_days=normalized_days,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            self._last_prune_epoch = reference_time.timestamp()
        return deleted

    def _persist_finding(
        self,
        conn: sqlite3.Connection,
        *,
        event: ValidationEvent,
        finding: ValidationFinding,
        sample_id: int | None,
        policy: ValidationEventPersistencePolicy,
    ) -> int:
        """Insert or update one sanitized finding inside a transaction."""

        rule_id = finding.rule_id.strip()
        code = finding.code.strip()
        severity = finding.severity.value
        reason = _limited_text(
            finding.message,
            policy.max_reason_chars,
        )
        details_json = _details_json(
            finding.details,
            policy.max_details_chars,
        )
        raw_value_json = _raw_value_json(
            event.raw_value,
            policy.max_raw_value_chars,
        )
        observed_value = _observed_numeric_value(event)
        occurred_epoch = event.occurred_at.timestamp()
        occurred_local = event.occurred_at.isoformat()

        row = conn.execute(
            """
            SELECT id,
                   first_seen_epoch,
                   first_seen_local,
                   last_seen_epoch,
                   last_seen_local,
                   occurrence_count,
                   minimum_value,
                   maximum_value
            FROM validation_events
            WHERE source_id = ?
              AND role = ?
              AND metric = ?
              AND rule_id = ?
              AND finding_code = ?
              AND decision = ?
              AND last_seen_epoch >= ?
              AND last_seen_epoch <= ?
            ORDER BY last_seen_epoch DESC, id DESC
            LIMIT 1
            """,
            (
                event.source_id,
                event.role.value,
                event.metric.value,
                rule_id,
                code,
                event.decision.value,
                occurred_epoch - policy.dedup_window_seconds,
                occurred_epoch + policy.dedup_window_seconds,
            ),
        ).fetchone()

        if row is None:
            cursor = conn.execute(
                """
                INSERT INTO validation_events (
                    first_seen_epoch,
                    first_seen_local,
                    last_seen_epoch,
                    last_seen_local,
                    source_id,
                    role,
                    metric,
                    unit,
                    rule_id,
                    finding_code,
                    severity,
                    decision,
                    quality,
                    reason,
                    raw_value_json,
                    accepted_value,
                    details_json,
                    occurrence_count,
                    minimum_value,
                    maximum_value,
                    first_sample_id,
                    last_sample_id
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    occurred_epoch,
                    occurred_local,
                    occurred_epoch,
                    occurred_local,
                    event.source_id,
                    event.role.value,
                    event.metric.value,
                    unit_for_metric(event.metric).value,
                    rule_id,
                    code,
                    severity,
                    event.decision.value,
                    event.quality.value,
                    reason,
                    raw_value_json,
                    event.accepted_value,
                    details_json,
                    1,
                    observed_value,
                    observed_value,
                    sample_id,
                    sample_id,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a validation event ID.")
            return int(cursor.lastrowid)

        event_id = int(row["id"])
        first_epoch = min(
            float(row["first_seen_epoch"]),
            occurred_epoch,
        )
        last_epoch = max(
            float(row["last_seen_epoch"]),
            occurred_epoch,
        )
        first_local = (
            occurred_local
            if occurred_epoch < float(row["first_seen_epoch"])
            else str(row["first_seen_local"])
        )
        last_local = (
            occurred_local
            if occurred_epoch >= float(row["last_seen_epoch"])
            else str(row["last_seen_local"])
        )
        minimum_value = _minimum(
            _optional_float(row["minimum_value"]),
            observed_value,
        )
        maximum_value = _maximum(
            _optional_float(row["maximum_value"]),
            observed_value,
        )

        conn.execute(
            """
            UPDATE validation_events
            SET first_seen_epoch = ?,
                first_seen_local = ?,
                last_seen_epoch = ?,
                last_seen_local = ?,
                severity = ?,
                quality = ?,
                reason = ?,
                raw_value_json = ?,
                accepted_value = ?,
                details_json = ?,
                occurrence_count = ?,
                minimum_value = ?,
                maximum_value = ?,
                last_sample_id = ?
            WHERE id = ?
            """,
            (
                first_epoch,
                first_local,
                last_epoch,
                last_local,
                severity,
                event.quality.value,
                reason,
                raw_value_json,
                event.accepted_value,
                details_json,
                int(row["occurrence_count"]) + 1,
                minimum_value,
                maximum_value,
                sample_id,
                event_id,
            ),
        )
        return event_id

    def _prune_due(
        self,
        reference_epoch: float,
        interval_seconds: float,
    ) -> bool:
        """Return whether retention cleanup is due."""

        with self._lock:
            if self._last_prune_epoch is None:
                return True
            return reference_epoch - self._last_prune_epoch >= interval_seconds

    @staticmethod
    def _delete_expired(
        conn: sqlite3.Connection,
        *,
        reference_epoch: float,
        retention_days: float,
    ) -> int:
        """Delete expired rows and return SQLite's affected-row count."""

        cutoff = reference_epoch - retention_days * 86400.0
        cursor = conn.execute(
            "DELETE FROM validation_events WHERE last_seen_epoch < ?",
            (cutoff,),
        )
        return max(0, int(cursor.rowcount))


def _reference_time(
    events: tuple[ValidationEvent, ...],
    reference_time: datetime | None,
) -> datetime:
    """Resolve one timezone-aware deterministic cleanup reference."""

    if reference_time is not None:
        _require_aware(reference_time, "reference_time")
        return reference_time
    if events:
        return max(event.occurred_at for event in events)
    return datetime.now(timezone.utc)


def _details_json(
    details: object,
    max_chars: int,
) -> str:
    """Serialize sanitized rule details within a strict size limit."""

    sanitized: dict[str, object] = {}
    if isinstance(details, tuple):
        for item in details:
            if not (
                isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            ):
                continue
            key, value = item
            sanitized[key] = _sanitize_detail(value, key=key, depth=0)
    return _limited_json(sanitized, max_chars)


def _raw_value_json(value: object, max_chars: int) -> str:
    """Serialize only safe scalar raw values, never full device responses."""

    safe_value: object
    if value is None or isinstance(value, bool):
        safe_value = value
    elif isinstance(value, Real):
        normalized = float(value)
        safe_value = normalized if math.isfinite(normalized) else "<non-finite-number>"
    elif isinstance(value, str):
        safe_value = _sanitize_text(value)
    else:
        safe_value = f"<complex-raw-value:{type(value).__name__}>"
    return _limited_json(safe_value, max_chars)


def _sanitize_detail(
    value: object,
    *,
    key: str,
    depth: int,
) -> object:
    """Sanitize nested details and redact sensitive key/value shapes."""

    lowered_key = key.casefold()
    if any(part in lowered_key for part in _SENSITIVE_KEY_PARTS):
        return "<redacted>"
    if depth >= 3:
        return "<maximum-depth>"

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else "<non-finite-number>"
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (nested_key, nested_value) in enumerate(value.items()):
            if index >= 20:
                result["truncated_items"] = True
                break
            text_key = str(nested_key)
            result[text_key] = _sanitize_detail(
                nested_value,
                key=text_key,
                depth=depth + 1,
            )
        return result
    if isinstance(value, (list, tuple)):
        sanitized = [
            _sanitize_detail(
                item,
                key=key,
                depth=depth + 1,
            )
            for item in value[:20]
        ]
        if len(value) > 20:
            sanitized.append("<truncated-items>")
        return sanitized
    return f"<unsupported:{type(value).__name__}>"


def _sanitize_text(value: str) -> str:
    """Redact URL-like and credential-like text, then bound its length."""

    normalized = value.strip()
    folded = normalized.casefold()
    if "://" in normalized:
        return "<redacted-url>"
    if any(marker in folded for marker in _SENSITIVE_TEXT_MARKERS):
        return "<redacted-sensitive-text>"
    return _limited_text(normalized, 256)


def _limited_text(value: str, max_chars: int) -> str:
    """Truncate one string deterministically without invalid encodings."""

    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1] + "…"


def _limited_json(value: object, max_chars: int) -> str:
    """Return valid compact JSON or one valid truncation marker."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(encoded) <= max_chars:
        return encoded
    marker = json.dumps(
        {
            "original_length": len(encoded),
            "truncated": True,
        },
        separators=(",", ":"),
    )
    if len(marker) > max_chars:
        return '{"truncated":true}'
    return marker


def _decoded_row(row: sqlite3.Row) -> dict[str, object]:
    """Decode safe JSON fields for later API and dashboard use."""

    result: dict[str, object] = dict(row)
    result["raw_value"] = json.loads(str(result["raw_value_json"]))
    result["details"] = json.loads(str(result["details_json"]))
    return result


def _observed_numeric_value(
    event: ValidationEvent,
) -> float | None:
    """Return a finite numeric raw value, falling back to accepted value."""

    raw = event.raw_value
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        normalized = float(raw)
        if math.isfinite(normalized):
            return normalized

    accepted = event.accepted_value
    if accepted is not None and math.isfinite(accepted):
        return float(accepted)
    return None


def _optional_float(value: object) -> float | None:
    """Convert nullable SQLite numeric fields safely."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("SQLite numeric field must be int, float, or null")
    return float(value)


def _minimum(
    left: float | None,
    right: float | None,
) -> float | None:
    """Return the minimum of two optional finite values."""

    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _maximum(
    left: float | None,
    right: float | None,
) -> float | None:
    """Return the maximum of two optional finite values."""

    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _non_negative_float(value: object, field_name: str) -> float:
    """Normalize one non-negative finite real or numeric string."""

    normalized = _finite_float(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


def _positive_float(value: object, field_name: str) -> float:
    """Normalize one strictly positive finite real or numeric string."""

    normalized = _finite_float(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized


def _finite_float(value: object, field_name: str) -> float:
    """Normalize one finite real or numeric string without accepting bool."""

    if isinstance(value, bool) or not isinstance(value, (Real, str)):
        raise TypeError(f"{field_name} must be a real number")
    try:
        normalized = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _bounded_positive_int(
    value: object,
    field_name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Normalize one positive integer within explicit resource bounds."""

    if isinstance(value, bool) or not isinstance(value, (Real, str)):
        raise TypeError(f"{field_name} must be an integer")
    try:
        numeric = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{field_name} must be an integer")
    normalized = int(numeric)
    if normalized < minimum or normalized > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return normalized


def _require_aware(value: datetime, field_name: str) -> None:
    """Require one timezone-aware datetime."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
