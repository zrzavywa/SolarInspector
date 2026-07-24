"""Tests for pure three-phase power analysis."""

from __future__ import annotations

import pytest
from solarinspector_core.services.phase_power import analyze_phase_power


def test_complete_phase_distribution_and_consistent_device_total() -> None:
    """A small device-total deviation stays within the defined tolerance."""

    analysis = analyze_phase_power(
        (100.0, 200.0, 300.0),
        reported_total_w=610.0,
    )

    assert analysis.available_count == 3
    assert analysis.complete is True
    assert analysis.calculated_total_w == pytest.approx(600.0)
    assert analysis.total_delta_w == pytest.approx(10.0)
    assert analysis.total_consistent is True
    assert analysis.spread_w == pytest.approx(200.0)
    assert analysis.shares_pct == pytest.approx((100.0 / 6.0, 100.0 / 3.0, 50.0))


def test_large_device_total_deviation_is_inconsistent() -> None:
    """A material mismatch is retained as a diagnostic, not hidden."""

    analysis = analyze_phase_power(
        (100.0, 200.0, 300.0),
        reported_total_w=999.0,
    )

    assert analysis.calculated_total_w == pytest.approx(600.0)
    assert analysis.total_delta_w == pytest.approx(399.0)
    assert analysis.total_consistent is False


def test_partial_phases_do_not_produce_misleading_distribution() -> None:
    """Shares and sums require all three phase-power values."""

    analysis = analyze_phase_power(
        (100.0, None, -20.0),
        reported_total_w=None,
    )

    assert analysis.available_count == 2
    assert analysis.complete is False
    assert analysis.calculated_total_w is None
    assert analysis.total_consistent is None
    assert analysis.spread_w is None
    assert analysis.shares_pct == (None, None, None)


def test_signed_values_use_absolute_magnitudes_for_load_distribution() -> None:
    """Opposite power directions cannot cancel the distribution denominator."""

    analysis = analyze_phase_power(
        (100.0, -50.0, 50.0),
        reported_total_w=None,
    )

    assert analysis.calculated_total_w == pytest.approx(100.0)
    assert analysis.shares_pct == pytest.approx((50.0, 25.0, 25.0))
    assert analysis.spread_w == pytest.approx(50.0)
