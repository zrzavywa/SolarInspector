"""Test source age, nearest-value selection, averaging, and alignment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.source_selection import (
    CandidateRejectionReason,
    SourceAlignmentStatus,
    SourceSelectionFinding,
    SourceSelectionResult,
)
from zrzavy_energy_monitor_core.models.units import Unit
from zrzavy_energy_monitor_core.services.source_selector import (
    SourceCandidate,
    SourceSelector,
    assess_source_alignment,
)
from zrzavy_energy_monitor_core.validation import ValidationDecision

NOW = datetime(2026, 7, 26, 15, 0, tzinfo=timezone.utc)
PRIORITIES = {
    Metric.GRID_POWER.value: ("grid_meter_primary", "house_meter"),
    Metric.PLANT_AC_POWER.value: ("solakon_meter",),
}


def _candidate(
    value: float,
    *,
    source_id: str,
    measured_at: datetime,
    metric: Metric = Metric.GRID_POWER,
    role: MeasurementRole = MeasurementRole.GRID_METER,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
    measurement_position: str | None = None,
    findings: tuple[SourceSelectionFinding, ...] = (),
) -> SourceCandidate:
    measurement = Measurement(
        metric=metric,
        value=value,
        unit=Unit.WATT,
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=quality,
    )
    return SourceCandidate(
        source_id=source_id,
        metric=metric,
        source_role=role,
        decision=(
            ValidationDecision.ACCEPT_WITH_WARNING
            if quality is MeasurementQuality.SUSPECT
            else ValidationDecision.ACCEPT
        ),
        quality=quality,
        measurement=measurement,
        measured_at=measured_at,
        measurement_position=measurement_position,
        findings=findings,
    )


def _selection(
    metric: Metric,
    *,
    source_id: str,
    measured_at: datetime,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
    findings: tuple[SourceSelectionFinding, ...] = (),
) -> SourceSelectionResult:
    role = (
        MeasurementRole.GRID_METER
        if metric is Metric.GRID_POWER
        else MeasurementRole.PLANT_METER
    )
    measurement = Measurement(
        metric=metric,
        value=100.0,
        unit=Unit.WATT,
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=quality,
    )
    return SourceSelectionResult.selected(
        measurement,
        selection_timestamp=NOW,
        fallback_used=False,
        findings=findings,
    )


def test_nearest_valid_measurement_is_selected_within_primary_source() -> None:
    result = SourceSelector(
        PRIORITIES,
        maximum_measurement_age_seconds=30,
    ).select(
        Metric.GRID_POWER,
        (
            _candidate(
                100.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=20),
            ),
            _candidate(
                200.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=2),
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is not None
    assert result.measurement.value == 200.0
    assert result.selected_measurement_timestamp == NOW - timedelta(seconds=2)


def test_stale_primary_falls_back_with_age_reason() -> None:
    result = SourceSelector(
        PRIORITIES,
        maximum_measurement_age_seconds=30,
    ).select(
        Metric.GRID_POWER,
        (
            _candidate(
                100.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=30, microseconds=1),
            ),
            _candidate(
                200.0,
                source_id="house_meter",
                measured_at=NOW,
                measurement_position="grid_fallback",
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.selected_source_id == "house_meter"
    assert result.fallback_used is True
    assert result.rejected_candidates[0].reason is (
        CandidateRejectionReason.MEASUREMENT_TOO_OLD
    )


def test_future_measurement_is_rejected_without_fallback_value_invention() -> None:
    result = SourceSelector(PRIORITIES).select(
        Metric.GRID_POWER,
        (
            _candidate(
                100.0,
                source_id="grid_meter_primary",
                measured_at=NOW + timedelta(microseconds=1),
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is None
    assert result.rejected_candidates[0].reason is (
        CandidateRejectionReason.INVALID_TIMESTAMP
    )


def test_selection_rejects_a_naive_reference_timestamp() -> None:
    with pytest.raises(ValueError, match="selection_timestamp"):
        SourceSelector(PRIORITIES).select(
            Metric.GRID_POWER,
            (),
            selection_timestamp=datetime(2026, 7, 26, 15, 0),
        )


def test_short_window_average_uses_only_current_accepted_source_values() -> None:
    result = SourceSelector(
        PRIORITIES,
        maximum_measurement_age_seconds=30,
        short_window_average_seconds=10,
    ).select(
        Metric.GRID_POWER,
        (
            _candidate(
                100.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=9),
            ),
            _candidate(
                300.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=1),
            ),
            _candidate(
                900.0,
                source_id="grid_meter_primary",
                measured_at=NOW - timedelta(seconds=11),
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is not None
    assert result.measurement.value == 200.0
    assert result.measurement.quality is MeasurementQuality.CALCULATED
    assert result.selected_measurement_timestamp == NOW - timedelta(seconds=1)


def test_alignment_reports_aligned_suspect_incomplete_and_excessive_skew() -> None:
    warning = SourceSelectionFinding(
        rule_id="VAL-TEST",
        code="suspect",
        message="Value is suspect.",
        severity="warning",
    )
    grid = _selection(
        Metric.GRID_POWER,
        source_id="grid_meter_primary",
        measured_at=NOW,
    )
    plant = _selection(
        Metric.PLANT_AC_POWER,
        source_id="solakon_meter",
        measured_at=NOW - timedelta(seconds=10),
    )
    suspect_plant = _selection(
        Metric.PLANT_AC_POWER,
        source_id="solakon_meter",
        measured_at=NOW - timedelta(seconds=10),
        quality=MeasurementQuality.SUSPECT,
        findings=(warning,),
    )
    missing = SourceSelectionResult.unavailable(
        Metric.PLANT_AC_POWER,
        selection_timestamp=NOW,
    )

    aligned = assess_source_alignment(
        (grid, plant),
        maximum_source_skew_seconds=10,
    )
    suspect = assess_source_alignment(
        (grid, suspect_plant),
        maximum_source_skew_seconds=10,
    )
    incomplete = assess_source_alignment(
        (grid, missing),
        maximum_source_skew_seconds=10,
    )
    skewed = assess_source_alignment(
        (
            grid,
            _selection(
                Metric.PLANT_AC_POWER,
                source_id="solakon_meter",
                measured_at=NOW - timedelta(seconds=10, microseconds=1),
            ),
        ),
        maximum_source_skew_seconds=10,
    )

    assert aligned.status is SourceAlignmentStatus.ALIGNED
    assert aligned.maximum_skew_seconds == 10.0
    assert suspect.status is SourceAlignmentStatus.SUSPECT
    assert suspect.findings == (warning,)
    assert incomplete.status is SourceAlignmentStatus.INCOMPLETE
    assert incomplete.maximum_skew_seconds is None
    assert skewed.status is SourceAlignmentStatus.INCOMPLETE
    assert skewed.findings[0].code == "source_skew_exceeded"
