"""Persist existing SolarInspector samples in SQLite.

This module preserves the schema, migrations, SQL queries, transaction
behavior, and filesystem behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, Iterator, Optional

from solarinspector_core.models.device import DeviceSnapshot
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.paths import DATA_DIR


class Database:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
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
        *,
        measurement_role: str = "house_total",
    ) -> int:
        """Atomically persist aggregate and normalized details."""

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

    def latest(self) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM samples ORDER BY ts_epoch DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def rows_between(
        self, start_epoch: float, end_epoch: float
    ) -> list[dict[str, Any]]:
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
        with self.connect() as conn:
            conn.execute("DELETE FROM grid_meter_samples")
            conn.execute("DELETE FROM phase_samples")
            conn.execute("DELETE FROM samples")
            conn.commit()
            conn.execute("VACUUM")


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
