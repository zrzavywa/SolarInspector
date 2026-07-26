"""Test deterministic quality-based source selection."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.source_selection import (
    CandidateRejectionReason,
    SourceSelectionReason,
)
from solarinspector_core.models.units import unit_for_metric
from solarinspector_core.services.source_selector import (
    SourceCandidate,
    SourceSelector,
)
from solarinspector_core.validation import (
    ValidatedMeasurement,
    ValidationDecision,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 26, 14, 0, tzinfo=timezone.utc)
PRIORITIES = {
    Metric.GRID_POWER.value: ("grid_meter_primary", "house_meter"),
    Metric.PLANT_AC_POWER.value: ("solakon_meter", "solakon_one"),
    Metric.PV_POWER.value: ("solakon_one",),
    Metric.BATTERY_SOC.value: ("solakon_one",),
}


def _measurement(
    metric: Metric,
    value: float,
    *,
    source_id: str,
    role: MeasurementRole,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
) -> Measurement:
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=quality,
    )


def _candidate(
    metric: Metric,
    value: float,
    *,
    source_id: str,
    role: MeasurementRole,
    quality: MeasurementQuality = MeasurementQuality.VALIDATED,
    decision: ValidationDecision = ValidationDecision.ACCEPT,
    measurement_position: str | None = None,
) -> SourceCandidate:
    measurement = (
        None
        if decision is ValidationDecision.REJECT
        else _measurement(
            metric,
            value,
            source_id=source_id,
            role=role,
            quality=quality,
        )
    )
    return SourceCandidate(
        source_id=source_id,
        metric=metric,
        source_role=role,
        decision=decision,
        quality=quality,
        measurement=measurement,
        measured_at=NOW,
        measurement_position=measurement_position,
    )


@pytest.mark.parametrize("value", [0.0, 850.0, -125.0])
def test_primary_grid_meter_wins_and_preserves_signed_value(value: float) -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.GRID_POWER,
        (
            _candidate(
                Metric.GRID_POWER,
                300.0,
                source_id="house_meter",
                role=MeasurementRole.GRID_METER,
                measurement_position="grid_fallback",
            ),
            _candidate(
                Metric.GRID_POWER,
                value,
                source_id="grid_meter_primary",
                role=MeasurementRole.GRID_METER,
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is not None
    assert result.measurement.value == value
    assert result.selected_source_id == "grid_meter_primary"
    assert result.fallback_used is False
    assert result.selection_reason is SourceSelectionReason.PRIMARY_SELECTED


def test_rejected_primary_uses_eligible_grid_fallback_with_reason() -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.GRID_POWER,
        (
            _candidate(
                Metric.GRID_POWER,
                9000.0,
                source_id="grid_meter_primary",
                role=MeasurementRole.GRID_METER,
                quality=MeasurementQuality.REJECTED,
                decision=ValidationDecision.REJECT,
            ),
            _candidate(
                Metric.GRID_POWER,
                420.0,
                source_id="house_meter",
                role=MeasurementRole.GRID_METER,
                measurement_position="grid_fallback",
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.selected_source_id == "house_meter"
    assert result.fallback_used is True
    assert result.rejected_candidates[0].reason is (
        CandidateRejectionReason.VALIDATION_REJECTED
    )


def test_sub_distribution_is_never_eligible_as_grid_fallback() -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.GRID_POWER,
        (
            _candidate(
                Metric.GRID_POWER,
                300.0,
                source_id="house_meter",
                role=MeasurementRole.GRID_METER,
                measurement_position="sub_distribution",
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is None
    assert result.selected_quality is MeasurementQuality.UNAVAILABLE
    assert result.rejected_candidates[1].reason is (
        CandidateRejectionReason.MEASUREMENT_POSITION_MISMATCH
    )


def test_grid_fallback_requires_an_explicit_eligible_position() -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.GRID_POWER,
        (
            _candidate(
                Metric.GRID_POWER,
                300.0,
                source_id="house_meter",
                role=MeasurementRole.GRID_METER,
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is None
    assert result.rejected_candidates[1].reason is (
        CandidateRejectionReason.MEASUREMENT_POSITION_MISMATCH
    )


def test_suspect_policy_is_explicit_and_findings_are_forwarded() -> None:
    finding = ValidationFinding(
        rule_id="VAL-TEST",
        code="comparison_warning",
        message="Comparison differs.",
        severity=ValidationSeverity.WARNING,
    )
    original = _measurement(
        Metric.PLANT_AC_POWER,
        835.0,
        source_id="solakon_meter",
        role=MeasurementRole.PLANT_METER,
        quality=MeasurementQuality.REPORTED,
    )
    suspect = _measurement(
        Metric.PLANT_AC_POWER,
        835.0,
        source_id="solakon_meter",
        role=MeasurementRole.PLANT_METER,
        quality=MeasurementQuality.SUSPECT,
    )
    validated = ValidatedMeasurement(
        original=original,
        result=ValidationResult.warning(
            835.0,
            findings=(finding,),
        ),
        measurement=suspect,
    )
    candidate = SourceCandidate.from_validated(validated)

    accepted = SourceSelector(PRIORITIES).select(
        Metric.PLANT_AC_POWER,
        (candidate,),
        selection_timestamp=NOW,
    )
    rejected = SourceSelector(
        PRIORITIES,
        allow_suspect_measurements=False,
    ).select(
        Metric.PLANT_AC_POWER,
        (candidate,),
        selection_timestamp=NOW,
    )

    assert accepted.selected_quality is MeasurementQuality.SUSPECT
    assert accepted.findings[0].code == "comparison_warning"
    assert rejected.measurement is None
    assert rejected.rejected_candidates[0].reason is (
        CandidateRejectionReason.SUSPECT_NOT_ALLOWED
    )


def test_plant_fallback_can_be_disabled_without_affecting_primary() -> None:
    selector = SourceSelector(PRIORITIES, allow_plant_fallback=False)
    result = selector.select(
        Metric.PLANT_AC_POWER,
        (
            _candidate(
                Metric.PLANT_AC_POWER,
                380.0,
                source_id="solakon_one",
                role=MeasurementRole.SOLAR_SYSTEM,
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is None
    assert result.rejected_candidates[1].reason is (
        CandidateRejectionReason.FALLBACK_NOT_ALLOWED
    )


def test_wrong_role_and_unconfigured_source_are_explained() -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.PV_POWER,
        (
            _candidate(
                Metric.PV_POWER,
                600.0,
                source_id="solakon_one",
                role=MeasurementRole.PLANT_METER,
            ),
            _candidate(
                Metric.PV_POWER,
                610.0,
                source_id="other",
                role=MeasurementRole.SOLAR_SYSTEM,
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is None
    assert [candidate.reason for candidate in result.rejected_candidates] == [
        CandidateRejectionReason.ROLE_MISMATCH,
        CandidateRejectionReason.SOURCE_NOT_CONFIGURED,
    ]


def test_real_zero_from_plant_primary_does_not_fall_back() -> None:
    selector = SourceSelector(PRIORITIES)
    result = selector.select(
        Metric.PLANT_AC_POWER,
        (
            _candidate(
                Metric.PLANT_AC_POWER,
                0.0,
                source_id="solakon_meter",
                role=MeasurementRole.PLANT_METER,
            ),
            _candidate(
                Metric.PLANT_AC_POWER,
                250.0,
                source_id="solakon_one",
                role=MeasurementRole.SOLAR_SYSTEM,
            ),
        ),
        selection_timestamp=NOW,
    )

    assert result.measurement is not None
    assert result.measurement.value == 0.0
    assert result.selected_source_id == "solakon_meter"
    assert result.fallback_used is False
