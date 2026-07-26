"""Test additive, atomic persistence of Phase-09 energy balances."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from zrzavy_energy_monitor_core.models.energy_balance import EnergyBalanceInput
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.source_selection import SourceSelectionResult
from zrzavy_energy_monitor_core.models.units import unit_for_metric
from zrzavy_energy_monitor_core.persistence.database import Database
from zrzavy_energy_monitor_core.services.collector import Collector
from zrzavy_energy_monitor_core.services.energy_balance import EnergyBalanceService

NOW = datetime.fromisoformat("2026-07-26T18:00:00+02:00")


def _selection(
    metric: Metric,
    value: float | None,
    *,
    source_id: str,
    fallback_used: bool = False,
) -> SourceSelectionResult:
    if value is None:
        return SourceSelectionResult.unavailable(
            metric,
            selection_timestamp=NOW,
        )
    role = {
        Metric.GRID_POWER: MeasurementRole.GRID_METER,
        Metric.PLANT_AC_POWER: MeasurementRole.PLANT_METER,
        Metric.PV_POWER: MeasurementRole.SOLAR_SYSTEM,
        Metric.BATTERY_CHARGE_POWER: MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_DISCHARGE_POWER: MeasurementRole.BATTERY_SYSTEM,
        Metric.BATTERY_SOC: MeasurementRole.BATTERY_SYSTEM,
    }[metric]
    measurement = Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.VALIDATED,
    )
    return SourceSelectionResult.selected(
        measurement,
        selection_timestamp=NOW,
        fallback_used=fallback_used,
    )


def _balance(
    *,
    grid_power_w: float = 900.0,
    plant_ac_power_w: float = 600.0,
    fallback_used: bool = False,
):
    return EnergyBalanceService().calculate(
        EnergyBalanceInput(
            grid_power=_selection(
                Metric.GRID_POWER,
                grid_power_w,
                source_id=("house_meter" if fallback_used else "grid_meter_primary"),
                fallback_used=fallback_used,
            ),
            plant_ac_power=_selection(
                Metric.PLANT_AC_POWER,
                plant_ac_power_w,
                source_id="solakon_meter",
            ),
            pv_power=_selection(
                Metric.PV_POWER,
                720.0,
                source_id="solakon_one",
            ),
            battery_charge_power=_selection(
                Metric.BATTERY_CHARGE_POWER,
                100.0,
                source_id="solakon_one",
            ),
            battery_discharge_power=_selection(
                Metric.BATTERY_DISCHARGE_POWER,
                0.0,
                source_id="solakon_one",
            ),
            battery_soc=_selection(
                Metric.BATTERY_SOC,
                74.0,
                source_id="solakon_one",
            ),
            calculation_timestamp=NOW,
        )
    )


def _sample() -> dict[str, object]:
    return {
        "ts_epoch": NOW.timestamp(),
        "ts_local": NOW.isoformat(),
    }


def test_schema_adds_energy_balance_table_without_changing_samples(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "energy-schema.db")

    with database.connect() as connection:
        sample_columns = connection.execute("PRAGMA table_info(samples)").fetchall()
        columns = connection.execute(
            "PRAGMA table_info(energy_balance_samples)"
        ).fetchall()
        indexes = connection.execute(
            "PRAGMA index_list(energy_balance_samples)"
        ).fetchall()

    assert len(sample_columns) == 48
    assert [row["name"] for row in columns] == [
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
    ]
    assert {row["name"] for row in indexes} == {
        "idx_energy_balance_samples_quality_sample"
    }


def test_atomic_insert_persists_values_quality_and_source_decisions(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "energy-values.db")

    sample_id = database.insert_sample_with_snapshots(
        _sample(),
        energy_balance=_balance(fallback_used=True),
    )
    row = database.latest_energy_balance_sample()

    assert sample_id == 1
    assert row is not None
    assert row["sample_id"] == 1
    assert row["calculated_at"] == NOW.isoformat()
    assert row["quality"] == "calculated"
    assert row["house_power_w"] == 1500.0
    assert row["grid_import_power_w"] == 900.0
    assert row["grid_export_power_w"] == 0.0
    assert row["plant_ac_power_w"] == 600.0
    assert row["pv_power_w"] == 720.0
    assert row["battery_charge_power_w"] == 100.0
    assert row["battery_discharge_power_w"] == 0.0
    assert row["battery_soc_percent"] == 74.0
    assert row["self_consumed_power_w"] == 600.0
    assert row["self_consumption_rate_percent"] == 100.0
    assert row["autonomy_rate_percent"] == 40.0
    assert row["residual_power_w"] == 0.0
    assert row["fallback_used"] == 1
    sources = json.loads(row["source_metadata_json"])
    assert sources["grid_power"]["selected_source_id"] == "house_meter"
    assert sources["grid_power"]["fallback_used"] is True
    assert json.loads(row["findings_json"]) == []


def test_zero_and_missing_values_remain_distinct(tmp_path: Path) -> None:
    database = Database(tmp_path / "energy-zero.db")
    balance = _balance(grid_power_w=0.0, plant_ac_power_w=0.0)

    database.insert_sample_with_snapshots(
        _sample(),
        energy_balance=balance,
    )
    row = database.latest_energy_balance_sample()

    assert row is not None
    assert row["house_power_w"] == 0.0
    assert row["grid_import_power_w"] == 0.0
    assert row["grid_export_power_w"] == 0.0
    assert row["self_consumption_rate_percent"] is None
    assert row["autonomy_rate_percent"] is None


def test_source_decision_persistence_can_be_disabled(tmp_path: Path) -> None:
    database = Database(tmp_path / "energy-no-sources.db")

    database.insert_sample_with_snapshots(
        _sample(),
        energy_balance=_balance(fallback_used=True),
        persist_source_decisions=False,
    )
    row = database.latest_energy_balance_sample()

    assert row is not None
    assert row["fallback_used"] == 0
    assert json.loads(row["source_metadata_json"]) == {}


def test_quality_and_findings_are_persisted_for_normalized_balance(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "energy-findings.db")

    database.insert_sample_with_snapshots(
        _sample(),
        energy_balance=_balance(
            grid_power_w=-620.0,
            plant_ac_power_w=600.0,
        ),
    )
    row = database.latest_energy_balance_sample()

    assert row is not None
    assert row["quality"] == "suspect"
    assert row["house_power_w"] == 0.0
    assert row["residual_power_w"] == 20.0
    findings = json.loads(row["findings_json"])
    assert findings[0]["code"] == "negative_house_power_normalized"
    assert findings[0]["details"]["calculated_house_power_w"] == -20.0


def test_collector_insert_bridge_passes_balance_to_database(tmp_path: Path) -> None:
    database = Database(tmp_path / "collector-energy.db")

    class ConfigStub:
        def get(self) -> dict[str, object]:
            return {}

    collector = Collector(ConfigStub(), database)  # type: ignore[arg-type]
    balance = _balance()

    sample_id = collector._insert_sample(
        _sample(),
        phase_snapshot=None,
        grid_meter_snapshot=None,
        energy_balance=balance,
        persist_source_decisions=True,
        measurement_role="house_total",
    )

    row = database.latest_energy_balance_sample()
    assert sample_id == 1
    assert row is not None
    assert row["house_power_w"] == 1500.0


def test_balance_insert_failure_rolls_back_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "energy-rollback.db")

    def fail_insert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("energy balance insert failed")

    monkeypatch.setattr(database, "_insert_energy_balance", fail_insert)

    with pytest.raises(RuntimeError, match="energy balance insert failed"):
        database.insert_sample_with_snapshots(
            _sample(),
            energy_balance=_balance(),
        )

    assert database.latest() is None
    assert database.latest_energy_balance_sample() is None


def test_delete_all_removes_energy_balance_rows(tmp_path: Path) -> None:
    database = Database(tmp_path / "energy-delete.db")
    database.insert_sample_with_snapshots(
        _sample(),
        energy_balance=_balance(),
    )

    database.delete_all()

    assert database.latest() is None
    assert database.latest_energy_balance_sample() is None


def test_initialization_migrates_existing_database_idempotently(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_epoch REAL NOT NULL,
                ts_local TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO samples (ts_epoch, ts_local) VALUES (?, ?)",
            (100.0, "existing"),
        )
        connection.commit()

    database = Database(path)
    database.initialize()

    latest = database.latest()
    assert latest is not None
    assert latest["ts_local"] == "existing"
    with database.connect() as connection:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'energy_balance_samples'
            """
        ).fetchone()
    assert table is not None
