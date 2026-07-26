"""Replay real-world validation scenarios without network or waiting."""

from __future__ import annotations

from pathlib import Path

import pytest
from zrzavy_energy_monitor_core.validation.replay import (
    load_replay_scenario,
    run_replay_scenario,
)

FIXTURE_DIRECTORY = Path("tests/fixtures/replay")
SCENARIOS = (
    "normal_day.jsonl",
    "grid_meter_spike.jsonl",
    "solarkon_invalid_power.jsonl",
    "shelly_phase_dropout.jsonl",
    "counter_reset.jsonl",
    "network_recovery.jsonl",
)


@pytest.mark.parametrize("filename", SCENARIOS)
def test_replay_scenario_matches_expected_results(
    filename: str,
) -> None:
    scenario = load_replay_scenario(FIXTURE_DIRECTORY / filename)
    report = run_replay_scenario(scenario)

    assert len(report.results) == len(scenario.steps)
    for step, result in zip(scenario.steps, report.results):
        assert result.accepted_values == step.expectation.accepted_values
        assert result.rejected_metrics == step.expectation.rejected_metrics
        assert result.event_codes == step.expectation.event_codes
        assert result.statuses == step.expectation.statuses


def test_replay_catalog_has_all_required_phase_08_scenarios() -> None:
    scenario_names = {
        load_replay_scenario(FIXTURE_DIRECTORY / filename).name
        for filename in SCENARIOS
    }

    assert scenario_names == {
        "normal_day",
        "grid_meter_spike",
        "solarkon_invalid_power",
        "shelly_phase_dropout",
        "counter_reset",
        "network_recovery",
    }


def test_replay_is_deterministic_across_independent_runs() -> None:
    scenario = load_replay_scenario(FIXTURE_DIRECTORY / "normal_day.jsonl")

    first = run_replay_scenario(scenario)
    second = run_replay_scenario(scenario)

    assert first == second
    assert first.event_count == 0


def test_counter_reset_replay_records_one_actionable_rejection() -> None:
    scenario = load_replay_scenario(FIXTURE_DIRECTORY / "counter_reset.jsonl")

    report = run_replay_scenario(scenario)

    assert report.event_count == 1
    assert report.results[-1].rejected_metrics == (
        "grid_meter_primary:grid_import_total",
    )
