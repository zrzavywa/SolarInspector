"""Persist existing SolarInspector samples in SQLite.

This module preserves the schema, migrations, SQL queries, transaction
behavior, and filesystem behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import timezone
from pathlib import Path
from typing import Any, Final, Iterator, Optional

from zrzavy_energy_monitor_core.models.device import DeviceSnapshot
from zrzavy_energy_monitor_core.models.energy_balance import EnergyBalanceResult
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.source_selection import SourceSelectionResult


class Database:
    """Database groups the public state and operations for this component."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """connect provides the public operation implemented by this component."""
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """initialize performs the corresponding lifecycle or persistence operation."""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_epoch REAL NOT NULL,
                    ts_local TEXT NOT NULL,
                    grid_power_w REAL,
                    solar_power_w REAL,
                    house_power_w REAL,
                    grid_import_w REAL,
                    feed_in_w REAL,
                    self_consumption_w REAL,
                    voltage_v REAL,
                    current_a REAL,
                    power_factor REAL,
                    frequency_hz REAL,
                    grid_import_wh REAL NOT NULL DEFAULT 0,
                    feed_in_wh REAL NOT NULL DEFAULT 0,
                    solar_wh REAL NOT NULL DEFAULT 0,
                    house_wh REAL NOT NULL DEFAULT 0,
                    self_consumption_wh REAL NOT NULL DEFAULT 0,
                    house_ok INTEGER NOT NULL DEFAULT 0,
                    solar_ok INTEGER NOT NULL DEFAULT 0,
                    error_text TEXT
                )
                """
            )
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(samples)").fetchall()
            }
            additional_columns = {
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
                "solakon_ok": "INTEGER NOT NULL DEFAULT 0",
                "shelly_solar_wh": "REAL NOT NULL DEFAULT 0",
                "solakon_pv_wh": "REAL NOT NULL DEFAULT 0",
                "solakon_ac_wh": "REAL NOT NULL DEFAULT 0",
                "battery_charge_wh": "REAL NOT NULL DEFAULT 0",
                "battery_discharge_wh": "REAL NOT NULL DEFAULT 0",
            }
            for column, definition in additional_columns.items():
                if column not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE samples ADD COLUMN {column} {definition}"
                    )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_samples_ts_epoch ON samples(ts_epoch)"
            )
            conn.execute(
                """
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
                    FOREIGN KEY (sample_id) REFERENCES samples(id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_phase_samples_source_sample
                ON phase_samples(source_id, sample_id)
                """
            )
            conn.execute(
                """
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
                    FOREIGN KEY (sample_id) REFERENCES samples(id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_grid_meter_samples_source_sample
                ON grid_meter_samples(source_id, sample_id)
                """
            )
            conn.execute(
                """
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
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_validation_events_last_seen
                ON validation_events(last_seen_epoch DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_validation_events_identity
                ON validation_events(
                    source_id,
                    role,
                    metric,
                    rule_id,
                    finding_code,
                    decision,
                    last_seen_epoch
                )
                """
            )
            conn.execute(
                """
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
                    FOREIGN KEY (sample_id) REFERENCES samples(id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_energy_balance_samples_quality_sample
                ON energy_balance_samples(quality, sample_id)
                """
            )
            conn.commit()

    def insert_sample(self, sample: dict[str, Any]) -> int:
        """Insert one compatible aggregate sample."""

        return self.insert_sample_with_snapshots(sample)

    def insert_sample_with_phase_snapshot(
        self,
        sample: dict[str, Any],
        phase_snapshot: DeviceSnapshot | None = None,
        *,
        measurement_role: str = "house_total",
    ) -> int:
        """Retain the Phase-05 persistence interface."""

        return self.insert_sample_with_snapshots(
            sample,
            phase_snapshot=phase_snapshot,
            measurement_role=measurement_role,
        )

    def insert_sample_with_snapshots(
        self,
        sample: dict[str, Any],
        phase_snapshot: DeviceSnapshot | None = None,
        grid_meter_snapshot: DeviceSnapshot | None = None,
        measurement_snapshots: tuple[DeviceSnapshot, ...] = (),
        *,
        measurement_role: str = "house_total",
        energy_balance: EnergyBalanceResult | None = None,
        persist_source_decisions: bool = True,
    ) -> int:
        """Atomically persist aggregate and normalized details.

        Normalized time-series writes activate only after schema migration
        version 2. This keeps the persistence API backward-compatible until
        startup migration is integrated.
        """

        columns = list(sample.keys())
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT INTO samples ({','.join(columns)}) VALUES ({placeholders})"

        with self.connect() as conn:
            try:
                cursor = conn.execute(
                    sql,
                    [sample[column] for column in columns],
                )
                row_id = cursor.lastrowid
                if row_id is None:
                    raise RuntimeError("SQLite did not return an inserted sample ID.")
                sample_id = int(row_id)
                if phase_snapshot is not None:
                    self._insert_phase_snapshot(
                        conn,
                        sample_id=sample_id,
                        snapshot=phase_snapshot,
                        measurement_role=measurement_role,
                    )
                if grid_meter_snapshot is not None:
                    self._insert_grid_meter_snapshot(
                        conn,
                        sample_id=sample_id,
                        snapshot=grid_meter_snapshot,
                    )
                if energy_balance is not None:
                    self._insert_energy_balance(
                        conn,
                        sample_id=sample_id,
                        balance=energy_balance,
                        persist_source_decisions=persist_source_decisions,
                    )
                if _table_exists(conn, "measurements"):
                    self._insert_measurements(
                        conn,
                        sample_id=sample_id,
                        snapshots=measurement_snapshots,
                        energy_balance=energy_balance,
                    )
                if (
                    energy_balance is not None
                    and persist_source_decisions
                    and _table_exists(conn, "source_selection_events")
                ):
                    self._insert_source_selection_events(
                        conn,
                        sample_id=sample_id,
                        energy_balance=energy_balance,
                    )
                conn.commit()
                return sample_id
            except Exception:
                conn.rollback()
                raise

    def _insert_phase_snapshot(
        self,
        conn: sqlite3.Connection,
        *,
        sample_id: int,
        snapshot: DeviceSnapshot,
        measurement_role: str,
    ) -> None:
        """Insert one flattened phase snapshot in an existing transaction."""

        row = _phase_snapshot_row(
            sample_id=sample_id,
            snapshot=snapshot,
            measurement_role=measurement_role,
        )
        columns = list(row.keys())
        placeholders = ",".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO phase_samples ({','.join(columns)}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )

    def _insert_grid_meter_snapshot(
        self,
        conn: sqlite3.Connection,
        *,
        sample_id: int,
        snapshot: DeviceSnapshot,
    ) -> None:
        """Insert one normalized official grid-meter snapshot."""

        row = _grid_meter_snapshot_row(
            sample_id=sample_id,
            snapshot=snapshot,
        )
        columns = list(row.keys())
        placeholders = ",".join("?" for _ in columns)
        conn.execute(
            "INSERT INTO grid_meter_samples "
            f"({','.join(columns)}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )

    def _insert_energy_balance(
        self,
        conn: sqlite3.Connection,
        *,
        sample_id: int,
        balance: EnergyBalanceResult,
        persist_source_decisions: bool,
    ) -> None:
        """Insert one energy balance inside the aggregate transaction."""

        row = _energy_balance_row(
            sample_id=sample_id,
            balance=balance,
            persist_source_decisions=persist_source_decisions,
        )
        columns = list(row.keys())
        placeholders = ",".join("?" for _ in columns)
        conn.execute(
            "INSERT INTO energy_balance_samples "
            f"({','.join(columns)}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )

    def _insert_measurements(
        self,
        conn: sqlite3.Connection,
        *,
        sample_id: int,
        snapshots: tuple[DeviceSnapshot, ...],
        energy_balance: EnergyBalanceResult | None,
    ) -> None:
        """Store accepted normalized and calculated values for one cycle."""

        rows = [
            row
            for snapshot in snapshots
            for row in _measurement_rows(
                sample_id=sample_id,
                snapshot=snapshot,
            )
        ]
        if energy_balance is not None:
            rows.extend(
                _calculated_measurement_rows(
                    sample_id=sample_id,
                    balance=energy_balance,
                )
            )
        conn.executemany(
            """
            INSERT INTO measurements (
                sample_id,
                source_id,
                role,
                metric,
                value,
                unit,
                measured_at,
                received_at,
                quality,
                device_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _insert_source_selection_events(
        self,
        conn: sqlite3.Connection,
        *,
        sample_id: int,
        energy_balance: EnergyBalanceResult,
    ) -> None:
        """Store bounded Phase 09 source decisions for one cycle."""

        conn.executemany(
            """
            INSERT INTO source_selection_events (
                sample_id,
                selected_at,
                metric,
                selected_source_id,
                selected_source_role,
                selected_quality,
                fallback_used,
                selection_reason,
                rejected_candidates_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _source_selection_event_row(
                    sample_id=sample_id,
                    selection=selection,
                )
                for selection in energy_balance.source_metadata
            ),
        )

    def latest(self) -> Optional[dict[str, Any]]:
        """latest provides the public operation implemented by this component."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM samples ORDER BY ts_epoch DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def rows_between(
        self, start_epoch: float, end_epoch: float
    ) -> list[dict[str, Any]]:
        """rows_between provides the public operation implemented by this component."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM samples
                WHERE ts_epoch >= ? AND ts_epoch < ?
                ORDER BY ts_epoch
                """,
                (start_epoch, end_epoch),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_grid_meter_sample(
        self,
        source_id: str = "grid_meter_primary",
    ) -> Optional[dict[str, Any]]:
        """Return the newest official grid-meter detail row."""

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT grid_meter_samples.*,
                       samples.ts_epoch,
                       samples.ts_local,
                       samples.grid_source
                FROM grid_meter_samples
                JOIN samples
                  ON samples.id = grid_meter_samples.sample_id
                WHERE grid_meter_samples.source_id = ?
                ORDER BY samples.ts_epoch DESC
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def latest_energy_balance_sample(self) -> Optional[dict[str, Any]]:
        """Return the newest persisted energy-balance detail row."""

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT energy_balance_samples.*,
                       samples.ts_epoch,
                       samples.ts_local
                FROM energy_balance_samples
                JOIN samples
                  ON samples.id = energy_balance_samples.sample_id
                ORDER BY samples.ts_epoch DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def latest_phase_sample(
        self,
        source_id: str = "house_meter",
    ) -> Optional[dict[str, Any]]:
        """Return the newest persisted phase row for one source."""

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT phase_samples.*, samples.ts_epoch, samples.ts_local
                FROM phase_samples
                JOIN samples ON samples.id = phase_samples.sample_id
                WHERE phase_samples.source_id = ?
                ORDER BY samples.ts_epoch DESC
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def phase_rows_between(
        self,
        start_epoch: float,
        end_epoch: float,
        *,
        source_id: str = "house_meter",
    ) -> list[dict[str, Any]]:
        """Return phase rows in a lower-inclusive, upper-exclusive range."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT phase_samples.*, samples.ts_epoch, samples.ts_local
                FROM phase_samples
                JOIN samples ON samples.id = phase_samples.sample_id
                WHERE phase_samples.source_id = ?
                  AND samples.ts_epoch >= ?
                  AND samples.ts_epoch < ?
                ORDER BY samples.ts_epoch
                """,
                (source_id, start_epoch, end_epoch),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        """stats provides the public operation implemented by this component."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count,
                       MIN(ts_epoch) AS first_epoch,
                       MAX(ts_epoch) AS last_epoch
                FROM samples
                """
            ).fetchone()
        result = dict(row)
        result["db_size_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        return result

    def delete_all(self) -> None:
        """delete_all performs the corresponding lifecycle or persistence operation."""
        with self.connect() as conn:
            if _table_exists(conn, "source_selection_events"):
                conn.execute("DELETE FROM source_selection_events")
            if _table_exists(conn, "measurements"):
                conn.execute("DELETE FROM measurements")
            conn.execute("DELETE FROM validation_events")
            conn.execute("DELETE FROM energy_balance_samples")
            conn.execute("DELETE FROM grid_meter_samples")
            conn.execute("DELETE FROM phase_samples")
            conn.execute("DELETE FROM samples")
            conn.commit()
            conn.execute("VACUUM")


_COUNTER_METRICS: Final = frozenset(
    {
        Metric.GRID_IMPORT_TOTAL,
        Metric.GRID_EXPORT_TOTAL,
        Metric.PLANT_AC_ENERGY_TOTAL,
        Metric.PLANT_AC_RETURNED_ENERGY_TOTAL,
        Metric.PV_ENERGY_TODAY,
        Metric.PV_ENERGY_TOTAL,
        Metric.BATTERY_CHARGE_TOTAL,
        Metric.BATTERY_DISCHARGE_TOTAL,
    }
)

_UNUSABLE_TIME_SERIES_QUALITIES: Final = frozenset(
    {
        MeasurementQuality.REJECTED,
        MeasurementQuality.STALE,
        MeasurementQuality.UNAVAILABLE,
    }
)

_MAXIMUM_SELECTION_JSON_CHARACTERS: Final = 16_384


def _measurement_rows(
    *,
    sample_id: int,
    snapshot: DeviceSnapshot,
) -> list[tuple[object, ...]]:
    """Build accepted normalized time-series rows for one source snapshot."""

    rows: list[tuple[object, ...]] = []
    for measurement in snapshot.measurements:
        if measurement.quality in _UNUSABLE_TIME_SERIES_QUALITIES:
            continue
        is_counter = measurement.metric in _COUNTER_METRICS
        value = measurement.value / 1000.0 if is_counter else measurement.value
        unit = "kWh" if is_counter else measurement.unit.value
        rows.append(
            (
                sample_id,
                measurement.source_id,
                measurement.role.value,
                measurement.metric.value,
                value,
                unit,
                measurement.measured_at.astimezone(timezone.utc).isoformat(),
                measurement.received_at.astimezone(timezone.utc).isoformat(),
                measurement.quality.value,
                snapshot.status.value,
            )
        )
    return rows


def _calculated_measurement_rows(
    *,
    sample_id: int,
    balance: EnergyBalanceResult,
) -> list[tuple[object, ...]]:
    """Build non-missing calculated time-series rows for one energy balance."""

    calculated_at = balance.calculated_at.astimezone(timezone.utc).isoformat()
    values = (
        ("house_power", balance.house_power_w, "W"),
        ("self_consumed_power", balance.self_consumed_power_w, "W"),
        (
            "self_consumption_rate",
            balance.self_consumption_rate_percent,
            "%",
        ),
        ("autonomy_rate", balance.autonomy_rate_percent, "%"),
        (
            "energy_balance_residual_power",
            balance.residual_power_w,
            "W",
        ),
    )
    return [
        (
            sample_id,
            "energy_balance",
            "calculated",
            metric,
            value,
            unit,
            calculated_at,
            calculated_at,
            balance.quality.value,
            "calculated",
        )
        for metric, value, unit in values
        if value is not None
    ]


def _source_selection_event_row(
    *,
    sample_id: int,
    selection: SourceSelectionResult,
) -> tuple[object, ...]:
    """Build one bounded source-selection audit row."""

    rejected_candidates = [
        {
            "source_id": candidate.source_id,
            "source_role": (
                candidate.source_role.value
                if candidate.source_role is not None
                else None
            ),
            "quality": (
                candidate.quality.value if candidate.quality is not None else None
            ),
            "reason": candidate.reason.value,
            "measured_at": (
                candidate.measured_at.astimezone(timezone.utc).isoformat()
                if candidate.measured_at is not None
                else None
            ),
        }
        for candidate in selection.rejected_candidates
    ]
    rejected_candidates_json = _bounded_json_list(rejected_candidates)
    return (
        sample_id,
        selection.selection_timestamp.astimezone(timezone.utc).isoformat(),
        selection.requested_metric.value,
        selection.selected_source_id,
        (
            selection.selected_source_role.value
            if selection.selected_source_role is not None
            else None
        ),
        selection.selected_quality.value,
        int(selection.fallback_used),
        selection.selection_reason.value,
        rejected_candidates_json,
    )


def _bounded_json_list(values: list[dict[str, str | None]]) -> str:
    """Serialize a list within the schema's source-diagnostic size limit."""

    bounded_values = list(values)
    while bounded_values:
        encoded = json.dumps(
            bounded_values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(encoded) <= _MAXIMUM_SELECTION_JSON_CHARACTERS:
            return encoded
        bounded_values.pop()
    return "[]"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return whether one internal persistence table exists."""

    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_schema
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        is not None
    )


def _energy_balance_row(
    *,
    sample_id: int,
    balance: EnergyBalanceResult,
    persist_source_decisions: bool,
) -> dict[str, Any]:
    """Flatten one balance and safe explainability metadata."""

    source_metadata = (
        {
            selection.requested_metric.value: {
                "selected_source_id": selection.selected_source_id,
                "selected_source_role": (
                    selection.selected_source_role.value
                    if selection.selected_source_role is not None
                    else None
                ),
                "selected_quality": selection.selected_quality.value,
                "selection_reason": selection.selection_reason.value,
                "fallback_used": selection.fallback_used,
                "selected_measurement_timestamp": (
                    selection.selected_measurement_timestamp.isoformat()
                    if selection.selected_measurement_timestamp is not None
                    else None
                ),
                "selection_timestamp": selection.selection_timestamp.isoformat(),
                "rejected_candidates": [
                    {
                        "source_id": candidate.source_id,
                        "source_role": (
                            candidate.source_role.value
                            if candidate.source_role is not None
                            else None
                        ),
                        "quality": (
                            candidate.quality.value
                            if candidate.quality is not None
                            else None
                        ),
                        "reason": candidate.reason.value,
                        "measured_at": (
                            candidate.measured_at.isoformat()
                            if candidate.measured_at is not None
                            else None
                        ),
                    }
                    for candidate in selection.rejected_candidates
                ],
            }
            for selection in balance.source_metadata
        }
        if persist_source_decisions
        else {}
    )
    findings = [
        {
            "rule_id": finding.rule_id,
            "code": finding.code,
            "message": finding.message,
            "severity": finding.severity,
            "details": {
                key: _safe_balance_detail(key, value) for key, value in finding.details
            },
        }
        for finding in balance.findings
    ]
    return {
        "sample_id": sample_id,
        "calculated_at": balance.calculated_at.isoformat(),
        "quality": balance.quality.value,
        "house_power_w": balance.house_power_w,
        "grid_power_w": balance.grid_power_w,
        "grid_import_power_w": balance.grid_import_power_w,
        "grid_export_power_w": balance.grid_export_power_w,
        "plant_ac_power_w": balance.plant_ac_power_w,
        "pv_power_w": balance.pv_power_w,
        "battery_charge_power_w": balance.battery_charge_power_w,
        "battery_discharge_power_w": balance.battery_discharge_power_w,
        "battery_soc_percent": balance.battery_soc_percent,
        "self_consumed_power_w": balance.self_consumed_power_w,
        "self_consumption_rate_percent": (balance.self_consumption_rate_percent),
        "autonomy_rate_percent": balance.autonomy_rate_percent,
        "residual_power_w": balance.residual_power_w,
        "fallback_used": int(
            persist_source_decisions
            and any(selection.fallback_used for selection in balance.source_metadata)
        ),
        "source_metadata_json": json.dumps(
            source_metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "findings_json": json.dumps(
            findings,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _safe_balance_detail(key: str, value: object) -> object:
    """Serialize bounded primitive diagnostics and redact sensitive keys."""

    lowered = key.casefold()
    if any(
        marker in lowered
        for marker in (
            "password",
            "secret",
            "token",
            "credential",
            "authorization",
            "username",
            "host",
            "address",
            "url",
        )
    ):
        return "<redacted>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:256]
    return f"<unsupported:{type(value).__name__}>"


_PHASE_METRICS: Final[dict[str, tuple[Metric, Metric, Metric, Metric]]] = {
    "l1": (
        Metric.PHASE_POWER_L1,
        Metric.PHASE_VOLTAGE_L1,
        Metric.PHASE_CURRENT_L1,
        Metric.PHASE_POWER_FACTOR_L1,
    ),
    "l2": (
        Metric.PHASE_POWER_L2,
        Metric.PHASE_VOLTAGE_L2,
        Metric.PHASE_CURRENT_L2,
        Metric.PHASE_POWER_FACTOR_L2,
    ),
    "l3": (
        Metric.PHASE_POWER_L3,
        Metric.PHASE_VOLTAGE_L3,
        Metric.PHASE_CURRENT_L3,
        Metric.PHASE_POWER_FACTOR_L3,
    ),
}

_QUALITY_PRIORITY: Final[dict[MeasurementQuality, int]] = {
    MeasurementQuality.REJECTED: 9,
    MeasurementQuality.UNAVAILABLE: 8,
    MeasurementQuality.STALE: 7,
    MeasurementQuality.SUSPECT: 6,
    MeasurementQuality.FALLBACK: 5,
    MeasurementQuality.CALCULATED: 4,
    MeasurementQuality.VALIDATED: 3,
    MeasurementQuality.REPORTED: 2,
    MeasurementQuality.MEASURED: 1,
}


_GRID_METER_METRICS: Final[
    tuple[
        tuple[
            Metric,
            str,
            str,
            float,
        ],
        ...,
    ]
] = (
    (
        Metric.GRID_POWER,
        "grid_power_w",
        "grid_power_quality",
        1.0,
    ),
    (
        Metric.GRID_IMPORT_POWER,
        "grid_import_power_w",
        "grid_import_power_quality",
        1.0,
    ),
    (
        Metric.GRID_EXPORT_POWER,
        "grid_export_power_w",
        "grid_export_power_quality",
        1.0,
    ),
    (
        Metric.GRID_IMPORT_TOTAL,
        "grid_import_total_kwh",
        "grid_import_total_quality",
        1000.0,
    ),
    (
        Metric.GRID_EXPORT_TOTAL,
        "grid_export_total_kwh",
        "grid_export_total_quality",
        1000.0,
    ),
)


def _grid_meter_snapshot_row(
    *,
    sample_id: int,
    snapshot: DeviceSnapshot,
) -> dict[str, Any]:
    """Flatten one normalized official grid-meter snapshot."""

    metadata = dict(snapshot.metadata)
    measurements = {
        measurement.metric: measurement
        for measurement in snapshot.measurements
        if measurement.role is MeasurementRole.GRID_METER
    }
    measured_at = (
        min(measurement.measured_at for measurement in measurements.values())
        if measurements
        else snapshot.received_at
    )
    power_measurement = measurements.get(Metric.GRID_POWER)
    qualities = [measurement.quality for measurement in measurements.values()]
    overall_quality = (
        power_measurement.quality
        if power_measurement is not None
        else (
            max(
                qualities,
                key=lambda quality: _QUALITY_PRIORITY[quality],
            )
            if qualities
            else None
        )
    )

    row: dict[str, Any] = {
        "sample_id": sample_id,
        "source_id": snapshot.source_id,
        "source_name": (metadata.get("source_name") or "Offizieller Netzstromzähler"),
        "adapter": (metadata.get("adapter") or "tasmota_http"),
        "active_source_id": metadata.get("active_source_id"),
        "device_status": snapshot.status.value,
        "quality": (overall_quality.value if overall_quality is not None else None),
        "error_text": snapshot.error,
        "measured_at": measured_at.isoformat(),
        "received_at": snapshot.received_at.isoformat(),
        "metadata_json": json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }

    for (
        metric,
        value_column,
        quality_column,
        divisor,
    ) in _GRID_METER_METRICS:
        measurement = measurements.get(metric)
        row[value_column] = (
            float(measurement.value) / divisor if measurement is not None else None
        )
        row[quality_column] = (
            measurement.quality.value if measurement is not None else None
        )

    return row


def _phase_snapshot_row(
    *,
    sample_id: int,
    snapshot: DeviceSnapshot,
    measurement_role: str,
) -> dict[str, Any]:
    """Flatten normalized phase measurements without changing samples."""

    metadata = dict(snapshot.metadata)
    phase_measurements = tuple(
        measurement
        for measurement in snapshot.measurements
        if measurement.role is MeasurementRole.HOUSE_METER
    )
    measured_at = (
        min(measurement.measured_at for measurement in phase_measurements)
        if phase_measurements
        else snapshot.received_at
    )

    row: dict[str, Any] = {
        "sample_id": sample_id,
        "source_id": snapshot.source_id,
        "measurement_role": measurement_role,
        "device_status": snapshot.status.value,
        "error_text": snapshot.error,
        "measured_at": measured_at.isoformat(),
        "received_at": snapshot.received_at.isoformat(),
        "metadata_json": json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "phase_power_available_count": _metadata_int(
            metadata.get("phase_power_available_count"),
            default=0,
        ),
        "phase_power_complete": _metadata_bool_int(
            metadata.get("phase_power_complete"),
            default=0,
        ),
        "phase_power_total_source": metadata.get("phase_power_total_source"),
        "phase_power_sum_w": _metadata_float(metadata.get("phase_power_sum_w")),
        "phase_power_spread_w": _metadata_float(metadata.get("phase_power_spread_w")),
        "phase_power_share_l1_pct": _metadata_float(
            metadata.get("phase_power_share_l1_pct")
        ),
        "phase_power_share_l2_pct": _metadata_float(
            metadata.get("phase_power_share_l2_pct")
        ),
        "phase_power_share_l3_pct": _metadata_float(
            metadata.get("phase_power_share_l3_pct")
        ),
        "phase_power_total_delta_w": _metadata_float(
            metadata.get("phase_power_total_delta_w")
        ),
        "phase_power_total_delta_pct": _metadata_float(
            metadata.get("phase_power_total_delta_pct")
        ),
        "phase_power_total_consistent": _metadata_optional_bool_int(
            metadata.get("phase_power_total_consistent")
        ),
    }

    for phase, metrics in _PHASE_METRICS.items():
        power_metric, voltage_metric, current_metric, pf_metric = metrics
        row[f"{phase}_power_w"] = _phase_value(
            phase_measurements,
            power_metric,
        )
        row[f"{phase}_voltage_v"] = _phase_value(
            phase_measurements,
            voltage_metric,
        )
        row[f"{phase}_current_a"] = _phase_value(
            phase_measurements,
            current_metric,
        )
        row[f"{phase}_power_factor"] = _phase_value(
            phase_measurements,
            pf_metric,
        )
        row[f"{phase}_quality"] = _phase_quality(
            phase_measurements,
            metrics,
        )

    return row


def _phase_value(
    measurements: tuple[Any, ...],
    metric: Metric,
) -> float | None:
    """Return one phase metric without treating zero as unavailable."""

    for measurement in measurements:
        if measurement.metric is metric:
            return float(measurement.value)
    return None


def _phase_quality(
    measurements: tuple[Any, ...],
    metrics: tuple[Metric, Metric, Metric, Metric],
) -> str | None:
    """Return the most conservative quality emitted for one phase."""

    qualities = [
        measurement.quality
        for measurement in measurements
        if measurement.metric in metrics
    ]
    if not qualities:
        return None
    return max(
        qualities,
        key=lambda quality: _QUALITY_PRIORITY[quality],
    ).value


def _metadata_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metadata_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _metadata_bool_int(value: str | None, *, default: int) -> int:
    parsed = _metadata_optional_bool_int(value)
    return default if parsed is None else parsed


def _metadata_optional_bool_int(value: str | None) -> int | None:
    if value == "true":
        return 1
    if value == "false":
        return 0
    return None
