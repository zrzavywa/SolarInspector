"""Replay deterministic normalized snapshots through the validation bridge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zrzavy_energy_monitor_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from zrzavy_energy_monitor_core.models.measurement import Measurement
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.quality import MeasurementQuality
from zrzavy_energy_monitor_core.models.roles import MeasurementRole
from zrzavy_energy_monitor_core.models.units import unit_for_metric
from zrzavy_energy_monitor_core.validation.collector import (
    CollectorValidationBridge,
)
from zrzavy_energy_monitor_core.validation.result import ValidationDecision


@dataclass(frozen=True, slots=True)
class ReplayExpectation:
    """Describe the expected public result of one replay cycle."""

    accepted_values: tuple[tuple[str, float], ...] = ()
    rejected_metrics: tuple[str, ...] = ()
    event_codes: tuple[str, ...] = ()
    statuses: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayStep:
    """Contain one deterministic collector-validation input cycle."""

    at: str
    snapshots: tuple[DeviceSnapshot, ...]
    expectation: ReplayExpectation


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    """Contain metadata, validation configuration, and replay cycles."""

    name: str
    validation: dict[str, Any]
    steps: tuple[ReplayStep, ...]


@dataclass(frozen=True, slots=True)
class ReplayStepResult:
    """Expose a compact, deterministic result for one replay cycle."""

    accepted_values: tuple[tuple[str, float], ...]
    rejected_metrics: tuple[str, ...]
    event_codes: tuple[str, ...]
    statuses: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """Return all results generated while replaying one scenario."""

    name: str
    results: tuple[ReplayStepResult, ...]

    @property
    def event_count(self) -> int:
        """Return the number of actionable finding codes in the report."""

        return sum(len(result.event_codes) for result in self.results)


def load_replay_scenario(path: Path) -> ReplayScenario:
    """Load one JSONL replay without performing network or wall-clock waits."""

    metadata: dict[str, Any] | None = None
    steps: list[ReplayStep] = []

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number}: replay line must be an object")

        record_type = payload.get("type")
        if record_type == "metadata":
            if metadata is not None or steps:
                raise ValueError(f"{path}:{line_number}: metadata must be first")
            metadata = payload
            continue
        if record_type != "cycle":
            raise ValueError(f"{path}:{line_number}: unsupported replay record type")
        if metadata is None:
            raise ValueError(f"{path}:{line_number}: metadata record is missing")
        steps.append(_parse_step(payload, path, line_number))

    if metadata is None:
        raise ValueError(f"{path}: metadata record is missing")
    name = str(metadata.get("name", "")).strip()
    if not name:
        raise ValueError(f"{path}: replay name must not be empty")
    validation = metadata.get("validation", {})
    if not isinstance(validation, dict):
        raise ValueError(f"{path}: validation must be an object")
    if not steps:
        raise ValueError(f"{path}: replay contains no cycles")

    return ReplayScenario(
        name=name,
        validation=dict(validation),
        steps=tuple(steps),
    )


def run_replay_scenario(
    scenario: ReplayScenario,
    *,
    bridge: CollectorValidationBridge | None = None,
) -> ReplayReport:
    """Run all cycles immediately through one isolated validation bridge."""

    active_bridge = bridge or CollectorValidationBridge()
    results: list[ReplayStepResult] = []
    config = {"validation": scenario.validation}

    for step in scenario.steps:
        now = _parse_datetime(step.at, "cycle.at")
        validated = active_bridge.validate_cycle(
            step.snapshots,
            config=config,
            now=now,
        )
        accepted_values = tuple(
            sorted(
                (
                    f"{measurement.source_id}:{measurement.metric.value}",
                    float(measurement.value),
                )
                for snapshot in validated.snapshots
                for measurement in snapshot.measurements
            )
        )
        rejected_metrics = tuple(
            sorted(
                f"{event.source_id}:{event.metric.value}"
                for event in validated.events
                if event.decision is ValidationDecision.REJECT
            )
        )
        event_codes = tuple(
            sorted(
                finding.code for event in validated.events for finding in event.findings
            )
        )
        statuses = tuple(
            sorted(
                (
                    snapshot.source_id,
                    snapshot.status.value,
                )
                for snapshot in validated.snapshots
            )
        )
        results.append(
            ReplayStepResult(
                accepted_values=accepted_values,
                rejected_metrics=rejected_metrics,
                event_codes=event_codes,
                statuses=statuses,
            )
        )

    return ReplayReport(
        name=scenario.name,
        results=tuple(results),
    )


def _parse_step(
    payload: dict[str, Any],
    path: Path,
    line_number: int,
) -> ReplayStep:
    """Parse one replay cycle and its expected public outcome."""

    at = str(payload.get("at", "")).strip()
    cycle_time = _parse_datetime(
        at,
        f"{path}:{line_number}: cycle.at",
    )

    raw_snapshots = payload.get("snapshots")
    if not isinstance(raw_snapshots, list):
        raise ValueError(f"{path}:{line_number}: snapshots must be an array")
    snapshots = tuple(
        _parse_snapshot(
            item,
            cycle_time=cycle_time,
            location=f"{path}:{line_number}: snapshots[{index}]",
        )
        for index, item in enumerate(raw_snapshots)
    )

    raw_expectation = payload.get("expect", {})
    if not isinstance(raw_expectation, dict):
        raise ValueError(f"{path}:{line_number}: expect must be an object")

    accepted = raw_expectation.get("accepted_values", {})
    if not isinstance(accepted, dict):
        raise ValueError(f"{path}:{line_number}: accepted_values must be an object")
    statuses = raw_expectation.get("statuses", {})
    if not isinstance(statuses, dict):
        raise ValueError(f"{path}:{line_number}: statuses must be an object")

    return ReplayStep(
        at=at,
        snapshots=snapshots,
        expectation=ReplayExpectation(
            accepted_values=tuple(
                sorted((str(key), float(value)) for key, value in accepted.items())
            ),
            rejected_metrics=_string_tuple(raw_expectation.get("rejected_metrics", [])),
            event_codes=_string_tuple(raw_expectation.get("event_codes", [])),
            statuses=tuple(
                sorted((str(key), str(value)) for key, value in statuses.items())
            ),
        ),
    )


def _parse_snapshot(
    value: object,
    *,
    cycle_time: Any,
    location: str,
) -> DeviceSnapshot:
    """Build one normalized replay snapshot."""

    if not isinstance(value, dict):
        raise ValueError(f"{location}: snapshot must be an object")

    source_id = str(value.get("source_id", "")).strip()
    if not source_id:
        raise ValueError(f"{location}: source_id must not be empty")
    try:
        status = DeviceConnectionStatus(str(value.get("status", "online")))
    except ValueError as exc:
        raise ValueError(f"{location}: unsupported status") from exc

    raw_measurements = value.get("measurements", [])
    if not isinstance(raw_measurements, list):
        raise ValueError(f"{location}: measurements must be an array")

    measurements = tuple(
        _parse_measurement(
            item,
            source_id=source_id,
            cycle_time=cycle_time,
            location=f"{location}.measurements[{index}]",
        )
        for index, item in enumerate(raw_measurements)
    )
    metadata = value.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{location}: metadata must be an object")

    return DeviceSnapshot(
        source_id=source_id,
        status=status,
        measurements=measurements,
        received_at=cycle_time,
        error=(str(value["error"]) if value.get("error") is not None else None),
        metadata=tuple(sorted((str(key), str(item)) for key, item in metadata.items())),
    )


def _parse_measurement(
    value: object,
    *,
    source_id: str,
    cycle_time: Any,
    location: str,
) -> Measurement:
    """Build one strict normalized measurement from a replay record."""

    if not isinstance(value, dict):
        raise ValueError(f"{location}: measurement must be an object")
    try:
        metric = Metric(str(value["metric"]))
        role = MeasurementRole(str(value["role"]))
        quality = MeasurementQuality(str(value.get("quality", "reported")))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{location}: invalid metric, role, or quality") from exc

    measured_at = cycle_time
    if "offset_seconds" in value:
        from datetime import timedelta

        measured_at = cycle_time + timedelta(seconds=float(value["offset_seconds"]))

    numeric_value = value.get("value")
    if isinstance(numeric_value, bool) or not isinstance(
        numeric_value,
        (int, float),
    ):
        raise ValueError(f"{location}: value must be numeric")

    return Measurement(
        metric=metric,
        value=float(numeric_value),
        unit=unit_for_metric(metric),
        source_id=source_id,
        role=role,
        measured_at=measured_at,
        received_at=cycle_time,
        quality=quality,
        raw_value=value.get("raw_value", numeric_value),
    )


def _parse_datetime(value: str, location: str) -> Any:
    """Parse one timezone-aware ISO-8601 timestamp."""

    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{location}: invalid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{location}: timestamp must include timezone")
    return parsed


def _string_tuple(value: object) -> tuple[str, ...]:
    """Normalize an expected string array in deterministic order."""

    if not isinstance(value, list):
        raise ValueError("expected value must be an array")
    return tuple(sorted(str(item) for item in value))
