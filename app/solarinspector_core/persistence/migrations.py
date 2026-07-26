"""Plan, record, and verify forward-only SQLite schema migrations.

This module owns schema-version metadata and structural verification. It does
not create backups, expose command-line behavior, open database files, or run
migrations during application startup. Those side effects are integrated only
after the dedicated Phase 10 backup and startup work packages.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

TARGET_SCHEMA_VERSION: Final = 2
"""Latest schema version understood by this application."""

_SCHEMA_MIGRATIONS_TABLE_SQL: Final = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version >= 1),
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL,
    application_version TEXT NOT NULL,
    checksum TEXT NOT NULL
)
"""

_MIGRATION_FINDINGS_TABLE_SQL: Final = """
CREATE TABLE migration_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_version INTEGER NOT NULL,
    finding_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    table_name TEXT,
    column_name TEXT,
    source_row_id INTEGER,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
)
"""

_LEGACY_SAMPLE_COLUMNS: Final = frozenset(
    {
        "id",
        "ts_epoch",
        "ts_local",
        "grid_power_w",
        "solar_power_w",
        "house_power_w",
        "grid_import_w",
        "feed_in_w",
        "self_consumption_w",
        "voltage_v",
        "current_a",
        "power_factor",
        "frequency_hz",
        "grid_import_wh",
        "feed_in_wh",
        "solar_wh",
        "house_wh",
        "self_consumption_wh",
        "house_ok",
        "solar_ok",
        "error_text",
    }
)

_ADDITIONAL_SAMPLE_COLUMNS: Final[dict[str, str]] = {
    "shelly_solar_power_w": "REAL",
    "solakon_pv_power_w": "REAL",
    "solakon_ac_power_w": "REAL",
    "solakon_battery_power_w": "REAL",
    "solakon_battery_soc_pct": "REAL",
    "solakon_load_power_w": "REAL",
    "solakon_meter_power_w": "REAL",
    "solakon_temperature_c": "REAL",
    "solakon_daily_pv_kwh": "REAL",
    "solakon_total_pv_kwh": "REAL",
    "solakon_pv1_power_w": "REAL",
    "solakon_pv2_power_w": "REAL",
    "solakon_pv3_power_w": "REAL",
    "solakon_pv4_power_w": "REAL",
    "solar_difference_w": "REAL",
    "solar_difference_pct": "REAL",
    "solar_source": "TEXT",
    "grid_source": "TEXT",
    "solakon_model": "TEXT",
    "solakon_serial": "TEXT",
    "solakon_status": "TEXT",
    "solakon_ok": "INTEGER",
    "shelly_solar_wh": "REAL",
    "solakon_pv_wh": "REAL",
    "solakon_ac_wh": "REAL",
    "battery_charge_wh": "REAL",
    "battery_discharge_wh": "REAL",
}

_PHASE_SAMPLE_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS phase_samples (
    sample_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    measurement_role TEXT NOT NULL,
    device_status TEXT NOT NULL,
    error_text TEXT,
    measured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    l1_power_w REAL,
    l1_voltage_v REAL,
    l1_current_a REAL,
    l1_power_factor REAL,
    l1_quality TEXT,
    l2_power_w REAL,
    l2_voltage_v REAL,
    l2_current_a REAL,
    l2_power_factor REAL,
    l2_quality TEXT,
    l3_power_w REAL,
    l3_voltage_v REAL,
    l3_current_a REAL,
    l3_power_factor REAL,
    l3_quality TEXT,
    phase_power_available_count INTEGER NOT NULL DEFAULT 0,
    phase_power_complete INTEGER NOT NULL DEFAULT 0,
    phase_power_total_source TEXT,
    phase_power_sum_w REAL,
    phase_power_spread_w REAL,
    phase_power_share_l1_pct REAL,
    phase_power_share_l2_pct REAL,
    phase_power_share_l3_pct REAL,
    phase_power_total_delta_w REAL,
    phase_power_total_delta_pct REAL,
    phase_power_total_consistent INTEGER,
    PRIMARY KEY (sample_id, source_id),
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
)
"""

_GRID_METER_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS grid_meter_samples (
    sample_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    adapter TEXT NOT NULL,
    active_source_id TEXT,
    device_status TEXT NOT NULL,
    quality TEXT,
    error_text TEXT,
    measured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    grid_power_w REAL,
    grid_power_quality TEXT,
    grid_import_power_w REAL,
    grid_import_power_quality TEXT,
    grid_export_power_w REAL,
    grid_export_power_quality TEXT,
    grid_import_total_kwh REAL,
    grid_import_total_quality TEXT,
    grid_export_total_kwh REAL,
    grid_export_total_quality TEXT,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
)
"""

_VALIDATION_EVENTS_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS validation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_seen_epoch REAL NOT NULL,
    first_seen_local TEXT NOT NULL,
    last_seen_epoch REAL NOT NULL,
    last_seen_local TEXT NOT NULL,
    source_id TEXT NOT NULL,
    role TEXT NOT NULL,
    metric TEXT NOT NULL,
    unit TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    finding_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    decision TEXT NOT NULL,
    quality TEXT NOT NULL,
    reason TEXT NOT NULL,
    raw_value_json TEXT NOT NULL DEFAULT 'null',
    accepted_value REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurrence_count INTEGER NOT NULL DEFAULT 1
        CHECK (occurrence_count >= 1),
    minimum_value REAL,
    maximum_value REAL,
    first_sample_id INTEGER,
    last_sample_id INTEGER
)
"""

_ENERGY_BALANCE_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS energy_balance_samples (
    sample_id INTEGER PRIMARY KEY,
    calculated_at TEXT NOT NULL,
    quality TEXT NOT NULL,
    house_power_w REAL,
    grid_power_w REAL,
    grid_import_power_w REAL,
    grid_export_power_w REAL,
    plant_ac_power_w REAL,
    pv_power_w REAL,
    battery_charge_power_w REAL,
    battery_discharge_power_w REAL,
    battery_soc_percent REAL,
    self_consumed_power_w REAL,
    self_consumption_rate_percent REAL,
    autonomy_rate_percent REAL,
    residual_power_w REAL,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    findings_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
)
"""

_MEASUREMENTS_TABLE_SQL: Final = """
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    role TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    quality TEXT NOT NULL,
    device_status TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE,
    UNIQUE (sample_id, source_id, role, metric)
)
"""

_SOURCE_SELECTION_EVENTS_TABLE_SQL: Final = """
CREATE TABLE source_selection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER NOT NULL,
    selected_at TEXT NOT NULL,
    metric TEXT NOT NULL,
    selected_source_id TEXT,
    selected_source_role TEXT,
    selected_quality TEXT NOT NULL,
    fallback_used INTEGER NOT NULL CHECK (fallback_used IN (0, 1)),
    selection_reason TEXT NOT NULL,
    rejected_candidates_json TEXT NOT NULL DEFAULT '[]'
        CHECK (length(rejected_candidates_json) <= 16384),
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE,
    UNIQUE (sample_id, metric)
)
"""

_PHASE09_SCHEMA_SQL: Final = (
    _PHASE_SAMPLE_TABLE_SQL,
    _GRID_METER_TABLE_SQL,
    _VALIDATION_EVENTS_TABLE_SQL,
    _ENERGY_BALANCE_TABLE_SQL,
)

_REQUIRED_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "samples": frozenset(
        {
            "id",
            "ts_epoch",
            "ts_local",
            "grid_power_w",
            "solar_power_w",
            "house_power_w",
            "grid_import_w",
            "feed_in_w",
            "self_consumption_w",
            "voltage_v",
            "current_a",
            "power_factor",
            "frequency_hz",
            "grid_import_wh",
            "feed_in_wh",
            "solar_wh",
            "house_wh",
            "self_consumption_wh",
            "house_ok",
            "solar_ok",
            "error_text",
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
            "solar_source",
            "grid_source",
            "solakon_model",
            "solakon_serial",
            "solakon_status",
            "solakon_ok",
            "shelly_solar_wh",
            "solakon_pv_wh",
            "solakon_ac_wh",
            "battery_charge_wh",
            "battery_discharge_wh",
        }
    ),
    "phase_samples": frozenset(
        {
            "sample_id",
            "source_id",
            "measurement_role",
            "device_status",
            "error_text",
            "measured_at",
            "received_at",
            "metadata_json",
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
            "phase_power_total_source",
            "phase_power_sum_w",
            "phase_power_spread_w",
            "phase_power_share_l1_pct",
            "phase_power_share_l2_pct",
            "phase_power_share_l3_pct",
            "phase_power_total_delta_w",
            "phase_power_total_delta_pct",
            "phase_power_total_consistent",
        }
    ),
    "grid_meter_samples": frozenset(
        {
            "sample_id",
            "source_id",
            "source_name",
            "adapter",
            "active_source_id",
            "device_status",
            "quality",
            "error_text",
            "measured_at",
            "received_at",
            "metadata_json",
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
        }
    ),
    "validation_events": frozenset(
        {
            "id",
            "first_seen_epoch",
            "first_seen_local",
            "last_seen_epoch",
            "last_seen_local",
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
            "raw_value_json",
            "accepted_value",
            "details_json",
            "occurrence_count",
            "minimum_value",
            "maximum_value",
            "first_sample_id",
            "last_sample_id",
        }
    ),
    "energy_balance_samples": frozenset(
        {
            "sample_id",
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
            "source_metadata_json",
            "findings_json",
        }
    ),
    "schema_migrations": frozenset(
        {
            "version",
            "applied_at",
            "description",
            "application_version",
            "checksum",
        }
    ),
    "migration_findings": frozenset(
        {
            "id",
            "migration_version",
            "finding_code",
            "severity",
            "table_name",
            "column_name",
            "source_row_id",
            "details_json",
            "created_at",
        }
    ),
    "measurements": frozenset(
        {
            "id",
            "sample_id",
            "source_id",
            "role",
            "metric",
            "value",
            "unit",
            "measured_at",
            "received_at",
            "quality",
            "device_status",
        }
    ),
    "source_selection_events": frozenset(
        {
            "id",
            "sample_id",
            "selected_at",
            "metric",
            "selected_source_id",
            "selected_source_role",
            "selected_quality",
            "fallback_used",
            "selection_reason",
            "rejected_candidates_json",
        }
    ),
}

_REQUIRED_INDEXES: Final = frozenset(
    {
        "idx_samples_ts_epoch",
        "idx_phase_samples_source_sample",
        "idx_grid_meter_samples_source_sample",
        "idx_validation_events_last_seen",
        "idx_validation_events_identity",
        "idx_energy_balance_samples_quality_sample",
        "idx_migration_findings_version_code",
        "idx_measurements_metric_measured_at",
        "idx_measurements_source_metric_measured_at",
        "idx_source_selection_events_metric_selected_at",
    }
)


class DatabaseSchemaError(RuntimeError):
    """Base class for incompatible or invalid database schemas."""


class UnsupportedSchemaVersionError(DatabaseSchemaError):
    """Indicate that a database schema is newer than this application."""


class SchemaVerificationError(DatabaseSchemaError):
    """Indicate that schema objects do not match their recorded version."""


@dataclass(frozen=True)
class Migration:
    """Describe one ordered, forward-only schema migration.

    Attributes:
        version: Positive target version written by this migration.
        description: Stable human-readable purpose.
        checksum: SHA-256 digest of the migration definition.
        apply: Function that changes an open SQLite connection using the
            migration timestamp. The caller owns the encompassing transaction.
    """

    version: int
    description: str
    checksum: str
    apply: Callable[[sqlite3.Connection, str], None]


def _migrate_version_1(
    connection: sqlite3.Connection,
    applied_at: str,
) -> None:
    """Migrate a known unversioned 4.1.x or Phase 05–09 schema to version 1.

    The migration preserves the wide ``samples`` table and every source row.
    Later columns are added as nullable so missing historical measurements do
    not become artificial zeroes. No normalized detail row is synthesized.
    """

    sample_columns = _table_columns(connection, "samples")
    if not _LEGACY_SAMPLE_COLUMNS <= sample_columns:
        missing_columns = sorted(_LEGACY_SAMPLE_COLUMNS - sample_columns)
        raise SchemaVerificationError(
            "Unversioned database does not match the known 4.1.x samples "
            f"schema; missing columns: {', '.join(missing_columns)}."
        )

    connection.execute(_SCHEMA_MIGRATIONS_TABLE_SQL)
    connection.execute(_MIGRATION_FINDINGS_TABLE_SQL)
    connection.execute(
        """
        CREATE INDEX idx_migration_findings_version_code
        ON migration_findings(migration_version, finding_code)
        """
    )

    known_sample_columns = _LEGACY_SAMPLE_COLUMNS | frozenset(
        _ADDITIONAL_SAMPLE_COLUMNS
    )
    for column_name in sorted(sample_columns - known_sample_columns):
        _insert_migration_finding(
            connection,
            finding_code="unknown_legacy_column",
            severity="warning",
            table_name="samples",
            column_name=column_name,
            source_row_id=None,
            details={"action": "preserved_without_interpretation"},
            created_at=applied_at,
        )

    for column_name, definition in _ADDITIONAL_SAMPLE_COLUMNS.items():
        if column_name not in sample_columns:
            # Names and definitions come only from this reviewed constant.
            connection.execute(
                f"ALTER TABLE samples ADD COLUMN {column_name} {definition}"
            )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_samples_ts_epoch ON samples(ts_epoch)"
    )
    for statement in _PHASE09_SCHEMA_SQL:
        connection.execute(statement)
    _create_phase09_indexes(connection)
    _record_uninterpretable_timestamps(connection, created_at=applied_at)


def _create_phase09_indexes(connection: sqlite3.Connection) -> None:
    """Create the characterized Phase 05–09 access-path indexes."""

    statements = (
        """
        CREATE INDEX IF NOT EXISTS idx_phase_samples_source_sample
        ON phase_samples(source_id, sample_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_grid_meter_samples_source_sample
        ON grid_meter_samples(source_id, sample_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_validation_events_last_seen
        ON validation_events(last_seen_epoch DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_validation_events_identity
        ON validation_events(
            source_id,
            role,
            metric,
            rule_id,
            finding_code,
            decision,
            last_seen_epoch
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_energy_balance_samples_quality_sample
        ON energy_balance_samples(quality, sample_id)
        """,
    )
    for statement in statements:
        connection.execute(statement)


def _record_uninterpretable_timestamps(
    connection: sqlite3.Connection,
    *,
    created_at: str,
) -> None:
    """Record legacy timestamps that are not timezone-aware ISO-8601 values."""

    rows = connection.execute("SELECT id, ts_local FROM samples ORDER BY id").fetchall()
    for source_row_id, timestamp_text in rows:
        try:
            timestamp = datetime.fromisoformat(str(timestamp_text))
        except ValueError:
            timestamp = None
        if timestamp is not None and timestamp.utcoffset() is not None:
            continue
        _insert_migration_finding(
            connection,
            finding_code="uninterpretable_legacy_timestamp",
            severity="warning",
            table_name="samples",
            column_name="ts_local",
            source_row_id=int(source_row_id),
            details={"action": "preserved_without_conversion"},
            created_at=created_at,
        )


def _insert_migration_finding(
    connection: sqlite3.Connection,
    *,
    finding_code: str,
    severity: str,
    table_name: str | None,
    column_name: str | None,
    source_row_id: int | None,
    details: dict[str, str],
    created_at: str,
) -> None:
    """Insert one bounded, non-sensitive migration diagnostic."""

    connection.execute(
        """
        INSERT INTO migration_findings (
            migration_version,
            finding_code,
            severity,
            table_name,
            column_name,
            source_row_id,
            details_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            finding_code,
            severity,
            table_name,
            column_name,
            source_row_id,
            json.dumps(details, sort_keys=True, separators=(",", ":")),
            created_at,
        ),
    )


def _migrate_version_2(
    connection: sqlite3.Connection,
    _applied_at: str,
) -> None:
    """Add normalized measurement and source-selection time series."""

    connection.execute(_MEASUREMENTS_TABLE_SQL)
    connection.execute(
        """
        CREATE INDEX idx_measurements_metric_measured_at
        ON measurements(metric, measured_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_measurements_source_metric_measured_at
        ON measurements(source_id, metric, measured_at)
        """
    )
    connection.execute(_SOURCE_SELECTION_EVENTS_TABLE_SQL)
    connection.execute(
        """
        CREATE INDEX idx_source_selection_events_metric_selected_at
        ON source_selection_events(metric, selected_at)
        """
    )


_MIGRATIONS: Final = (
    Migration(
        version=1,
        description="Migrate known unversioned schemas to the Phase 09 baseline.",
        checksum=hashlib.sha256(
            "\n".join(
                (
                    _SCHEMA_MIGRATIONS_TABLE_SQL,
                    _MIGRATION_FINDINGS_TABLE_SQL,
                    *_PHASE09_SCHEMA_SQL,
                    repr(_ADDITIONAL_SAMPLE_COLUMNS),
                )
            ).encode("utf-8")
        ).hexdigest(),
        apply=_migrate_version_1,
    ),
    Migration(
        version=2,
        description="Add normalized measurements and source-selection events.",
        checksum=hashlib.sha256(
            "\n".join(
                (
                    _MEASUREMENTS_TABLE_SQL,
                    _SOURCE_SELECTION_EVENTS_TABLE_SQL,
                )
            ).encode("utf-8")
        ).hexdigest(),
        apply=_migrate_version_2,
    ),
)


def get_target_version() -> int:
    """Return the latest schema version understood by this application."""

    return TARGET_SCHEMA_VERSION


def get_current_version(connection: sqlite3.Connection) -> int:
    """Return the latest recorded schema version.

    Args:
        connection: Open SQLite connection used for the read.

    Returns:
        Zero for an unversioned database, otherwise the latest applied version.

    Raises:
        SchemaVerificationError: If the migration ledger has gaps, duplicate
            semantics, or does not match the known migration definitions.
        UnsupportedSchemaVersionError: If the database is newer than this
            application.

    Side Effects:
        Reads schema metadata and migration rows.
    """

    if not _table_exists(connection, "schema_migrations"):
        return 0

    rows = connection.execute(
        """
        SELECT version, description, checksum
        FROM schema_migrations
        ORDER BY version
        """
    ).fetchall()
    versions = [int(row[0]) for row in rows]
    if not versions:
        raise SchemaVerificationError("The schema migration ledger is empty.")
    if versions != list(range(1, versions[-1] + 1)):
        raise SchemaVerificationError(
            "The schema migration ledger is not a contiguous sequence."
        )
    if versions[-1] > TARGET_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            "Database schema version "
            f"{versions[-1]} is newer than supported version "
            f"{TARGET_SCHEMA_VERSION}."
        )

    known_applied_migrations = _MIGRATIONS[: len(rows)]
    for row, migration in zip(rows, known_applied_migrations, strict=True):
        if row[1] != migration.description or row[2] != migration.checksum:
            raise SchemaVerificationError(
                f"Schema migration {row[0]} does not match its definition."
            )
    return versions[-1]


def plan_migrations(current_version: int) -> tuple[Migration, ...]:
    """Plan ordered migrations after a known current version.

    Args:
        current_version: Non-negative application schema version.

    Returns:
        Pending migrations in ascending version order.

    Raises:
        ValueError: If ``current_version`` is negative.
        UnsupportedSchemaVersionError: If the version is newer than supported.
    """

    if current_version < 0:
        raise ValueError("Current schema version must not be negative.")
    if current_version > TARGET_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            "Database schema version "
            f"{current_version} is newer than supported version "
            f"{TARGET_SCHEMA_VERSION}."
        )
    return tuple(
        migration for migration in _MIGRATIONS if migration.version > current_version
    )


def apply_migrations(
    connection: sqlite3.Connection,
    *,
    application_version: str,
    applied_at: datetime | None = None,
) -> tuple[Migration, ...]:
    """Apply and verify pending migrations in one transaction.

    Version 1 migrates the known 4.1.x wide schema and additive Phase 05–09
    intermediate shapes. It never synthesizes missing historical values.

    Args:
        connection: Open SQLite connection. It must not already be inside a
            transaction.
        application_version: Non-empty application version recorded for audit.
        applied_at: Optional timezone-aware execution time. Defaults to UTC now.

    Returns:
        The migrations committed by this call, or an empty tuple when current.

    Raises:
        ValueError: If inputs are invalid or a transaction is already active.
        DatabaseSchemaError: If the version or schema is incompatible.
        sqlite3.DatabaseError: If SQLite cannot apply the migration.

    Side Effects:
        Creates schema objects and commits them atomically. Any failure rolls
        back all changes made by this call.
    """

    normalized_application_version = application_version.strip()
    if not normalized_application_version:
        raise ValueError("Application version must not be empty.")
    if connection.in_transaction:
        raise ValueError("Migration requires a connection without a transaction.")

    execution_time = applied_at or datetime.now(timezone.utc)
    if execution_time.utcoffset() is None:
        raise ValueError("Migration timestamp must be timezone-aware.")
    execution_time_utc = execution_time.astimezone(timezone.utc).isoformat()

    current_version = get_current_version(connection)
    pending = plan_migrations(current_version)
    if not pending:
        verify_schema(connection)
        return ()

    try:
        connection.execute("BEGIN IMMEDIATE")
        for migration in pending:
            migration.apply(connection, execution_time_utc)
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    version,
                    applied_at,
                    description,
                    application_version,
                    checksum
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    migration.version,
                    execution_time_utc,
                    migration.description,
                    normalized_application_version,
                    migration.checksum,
                ),
            )
        verify_schema(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return pending


def verify_schema(connection: sqlite3.Connection) -> None:
    """Verify the recorded version and required Phase 09 schema objects.

    Args:
        connection: Open SQLite connection used for metadata reads.

    Raises:
        DatabaseSchemaError: If the version ledger, required tables, columns,
            indexes, or foreign keys are missing or incompatible.

    Side Effects:
        Reads SQLite schema metadata without changing the database.
    """

    current_version = get_current_version(connection)
    if current_version != TARGET_SCHEMA_VERSION:
        raise SchemaVerificationError(
            f"Schema version {current_version} is not target version "
            f"{TARGET_SCHEMA_VERSION}."
        )

    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        actual_columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise SchemaVerificationError(
                f"Table {table_name} is missing columns: {', '.join(missing_columns)}."
            )

    actual_indexes = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    }
    missing_indexes = sorted(_REQUIRED_INDEXES - actual_indexes)
    if missing_indexes:
        raise SchemaVerificationError(
            f"Schema is missing indexes: {', '.join(missing_indexes)}."
        )

    for child_table in (
        "phase_samples",
        "grid_meter_samples",
        "energy_balance_samples",
        "measurements",
        "source_selection_events",
    ):
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({child_table})"
        ).fetchall()
        if not any(
            row[2] == "samples"
            and row[3] == "sample_id"
            and row[4] == "id"
            and row[6] == "CASCADE"
            for row in foreign_keys
        ):
            raise SchemaVerificationError(
                f"Table {child_table} is missing its samples cascade."
            )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Return whether an application-owned table exists."""

    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_schema
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> frozenset[str]:
    """Return column names for one application-owned table."""

    return frozenset(
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
    )
