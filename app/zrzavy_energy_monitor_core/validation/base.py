"""Define the common protocol implemented by all validation rules."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from zrzavy_energy_monitor_core.validation.result import RuleEvaluation


@runtime_checkable
class ValidationRule(Protocol):
    """Evaluate one candidate without performing I/O or changing state."""

    @property
    def rule_id(self) -> str:
        """Return the stable catalog identifier of the rule."""

        ...

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Return one immutable rule evaluation."""

        ...
