"""Test public validation event API builders and dashboard contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.persistence.database import Database
from zrzavy_energy_monitor_core.validation import (
    ValidationDecision,
    ValidationEvent,
    ValidationEventPersistencePolicy,
    ValidationEventStore,
    ValidationFinding,
    ValidationSeverity,
)
from zrzavy_energy_monitor_core.web.validation import (
    build_validation_events_api_response,
    build_validation_summary_api_response,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _event(
    *,
    occurred_at: datetime,
    source_id: str,
    decision: ValidationDecision,
    severity: ValidationSeverity,
    code: str,
    value: float,
) -> ValidationEvent:
    return ValidationEvent(
        occurred_at=occurred_at,
        source_id=source_id,
        role=MeasurementRole.SOLAR_SYSTEM,
        metric=Metric.PLANT_AC_POWER,
        decision=decision,
        quality=(
            MeasurementQuality.SUSPECT
            if decision is ValidationDecision.ACCEPT_WITH_WARNING
            else MeasurementQuality.REJECTED
        ),
        raw_value=value,
        accepted_value=(
            value if decision is ValidationDecision.ACCEPT_WITH_WARNING else None
        ),
        findings=(
            ValidationFinding(
                rule_id="VAL-RANGE-001",
                code=code,
                message="Configured validation threshold exceeded.",
                severity=severity,
                details=(
                    ("warning_limit", 800.0),
                    ("password", "must-not-be-persisted"),
                ),
            ),
        ),
    )


def _database(tmp_path: Path) -> Database:
    return Database(tmp_path / "validation-web.sqlite")


def test_summary_counts_groups_and_occurrences(tmp_path: Path) -> None:
    database = _database(tmp_path)
    store = ValidationEventStore(database)
    policy = ValidationEventPersistencePolicy(
        dedup_window_seconds=300,
    )
    warning = _event(
        occurred_at=NOW - timedelta(minutes=10),
        source_id="solakon_one",
        decision=ValidationDecision.ACCEPT_WITH_WARNING,
        severity=ValidationSeverity.WARNING,
        code="range_warning",
        value=835.0,
    )
    repeated = _event(
        occurred_at=NOW - timedelta(minutes=8),
        source_id="solakon_one",
        decision=ValidationDecision.ACCEPT_WITH_WARNING,
        severity=ValidationSeverity.WARNING,
        code="range_warning",
        value=840.0,
    )
    rejected = _event(
        occurred_at=NOW - timedelta(minutes=5),
        source_id="grid_meter_primary",
        decision=ValidationDecision.REJECT,
        severity=ValidationSeverity.ERROR,
        code="range_rejected",
        value=9999.0,
    )
    store.persist((warning,), policy=policy, reference_time=NOW)
    store.persist((repeated,), policy=policy, reference_time=NOW)
    store.persist((rejected,), policy=policy, reference_time=NOW)

    payload = build_validation_summary_api_response(
        database,
        enabled=True,
        hours_value=24,
        recent_limit_value=8,
        now_epoch=NOW.timestamp(),
    )

    assert payload["status"] == "error"
    assert payload["summary"]["event_group_count"] == 2
    assert payload["summary"]["occurrence_count"] == 3
    assert payload["summary"]["warning_occurrence_count"] == 2
    assert payload["summary"]["rejection_occurrence_count"] == 1
    assert len(payload["recent_events"]) == 2
    assert payload["recent_events"][0]["decision"] == "reject"
    assert payload["sources"][0]["source_id"] in {
        "grid_meter_primary",
        "solakon_one",
    }


def test_events_api_filters_and_decodes_safe_fields(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    store = ValidationEventStore(database)
    store.persist(
        (
            _event(
                occurred_at=NOW,
                source_id="solakon_one",
                decision=ValidationDecision.ACCEPT_WITH_WARNING,
                severity=ValidationSeverity.WARNING,
                code="range_warning",
                value=835.0,
            ),
        ),
        reference_time=NOW,
    )

    payload = build_validation_events_api_response(
        database,
        source_id=" solakon_one ",
        decision="accept_with_warning",
        severity="warning",
        limit_value="9999",
        hours_value="24",
        now_epoch=NOW.timestamp(),
    )

    assert payload["filters"]["limit"] == 500
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    assert event["source_id"] == "solakon_one"
    assert event["raw_value"] == 835.0
    assert event["details"]["password"] == "<redacted>"
    assert event["accepted_value"] == 835.0


def test_disabled_summary_has_explicit_status(tmp_path: Path) -> None:
    database = _database(tmp_path)

    payload = build_validation_summary_api_response(
        database,
        enabled=False,
        now_epoch=NOW.timestamp(),
    )

    assert payload["enabled"] is False
    assert payload["status"] == "disabled"
    assert payload["summary"]["occurrence_count"] == 0
    assert payload["recent_events"] == []


def test_dashboard_contains_validation_contract() -> None:
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    script = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    for identifier in (
        "validation-status",
        "validation-warning-count",
        "validation-rejection-count",
        "validation-event-body",
    ):
        assert f'id="{identifier}"' in template
    assert "/api/validation/summary" in script
