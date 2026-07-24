"""Analyze active-power distribution across three electrical phases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

ABSOLUTE_TOTAL_TOLERANCE_W: Final[float] = 20.0
RELATIVE_TOTAL_TOLERANCE: Final[float] = 0.05

PhasePowerValues = tuple[float | None, ...]
PhaseShareValues = tuple[
    float | None,
    float | None,
    float | None,
]


@dataclass(frozen=True, slots=True)
class PhasePowerAnalysis:
    """Describe completeness, totals, balance, and distribution of phases."""

    available_count: int
    complete: bool
    calculated_total_w: float | None
    reported_total_w: float | None
    total_delta_w: float | None
    total_delta_pct: float | None
    total_consistent: bool | None
    spread_w: float | None
    shares_pct: PhaseShareValues


def analyze_phase_power(
    phase_power_w: PhasePowerValues,
    *,
    reported_total_w: float | None,
) -> PhasePowerAnalysis:
    """Analyze exactly three signed phase-power values.

    Distribution and spread use absolute phase magnitudes so import and export
    values cannot cancel each other. A device total is compared only when it
    was explicitly reported by the device rather than calculated locally.
    """

    if len(phase_power_w) != 3:
        raise ValueError("exactly three phase-power values are required")

    available_count = sum(value is not None for value in phase_power_w)
    complete = available_count == 3
    if not complete:
        return PhasePowerAnalysis(
            available_count=available_count,
            complete=False,
            calculated_total_w=None,
            reported_total_w=reported_total_w,
            total_delta_w=None,
            total_delta_pct=None,
            total_consistent=None,
            spread_w=None,
            shares_pct=(None, None, None),
        )

    complete_values = tuple(
        float(value) for value in phase_power_w if value is not None
    )
    calculated_total_w = sum(complete_values)
    magnitudes = tuple(abs(value) for value in complete_values)
    magnitude_total = sum(magnitudes)
    if magnitude_total > 0.0:
        shares_pct: PhaseShareValues = (
            magnitudes[0] / magnitude_total * 100.0,
            magnitudes[1] / magnitude_total * 100.0,
            magnitudes[2] / magnitude_total * 100.0,
        )
    else:
        shares_pct = (0.0, 0.0, 0.0)
    spread_w = max(magnitudes) - min(magnitudes)

    if reported_total_w is None:
        return PhasePowerAnalysis(
            available_count=3,
            complete=True,
            calculated_total_w=calculated_total_w,
            reported_total_w=None,
            total_delta_w=None,
            total_delta_pct=None,
            total_consistent=None,
            spread_w=spread_w,
            shares_pct=shares_pct,
        )

    total_delta_w = reported_total_w - calculated_total_w
    reference_w = max(
        abs(reported_total_w),
        abs(calculated_total_w),
        1.0,
    )
    tolerance_w = max(
        ABSOLUTE_TOTAL_TOLERANCE_W,
        reference_w * RELATIVE_TOTAL_TOLERANCE,
    )
    total_delta_pct = total_delta_w / reference_w * 100.0

    return PhasePowerAnalysis(
        available_count=3,
        complete=True,
        calculated_total_w=calculated_total_w,
        reported_total_w=reported_total_w,
        total_delta_w=total_delta_w,
        total_delta_pct=total_delta_pct,
        total_consistent=abs(total_delta_w) <= tolerance_w,
        spread_w=spread_w,
        shares_pct=shares_pct,
    )
