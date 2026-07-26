"""Bridge validated collector cycles to the Phase-09 energy balance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from zrzavy_energy_monitor_core.config.energy_balance import (
    normalize_energy_balance_config,
)
from zrzavy_energy_monitor_core.models.energy_balance import (
    EnergyBalanceInput,
    EnergyBalanceResult,
)
from zrzavy_energy_monitor_core.models.metrics import Metric
from zrzavy_energy_monitor_core.models.source_selection import (
    SourceSelectionFinding,
    SourceSelectionResult,
)
from zrzavy_energy_monitor_core.services.energy_balance import EnergyBalanceService
from zrzavy_energy_monitor_core.services.source_selector import (
    SourceCandidate,
    SourceSelector,
)
from zrzavy_energy_monitor_core.validation.collector import ValidatedCycle

_BALANCE_METRICS = (
    Metric.GRID_POWER,
    Metric.PLANT_AC_POWER,
    Metric.PV_POWER,
    Metric.BATTERY_CHARGE_POWER,
    Metric.BATTERY_DISCHARGE_POWER,
    Metric.BATTERY_SOC,
)


def build_cycle_energy_balance(
    cycle: ValidatedCycle,
    *,
    config: Mapping[str, Any],
    calculation_timestamp: datetime,
) -> EnergyBalanceResult:
    """Select validated cycle values and calculate one current balance."""

    balance_config = normalize_energy_balance_config(config.get("energy_balance"))
    if balance_config["enabled"] is not True:
        return unavailable_cycle_energy_balance(
            calculation_timestamp,
            code="energy_balance_disabled",
            message="Energy balance calculation is disabled.",
        )

    validation = config.get("validation")
    if not isinstance(validation, Mapping) or validation.get("enabled") is not True:
        return unavailable_cycle_energy_balance(
            calculation_timestamp,
            code="validation_disabled",
            message=(
                "Energy balance is unavailable because central validation is disabled."
            ),
        )

    selector = SourceSelector(
        balance_config["source_priorities"],
        allow_suspect_measurements=bool(balance_config["allow_suspect_measurements"]),
        allow_grid_fallback=bool(balance_config["allow_grid_fallback"]),
        allow_plant_fallback=bool(balance_config["allow_plant_fallback"]),
        maximum_measurement_age_seconds=float(
            balance_config["maximum_measurement_age_seconds"]
        ),
        short_window_average_seconds=float(
            balance_config["short_window_average_seconds"]
        ),
    )
    candidates = tuple(
        SourceCandidate.from_validated(
            validated,
            measurement_position=_measurement_position(
                validated.original.source_id,
                validated.original.metric,
                config,
            ),
        )
        for snapshot in cycle.validated_snapshots
        for validated in snapshot.measurements
        if validated.original.metric in _BALANCE_METRICS
    )
    selections = {
        metric: selector.select(
            metric,
            candidates,
            selection_timestamp=calculation_timestamp,
        )
        for metric in _BALANCE_METRICS
    }
    inputs = EnergyBalanceInput(
        grid_power=selections[Metric.GRID_POWER],
        plant_ac_power=selections[Metric.PLANT_AC_POWER],
        pv_power=selections[Metric.PV_POWER],
        battery_charge_power=selections[Metric.BATTERY_CHARGE_POWER],
        battery_discharge_power=selections[Metric.BATTERY_DISCHARGE_POWER],
        battery_soc=selections[Metric.BATTERY_SOC],
        calculation_timestamp=calculation_timestamp,
    )
    return EnergyBalanceService(
        maximum_source_skew_seconds=float(
            balance_config["maximum_source_skew_seconds"]
        ),
        negative_house_power_tolerance_w=float(
            balance_config["negative_house_power_tolerance_w"]
        ),
    ).calculate(inputs)


def unavailable_cycle_energy_balance(
    calculation_timestamp: datetime,
    *,
    code: str,
    message: str,
) -> EnergyBalanceResult:
    """Build one explicit unavailable balance for a controlled cycle failure."""

    finding = SourceSelectionFinding(
        rule_id="ENERGY-COLLECTOR-001",
        code=code,
        message=message,
        severity="warning",
    )
    selections = {
        metric: SourceSelectionResult.unavailable(
            metric,
            selection_timestamp=calculation_timestamp,
            findings=(finding,),
        )
        for metric in _BALANCE_METRICS
    }
    return EnergyBalanceService().calculate(
        EnergyBalanceInput(
            grid_power=selections[Metric.GRID_POWER],
            plant_ac_power=selections[Metric.PLANT_AC_POWER],
            pv_power=selections[Metric.PV_POWER],
            battery_charge_power=selections[Metric.BATTERY_CHARGE_POWER],
            battery_discharge_power=selections[Metric.BATTERY_DISCHARGE_POWER],
            battery_soc=selections[Metric.BATTERY_SOC],
            calculation_timestamp=calculation_timestamp,
        )
    )


def _measurement_position(
    source_id: str,
    metric: Metric,
    config: Mapping[str, Any],
) -> str | None:
    """Resolve only positions relevant to an eligible grid fallback."""

    if metric is not Metric.GRID_POWER:
        return None
    if source_id == "house_meter":
        house = config.get("house_meter")
        if isinstance(house, Mapping):
            value = house.get("measurement_role")
            return str(value) if value is not None else None
    if source_id == "solakon_one":
        return "legacy_grid_source"
    return None
