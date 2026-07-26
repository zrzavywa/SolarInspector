"""Test normalized measurement and source-selection persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.energy_balance import (
    EnergyBalanceQuality,
    EnergyBalanceResult,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.source_selection import SourceSelectionResult
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.persistence.database import Database
from solarinspector_core.persistence.migrations import apply_migrations
from solarinspector_core.services.collector import Collector

NOW = datetime.fromisoformat("2026-07-26T18:00:00+02:00")


def _measurement(
    metric: Metric,
    value: float,
    quality: MeasurementQuality,
) -> Measurement:
    """Build one normalized official-grid measurement."""

    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id="grid_meter_primary",
        role=MeasurementRole.GRID_METER,
        measured_at=NOW,
        received_at=NOW,
        quality=quality,
    )


def _grid_snapshot() -> DeviceSnapshot:
    """Build accepted, suspect, and rejected time-series candidates."""

    return DeviceSnapshot(
        source_id="grid_meter_primary",
        status=DeviceConnectionStatus.DEGRADED,
        measurements=(
            _measurement(Metric.GRID_POWER, 0.0, MeasurementQuality.VALIDATED),
            _measurement(
                Metric.GRID_IMPORT_TOTAL,
                1_234_500.0,
                MeasurementQuality.SUSPECT,
            ),
            _measurement(
                Metric.GRID_VOLTAGE,
                999.0,
                MeasurementQuality.REJECTED,
            ),
        ),
        received_at=NOW,
    )


def _balance() -> EnergyBalanceResult:
    """Build a partial balance with one selected and five unavailable inputs."""

    grid_measurement = _measurement(
        Metric.GRID_POWER,
        0.0,
        MeasurementQuality.VALIDATED,
    )
    selections = (
        SourceSelectionResult.selected(
            grid_measurement,
            selection_timestamp=NOW,
            fallback_used=False,
        ),
        *(
            SourceSelectionResult.unavailable(
                metric,
                selection_timestamp=NOW,
            )
            for metric in (
                Metric.PLANT_AC_POWER,
                Metric.PV_POWER,
                Metric.BATTERY_CHARGE_POWER,
                Metric.BATTERY_DISCHARGE_POWER,
                Metric.BATTERY_SOC,
            )
        ),
    )
    return EnergyBalanceResult(
        house_power_w=0.0,
        grid_power_w=0.0,
        grid_import_power_w=0.0,
        grid_export_power_w=0.0,
        plant_ac_power_w=None,
        pv_power_w=None,
        battery_charge_power_w=None,
        battery_discharge_power_w=None,
        battery_soc_percent=None,
        self_consumed_power_w=None,
        self_consumption_rate_percent=None,
        autonomy_rate_percent=0.0,
        residual_power_w=0.0,
        quality=EnergyBalanceQuality.INCOMPLETE,
        calculated_at=NOW,
        source_metadata=selections,
    )


def _migrated_database(tmp_path: Path) -> Database:
    """Create an isolated database with target schema version 2."""

    database = Database(tmp_path / "time-series.db")
    with database.connect() as connection:
        apply_migrations(connection, application_version="4.5.0")
    return database


def test_version_2_persists_measurements_null_policy_and_counter_units(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)

    sample_id = database.insert_sample_with_snapshots(
        {
            "ts_epoch": NOW.timestamp(),
            "ts_local": NOW.isoformat(),
        },
        measurement_snapshots=(_grid_snapshot(),),
        energy_balance=_balance(),
    )

    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT source_id, role, metric, value, unit, measured_at,
                   received_at, quality, device_status
            FROM measurements
            WHERE sample_id = ?
            ORDER BY source_id, metric
            """,
            (sample_id,),
        ).fetchall()

    by_metric = {row["metric"]: row for row in rows}
    assert "grid_voltage" not in by_metric
    assert by_metric["grid_power"]["value"] == 0.0
    assert by_metric["grid_power"]["unit"] == "W"
    assert by_metric["grid_power"]["measured_at"] == "2026-07-26T16:00:00+00:00"
    assert by_metric["grid_power"]["received_at"] == "2026-07-26T16:00:00+00:00"
    assert by_metric["grid_power"]["device_status"] == "degraded"
    assert by_metric["grid_import_total"]["value"] == 1234.5
    assert by_metric["grid_import_total"]["unit"] == "kWh"
    assert by_metric["grid_import_total"]["quality"] == "suspect"
    assert by_metric["house_power"]["value"] == 0.0
    assert by_metric["autonomy_rate"]["value"] == 0.0
    assert "self_consumed_power" not in by_metric


def test_source_selection_events_preserve_available_and_unavailable_decisions(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)

    sample_id = database.insert_sample_with_snapshots(
        {
            "ts_epoch": NOW.timestamp(),
            "ts_local": NOW.isoformat(),
        },
        energy_balance=_balance(),
    )

    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT metric, selected_source_id, selected_quality,
                   fallback_used, selection_reason, rejected_candidates_json
            FROM source_selection_events
            WHERE sample_id = ?
            ORDER BY metric
            """,
            (sample_id,),
        ).fetchall()

    assert len(rows) == 6
    by_metric = {row["metric"]: row for row in rows}
    assert by_metric["grid_power"]["selected_source_id"] == "grid_meter_primary"
    assert by_metric["grid_power"]["selected_quality"] == "validated"
    assert by_metric["grid_power"]["fallback_used"] == 0
    assert by_metric["grid_power"]["selection_reason"] == "primary_selected"
    assert by_metric["plant_ac_power"]["selected_source_id"] is None
    assert by_metric["plant_ac_power"]["selected_quality"] == "unavailable"
    assert json.loads(by_metric["plant_ac_power"]["rejected_candidates_json"]) == []


def test_source_decision_persistence_switch_disables_normalized_events(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)

    database.insert_sample_with_snapshots(
        {
            "ts_epoch": NOW.timestamp(),
            "ts_local": NOW.isoformat(),
        },
        energy_balance=_balance(),
        persist_source_decisions=False,
    )

    with database.connect() as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM source_selection_events"
        ).fetchone()[0]

    assert event_count == 0


def test_duplicate_normalized_measurement_rolls_back_complete_cycle(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    snapshot = _grid_snapshot()

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
        database.insert_sample_with_snapshots(
            {
                "ts_epoch": NOW.timestamp(),
                "ts_local": NOW.isoformat(),
            },
            measurement_snapshots=(snapshot, snapshot),
            energy_balance=_balance(),
        )

    assert database.latest() is None
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM energy_balance_samples"
            ).fetchone()[0]
            == 0
        )


def test_delete_all_removes_version_2_time_series(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    database.insert_sample_with_snapshots(
        {
            "ts_epoch": NOW.timestamp(),
            "ts_local": NOW.isoformat(),
        },
        measurement_snapshots=(_grid_snapshot(),),
        energy_balance=_balance(),
    )

    database.delete_all()

    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM source_selection_events"
            ).fetchone()[0]
            == 0
        )


def test_collector_insert_bridge_forwards_validated_snapshots(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)

    class ConfigStub:
        def get(self) -> dict[str, object]:
            return {}

    collector = Collector(ConfigStub(), database)  # type: ignore[arg-type]
    collector._insert_sample(
        {
            "ts_epoch": NOW.timestamp(),
            "ts_local": NOW.isoformat(),
        },
        phase_snapshot=None,
        grid_meter_snapshot=None,
        measurement_snapshots=(_grid_snapshot(),),
        energy_balance=_balance(),
        persist_source_decisions=True,
        measurement_role="house_total",
    )

    with database.connect() as connection:
        metrics = {
            row[0]
            for row in connection.execute("SELECT metric FROM measurements").fetchall()
        }

    assert {"grid_power", "grid_import_total", "house_power"} <= metrics
