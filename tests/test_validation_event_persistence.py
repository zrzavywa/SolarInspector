"""Test SQLite migration, aggregation, retention, and collector persistence."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

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
from zrzavy_energy_monitor_core.persistence.database import Database
from zrzavy_energy_monitor_core.services.collector import Collector
from zrzavy_energy_monitor_core.validation import (
    ValidationDecision,
    ValidationEvent,
    ValidationEventPersistencePolicy,
    ValidationEventStore,
    ValidationFinding,
    ValidationSeverity,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _event(
    *,
    occurred_at: datetime = NOW,
    raw_value: object = 835.0,
    accepted_value: float | None = 835.0,
    decision: ValidationDecision = (ValidationDecision.ACCEPT_WITH_WARNING),
    quality: MeasurementQuality = MeasurementQuality.SUSPECT,
    rule_id: str = "VAL-RANGE-001",
    code: str = "range_warning_threshold_exceeded",
    severity: ValidationSeverity = ValidationSeverity.WARNING,
    details: tuple[tuple[str, object], ...] = (("warning_max", 800.0),),
) -> ValidationEvent:
    return ValidationEvent(
        occurred_at=occurred_at,
        source_id="solakon_one",
        role=MeasurementRole.SOLAR_SYSTEM,
        metric=Metric.PLANT_AC_POWER,
        decision=decision,
        quality=quality,
        raw_value=raw_value,
        accepted_value=accepted_value,
        findings=(
            ValidationFinding(
                rule_id=rule_id,
                code=code,
                message="Configured validation threshold exceeded.",
                severity=severity,
                details=details,
            ),
        ),
    )


def _sample(epoch: float) -> dict[str, object]:
    return {
        "ts_epoch": epoch,
        "ts_local": datetime.fromtimestamp(
            epoch,
            tz=timezone.utc,
        ).isoformat(),
    }


def test_database_migration_is_idempotent_and_preserves_samples(
    tmp_path,
) -> None:
    database = Database(tmp_path / "solarinspector.db")
    sample_id = database.insert_sample(_sample(NOW.timestamp()))

    database.initialize()
    database.initialize()

    assert database.latest()["id"] == sample_id
    with database.connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(validation_events)").fetchall()
        }
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(validation_events)").fetchall()
        }

    assert {
        "first_seen_epoch",
        "last_seen_epoch",
        "source_id",
        "metric",
        "rule_id",
        "raw_value_json",
        "accepted_value",
        "occurrence_count",
        "minimum_value",
        "maximum_value",
    } <= columns
    assert "idx_validation_events_last_seen" in indexes
    assert "idx_validation_events_identity" in indexes


def test_warning_event_persists_safe_structured_fields(tmp_path) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)
    sample_id = database.insert_sample(_sample(NOW.timestamp()))

    persisted_ids = store.persist(
        (_event(),),
        sample_id=sample_id,
        reference_time=NOW,
    )
    row = store.latest(limit=1)[0]

    assert persisted_ids == (row["id"],)
    assert row["source_id"] == "solakon_one"
    assert row["metric"] == "plant_ac_power"
    assert row["unit"] == "W"
    assert row["decision"] == "accept_with_warning"
    assert row["quality"] == "suspect"
    assert row["accepted_value"] == 835.0
    assert row["raw_value"] == 835.0
    assert row["details"] == {"warning_max": 800.0}
    assert row["occurrence_count"] == 1
    assert row["first_sample_id"] == sample_id
    assert row["last_sample_id"] == sample_id


def test_rejected_event_stores_null_accepted_value(tmp_path) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)

    store.persist(
        (
            _event(
                raw_value=8350.0,
                accepted_value=None,
                decision=ValidationDecision.REJECT,
                quality=MeasurementQuality.REJECTED,
                severity=ValidationSeverity.ERROR,
                code="range_reject_threshold_exceeded",
            ),
        ),
        reference_time=NOW,
    )
    row = store.latest(limit=1)[0]

    assert row["decision"] == "reject"
    assert row["accepted_value"] is None
    assert row["raw_value"] == 8350.0


def test_identical_events_are_deduplicated_with_minimum_and_maximum(
    tmp_path,
) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)
    policy = ValidationEventPersistencePolicy(
        dedup_window_seconds=300,
    )

    first_ids = store.persist(
        (_event(raw_value=835.0, accepted_value=835.0),),
        policy=policy,
        reference_time=NOW,
    )
    second_ids = store.persist(
        (
            _event(
                occurred_at=NOW + timedelta(seconds=30),
                raw_value=845.0,
                accepted_value=845.0,
            ),
        ),
        policy=policy,
        reference_time=NOW + timedelta(seconds=30),
    )
    row = store.latest(limit=1)[0]

    assert first_ids == second_ids
    assert store.count() == 1
    assert row["occurrence_count"] == 2
    assert row["first_seen_epoch"] == NOW.timestamp()
    assert row["last_seen_epoch"] == (NOW + timedelta(seconds=30)).timestamp()
    assert row["minimum_value"] == 835.0
    assert row["maximum_value"] == 845.0
    assert row["raw_value"] == 845.0


def test_event_after_deduplication_window_creates_new_row(
    tmp_path,
) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)
    policy = ValidationEventPersistencePolicy(
        dedup_window_seconds=30,
    )

    store.persist(
        (_event(),),
        policy=policy,
        reference_time=NOW,
    )
    store.persist(
        (
            _event(
                occurred_at=NOW + timedelta(seconds=31),
            ),
        ),
        policy=policy,
        reference_time=NOW + timedelta(seconds=31),
    )

    assert store.count() == 2


def test_different_rules_are_not_merged(tmp_path) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)

    store.persist(
        (
            _event(),
            _event(
                rule_id="VAL-DELTA-001",
                code="delta_warning_threshold_exceeded",
            ),
        ),
        reference_time=NOW,
    )

    assert store.count() == 2


def test_sensitive_and_oversized_details_are_not_persisted(
    tmp_path,
) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)
    policy = ValidationEventPersistencePolicy(
        max_details_chars=64,
        max_raw_value_chars=64,
    )

    store.persist(
        (
            _event(
                raw_value="https://user:password@example.test/value",
                details=(
                    ("token", "very-secret-token"),
                    (
                        "url",
                        "https://user:password@example.test/path",
                    ),
                    ("diagnostic", "x" * 5000),
                ),
            ),
        ),
        policy=policy,
        reference_time=NOW,
    )
    row = store.latest(limit=1)[0]

    serialized = json.dumps(row, ensure_ascii=False)
    assert "very-secret-token" not in serialized
    assert "user:password" not in serialized
    assert row["raw_value"] == "<redacted-url>"
    assert len(str(row["details_json"])) <= 64
    assert row["details"]["truncated"] is True
    assert row["details"]["original_length"] > 64


def test_retention_removes_only_expired_rows(tmp_path) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)

    store.persist(
        (_event(),),
        reference_time=NOW,
    )
    store.persist(
        (
            _event(
                occurred_at=NOW + timedelta(days=2),
                rule_id="VAL-DELTA-001",
                code="delta_warning_threshold_exceeded",
            ),
        ),
        reference_time=NOW + timedelta(days=2),
    )

    deleted = store.prune_expired(
        reference_time=NOW + timedelta(days=91),
        retention_days=90,
    )

    assert deleted == 1
    rows = store.latest(limit=10)
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "VAL-DELTA-001"


def test_delete_all_removes_validation_events_too(tmp_path) -> None:
    database = Database(tmp_path / "solarinspector.db")
    store = ValidationEventStore(database)
    database.insert_sample(_sample(NOW.timestamp()))
    store.persist((_event(),), reference_time=NOW)

    database.delete_all()

    assert database.latest() is None
    assert store.count() == 0


def test_policy_accepts_legacy_absence_and_rejects_invalid_limits() -> None:
    defaults = ValidationEventPersistencePolicy.from_config(None)
    configured = ValidationEventPersistencePolicy.from_config(
        {
            "dedup_window_seconds": "60",
            "retention_days": "30",
            "prune_interval_seconds": "600",
            "max_reason_chars": "256",
            "max_details_chars": "1024",
            "max_raw_value_chars": "128",
        }
    )

    assert defaults.dedup_window_seconds == 300.0
    assert defaults.retention_days == 90.0
    assert configured.dedup_window_seconds == 60.0
    assert configured.retention_days == 30.0

    try:
        ValidationEventPersistencePolicy(retention_days=0)
    except ValueError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("invalid retention was accepted")


def _measurement(
    metric: Metric,
    value: float,
    *,
    role: MeasurementRole = MeasurementRole.SOLAR_SYSTEM,
) -> Measurement:
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id="solakon_one",
        role=role,
        measured_at=NOW,
        received_at=NOW,
        quality=MeasurementQuality.REPORTED,
        raw_value=value,
    )


def _snapshot(*measurements: Measurement) -> DeviceSnapshot:
    return DeviceSnapshot(
        source_id="solakon_one",
        status=DeviceConnectionStatus.ONLINE,
        measurements=tuple(measurements),
        received_at=NOW,
        metadata=(("model_name", "test"),),
    )


class _ConfigStub:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def get(self) -> dict[str, Any]:
        return self._config


def test_collector_persists_generated_validation_events(
    tmp_path,
) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    for key in (
        "grid_meter",
        "house_meter",
        "solakon_meter",
        "solakon_one",
    ):
        config[key]["enabled"] = False
    config["solakon_one"]["enabled"] = True
    config["validation"]["enabled"] = True
    config["validation"]["persistence"] = {
        "dedup_window_seconds": 300,
        "retention_days": 90,
    }

    database = Database(tmp_path / "solarinspector.db")
    collector = Collector(
        _ConfigStub(config),  # type: ignore[arg-type]
        database,
    )
    snapshot = _snapshot(
        _measurement(Metric.PLANT_AC_POWER, 8350.0),
        _measurement(Metric.PV_POWER, 400.0),
    )
    collector._now = lambda: NOW  # type: ignore[method-assign]
    collector._read_solakon_snapshot_result = (  # type: ignore[method-assign]
        lambda _config: (None, snapshot, None)
    )

    sample = collector.collect_once()
    rows = ValidationEventStore(database).latest(limit=10)

    assert sample["id"] == 1
    assert len(rows) == 1
    assert rows[0]["metric"] == "plant_ac_power"
    assert rows[0]["decision"] == "reject"
    assert rows[0]["accepted_value"] is None
