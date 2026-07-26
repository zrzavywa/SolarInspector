"""Test validation configuration defaults, normalization, and migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from zrzavy_energy_monitor_core.config.manager import ConfigManager
from zrzavy_energy_monitor_core.validation import (
    DEFAULT_COMPARISON_CONFIG,
    DEFAULT_TIME_CONFIG,
    DEFAULT_VALIDATION_CONFIG,
    ValidationConfigurationError,
    normalize_comparison_config,
    normalize_delta_config,
    normalize_range_config,
    normalize_time_config,
    normalize_validation_config,
    normalize_validation_profile,
)


def test_default_validation_configuration_is_disabled_and_empty() -> None:
    normalized = normalize_validation_config(None)

    assert normalized == DEFAULT_VALIDATION_CONFIG
    assert normalized["enabled"] is False
    assert normalized["profiles"] == {}
    assert normalized["sources"] == {}


def test_explicit_boolean_strings_are_not_treated_as_truthy() -> None:
    assert normalize_validation_config({"enabled": "false"})["enabled"] is False
    assert normalize_validation_config({"enabled": "true"})["enabled"] is True


def test_profile_normalization_preserves_unknown_future_fields() -> None:
    normalized = normalize_validation_config(
        {
            "enabled": True,
            "future_top_level": {"mode": "observe"},
            "profiles": {
                "solarkon_800w": {
                    "future_profile_field": "preserved",
                    "required_metrics": [
                        "plant_ac_power",
                        "plant_ac_power",
                        "battery_soc",
                    ],
                    "time": {
                        "fresh_seconds": "10",
                        "stale_seconds": 45,
                        "maximum_future_seconds": 3,
                        "future_time_field": "preserved",
                    },
                    "ranges": {
                        "plant_ac_power": {
                            "warning_max": 800,
                            "reject_min": -100,
                            "reject_max": 960,
                        }
                    },
                    "deltas": {
                        "plant_ac_power": {
                            "warning_absolute": 100,
                            "reject_absolute": 300,
                        }
                    },
                    "known_error_values": {
                        "battery_soc": [65535, 65535.0],
                    },
                }
            },
            "sources": {
                "solakon_one": {
                    "profile": "solarkon_800w",
                    "measurement_position_comparable": "false",
                    "future_source_field": 7,
                }
            },
        }
    )

    profile = normalized["profiles"]["solarkon_800w"]
    source = normalized["sources"]["solakon_one"]
    assert normalized["future_top_level"] == {"mode": "observe"}
    assert profile["future_profile_field"] == "preserved"
    assert profile["required_metrics"] == [
        "plant_ac_power",
        "battery_soc",
    ]
    assert profile["time"]["fresh_seconds"] == 10.0
    assert profile["time"]["future_time_field"] == "preserved"
    assert profile["ranges"]["plant_ac_power"]["reject_min"] == -100.0
    assert profile["known_error_values"]["battery_soc"] == [65535.0]
    assert source["measurement_position_comparable"] is False
    assert source["future_source_field"] == 7


def test_time_limits_require_monotonic_age_thresholds() -> None:
    assert normalize_time_config({}) == DEFAULT_TIME_CONFIG

    with pytest.raises(
        ValidationConfigurationError,
        match="fresh_seconds must not exceed stale_seconds",
    ):
        normalize_time_config(
            {
                "fresh_seconds": 61,
                "stale_seconds": 60,
            }
        )


def test_range_limits_require_warning_bounds_inside_rejection_bounds() -> None:
    with pytest.raises(
        ValidationConfigurationError,
        match="warning_max must not exceed reject_max",
    ):
        normalize_range_config(
            {
                "warning_max": 1000,
                "reject_max": 960,
            }
        )


def test_delta_limits_require_warning_not_above_rejection() -> None:
    with pytest.raises(
        ValidationConfigurationError,
        match="warning_absolute must not exceed reject_absolute",
    ):
        normalize_delta_config(
            {
                "warning_absolute": 400,
                "reject_absolute": 300,
            }
        )


def test_non_finite_or_boolean_limits_are_rejected() -> None:
    with pytest.raises(ValidationConfigurationError, match="must be finite"):
        normalize_range_config({"reject_max": "nan"})

    with pytest.raises(
        ValidationConfigurationError,
        match="must be a finite number",
    ):
        normalize_delta_config({"warning_absolute": True})


def test_unknown_metrics_are_rejected_in_active_rule_configuration() -> None:
    with pytest.raises(
        ValidationConfigurationError,
        match="unknown validation metric",
    ):
        normalize_validation_config(
            {
                "profiles": {
                    "invalid": {
                        "ranges": {
                            "not_a_metric": {
                                "reject_max": 1,
                            }
                        }
                    }
                }
            }
        )


def test_enabled_source_cannot_reference_unknown_profile() -> None:
    with pytest.raises(
        ValidationConfigurationError,
        match="refers to unknown profile",
    ):
        normalize_validation_config(
            {
                "sources": {
                    "grid_meter_primary": {
                        "profile": "missing",
                    }
                }
            }
        )


def test_disabled_source_may_keep_future_profile_assignment() -> None:
    normalized = normalize_validation_config(
        {
            "sources": {
                "grid_meter_primary": {
                    "enabled": False,
                    "profile": "not_created_yet",
                }
            }
        }
    )

    assert normalized["sources"]["grid_meter_primary"]["profile"] == "not_created_yet"


def test_legacy_configuration_receives_additive_validation_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "general": {
                    "site_name": "Legacy site",
                },
                "legacy_extension": {
                    "keep": True,
                },
            }
        ),
        encoding="utf-8",
    )

    config = ConfigManager(path, logger=lambda _message: None).get()

    assert config["validation"] == DEFAULT_VALIDATION_CONFIG
    assert config["general"]["site_name"] == "Legacy site"
    assert config["legacy_extension"] == {"keep": True}


def test_manager_save_preserves_unknown_validation_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    manager = ConfigManager(path, logger=lambda _message: None)
    config = manager.get()
    config["validation"] = {
        "enabled": True,
        "future_field": "keep",
        "profiles": {
            "official": {
                "time": {
                    "fresh_seconds": 15,
                    "stale_seconds": 60,
                }
            }
        },
        "sources": {
            "grid_meter_primary": {
                "profile": "official",
            }
        },
    }

    manager.save(config)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["validation"]["enabled"] is True
    assert saved["validation"]["future_field"] == "keep"
    assert saved["validation"]["sources"]["grid_meter_primary"]["profile"] == "official"


def test_comparison_configuration_defaults_are_observational() -> None:
    normalized = normalize_comparison_config(None)

    assert normalized == DEFAULT_COMPARISON_CONFIG
    assert normalized["allow_rejection"] is False


def test_comparison_configuration_normalizes_values() -> None:
    normalized = normalize_comparison_config(
        {
            "warning_absolute_w": "30",
            "reject_absolute_w": "100",
            "window_seconds": "60",
            "minimum_duration_seconds": "30",
            "minimum_samples": "3",
            "allow_rejection": "true",
            "future_field": "preserved",
        }
    )

    assert normalized["warning_absolute_w"] == 30.0
    assert normalized["reject_absolute_w"] == 100.0
    assert normalized["minimum_samples"] == 3
    assert normalized["allow_rejection"] is True
    assert normalized["future_field"] == "preserved"


def test_comparison_configuration_rejects_contradictions() -> None:
    with pytest.raises(
        ValidationConfigurationError,
        match="warning_absolute_w must not exceed reject_absolute_w",
    ):
        normalize_comparison_config(
            {
                "warning_absolute_w": 101,
                "reject_absolute_w": 100,
            }
        )

    with pytest.raises(
        ValidationConfigurationError,
        match="minimum_duration_seconds must not exceed window_seconds",
    ):
        normalize_comparison_config(
            {
                "window_seconds": 10,
                "minimum_duration_seconds": 11,
            }
        )

    with pytest.raises(
        ValidationConfigurationError,
        match="minimum_samples must be a positive integer",
    ):
        normalize_comparison_config({"minimum_samples": 2.5})


def test_profile_normalizes_named_comparisons() -> None:
    normalized = normalize_validation_profile(
        {
            "comparisons": {
                "plant_meter": {
                    "window_seconds": 60,
                    "minimum_duration_seconds": 30,
                    "minimum_samples": 3,
                }
            }
        }
    )

    comparison = normalized["comparisons"]["plant_meter"]
    assert comparison["window_seconds"] == 60.0
    assert comparison["minimum_duration_seconds"] == 30.0
    assert comparison["minimum_samples"] == 3
