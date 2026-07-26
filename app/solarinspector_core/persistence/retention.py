"""Explicit, bounded retention for SolarInspector time-series data."""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Mapping

DEFAULT_RETENTION_BATCH_ROWS: Final = 1_000
MAXIMUM_RETENTION_BATCH_ROWS: Final = 10_000
DEFAULT_RETENTION_CONFIG: Final[dict[str, object]] = {
    "enabled": False,
    "raw_high_resolution_days": 30.0,
    "validation_events_days": 365.0,
    "source_selection_events_days": 90.0,
    "batch_rows": DEFAULT_RETENTION_BATCH_ROWS,
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionPolicy:
    """Configure opt-in deletion of expired persisted history.

    Args:
        enabled: Whether cleanup may delete data. The safe default is false.
        raw_high_resolution_days: Age of parent samples and all cascading
            detail data in days, or ``None`` to retain indefinitely.
        validation_events_days: Age of validation events in days, or ``None``.
        source_selection_events_days: Age of source decisions in days, or
            ``None``.
        batch_rows: Maximum rows deleted from each category per invocation.

    Raises:
        ValueError: If a configured age or batch size is outside safe bounds.
    """

    enabled: bool = False
    raw_high_resolution_days: float | None = None
    validation_events_days: float | None = None
    source_selection_events_days: float | None = None
    batch_rows: int = DEFAULT_RETENTION_BATCH_ROWS

    def __post_init__(self) -> None:
        for name, value in (
            ("raw_high_resolution_days", self.raw_high_resolution_days),
            ("validation_events_days", self.validation_events_days),
            (
                "source_selection_events_days",
                self.source_selection_events_days,
            ),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise ValueError(f"{name} must be a positive number or null")
            if value is not None and (not math.isfinite(float(value)) or value <= 0):
                raise ValueError(f"{name} must be greater than zero")
        if (
            isinstance(self.batch_rows, bool)
            or not isinstance(self.batch_rows, int)
            or not 1 <= self.batch_rows <= MAXIMUM_RETENTION_BATCH_ROWS
        ):
            raise ValueError(
                f"batch_rows must be between 1 and {MAXIMUM_RETENTION_BATCH_ROWS}"
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object] | None) -> RetentionPolicy:
        """Build a policy from optional configuration without implicit deletion.

        Args:
            raw: Retention configuration. Missing configuration returns the
                disabled default. Unknown fields are ignored for forward
                compatibility.

        Returns:
            A validated immutable policy.

        Raises:
            ValueError: If a known setting has an invalid type or range.
        """

        if raw is None:
            return cls()
        enabled = raw.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        return cls(
            enabled=enabled,
            raw_high_resolution_days=_optional_days(
                raw.get("raw_high_resolution_days"),
                "raw_high_resolution_days",
            ),
            validation_events_days=_optional_days(
                raw.get("validation_events_days"),
                "validation_events_days",
            ),
            source_selection_events_days=_optional_days(
                raw.get("source_selection_events_days"),
                "source_selection_events_days",
            ),
            batch_rows=_batch_rows(raw.get("batch_rows")),
        )


@dataclass(frozen=True)
class RetentionResult:
    """Report committed deletion counts from one retention transaction."""

    raw_samples_deleted: int = 0
    validation_events_deleted: int = 0
    source_selection_events_deleted: int = 0

    @property
    def total_deleted(self) -> int:
        """Return the number of explicitly deleted rows.

        Cascading child rows of raw samples are intentionally not counted
        because SQLite does not expose those counts reliably.
        """

        return (
            self.raw_samples_deleted
            + self.validation_events_deleted
            + self.source_selection_events_deleted
        )


def apply_retention(
    connection: sqlite3.Connection,
    policy: RetentionPolicy,
    *,
    reference_time: datetime,
) -> RetentionResult:
    """Delete one bounded batch per enabled retention category atomically.

    Args:
        connection: Open SQLite connection with foreign keys enabled. It must
            not already have a transaction.
        policy: Explicit cleanup policy. A disabled policy is a strict no-op.
        reference_time: Timezone-aware clock used to calculate all cutoffs.

    Returns:
        Counts committed for parent samples and independent event tables.

    Raises:
        ValueError: If the clock is naive or a transaction is already active.
        sqlite3.DatabaseError: If cleanup fails. All category deletions are
            rolled back before the error is propagated.

    Side Effects:
        With an enabled policy, starts one ``BEGIN IMMEDIATE`` transaction and
        commits at most ``batch_rows`` per configured category. It never runs
        ``VACUUM`` and does not delete rows exactly on a cutoff.
    """

    if reference_time.utcoffset() is None:
        raise ValueError("retention reference_time must be timezone-aware")
    if connection.in_transaction:
        raise ValueError("retention requires a connection without a transaction")
    if not policy.enabled:
        return RetentionResult()

    reference_utc = reference_time.astimezone(timezone.utc)
    try:
        connection.execute("BEGIN IMMEDIATE")
        selection_count = _delete_source_selection_events(
            connection,
            policy=policy,
            reference_utc=reference_utc,
        )
        validation_count = _delete_validation_events(
            connection,
            policy=policy,
            reference_utc=reference_utc,
        )
        sample_count = _delete_raw_samples(
            connection,
            policy=policy,
            reference_utc=reference_utc,
        )
        result = RetentionResult(
            raw_samples_deleted=sample_count,
            validation_events_deleted=validation_count,
            source_selection_events_deleted=selection_count,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    logger.info(
        "Phase 10 retention committed: raw_samples=%d validation_events=%d "
        "source_selection_events=%d batch_rows=%d",
        result.raw_samples_deleted,
        result.validation_events_deleted,
        result.source_selection_events_deleted,
        policy.batch_rows,
    )
    return result


def _delete_raw_samples(
    connection: sqlite3.Connection,
    *,
    policy: RetentionPolicy,
    reference_utc: datetime,
) -> int:
    if policy.raw_high_resolution_days is None:
        return 0
    cutoff_epoch = (
        reference_utc - timedelta(days=policy.raw_high_resolution_days)
    ).timestamp()
    cursor = connection.execute(
        """
        DELETE FROM samples
        WHERE id IN (
            SELECT id
            FROM samples
            WHERE ts_epoch < ?
            ORDER BY ts_epoch ASC
            LIMIT ?
        )
        """,
        (cutoff_epoch, policy.batch_rows),
    )
    return cursor.rowcount


def _delete_validation_events(
    connection: sqlite3.Connection,
    *,
    policy: RetentionPolicy,
    reference_utc: datetime,
) -> int:
    if policy.validation_events_days is None:
        return 0
    cutoff_epoch = (
        reference_utc - timedelta(days=policy.validation_events_days)
    ).timestamp()
    cursor = connection.execute(
        """
        DELETE FROM validation_events
        WHERE id IN (
            SELECT id
            FROM validation_events
            WHERE last_seen_epoch < ?
            ORDER BY last_seen_epoch ASC
            LIMIT ?
        )
        """,
        (cutoff_epoch, policy.batch_rows),
    )
    return cursor.rowcount


def _delete_source_selection_events(
    connection: sqlite3.Connection,
    *,
    policy: RetentionPolicy,
    reference_utc: datetime,
) -> int:
    if policy.source_selection_events_days is None:
        return 0
    cutoff = (
        reference_utc - timedelta(days=policy.source_selection_events_days)
    ).isoformat()
    cursor = connection.execute(
        """
        DELETE FROM source_selection_events
        WHERE id IN (
            SELECT id
            FROM source_selection_events
            WHERE selected_at < ?
            ORDER BY selected_at ASC
            LIMIT ?
        )
        """,
        (cutoff, policy.batch_rows),
    )
    return cursor.rowcount


def _optional_days(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number or null")
    return float(value)


def _batch_rows(value: object) -> int:
    if value is None:
        return DEFAULT_RETENTION_BATCH_ROWS
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("batch_rows must be an integer")
    return value
