"""Test additive bounded Phase 10 CSV exports."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.migrations import apply_migrations
from solarinspector_core.web.export import build_time_series_csv_export

START = datetime(2026, 7, 26, 8, tzinfo=timezone.utc)


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    """Create representative rows without sensitive production data."""

    database = Database(tmp_path / "exports.db")
    with database.connect() as setup:
        apply_migrations(setup, application_version="4.5.0")
        sample_id = int(
            setup.execute(
                "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
                (START.timestamp(), START.isoformat()),
            ).lastrowid
            or 0
        )
        setup.executemany(
            """
            INSERT INTO measurements (
                sample_id, source_id, role, metric, value, unit, measured_at,
                received_at, quality, device_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    sample_id,
                    "grid",
                    "grid",
                    "grid_power",
                    0.0,
                    "W",
                    START.isoformat(),
                    START.isoformat(),
                    "measured",
                    "available",
                ),
                (
                    sample_id,
                    "grid",
                    "grid",
                    "grid_voltage",
                    230.0,
                    "V",
                    START.isoformat(),
                    START.isoformat(),
                    "measured",
                    "available",
                ),
            ),
        )
        setup.execute(
            """
            INSERT INTO phase_samples (
                sample_id, source_id, measurement_role, device_status,
                measured_at, received_at, l1_power_w, l1_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                "shelly",
                "house_total",
                "available",
                START.isoformat(),
                START.isoformat(),
                0.0,
                "measured",
            ),
        )
        setup.execute(
            """
            INSERT INTO grid_meter_samples (
                sample_id, source_id, source_name, adapter, device_status,
                measured_at, received_at, grid_power_w,
                grid_import_total_kwh, grid_export_total_kwh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                "grid",
                "=spreadsheet-command",
                "test",
                "available",
                START.isoformat(),
                START.isoformat(),
                0.0,
                None,
                0.0,
            ),
        )
        setup.execute(
            """
            INSERT INTO energy_balance_samples (
                sample_id, calculated_at, quality, house_power_w,
                grid_power_w, source_metadata_json, findings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                START.isoformat(),
                "complete",
                0.0,
                None,
                '{"secret": "must-not-export"}',
                '["internal"]',
            ),
        )
        setup.execute(
            """
            INSERT INTO validation_events (
                first_seen_epoch, first_seen_local, last_seen_epoch,
                last_seen_local, source_id, role, metric, unit, rule_id,
                finding_code, severity, decision, quality, reason,
                raw_value_json, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                START.timestamp(),
                START.isoformat(),
                START.timestamp(),
                START.isoformat(),
                "@source",
                "grid",
                "grid_power",
                "W",
                "range",
                "high",
                "warning",
                "accept",
                "suspect",
                "safe reason",
                '"private raw response"',
                '{"password": "private"}',
            ),
        )
        setup.execute(
            """
            INSERT INTO source_selection_events (
                sample_id, selected_at, metric, selected_source_id,
                selected_quality, fallback_used, selection_reason,
                rejected_candidates_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                START.isoformat(),
                "grid_power",
                "+source",
                "measured",
                0,
                "primary_selected",
                '[{"raw": "private"}]',
            ),
        )
        setup.commit()
    opened = sqlite3.connect(database.path)
    opened.row_factory = sqlite3.Row
    try:
        yield opened
    finally:
        opened.close()


@pytest.mark.parametrize(
    ("dataset", "required_header"),
    [
        ("phases", "l1_power_w"),
        ("grid", "grid_import_total_kwh"),
        ("energy_balance", "house_power_w"),
        ("validation_events", "finding_code"),
        ("source_selection_events", "selection_reason"),
    ],
)
def test_additive_exports_have_explicit_unit_headers_and_utc_timestamps(
    connection: sqlite3.Connection,
    dataset: str,
    required_header: str,
) -> None:
    content, filename = build_time_series_csv_export(
        connection,
        dataset,
        START,
        START + timedelta(days=1),
    )
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    rows = list(reader)

    assert required_header in (reader.fieldnames or [])
    assert (
        rows[0][
            "timestamp_utc"
            if dataset
            not in {
                "validation_events",
                "source_selection_events",
            }
            else (
                "last_seen_at_utc"
                if dataset == "validation_events"
                else "selected_at_utc"
            )
        ]
        == START.isoformat()
    )
    assert filename == (f"solarinspector_{dataset}_2026-07-26_2026-07-27.csv")


def test_measurement_export_requires_metric_and_preserves_real_zero(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(ValueError, match="requires a metric"):
        build_time_series_csv_export(
            connection,
            "measurements",
            START,
            START + timedelta(days=1),
        )

    content, _filename = build_time_series_csv_export(
        connection,
        "measurements",
        START,
        START + timedelta(days=1),
        metric="grid_power",
    )
    rows = list(csv.DictReader(io.StringIO(content), delimiter=";"))

    assert len(rows) == 1
    assert rows[0]["value"] == "0.0"
    assert rows[0]["unit"] == "W"
    assert rows[0]["quality"] == "measured"
    assert rows[0]["source_id"] == "grid"


def test_missing_values_are_empty_and_spreadsheet_formulas_are_escaped(
    connection: sqlite3.Connection,
) -> None:
    grid_content, _filename = build_time_series_csv_export(
        connection,
        "grid",
        START,
        START + timedelta(days=1),
    )
    grid_row = next(csv.DictReader(io.StringIO(grid_content), delimiter=";"))

    assert grid_row["grid_power_w"] == "0.0"
    assert grid_row["grid_import_total_kwh"] == ""
    assert grid_row["grid_export_total_kwh"] == "0.0"
    assert grid_row["source_name"] == "'=spreadsheet-command"


def test_diagnostic_exports_exclude_raw_json_and_sensitive_metadata(
    connection: sqlite3.Connection,
) -> None:
    validation, _filename = build_time_series_csv_export(
        connection,
        "validation_events",
        START,
        START + timedelta(days=1),
    )
    selection, _filename = build_time_series_csv_export(
        connection,
        "source_selection_events",
        START,
        START + timedelta(days=1),
    )
    balance, _filename = build_time_series_csv_export(
        connection,
        "energy_balance",
        START,
        START + timedelta(days=1),
    )

    assert "raw_value_json" not in validation
    assert "details_json" not in validation
    assert "private raw response" not in validation
    assert "'@source" in validation
    assert "rejected_candidates_json" not in selection
    assert "'+source" in selection
    assert "source_metadata_json" not in balance
    assert "must-not-export" not in balance


def test_export_is_bounded_and_rejects_unknown_dataset(
    connection: sqlite3.Connection,
) -> None:
    content, _filename = build_time_series_csv_export(
        connection,
        "measurements",
        START,
        START + timedelta(days=1),
        metric="grid_power",
        maximum_rows=1,
    )
    assert len(list(csv.DictReader(io.StringIO(content), delimiter=";"))) == 1

    with pytest.raises(ValueError, match="unsupported"):
        build_time_series_csv_export(
            connection,
            "secrets",
            START,
            START + timedelta(days=1),
        )


def test_large_export_stops_at_explicit_row_limit(
    connection: sqlite3.Connection,
) -> None:
    rows_to_add = 1_200
    for offset in range(1, rows_to_add + 1):
        measured_at = START + timedelta(seconds=offset)
        sample_id = int(
            connection.execute(
                "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
                (measured_at.timestamp(), measured_at.isoformat()),
            ).lastrowid
            or 0
        )
        connection.execute(
            """
            INSERT INTO measurements (
                sample_id, source_id, role, metric, value, unit, measured_at,
                received_at, quality, device_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                "grid",
                "grid",
                "grid_power",
                float(offset),
                "W",
                measured_at.isoformat(),
                measured_at.isoformat(),
                "measured",
                "available",
            ),
        )
    connection.commit()

    content, _filename = build_time_series_csv_export(
        connection,
        "measurements",
        START,
        START + timedelta(days=1),
        metric="grid_power",
        maximum_rows=1_000,
    )

    exported = list(csv.DictReader(io.StringIO(content), delimiter=";"))
    assert len(exported) == 1_000
    assert exported[0]["value"] == "0.0"
    assert exported[-1]["value"] == "999.0"


def test_http_route_keeps_legacy_default_and_serves_additive_dataset(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import solarinspector as application

    database_path = Path(connection.execute("PRAGMA database_list").fetchone()["file"])
    monkeypatch.setattr(application, "database", Database(database_path))

    response = application.app.test_client().get(
        "/api/export.csv?from=2026-07-26&to=2026-07-26&dataset=grid"
    )
    missing_metric = application.app.test_client().get(
        "/api/export.csv?from=2026-07-26&to=2026-07-26&dataset=measurements"
    )

    assert response.status_code == 200
    assert "grid_import_total_kwh" in response.get_data(as_text=True)
    assert response.headers["Content-Disposition"].startswith(
        'attachment; filename="solarinspector_grid_'
    )
    assert missing_metric.status_code == 400
    assert "requires a metric" in missing_metric.get_json()["error"]
