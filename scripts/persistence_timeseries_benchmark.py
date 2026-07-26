#!/usr/bin/env python3
"""Benchmark representative Phase 10 SQLite writes and concurrent reads."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.migrations import apply_migrations

POLL_INTERVAL_SECONDS: Final = 5
MEASUREMENTS_PER_CYCLE: Final = 25
SOURCE_DECISIONS_PER_CYCLE: Final = 6
DEFAULT_CYCLES: Final = 3_000
DEFAULT_MAXIMUM_AVERAGE_WRITE_MS: Final = 5_000.0
DEFAULT_MAXIMUM_TREND_RATIO: Final = 3.0
QUERY_LIMIT_ROWS: Final = 5_000


def parse_args() -> argparse.Namespace:
    """Parse deterministic persistence benchmark options."""

    parser = argparse.ArgumentParser(
        description=(
            "Simuliert SolarInspector-Zeitreihen ohne Geräte oder Wartezeiten."
        )
    )
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument(
        "--max-average-write-ms",
        type=float,
        default=DEFAULT_MAXIMUM_AVERAGE_WRITE_MS,
    )
    parser.add_argument(
        "--max-trend-ratio",
        type=float,
        default=DEFAULT_MAXIMUM_TREND_RATIO,
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def run_benchmark(cycles: int) -> dict[str, object]:
    """Run a no-wait representative SQLite persistence workload.

    Args:
        cycles: Positive number of simulated five-second collector cycles.

    Returns:
        JSON-compatible measurements for writes, reads, growth, integrity,
        and concurrent-lock behavior.

    Raises:
        ValueError: If ``cycles`` is not positive.
        sqlite3.DatabaseError: If setup or persistence fails.

    Side Effects:
        Creates and removes a temporary database. A reader thread uses its own
        SQLite connection while the main thread commits one transaction per
        cycle. No application data, webserver, Collector, or device is used.
    """

    if cycles < 1:
        raise ValueError("cycles must be positive")
    with tempfile.TemporaryDirectory(
        prefix="solarinspector-persistence-benchmark-"
    ) as raw_directory:
        database_path = Path(raw_directory) / "benchmark.db"
        database = Database(database_path)
        with database.connect() as connection:
            apply_migrations(connection, application_version="benchmark")

        stop_reader = threading.Event()
        reader_errors: list[str] = []
        reader_queries = [0]
        reader = threading.Thread(
            target=_read_concurrently,
            args=(
                database_path,
                stop_reader,
                reader_queries,
                reader_errors,
            ),
            name="persistence-benchmark-reader",
            daemon=True,
        )
        reader.start()
        write_milliseconds: list[float] = []
        base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
        try:
            with closing(sqlite3.connect(database_path, timeout=30)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                for index in range(cycles):
                    measured_at = base_time + timedelta(
                        seconds=index * POLL_INTERVAL_SECONDS
                    )
                    started = time.perf_counter()
                    _write_cycle(connection, index, measured_at)
                    write_milliseconds.append((time.perf_counter() - started) * 1_000.0)
        finally:
            stop_reader.set()
            reader.join(timeout=10)
        if reader.is_alive():
            raise RuntimeError("concurrent benchmark reader did not stop")

        with closing(sqlite3.connect(database_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            counts = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in (
                    "samples",
                    "measurements",
                    "phase_samples",
                    "grid_meter_samples",
                    "energy_balance_samples",
                    "source_selection_events",
                )
            }
            one_day_query_ms, one_day_rows = _timed_metric_query(
                connection,
                base_time,
                base_time + timedelta(days=1),
            )
            thirty_day_query_ms, thirty_day_rows = _timed_metric_query(
                connection,
                base_time,
                base_time + timedelta(days=30),
            )
        size_bytes = database_path.stat().st_size

    quarter = max(1, cycles // 4)
    first_average = statistics.fmean(write_milliseconds[:quarter])
    last_average = statistics.fmean(write_milliseconds[-quarter:])
    bytes_per_cycle = size_bytes / cycles
    cycles_per_day = 86_400 / POLL_INTERVAL_SECONDS
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hardware_scope": "development machine; not Raspberry Pi",
        },
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "cycles": cycles,
        "simulated_duration_seconds": cycles * POLL_INTERVAL_SECONDS,
        "row_counts": counts,
        "database_size_bytes": size_bytes,
        "bytes_per_cycle": bytes_per_cycle,
        "projected_size_30_days_bytes": bytes_per_cycle * cycles_per_day * 30,
        "projected_size_365_days_bytes": bytes_per_cycle * cycles_per_day * 365,
        "write_ms": {
            "average": statistics.fmean(write_milliseconds),
            "median": statistics.median(write_milliseconds),
            "p95": _percentile(write_milliseconds, 0.95),
            "maximum": max(write_milliseconds),
            "first_quarter_average": first_average,
            "last_quarter_average": last_average,
            "trend_ratio": last_average / first_average,
        },
        "queries": {
            "one_day": {
                "milliseconds": one_day_query_ms,
                "rows": one_day_rows,
            },
            "thirty_days": {
                "milliseconds": thirty_day_query_ms,
                "rows": thirty_day_rows,
            },
            "limit_rows": QUERY_LIMIT_ROWS,
        },
        "concurrent_reader_queries": reader_queries[0],
        "locking_errors": reader_errors,
        "integrity_check": integrity,
    }


def _write_cycle(
    connection: sqlite3.Connection,
    index: int,
    measured_at: datetime,
) -> None:
    timestamp = measured_at.isoformat()
    connection.execute("BEGIN")
    try:
        cursor = connection.execute(
            "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
            (measured_at.timestamp(), timestamp),
        )
        sample_id = int(cursor.lastrowid or 0)
        connection.executemany(
            """
            INSERT INTO measurements (
                sample_id, source_id, role, metric, value, unit, measured_at,
                received_at, quality, device_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    sample_id,
                    _source_for_metric(metric_index),
                    _role_for_metric(metric_index),
                    f"benchmark_metric_{metric_index}",
                    float(index + metric_index),
                    "W",
                    timestamp,
                    timestamp,
                    "measured",
                    "online",
                )
                for metric_index in range(MEASUREMENTS_PER_CYCLE)
            ),
        )
        connection.execute(
            """
            INSERT INTO phase_samples (
                sample_id, source_id, measurement_role, device_status,
                measured_at, received_at, l1_power_w, l2_power_w, l3_power_w,
                phase_power_available_count, phase_power_complete
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                "shelly_house",
                "house_total",
                "online",
                timestamp,
                timestamp,
                300.0,
                310.0,
                320.0,
                3,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO grid_meter_samples (
                sample_id, source_id, source_name, adapter, device_status,
                measured_at, received_at, grid_power_w,
                grid_import_total_kwh, grid_export_total_kwh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                "grid_meter_primary",
                "Benchmark grid",
                "synthetic",
                "online",
                timestamp,
                timestamp,
                120.0,
                1_000.0 + index / 1_000.0,
                100.0,
            ),
        )
        connection.execute(
            """
            INSERT INTO energy_balance_samples (
                sample_id, calculated_at, quality, house_power_w,
                grid_power_w, plant_ac_power_w, self_consumed_power_w,
                self_consumption_rate_percent, autonomy_rate_percent,
                residual_power_w
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                timestamp,
                "complete",
                930.0,
                120.0,
                810.0,
                810.0,
                100.0,
                87.1,
                0.0,
            ),
        )
        connection.executemany(
            """
            INSERT INTO source_selection_events (
                sample_id, selected_at, metric, selected_source_id,
                selected_source_role, selected_quality, fallback_used,
                selection_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    sample_id,
                    timestamp,
                    f"selection_metric_{decision_index}",
                    _source_for_metric(decision_index),
                    _role_for_metric(decision_index),
                    "measured",
                    0,
                    "primary_selected",
                )
                for decision_index in range(SOURCE_DECISIONS_PER_CYCLE)
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _read_concurrently(
    database_path: Path,
    stop: threading.Event,
    query_count: list[int],
    errors: list[str],
) -> None:
    try:
        with closing(sqlite3.connect(database_path, timeout=0.1)) as connection:
            while not stop.is_set():
                try:
                    connection.execute(
                        """
                        SELECT id
                        FROM measurements
                        WHERE metric = ?
                        ORDER BY measured_at DESC
                        LIMIT 1
                        """,
                        ("benchmark_metric_0",),
                    ).fetchone()
                    query_count[0] += 1
                except sqlite3.OperationalError as exc:
                    errors.append(str(exc))
                time.sleep(0.001)
    except sqlite3.Error as exc:
        errors.append(str(exc))


def _timed_metric_query(
    connection: sqlite3.Connection,
    start: datetime,
    end: datetime,
) -> tuple[float, int]:
    started = time.perf_counter()
    rows = connection.execute(
        """
        SELECT id, measured_at, value
        FROM measurements
        WHERE metric = ? AND measured_at >= ? AND measured_at < ?
        ORDER BY measured_at
        LIMIT ?
        """,
        (
            "benchmark_metric_0",
            start.isoformat(),
            end.isoformat(),
            QUERY_LIMIT_ROWS,
        ),
    ).fetchall()
    return (time.perf_counter() - started) * 1_000.0, len(rows)


def _source_for_metric(index: int) -> str:
    return (
        "grid_meter_primary"
        if index < 7
        else "shelly_house"
        if index < 15
        else "solakon_one"
    )


def _role_for_metric(index: int) -> str:
    return (
        "grid_meter" if index < 7 else "house_meter" if index < 15 else "solar_system"
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


def main() -> int:
    """Run the benchmark, write optional JSON, and enforce broad guards."""

    args = parse_args()
    if args.max_average_write_ms <= 0 or args.max_trend_ratio <= 0:
        raise SystemExit("performance guards must be positive")
    result = run_benchmark(args.cycles)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    write = result["write_ms"]
    assert isinstance(write, dict)
    failed = (
        result["integrity_check"] != "ok"
        or bool(result["locking_errors"])
        or float(write["average"]) > args.max_average_write_ms
        or float(write["trend_ratio"]) > args.max_trend_ratio
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
