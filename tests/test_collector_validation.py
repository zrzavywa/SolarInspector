"""Test snapshot validation and the collector processing boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from zrzavy_energy_monitor_core.config.defaults import DEFAULT_CONFIG
from zrzavy_energy_monitor_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from zrzavy_energy_monitor_core.models.energy_balance import EnergyBalanceQuality
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import unit_for_metric
from zrzavy_energy_monitor_core.services.collector import Collector
from zrzavy_energy_monitor_core.validation import (
    CollectorValidationBridge,
    ValidationDecision,
)

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _measurement(
    metric: Metric,
    value: float,
    *,
    source_id: str = "solakon_one",
    role: MeasurementRole = MeasurementRole.SOLAR_SYSTEM,
    measured_at: datetime = NOW,
) -> Measurement:
    return Measurement(
        metric=metric,
        value=value,
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=measured_at,
        quality=MeasurementQuality.REPORTED,
        raw_value=value,
    )


def _snapshot(
    *measurements: Measurement,
    source_id: str = "solakon_one",
) -> DeviceSnapshot:
    return DeviceSnapshot(
        source_id=source_id,
        status=DeviceConnectionStatus.ONLINE,
        measurements=tuple(measurements),
        received_at=NOW,
        metadata=(("model_name", "test"),),
    )


def _config(enabled: bool = True) -> dict[str, Any]:
    return {
        "validation": {
            "enabled": enabled,
            "profiles": {},
            "sources": {},
        }
    }


def test_disabled_validation_is_a_strict_no_op() -> None:
    snapshot = _snapshot(_measurement(Metric.PLANT_AC_POWER, 8350.0))
    result = CollectorValidationBridge().validate_cycle(
        (snapshot,),
        config=_config(False),
        now=NOW,
    )

    assert result.snapshots == (snapshot,)
    assert result.validated_snapshots == ()
    assert result.events == ()


def test_solarkon_warning_remains_usable_and_is_marked_suspect() -> None:
    result = CollectorValidationBridge().validate_cycle(
        (_snapshot(_measurement(Metric.PLANT_AC_POWER, 835.0)),),
        config=_config(),
        now=NOW,
    )
    output = result.snapshots[0]

    assert len(output.measurements) == 1
    assert output.measurements[0].value == 835.0
    assert output.measurements[0].quality is MeasurementQuality.SUSPECT
    assert output.status is DeviceConnectionStatus.DEGRADED
    assert len(result.events) == 1
    assert result.events[0].decision is ValidationDecision.ACCEPT_WITH_WARNING


def test_rejected_value_is_removed_but_other_device_values_survive() -> None:
    result = CollectorValidationBridge().validate_cycle(
        (
            _snapshot(
                _measurement(Metric.PLANT_AC_POWER, 8350.0),
                _measurement(
                    Metric.BATTERY_SOC,
                    50.0,
                    role=MeasurementRole.BATTERY_SYSTEM,
                ),
            ),
        ),
        config=_config(),
        now=NOW,
    )
    output = result.snapshots[0]

    assert {measurement.metric for measurement in output.measurements} == {
        Metric.BATTERY_SOC
    }
    assert result.events[0].metric is Metric.PLANT_AC_POWER
    assert result.events[0].decision is ValidationDecision.REJECT


def test_real_zero_remains_available() -> None:
    result = CollectorValidationBridge().validate_cycle(
        (_snapshot(_measurement(Metric.PLANT_AC_POWER, 0.0)),),
        config=_config(),
        now=NOW,
    )

    assert result.snapshots[0].measurements[0].value == 0.0
    assert result.events == ()


def test_stale_value_is_removed_from_current_snapshot() -> None:
    result = CollectorValidationBridge().validate_cycle(
        (
            _snapshot(
                _measurement(
                    Metric.PLANT_AC_POWER,
                    400.0,
                    measured_at=NOW - timedelta(seconds=61),
                )
            ),
        ),
        config=_config(),
        now=NOW,
    )

    assert result.snapshots[0].measurements == ()
    assert result.events[0].quality is MeasurementQuality.STALE


def test_explicit_profile_overrides_built_in_range() -> None:
    config = {
        "validation": {
            "enabled": True,
            "profiles": {
                "custom": {
                    "ranges": {
                        "plant_ac_power": {
                            "warning_max": 1000,
                            "reject_max": 1200,
                        }
                    }
                }
            },
            "sources": {
                "solakon_one": {
                    "profile": "custom",
                }
            },
        }
    }
    result = CollectorValidationBridge().validate_cycle(
        (_snapshot(_measurement(Metric.PLANT_AC_POWER, 1000.0)),),
        config=config,
        now=NOW,
    )

    assert result.snapshots[0].measurements[0].value == 1000.0
    assert result.events == ()


def test_historical_delta_uses_only_last_accepted_reference() -> None:
    bridge = CollectorValidationBridge()
    config = {
        "validation": {
            "enabled": True,
            "profiles": {
                "custom": {
                    "deltas": {
                        "plant_ac_power": {
                            "warning_absolute": 50,
                            "reject_absolute": 100,
                        }
                    }
                }
            },
            "sources": {
                "custom": {
                    "profile": "custom",
                }
            },
        }
    }
    first = _snapshot(
        _measurement(
            Metric.PLANT_AC_POWER,
            100.0,
            source_id="custom",
        ),
        source_id="custom",
    )
    second_measurement = _measurement(
        Metric.PLANT_AC_POWER,
        500.0,
        source_id="custom",
        measured_at=NOW + timedelta(seconds=10),
    )
    second = DeviceSnapshot(
        source_id="custom",
        status=DeviceConnectionStatus.ONLINE,
        measurements=(second_measurement,),
        received_at=NOW + timedelta(seconds=10),
    )

    bridge.validate_cycle((first,), config=config, now=NOW)
    rejected = bridge.validate_cycle(
        (second,),
        config=config,
        now=NOW + timedelta(seconds=10),
    )

    assert rejected.snapshots[0].measurements == ()
    bridge.clear()
    accepted_after_reset = bridge.validate_cycle(
        (second,),
        config=config,
        now=NOW + timedelta(seconds=10),
    )
    assert accepted_after_reset.snapshots[0].measurements


class _ConfigStub:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def get(self) -> dict[str, Any]:
        return self._config


class _DatabaseStub:
    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []

    def latest(self) -> None:
        return None

    def insert_sample(self, sample: dict[str, Any]) -> int:
        self.samples.append(dict(sample))
        return len(self.samples)


def test_collector_excludes_rejected_power_before_energy_integration() -> None:
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
    config["general"]["solar_power_source"] = "auto"

    snapshot = _snapshot(
        _measurement(Metric.PLANT_AC_POWER, 8350.0),
        _measurement(Metric.PV_POWER, 400.0),
    )
    collector = Collector(
        _ConfigStub(config),  # type: ignore[arg-type]
        _DatabaseStub(),  # type: ignore[arg-type]
    )
    collector._now = lambda: NOW  # type: ignore[method-assign]
    collector._read_solakon_snapshot_result = (  # type: ignore[method-assign]
        lambda _config: (None, snapshot, None)
    )

    sample = collector.collect_once()

    assert sample["solakon_ac_power_w"] is None
    assert sample["solakon_ac_wh"] == 0.0
    assert sample["solakon_pv_power_w"] == 400.0
    assert sample["solar_power_w"] == 400.0
    events = collector.validation_events()
    assert len(events) == 1
    assert events[0].metric is Metric.PLANT_AC_POWER
    assert events[0].decision is ValidationDecision.REJECT
    balance = collector.energy_balance()
    assert balance is not None
    assert balance.quality is EnergyBalanceQuality.UNAVAILABLE
    assert balance.pv_power_w == 400.0


def test_collector_evaluates_sources_after_device_reads() -> None:
    config = deepcopy(DEFAULT_CONFIG)
    for key in (
        "grid_meter",
        "house_meter",
        "solakon_meter",
        "solakon_one",
    ):
        config[key]["enabled"] = False
    config["solakon_meter"]["enabled"] = True
    config["validation"]["enabled"] = True
    measurement_timestamp = NOW + timedelta(milliseconds=100)
    snapshot = _snapshot(
        _measurement(
            Metric.PLANT_AC_POWER,
            400.0,
            source_id="solakon_meter",
            role=MeasurementRole.PLANT_METER,
            measured_at=measurement_timestamp,
        ),
        source_id="solakon_meter",
    )
    collector = Collector(
        _ConfigStub(config),  # type: ignore[arg-type]
        _DatabaseStub(),  # type: ignore[arg-type]
    )
    timestamps = iter((NOW, NOW + timedelta(milliseconds=200)))
    collector._now = lambda: next(timestamps)  # type: ignore[method-assign]
    collector._read_shelly_snapshot_result = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (None, snapshot, None)
    )

    collector.collect_once()

    balance = collector.energy_balance()
    assert balance is not None
    assert balance.calculated_at == NOW + timedelta(milliseconds=200)
    plant_source = next(
        source
        for source in balance.source_metadata
        if source.requested_metric is Metric.PLANT_AC_POWER
    )
    assert plant_source.selected_source_id == "solakon_meter"
    assert plant_source.selected_measurement_timestamp == measurement_timestamp
    assert (
        plant_source.selection_timestamp - measurement_timestamp
    ).total_seconds() == 0.1
    assert all(
        rejected.reason.value != "invalid_timestamp"
        for rejected in plant_source.rejected_candidates
    )


def test_collector_continues_after_controlled_balance_failure(
    monkeypatch: Any,
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
    snapshot = _snapshot(_measurement(Metric.PV_POWER, 400.0))
    database = _DatabaseStub()
    collector = Collector(
        _ConfigStub(config),  # type: ignore[arg-type]
        database,  # type: ignore[arg-type]
    )
    collector._now = lambda: NOW  # type: ignore[method-assign]
    collector._read_solakon_snapshot_result = (  # type: ignore[method-assign]
        lambda _config: (None, snapshot, None)
    )

    def fail_balance(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic balance failure")

    monkeypatch.setattr(
        "zrzavy_energy_monitor_core.services.collector.build_cycle_energy_balance",
        fail_balance,
    )

    sample = collector.collect_once()

    assert sample["id"] == 1
    assert len(database.samples) == 1
    assert "Energiebilanz: Berechnung fehlgeschlagen." in sample["error_text"]
    balance = collector.energy_balance()
    assert balance is not None
    assert balance.quality is EnergyBalanceQuality.UNAVAILABLE
    assert any(
        finding.code == "energy_balance_calculation_failed"
        for finding in balance.findings
    )
