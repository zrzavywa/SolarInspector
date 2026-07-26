"""Test explainable source-selection result models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.source_selection import (
    CandidateRejectionReason,
    RejectedSourceCandidate,
    SourceSelectionFinding,
    SourceSelectionReason,
    SourceSelectionResult,
)
from zrzavy_energy_monitor_core.models.units import Unit

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _measurement(
    *,
    value: float = 0.0,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
) -> Measurement:
    return Measurement(
        metric=Metric.GRID_POWER,
        value=value,
        unit=Unit.WATT,
        source_id="grid_meter_primary",
        role=MeasurementRole.GRID_METER,
        measured_at=NOW,
        received_at=NOW,
        quality=quality,
    )


def test_selected_result_preserves_real_zero_and_measurement_metadata() -> None:
    result = SourceSelectionResult.selected(
        _measurement(value=0.0),
        selection_timestamp=NOW,
        fallback_used=False,
    )

    assert result.measurement is not None
    assert result.measurement.value == 0.0
    assert result.selected_source_id == "grid_meter_primary"
    assert result.selected_source_role is MeasurementRole.GRID_METER
    assert result.selected_quality is MeasurementQuality.VALIDATED
    assert result.selection_reason is SourceSelectionReason.PRIMARY_SELECTED
    assert result.fallback_used is False
    assert result.selected_measurement_timestamp == NOW


def test_fallback_result_carries_rejections_and_warning_findings() -> None:
    stale_finding = SourceSelectionFinding(
        rule_id="measurement_age",
        code="measurement_stale",
        message="Measurement is stale.",
        severity="error",
    )
    rejected = RejectedSourceCandidate(
        source_id="grid_meter_primary",
        reason=CandidateRejectionReason.MEASUREMENT_TOO_OLD,
        quality=MeasurementQuality.STALE,
        measured_at=NOW,
        findings=(stale_finding,),
    )
    fallback = Measurement(
        metric=Metric.GRID_POWER,
        value=400.0,
        unit=Unit.WATT,
        source_id="house_meter",
        role=MeasurementRole.GRID_METER,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.SUSPECT,
    )

    warning = SourceSelectionFinding(
        rule_id="phase_comparison",
        code="phase_difference",
        message="Phase comparison warning.",
        severity="warning",
    )
    result = SourceSelectionResult.selected(
        fallback,
        selection_timestamp=NOW,
        fallback_used=True,
        rejected_candidates=(rejected,),
        findings=(warning,),
    )

    assert result.selection_reason is SourceSelectionReason.FALLBACK_SELECTED
    assert result.selected_quality is MeasurementQuality.SUSPECT
    assert result.rejected_candidates == (rejected,)
    assert result.findings == (warning,)


def test_unavailable_result_has_no_invented_source_or_value() -> None:
    rejected = RejectedSourceCandidate(
        source_id="house_meter",
        reason=CandidateRejectionReason.MEASUREMENT_POSITION_MISMATCH,
    )

    result = SourceSelectionResult.unavailable(
        Metric.GRID_POWER,
        selection_timestamp=NOW,
        rejected_candidates=(rejected,),
    )

    assert result.measurement is None
    assert result.selected_source_id is None
    assert result.selected_measurement_timestamp is None
    assert result.selected_quality is MeasurementQuality.UNAVAILABLE
    assert result.selection_reason is SourceSelectionReason.NO_ELIGIBLE_SOURCE
    assert result.fallback_used is False


def test_result_rejects_metadata_that_does_not_match_measurement() -> None:
    with pytest.raises(ValueError, match="selected_source_id must match"):
        SourceSelectionResult(
            requested_metric=Metric.GRID_POWER,
            measurement=_measurement(),
            selected_source_id="other",
            selected_source_role=MeasurementRole.GRID_METER,
            selected_quality=MeasurementQuality.VALIDATED,
            selection_reason=SourceSelectionReason.PRIMARY_SELECTED,
            fallback_used=False,
            rejected_candidates=(),
            selected_measurement_timestamp=NOW,
            selection_timestamp=NOW,
        )


def test_selected_result_rejects_unusable_measurement_quality() -> None:
    with pytest.raises(ValueError, match="quality must be usable"):
        SourceSelectionResult.selected(
            _measurement(quality=MeasurementQuality.STALE),
            selection_timestamp=NOW,
            fallback_used=False,
        )


def test_selection_models_require_timezone_aware_timestamps() -> None:
    naive = datetime(2026, 7, 26, 12, 0)

    with pytest.raises(ValueError, match="selection_timestamp"):
        SourceSelectionResult.unavailable(
            Metric.GRID_POWER,
            selection_timestamp=naive,
        )
    with pytest.raises(ValueError, match="measured_at"):
        RejectedSourceCandidate(
            source_id="grid_meter_primary",
            reason=CandidateRejectionReason.INVALID_TIMESTAMP,
            measured_at=naive,
        )
