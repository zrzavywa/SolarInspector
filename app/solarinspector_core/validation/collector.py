"""Connect normalized snapshots to the validation engine and rule profiles."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from solarinspector_core.models.device import (
    DeviceConnectionStatus,
    DeviceSnapshot,
)
from solarinspector_core.models.measurement import Measurement
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.validation.base import ValidationRule
from solarinspector_core.validation.config import (
    normalize_validation_config,
    normalize_validation_profile,
)
from solarinspector_core.validation.context import MeasurementCandidate
from solarinspector_core.validation.engine import (
    ValidatedDeviceSnapshot,
    ValidatedMeasurement,
    ValidationEngine,
    ValidationEvent,
)
from solarinspector_core.validation.profiles import (
    shelly_plant_profile,
    solarkon_800w_profile,
)
from solarinspector_core.validation.result import ValidationDecision
from solarinspector_core.validation.rules import (
    CrossSourceComparisonLimits,
    CrossSourceTimeAlignmentRule,
    DeviceDiagnosticRule,
    EnergyDeltaRule,
    ExpectedUnitRule,
    FiniteNumberRule,
    GridMeterCrossCheckRule,
    KnownDeviceErrorValueRule,
    MaximumDeltaRule,
    MeasurementAgeRule,
    MonotonicCounterRule,
    PhaseCompletenessRule,
    PhaseSumConsistencyRule,
    PlantPowerCrossCheckRule,
    RangeRule,
    TimestampRule,
)

_COUNTER_METRICS = {
    Metric.GRID_IMPORT_TOTAL,
    Metric.GRID_EXPORT_TOTAL,
    Metric.PLANT_AC_ENERGY_TOTAL,
    Metric.PLANT_AC_RETURNED_ENERGY_TOTAL,
    Metric.PV_ENERGY_TOTAL,
    Metric.BATTERY_CHARGE_TOTAL,
    Metric.BATTERY_DISCHARGE_TOTAL,
}


@dataclass(frozen=True, slots=True)
class ValidatedCycle:
    """Return validated snapshots and generated in-memory events."""

    snapshots: tuple[DeviceSnapshot, ...]
    validated_snapshots: tuple[ValidatedDeviceSnapshot, ...]
    events: tuple[ValidationEvent, ...]

    def snapshot_by_source(self) -> dict[str, DeviceSnapshot]:
        """Index the validated snapshots by stable source identity."""

        return {snapshot.source_id: snapshot for snapshot in self.snapshots}


class CollectorValidationBridge:
    """Validate one collector cycle before legacy selection and integration."""

    def __init__(
        self,
        *,
        history_limit: int = 512,
        history_seconds: float = 300.0,
        engine: ValidationEngine | None = None,
    ) -> None:
        """Create one bounded, restart-local comparison history."""

        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        if history_seconds <= 0:
            raise ValueError("history_seconds must be greater than zero")
        self._engine = engine or ValidationEngine()
        self._history: deque[Measurement] = deque(maxlen=history_limit)
        self._history_seconds = float(history_seconds)

    def validate_cycle(
        self,
        snapshots: tuple[DeviceSnapshot, ...],
        *,
        config: Mapping[str, Any],
        now: datetime,
    ) -> ValidatedCycle:
        """Validate all cycle snapshots before downstream calculation."""

        validation_config = normalize_validation_config(config.get("validation"))
        if validation_config["enabled"] is not True:
            return ValidatedCycle(
                snapshots=snapshots,
                validated_snapshots=(),
                events=(),
            )

        self._prune_history(now)
        all_original = tuple(
            measurement
            for snapshot in snapshots
            for measurement in snapshot.measurements
        )
        provisional: list[Measurement] = []

        for snapshot in snapshots:
            for measurement in snapshot.measurements:
                profile_name, profile, source = self._profile_for(
                    validation_config,
                    measurement.source_id,
                )
                if source.get("enabled", True) is not True:
                    provisional.append(measurement)
                    continue
                candidate = _candidate_from_measurement(measurement)
                context = self._engine.state_store.context_for(
                    candidate,
                    now=now,
                    comparison_measurements=tuple(self._history) + all_original,
                    profile_name=profile_name,
                    source_settings=_source_settings(source),
                )
                validated = self._engine.validate(
                    measurement,
                    context,
                    self._local_rules(
                        measurement,
                        profile,
                        source,
                    ),
                    diagnostics=_snapshot_diagnostics(snapshot),
                    record_state=False,
                )
                if validated.measurement is not None:
                    provisional.append(validated.measurement)

        comparison_measurements = tuple(self._history) + tuple(provisional)
        validated_snapshots: list[ValidatedDeviceSnapshot] = []
        final_accepted: list[Measurement] = []
        events: list[ValidationEvent] = []

        for snapshot in snapshots:
            validated_measurements: list[ValidatedMeasurement] = []
            accepted_for_snapshot: list[Measurement] = []

            for measurement in snapshot.measurements:
                profile_name, profile, source = self._profile_for(
                    validation_config,
                    measurement.source_id,
                )
                if source.get("enabled", True) is not True:
                    accepted_for_snapshot.append(measurement)
                    final_accepted.append(measurement)
                    continue

                candidate = _candidate_from_measurement(measurement)
                context = self._engine.state_store.context_for(
                    candidate,
                    now=now,
                    comparison_measurements=comparison_measurements,
                    profile_name=profile_name,
                    source_settings=_source_settings(source),
                )
                rules = self._local_rules(
                    measurement,
                    profile,
                    source,
                ) + self._cross_source_rules(
                    measurement,
                    profile,
                    source,
                )
                validated = self._engine.validate(
                    measurement,
                    context,
                    rules,
                    diagnostics=_snapshot_diagnostics(snapshot),
                    record_state=False,
                )
                validated_measurements.append(validated)
                if validated.measurement is not None:
                    accepted_for_snapshot.append(validated.measurement)
                    final_accepted.append(validated.measurement)
                event = ValidationEvent.from_validated(
                    validated,
                    occurred_at=now,
                )
                if event is not None:
                    events.append(event)

            output_snapshot = DeviceSnapshot(
                source_id=snapshot.source_id,
                status=_validated_status(
                    snapshot.status,
                    validated_measurements,
                ),
                measurements=tuple(accepted_for_snapshot),
                received_at=snapshot.received_at,
                error=snapshot.error,
                metadata=snapshot.metadata,
            )
            validated_snapshots.append(
                ValidatedDeviceSnapshot(
                    original=snapshot,
                    snapshot=output_snapshot,
                    measurements=tuple(validated_measurements),
                    events=tuple(
                        event
                        for event in events
                        if event.source_id == snapshot.source_id
                    ),
                )
            )

        for measurement in final_accepted:
            self._engine.state_store.record_accepted(measurement)
            self._history.append(measurement)

        return ValidatedCycle(
            snapshots=tuple(validated.snapshot for validated in validated_snapshots),
            validated_snapshots=tuple(validated_snapshots),
            events=tuple(events),
        )

    def clear(self) -> None:
        """Clear historical references and short comparison windows."""

        self._engine.clear()
        self._history.clear()

    def _profile_for(
        self,
        validation_config: Mapping[str, Any],
        source_id: str,
    ) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
        """Resolve an explicit profile or a safe source-specific built-in."""

        raw_sources = validation_config.get("sources", {})
        sources = raw_sources if isinstance(raw_sources, Mapping) else {}
        raw_source = sources.get(source_id, {})
        source = dict(raw_source) if isinstance(raw_source, Mapping) else {}
        profile_name = str(source.get("profile") or "").strip()

        raw_profiles = validation_config.get("profiles", {})
        profiles = raw_profiles if isinstance(raw_profiles, Mapping) else {}
        if profile_name:
            raw_profile = profiles.get(profile_name, {})
            return (
                profile_name,
                normalize_validation_profile(raw_profile),
                source,
            )

        built_in = _built_in_profile(source_id)
        if built_in is None:
            return None, normalize_validation_profile({}), source
        return (
            str(built_in["name"]),
            normalize_validation_profile(built_in["config"]),
            source,
        )

    def _local_rules(
        self,
        measurement: Measurement,
        profile: Mapping[str, Any],
        source: Mapping[str, Any],
    ) -> tuple[ValidationRule, ...]:
        """Build deterministic local rules for one source and metric."""

        time_config = profile.get("time")
        rules: list[ValidationRule] = [
            FiniteNumberRule(),
            ExpectedUnitRule(),
            TimestampRule.from_config(time_config),
            MeasurementAgeRule.from_config(time_config),
        ]
        metric_name = measurement.metric.value

        ranges = profile.get("ranges", {})
        if isinstance(ranges, Mapping) and metric_name in ranges:
            rules.append(RangeRule.from_config(ranges[metric_name]))

        error_values = profile.get("known_error_values", {})
        if isinstance(error_values, Mapping):
            raw_values = error_values.get(metric_name)
            if isinstance(raw_values, (list, tuple)) and raw_values:
                rules.append(
                    KnownDeviceErrorValueRule(
                        tuple(float(value) for value in raw_values)
                    )
                )

        warning_markers = _string_tuple(source.get("diagnostic_warning_markers"))
        error_markers = _string_tuple(source.get("diagnostic_error_markers"))
        if warning_markers or error_markers:
            rules.append(
                DeviceDiagnosticRule(
                    warning_markers=warning_markers,
                    error_markers=error_markers,
                )
            )

        deltas = profile.get("deltas", {})
        delta_config: Mapping[str, Any] | None = None
        if isinstance(deltas, Mapping):
            raw_delta = deltas.get(metric_name)
            if isinstance(raw_delta, Mapping):
                delta_config = raw_delta
                if any(
                    raw_delta.get(key) is not None
                    for key in (
                        "warning_absolute",
                        "reject_absolute",
                        "warning_relative_percent",
                        "reject_relative_percent",
                        "warning_per_second",
                        "reject_per_second",
                    )
                ):
                    rules.append(MaximumDeltaRule.from_config(raw_delta))

        if measurement.metric in _COUNTER_METRICS:
            tolerance = source.get("counter_warning_tolerance", 0.0)
            rules.append(MonotonicCounterRule(warning_tolerance=float(tolerance)))
            if (
                delta_config is not None
                and delta_config.get("maximum_power_w") is not None
            ):
                rules.append(
                    EnergyDeltaRule(
                        maximum_power_w=float(delta_config["maximum_power_w"]),
                        warning_factor=float(delta_config.get("warning_factor", 1.0)),
                        reject_factor=float(delta_config.get("reject_factor", 1.2)),
                    )
                )

        phase_config = profile.get("phase_consistency")
        if isinstance(phase_config, Mapping) and measurement.metric in {
            Metric.GRID_POWER,
            Metric.HOUSE_POWER,
        }:
            rules.extend(
                (
                    PhaseCompletenessRule(
                        maximum_phase_skew_seconds=float(
                            phase_config.get(
                                "maximum_phase_skew_seconds",
                                2.0,
                            )
                        )
                    ),
                    PhaseSumConsistencyRule(
                        warning_absolute_w=float(
                            phase_config.get(
                                "warning_absolute_w",
                                20.0,
                            )
                        ),
                        warning_relative=float(
                            phase_config.get(
                                "warning_relative",
                                0.03,
                            )
                        ),
                        reject_absolute_w=float(
                            phase_config.get(
                                "reject_absolute_w",
                                100.0,
                            )
                        ),
                        reject_relative=float(
                            phase_config.get(
                                "reject_relative",
                                0.10,
                            )
                        ),
                        maximum_phase_skew_seconds=float(
                            phase_config.get(
                                "maximum_phase_skew_seconds",
                                2.0,
                            )
                        ),
                    ),
                )
            )

        return tuple(rules)

    def _cross_source_rules(
        self,
        measurement: Measurement,
        profile: Mapping[str, Any],
        source: Mapping[str, Any],
    ) -> tuple[ValidationRule, ...]:
        """Build only comparisons matching the candidate's source contract."""

        profile_comparisons = profile.get("comparisons", {})
        source_comparisons = source.get("comparisons", {})
        comparison_map = {
            **(
                dict(profile_comparisons)
                if isinstance(profile_comparisons, Mapping)
                else {}
            ),
            **(
                dict(source_comparisons)
                if isinstance(source_comparisons, Mapping)
                else {}
            ),
        }

        if (
            measurement.source_id == "solakon_one"
            and measurement.role is MeasurementRole.SOLAR_SYSTEM
            and measurement.metric is Metric.PLANT_AC_POWER
        ):
            limits = CrossSourceComparisonLimits.from_config(
                comparison_map.get("plant_meter")
            )
            peer = (
                str(
                    source.get(
                        "plant_comparison_source_id",
                        "solakon_meter",
                    )
                ).strip()
                or "solakon_meter"
            )
            return (
                CrossSourceTimeAlignmentRule(
                    comparison_source_id=peer,
                    comparison_roles=(MeasurementRole.PLANT_METER,),
                    comparison_metrics=(Metric.PLANT_AC_POWER,),
                    maximum_skew_seconds=limits.window_seconds,
                ),
                PlantPowerCrossCheckRule(
                    comparison_source_id=peer,
                    limits=limits,
                ),
            )

        if (
            measurement.role is MeasurementRole.GRID_METER
            and measurement.metric is Metric.GRID_POWER
            and (
                measurement.source_id == "grid_meter_primary"
                or source.get("authoritative_grid_meter") is True
            )
        ):
            limits = CrossSourceComparisonLimits.from_config(
                comparison_map.get("grid_meter")
            )
            peer = (
                str(
                    source.get(
                        "grid_comparison_source_id",
                        "house_meter",
                    )
                ).strip()
                or "house_meter"
            )
            return (
                CrossSourceTimeAlignmentRule(
                    comparison_source_id=peer,
                    comparison_roles=(
                        MeasurementRole.GRID_METER,
                        MeasurementRole.HOUSE_METER,
                    ),
                    comparison_metrics=(
                        Metric.GRID_POWER,
                        Metric.HOUSE_POWER,
                    ),
                    maximum_skew_seconds=limits.window_seconds,
                ),
                GridMeterCrossCheckRule(
                    comparison_source_id=peer,
                    limits=limits,
                ),
            )

        return ()

    def _prune_history(self, now: datetime) -> None:
        """Drop old values while preserving the bounded deque contract."""

        cutoff = now.timestamp() - self._history_seconds
        retained = [
            measurement
            for measurement in self._history
            if measurement.measured_at.timestamp() >= cutoff
        ]
        self._history.clear()
        self._history.extend(retained)


def _candidate_from_measurement(
    measurement: Measurement,
) -> MeasurementCandidate:
    """Build the state lookup candidate for one strict measurement."""

    return MeasurementCandidate(
        metric=measurement.metric,
        value=measurement.value,
        unit=measurement.unit,
        source_id=measurement.source_id,
        role=measurement.role,
        measured_at=measurement.measured_at,
        received_at=measurement.received_at,
        quality=measurement.quality,
        raw_value=measurement.raw_value,
    )


def _snapshot_diagnostics(
    snapshot: DeviceSnapshot,
) -> tuple[str, ...]:
    """Expose the adapter error text without inventing a validation error."""

    return (snapshot.error,) if snapshot.error else ()


def _source_settings(
    source: Mapping[str, Any],
) -> tuple[tuple[str, object], ...]:
    """Pass only settings currently required by cross-source rules."""

    return (
        (
            "measurement_position_comparable",
            source.get("measurement_position_comparable", False),
        ),
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    """Normalize optional marker lists without accepting scalar strings."""

    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item).strip()))


def _built_in_profile(
    source_id: str,
) -> dict[str, object] | None:
    """Return safe defaults only where the connected installation is known."""

    if source_id == "solakon_one":
        profile = solarkon_800w_profile()
    elif source_id == "solakon_meter":
        profile = shelly_plant_profile()
    else:
        return None
    return {
        "name": profile.name,
        "config": profile.as_config(),
    }


def _validated_status(
    status: DeviceConnectionStatus,
    measurements: list[ValidatedMeasurement],
) -> DeviceConnectionStatus:
    """Keep connection state separate while marking partial data degraded."""

    if status is not DeviceConnectionStatus.ONLINE:
        return status
    if any(
        validated.result.decision is not ValidationDecision.ACCEPT
        for validated in measurements
    ):
        return DeviceConnectionStatus.DEGRADED
    return status
