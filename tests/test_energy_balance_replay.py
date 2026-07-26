"""Replay Phase-09 operating and failure scenarios deterministically."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from zrzavy_energy_monitor_core.config.defaults import DEFAULT_CONFIG
from zrzavy_energy_monitor_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import unit_for_metric
from zrzavy_energy_monitor_core.services.energy_balance_collector import (
    build_cycle_energy_balance,
)
from zrzavy_energy_monitor_core.validation import (
    ValidatedCycle,
    ValidatedDeviceSnapshot,
    ValidatedMeasurement,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=timezone.utc)
FIXTURE = Path("tests/fixtures/energy_balance_replay.jsonl")
SOURCE_FIELDS = {
    "grid_primary": (
        "grid_meter_primary",
        Metric.GRID_POWER,
        MeasurementRole.GRID_METER,
    ),
    "grid_fallback": (
        "house_meter",
        Metric.GRID_POWER,
        MeasurementRole.GRID_METER,
    ),
    "plant_primary": (
        "solakon_meter",
        Metric.PLANT_AC_POWER,
        MeasurementRole.PLANT_METER,
    ),
    "plant_fallback": (
        "solakon_one",
        Metric.PLANT_AC_POWER,
        MeasurementRole.SOLAR_SYSTEM,
    ),
    "pv": (
        "solakon_one",
        Metric.PV_POWER,
        MeasurementRole.SOLAR_SYSTEM,
    ),
}


def _scenarios() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _validated_measurement(
    source: dict[str, Any],
    *,
    source_id: str,
    metric: Metric,
    role: MeasurementRole,
) -> ValidatedMeasurement:
    measured_at = NOW + timedelta(seconds=float(source.get("offset_seconds", 0)))
    original = Measurement(
        metric=metric,
        value=float(source["value"]),
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=MeasurementQuality.REPORTED,
    )
    if source.get("rejected") is True:
        finding = ValidationFinding(
            rule_id="ENERGY-REPLAY",
            code="rejected_replay_value",
            message="Replay value rejected by validation.",
            severity=ValidationSeverity.ERROR,
        )
        return ValidatedMeasurement(
            original=original,
            result=ValidationResult.rejected(
                raw_value=original.value,
                candidate_value=original.value,
                findings=(finding,),
            ),
            measurement=None,
        )
    accepted = Measurement(
        metric=metric,
        value=original.value,
        unit=original.unit,
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=MeasurementQuality.VALIDATED,
    )
    return ValidatedMeasurement(
        original=original,
        result=ValidationResult.accepted(
            original.value,
            current_quality=accepted.quality,
        ),
        measurement=accepted,
    )


def _cycle(scenario: dict[str, Any]) -> ValidatedCycle:
    grouped: dict[str, list[ValidatedMeasurement]] = {}
    for field, (source_id, metric, role) in SOURCE_FIELDS.items():
        source = scenario.get(field)
        if not isinstance(source, dict):
            continue
        grouped.setdefault(source_id, []).append(
            _validated_measurement(
                source,
                source_id=source_id,
                metric=metric,
                role=role,
            )
        )

    validated_snapshots = []
    for source_id, measurements in grouped.items():
        original = DeviceSnapshot(
            source_id=source_id,
            status=DeviceConnectionStatus.ONLINE,
            measurements=tuple(item.original for item in measurements),
            received_at=NOW,
        )
        filtered = DeviceSnapshot(
            source_id=source_id,
            status=DeviceConnectionStatus.ONLINE,
            measurements=tuple(
                item.measurement
                for item in measurements
                if item.measurement is not None
            ),
            received_at=NOW,
        )
        validated_snapshots.append(
            ValidatedDeviceSnapshot(
                original=original,
                snapshot=filtered,
                measurements=tuple(measurements),
                events=(),
            )
        )
    return ValidatedCycle(
        snapshots=tuple(item.snapshot for item in validated_snapshots),
        validated_snapshots=tuple(validated_snapshots),
        events=(),
    )


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda item: item["name"])
def test_energy_balance_replay_scenarios(scenario: dict[str, Any]) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["validation"]["enabled"] = True
    config["house_meter"]["measurement_role"] = "grid_fallback"

    result = build_cycle_energy_balance(
        _cycle(scenario),
        config=config,
        calculation_timestamp=NOW,
    )
    expected = scenario["expected"]
    selections = {
        selection.requested_metric: selection for selection in result.source_metadata
    }

    assert result.quality.value == expected["quality"]
    assert result.house_power_w == expected["house_power_w"]
    if "grid_export_power_w" in expected:
        assert result.grid_export_power_w == expected["grid_export_power_w"]
    if "pv_power_w" in expected:
        assert result.pv_power_w == expected["pv_power_w"]
    assert selections[Metric.GRID_POWER].selected_source_id == expected["grid_source"]
    assert (
        selections[Metric.PLANT_AC_POWER].selected_source_id == expected["plant_source"]
    )
    assert (
        any(selection.fallback_used for selection in result.source_metadata)
        is expected["fallback_used"]
    )


def test_energy_balance_replay_catalog_is_complete_and_deterministic() -> None:
    scenarios = _scenarios()

    assert {scenario["name"] for scenario in scenarios} == {
        "normal_day",
        "night_operation",
        "grid_export",
        "grid_meter_failure",
        "plant_meter_failure",
        "solakon_failure",
        "stale_measurements",
        "source_time_skew",
        "rejected_measurements",
        "zero_power",
    }
    assert _scenarios() == scenarios
