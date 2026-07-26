"""Tests for explicit and bounded Phase 10 retention."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from solarinspector_core.config.manager import ConfigManager
from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.migrations import apply_migrations
from solarinspector_core.persistence.retention import (
    MAXIMUM_RETENTION_BATCH_ROWS,
    RetentionPolicy,
    apply_retention,
)

NOW = datetime(2026, 7, 26, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    """Create a target-schema database with expired and current rows."""

    result = Database(tmp_path / "retention.db")
    with result.connect() as connection:
        apply_migrations(connection, application_version="4.5.0")
        for days_old in (40, 39, 38, 30, 1):
            timestamp = NOW - timedelta(days=days_old)
            cursor = connection.execute(
                "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
                (timestamp.timestamp(), timestamp.isoformat()),
            )
            sample_id = int(cursor.lastrowid or 0)
            connection.execute(
                """
                INSERT INTO measurements (
                    sample_id, source_id, role, metric, value, unit,
                    measured_at, received_at, quality, device_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    "grid",
                    "grid",
                    "grid_power",
                    0.0,
                    "W",
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    "measured",
                    "available",
                ),
            )
            connection.execute(
                """
                INSERT INTO source_selection_events (
                    sample_id, selected_at, metric, selected_quality,
                    fallback_used, selection_reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    timestamp.isoformat(),
                    "grid_power",
                    "measured",
                    0,
                    "primary_selected",
                ),
            )
        for days_old in (400, 365, 1):
            timestamp = NOW - timedelta(days=days_old)
            connection.execute(
                """
                INSERT INTO validation_events (
                    first_seen_epoch, first_seen_local, last_seen_epoch,
                    last_seen_local, source_id, role, metric, unit, rule_id,
                    finding_code, severity, decision, quality, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.timestamp(),
                    timestamp.isoformat(),
                    timestamp.timestamp(),
                    timestamp.isoformat(),
                    "grid",
                    "grid",
                    "grid_power",
                    "W",
                    "range",
                    f"old-{days_old}",
                    "warning",
                    "accept",
                    "suspect",
                    "test",
                ),
            )
        connection.commit()
    return result


def test_missing_or_disabled_policy_is_strict_no_op(database: Database) -> None:
    with database.connect() as connection:
        before = _counts(connection)
        assert RetentionPolicy.from_mapping(None) == RetentionPolicy()
        result = apply_retention(
            connection,
            RetentionPolicy(
                raw_high_resolution_days=30,
                validation_events_days=365,
                source_selection_events_days=30,
            ),
            reference_time=NOW,
        )

        assert result.total_deleted == 0
        assert _counts(connection) == before


def test_retention_is_bounded_half_open_and_repeatable(database: Database) -> None:
    policy = RetentionPolicy(
        enabled=True,
        raw_high_resolution_days=30,
        validation_events_days=365,
        source_selection_events_days=30,
        batch_rows=2,
    )

    with database.connect() as connection:
        first = apply_retention(connection, policy, reference_time=NOW)
        second = apply_retention(connection, policy, reference_time=NOW)
        stable = apply_retention(connection, policy, reference_time=NOW)

        assert first.raw_samples_deleted == 2
        assert first.validation_events_deleted == 1
        assert first.source_selection_events_deleted == 2
        assert second.raw_samples_deleted == 1
        assert second.validation_events_deleted == 0
        assert second.source_selection_events_deleted == 1
        assert stable.total_deleted == 0
        # The exact cutoff and current row survive; child rows cascade with parents.
        assert _counts(connection) == (2, 2, 2, 2)
        oldest_remaining = connection.execute(
            "SELECT MIN(ts_epoch) FROM samples"
        ).fetchone()[0]
        assert oldest_remaining == (NOW - timedelta(days=30)).timestamp()


def test_retention_failure_rolls_back_every_category(database: Database) -> None:
    policy = RetentionPolicy(
        enabled=True,
        raw_high_resolution_days=30,
        validation_events_days=365,
        source_selection_events_days=30,
    )
    with database.connect() as connection:
        before = _counts(connection)
        connection.execute(
            """
            CREATE TRIGGER reject_sample_retention
            BEFORE DELETE ON samples
            BEGIN
                SELECT RAISE(ABORT, 'retention test failure');
            END
            """
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="retention test failure"):
            apply_retention(connection, policy, reference_time=NOW)

        assert not connection.in_transaction
        assert _counts(connection) == before


@pytest.mark.parametrize(
    "policy",
    [
        {"enabled": "yes"},
        {"enabled": True, "raw_high_resolution_days": 0},
        {"enabled": True, "validation_events_days": float("nan")},
        {"enabled": True, "source_selection_events_days": True},
        {"enabled": True, "batch_rows": 0},
        {"enabled": True, "batch_rows": MAXIMUM_RETENTION_BATCH_ROWS + 1},
    ],
)
def test_policy_rejects_unsafe_configuration(policy: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RetentionPolicy.from_mapping(policy)


def test_legacy_configuration_receives_disabled_retention_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"general": {"site_name": "Legacy"}}', encoding="utf-8")

    retention = ConfigManager(path).get()["persistence"]["retention"]

    assert retention == {
        "enabled": False,
        "raw_high_resolution_days": 30.0,
        "validation_events_days": 365.0,
        "source_selection_events_days": 90.0,
        "batch_rows": 1_000,
    }


def test_retention_rejects_naive_clock_and_existing_transaction(
    database: Database,
) -> None:
    policy = RetentionPolicy(enabled=True, raw_high_resolution_days=30)
    with database.connect() as connection:
        with pytest.raises(ValueError, match="timezone-aware"):
            apply_retention(
                connection,
                policy,
                reference_time=NOW.replace(tzinfo=None),
            )

        connection.execute("BEGIN")
        with pytest.raises(ValueError, match="without a transaction"):
            apply_retention(connection, policy, reference_time=NOW)
        connection.rollback()


def _counts(connection: sqlite3.Connection) -> tuple[int, int, int, int]:
    return tuple(
        int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "samples",
            "measurements",
            "source_selection_events",
            "validation_events",
        )
    )
