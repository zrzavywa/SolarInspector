"""Expose the central validation foundation for SolarInspector 4.5."""

from solarinspector_core.validation.base import ValidationRule
from solarinspector_core.validation.config import (
    DEFAULT_TIME_CONFIG,
    DEFAULT_VALIDATION_CONFIG,
    ValidationConfigurationError,
    normalize_delta_config,
    normalize_range_config,
    normalize_time_config,
    normalize_validation_config,
    normalize_validation_profile,
    normalize_validation_source,
)
from solarinspector_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
    ValidationStateKey,
)
from solarinspector_core.validation.result import (
    RuleEvaluation,
    ValidationDecision,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
    quality_for_decision,
)
from solarinspector_core.validation.rules import (
    EnergyDeltaRule,
    ExpectedUnitRule,
    FiniteNumberRule,
    MaximumDeltaRule,
    MeasurementAgeRule,
    MonotonicCounterRule,
    RangeRule,
    TimestampRule,
)
from solarinspector_core.validation.state import ValidationStateStore

__all__ = [
    "DEFAULT_TIME_CONFIG",
    "DEFAULT_VALIDATION_CONFIG",
    "EnergyDeltaRule",
    "ExpectedUnitRule",
    "FiniteNumberRule",
    "MaximumDeltaRule",
    "MeasurementAgeRule",
    "MonotonicCounterRule",
    "MeasurementCandidate",
    "RangeRule",
    "RuleEvaluation",
    "ValidationConfigurationError",
    "ValidationContext",
    "ValidationDecision",
    "ValidationFinding",
    "ValidationResult",
    "ValidationRule",
    "ValidationSeverity",
    "TimestampRule",
    "ValidationStateKey",
    "ValidationStateStore",
    "normalize_delta_config",
    "normalize_range_config",
    "normalize_time_config",
    "normalize_validation_config",
    "normalize_validation_profile",
    "normalize_validation_source",
    "quality_for_decision",
]
