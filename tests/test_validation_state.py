"""Test historical reference management for validation rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.models.units import Unit
from solarinspector_core.validation import (
    MeasurementCandidate,
    ValidationStateStore,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _measurement(**overrides: object) -> Measurement:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 100.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW,
        "received_at": NOW,
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return Measurement(**values)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> MeasurementCandidate:
    values: dict[str, object] = {
        "metric": Metric.GRID_POWER,
        "value": 120.0,
        "unit": Unit.WATT,
        "source_id": "grid_meter_primary",
        "role": MeasurementRole.GRID_METER,
        "measured_at": NOW + timedelta(seconds=10),
        "received_at": NOW + timedelta(seconds=10),
        "quality": MeasurementQuality.REPORTED,
    }
    values.update(overrides)
    return MeasurementCandidate(**values)  # type: ignore[arg-type]


def test_state_store_records_and_returns_matching_stream() -> None:
    store = ValidationStateStore()
    measurement = _measurement()

    assert store.record_accepted(measurement) is True
    assert store.previous_for(_candidate()) == measurement
    assert len(store) == 1


def test_state_store_isolates_sources_roles_and_metrics() -> None:
    store = ValidationStateStore()
    store.record_accepted(_measurement())

    assert store.previous_for(_candidate(source_id="other")) is None
    assert store.previous_for(_candidate(role=MeasurementRole.HOUSE_METER)) is None
    assert store.previous_for(_candidate(metric=Metric.GRID_VOLTAGE)) is None


def test_state_store_does_not_use_empty_candidate_source() -> None:
    store = ValidationStateStore()
    store.record_accepted(_measurement())

    assert store.previous_for(_candidate(source_id="")) is None


def test_state_store_keeps_newer_reference_when_old_data_arrives() -> None:
    store = ValidationStateStore()
    newer = _measurement(
        value=120.0,
        measured_at=NOW + timedelta(seconds=20),
        received_at=NOW + timedelta(seconds=20),
    )
    older = _measurement(value=90.0)

    assert store.record_accepted(newer) is True
    assert store.record_accepted(older) is False
    assert store.previous_for(_candidate()) == newer


def test_state_store_allows_equal_timestamp_replacement() -> None:
    store = ValidationStateStore()
    first = _measurement(value=100.0)
    replacement = _measurement(value=101.0)

    assert store.record_accepted(first) is True
    assert store.record_accepted(replacement) is True
    assert store.previous_for(_candidate()) == replacement


def test_state_store_rejects_unusable_reference_qualities() -> None:
    store = ValidationStateStore()

    for quality in (
        MeasurementQuality.REJECTED,
        MeasurementQuality.STALE,
        MeasurementQuality.UNAVAILABLE,
    ):
        assert store.record_accepted(_measurement(quality=quality)) is False

    assert len(store) == 0


def test_state_store_accepts_suspect_measurement_as_usable_reference() -> None:
    store = ValidationStateStore()
    suspect = _measurement(quality=MeasurementQuality.SUSPECT)

    assert store.record_accepted(suspect) is True
    assert store.previous_for(_candidate()) == suspect


def test_state_store_builds_context_without_hidden_rule_logic() -> None:
    store = ValidationStateStore()
    previous = _measurement()
    store.record_accepted(previous)
    candidate = _candidate()

    context = store.context_for(
        candidate,
        now=NOW + timedelta(seconds=10),
        profile_name="official_grid_meter",
        source_settings=(("site", "home"),),
    )

    assert context.previous_measurement == previous
    assert context.profile_name == "official_grid_meter"
    assert context.source_settings == (("site", "home"),)


def test_state_store_clear_removes_all_streams() -> None:
    store = ValidationStateStore()
    store.record_accepted(_measurement())
    store.record_accepted(
        _measurement(
            metric=Metric.GRID_VOLTAGE,
            value=230.0,
            unit=Unit.VOLT,
        )
    )

    store.clear()

    assert len(store) == 0
    assert store.previous_for(_candidate()) is None
