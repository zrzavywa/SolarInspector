"""Persist existing SolarInspector samples in SQLite.

This module preserves the schema, migrations, SQL queries, transaction
behavior, and filesystem behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

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
            conn.commit()

    def insert_sample(self, sample: dict[str, Any]) -> int:
        columns = list(sample.keys())
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT INTO samples ({','.join(columns)}) VALUES ({placeholders})"
        with self.connect() as conn:
            cursor = conn.execute(sql, [sample[column] for column in columns])
            conn.commit()
            return int(cursor.lastrowid)

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
            conn.execute("DELETE FROM samples")
            conn.commit()
            conn.execute("VACUUM")
