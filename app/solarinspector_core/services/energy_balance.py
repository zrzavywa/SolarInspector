"""Calculate a current whole-site power balance from selected measurements."""

from __future__ import annotations

from solarinspector_core.models.energy_balance import (
    EnergyBalanceInput,
    EnergyBalanceQuality,
    EnergyBalanceResult,
)
from solarinspector_core.models.quality import MeasurementQuality
from solarinspector_core.models.source_selection import (
    SourceAlignmentStatus,
    SourceSelectionFinding,
    SourceSelectionResult,
)
from solarinspector_core.services.source_selector import assess_source_alignment


class EnergyBalanceService:
    """Calculate grid directions and household power without estimation."""

    def __init__(
        self,
        *,
        maximum_source_skew_seconds: float = 10.0,
        negative_house_power_tolerance_w: float = 30.0,
    ) -> None:
        """Create a service with explicit time and physical tolerances."""

        if maximum_source_skew_seconds <= 0:
            raise ValueError("maximum_source_skew_seconds must be greater than zero")
        if negative_house_power_tolerance_w < 0:
            raise ValueError("negative_house_power_tolerance_w must not be negative")
        self._maximum_source_skew_seconds = float(maximum_source_skew_seconds)
        self._negative_house_power_tolerance_w = float(negative_house_power_tolerance_w)

    def calculate(self, inputs: EnergyBalanceInput) -> EnergyBalanceResult:
        """Calculate the current AC balance from selected Grid and plant values."""

        grid_power_w = _selected_value(inputs.grid_power)
        plant_ac_power_w = _selected_value(inputs.plant_ac_power)
        pv_power_w = _selected_value(inputs.pv_power)
        grid_import_power_w = (
            max(grid_power_w, 0.0) if grid_power_w is not None else None
        )
        grid_export_power_w = (
            max(-grid_power_w, 0.0) if grid_power_w is not None else None
        )
        alignment = assess_source_alignment(
            (inputs.grid_power, inputs.plant_ac_power),
            maximum_source_skew_seconds=self._maximum_source_skew_seconds,
        )
        findings = list(alignment.findings)
        for selection in (inputs.grid_power, inputs.plant_ac_power):
            for finding in selection.findings:
                if finding not in findings:
                    findings.append(finding)
        (
            battery_charge_power_w,
            battery_discharge_power_w,
            battery_soc_percent,
            battery_suspect,
            battery_findings,
        ) = _battery_values(inputs)
        findings.extend(battery_findings)
        optional_selections = (
            inputs.pv_power,
            inputs.battery_charge_power,
            inputs.battery_discharge_power,
            inputs.battery_soc,
        )
        optional_suspect = battery_suspect or any(
            selection.selected_quality is MeasurementQuality.SUSPECT
            for selection in optional_selections
            if selection.measurement is not None
        )
        findings.extend(
            finding
            for selection in optional_selections
            for finding in selection.findings
            if finding not in findings
        )

        if grid_power_w is None and plant_ac_power_w is None:
            return self._result(
                inputs,
                grid_power_w=None,
                grid_import_power_w=None,
                grid_export_power_w=None,
                plant_ac_power_w=None,
                pv_power_w=pv_power_w,
                house_power_w=None,
                residual_power_w=None,
                quality=EnergyBalanceQuality.UNAVAILABLE,
                battery_charge_power_w=battery_charge_power_w,
                battery_discharge_power_w=battery_discharge_power_w,
                battery_soc_percent=battery_soc_percent,
                findings=tuple(findings),
            )

        if alignment.status is SourceAlignmentStatus.INCOMPLETE:
            return self._result(
                inputs,
                grid_power_w=grid_power_w,
                grid_import_power_w=grid_import_power_w,
                grid_export_power_w=grid_export_power_w,
                plant_ac_power_w=plant_ac_power_w,
                pv_power_w=pv_power_w,
                house_power_w=None,
                residual_power_w=None,
                quality=EnergyBalanceQuality.INCOMPLETE,
                battery_charge_power_w=battery_charge_power_w,
                battery_discharge_power_w=battery_discharge_power_w,
                battery_soc_percent=battery_soc_percent,
                findings=tuple(findings),
            )

        if grid_power_w is None or plant_ac_power_w is None:
            raise AssertionError("aligned balance requires both AC inputs")
        raw_house_power_w = plant_ac_power_w + grid_power_w
        house_power_w = raw_house_power_w
        quality = (
            EnergyBalanceQuality.SUSPECT
            if alignment.status is SourceAlignmentStatus.SUSPECT or optional_suspect
            else EnergyBalanceQuality.CALCULATED
        )

        if raw_house_power_w < -self._negative_house_power_tolerance_w:
            findings.append(
                _balance_finding(
                    code="negative_house_power_rejected",
                    message=(
                        "Calculated household power is below the permitted "
                        "negative tolerance; the balance is unavailable."
                    ),
                    severity="error",
                    details=(
                        ("calculated_house_power_w", raw_house_power_w),
                        (
                            "negative_tolerance_w",
                            self._negative_house_power_tolerance_w,
                        ),
                    ),
                )
            )
            return self._result(
                inputs,
                grid_power_w=grid_power_w,
                grid_import_power_w=grid_import_power_w,
                grid_export_power_w=grid_export_power_w,
                plant_ac_power_w=plant_ac_power_w,
                pv_power_w=pv_power_w,
                house_power_w=None,
                residual_power_w=None,
                quality=EnergyBalanceQuality.UNAVAILABLE,
                battery_charge_power_w=battery_charge_power_w,
                battery_discharge_power_w=battery_discharge_power_w,
                battery_soc_percent=battery_soc_percent,
                findings=tuple(findings),
            )

        if raw_house_power_w < 0:
            house_power_w = 0.0
            quality = EnergyBalanceQuality.SUSPECT
            findings.append(
                _balance_finding(
                    code="negative_house_power_normalized",
                    message=(
                        "A small negative household power was normalized "
                        "to zero within the configured tolerance."
                    ),
                    severity="warning",
                    details=(
                        ("calculated_house_power_w", raw_house_power_w),
                        (
                            "negative_tolerance_w",
                            self._negative_house_power_tolerance_w,
                        ),
                    ),
                )
            )

        residual_power_w = house_power_w - (plant_ac_power_w + grid_power_w)
        self_consumed_power_w = max(
            plant_ac_power_w - (grid_export_power_w or 0.0),
            0.0,
        )
        self_consumption_rate_percent = (
            _percentage(self_consumed_power_w, plant_ac_power_w)
            if plant_ac_power_w > 0
            else None
        )
        autonomy_rate_percent = (
            _percentage(self_consumed_power_w, house_power_w)
            if house_power_w > 0
            else None
        )
        return self._result(
            inputs,
            grid_power_w=grid_power_w,
            grid_import_power_w=grid_import_power_w,
            grid_export_power_w=grid_export_power_w,
            plant_ac_power_w=plant_ac_power_w,
            pv_power_w=pv_power_w,
            house_power_w=house_power_w,
            residual_power_w=residual_power_w,
            quality=quality,
            battery_charge_power_w=battery_charge_power_w,
            battery_discharge_power_w=battery_discharge_power_w,
            battery_soc_percent=battery_soc_percent,
            self_consumed_power_w=self_consumed_power_w,
            self_consumption_rate_percent=self_consumption_rate_percent,
            autonomy_rate_percent=autonomy_rate_percent,
            findings=tuple(findings),
        )

    @staticmethod
    def _result(
        inputs: EnergyBalanceInput,
        *,
        grid_power_w: float | None,
        grid_import_power_w: float | None,
        grid_export_power_w: float | None,
        plant_ac_power_w: float | None,
        pv_power_w: float | None,
        house_power_w: float | None,
        residual_power_w: float | None,
        quality: EnergyBalanceQuality,
        battery_charge_power_w: float | None,
        battery_discharge_power_w: float | None,
        battery_soc_percent: float | None,
        findings: tuple[SourceSelectionFinding, ...],
        self_consumed_power_w: float | None = None,
        self_consumption_rate_percent: float | None = None,
        autonomy_rate_percent: float | None = None,
    ) -> EnergyBalanceResult:
        """Build one base result; later blocks add battery and KPI outputs."""

        return EnergyBalanceResult(
            house_power_w=house_power_w,
            grid_power_w=grid_power_w,
            grid_import_power_w=grid_import_power_w,
            grid_export_power_w=grid_export_power_w,
            plant_ac_power_w=plant_ac_power_w,
            pv_power_w=pv_power_w,
            battery_charge_power_w=battery_charge_power_w,
            battery_discharge_power_w=battery_discharge_power_w,
            battery_soc_percent=battery_soc_percent,
            self_consumed_power_w=self_consumed_power_w,
            self_consumption_rate_percent=self_consumption_rate_percent,
            autonomy_rate_percent=autonomy_rate_percent,
            residual_power_w=residual_power_w,
            quality=quality,
            calculated_at=inputs.calculation_timestamp,
            source_metadata=inputs.source_metadata,
            findings=findings,
        )


def _selected_value(selection: SourceSelectionResult) -> float | None:
    """Return a selected numeric value or explicit absence."""

    return selection.measurement.value if selection.measurement is not None else None


def _balance_finding(
    *,
    code: str,
    message: str,
    severity: str,
    details: tuple[tuple[str, object], ...],
) -> SourceSelectionFinding:
    """Build one structured energy-balance finding."""

    return SourceSelectionFinding(
        rule_id="ENERGY-BALANCE-001",
        code=code,
        message=message,
        severity=severity,
        details=details,
    )


def _battery_values(
    inputs: EnergyBalanceInput,
) -> tuple[
    float | None,
    float | None,
    float | None,
    bool,
    tuple[SourceSelectionFinding, ...],
]:
    """Normalize selected battery channels without estimating losses."""

    charge = _selected_value(inputs.battery_charge_power)
    discharge = _selected_value(inputs.battery_discharge_power)
    soc = _selected_value(inputs.battery_soc)
    findings: list[SourceSelectionFinding] = []
    suspect = False

    if charge is not None and charge < 0:
        findings.append(
            _battery_finding(
                code="negative_battery_charge_power",
                message="Negative battery charge power is not usable.",
                severity="error",
                details=(("battery_charge_power_w", charge),),
            )
        )
        charge = None
        suspect = True
    if discharge is not None and discharge < 0:
        findings.append(
            _battery_finding(
                code="negative_battery_discharge_power",
                message="Negative battery discharge power is not usable.",
                severity="error",
                details=(("battery_discharge_power_w", discharge),),
            )
        )
        discharge = None
        suspect = True
    if soc is not None and not 0 <= soc <= 100:
        findings.append(
            _battery_finding(
                code="battery_soc_out_of_range",
                message="Battery state of charge is outside 0 to 100 percent.",
                severity="error",
                details=(("battery_soc_percent", soc),),
            )
        )
        soc = None
        suspect = True
    if charge is not None and discharge is not None and charge > 0 and discharge > 0:
        findings.append(
            _battery_finding(
                code="simultaneous_battery_charge_and_discharge",
                message="Battery charge and discharge power are both positive.",
                severity="warning",
                details=(
                    ("battery_charge_power_w", charge),
                    ("battery_discharge_power_w", discharge),
                ),
            )
        )
        suspect = True
    return charge, discharge, soc, suspect, tuple(findings)


def _battery_finding(
    *,
    code: str,
    message: str,
    severity: str,
    details: tuple[tuple[str, object], ...],
) -> SourceSelectionFinding:
    """Build one structured battery-flow finding."""

    return SourceSelectionFinding(
        rule_id="ENERGY-BATTERY-001",
        code=code,
        message=message,
        severity=severity,
        details=details,
    )


def _percentage(numerator: float, denominator: float) -> float:
    """Calculate a bounded percentage after validating its denominator."""

    return min(max(numerator / denominator * 100.0, 0.0), 100.0)
