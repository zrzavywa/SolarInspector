"""Validate measurement timestamps and configurable data age."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Real
from typing import ClassVar

from zrzavy_energy_monitor_core.validation.config import normalize_time_config
from zrzavy_energy_monitor_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from zrzavy_energy_monitor_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)


def _is_timezone_aware(value: datetime) -> bool:
    """Return whether a timestamp carries a usable UTC offset."""

    return value.tzinfo is not None and value.utcoffset() is not None


def _details(
    candidate: MeasurementCandidate,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable timestamp diagnostic details."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        *items,
    )


def _non_negative_finite(
    value: object,
    field_name: str,
) -> float:
    """Normalize one non-negative finite constructor parameter."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


@dataclass(frozen=True, slots=True)
class TimestampRule:
    """Require usable timestamps with bounded future clock skew."""

    maximum_future_seconds: float = 5.0

    rule_id: ClassVar[str] = "VAL-TIME-001"

    def __post_init__(self) -> None:
        """Normalize and validate the future tolerance."""

        object.__setattr__(
            self,
            "maximum_future_seconds",
            _non_negative_finite(
                self.maximum_future_seconds,
                "maximum_future_seconds",
            ),
        )

    @classmethod
    def from_config(cls, value: object) -> TimestampRule:
        """Build one timestamp rule from a time configuration."""

        normalized = normalize_time_config(value)
        return cls(maximum_future_seconds=normalized["maximum_future_seconds"])

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Reject missing, naive, contradictory, or far-future timestamps."""

        measured_at = candidate.measured_at
        if measured_at is None:
            return self._reject(
                candidate,
                code="measured_at_missing",
                message="Measurement timestamp is missing.",
            )
        if not _is_timezone_aware(measured_at):
            return self._reject(
                candidate,
                code="measured_at_naive",
                message="Measurement timestamp must be timezone-aware.",
                measured_at=measured_at.isoformat(),
            )

        tolerance = timedelta(seconds=self.maximum_future_seconds)

        if candidate.received_at > context.now + tolerance:
            return self._reject(
                candidate,
                code="received_at_in_future",
                message="Receive timestamp is too far in the future.",
                received_at=candidate.received_at.isoformat(),
                now=context.now.isoformat(),
                maximum_future_seconds=self.maximum_future_seconds,
            )

        if measured_at > context.now + tolerance:
            return self._reject(
                candidate,
                code="measured_at_in_future",
                message="Measurement timestamp is too far in the future.",
                measured_at=measured_at.isoformat(),
                now=context.now.isoformat(),
                maximum_future_seconds=self.maximum_future_seconds,
            )

        if measured_at > candidate.received_at + tolerance:
            return self._reject(
                candidate,
                code="measured_after_received",
                message="Measurement timestamp is after the receive timestamp.",
                measured_at=measured_at.isoformat(),
                received_at=candidate.received_at.isoformat(),
                maximum_future_seconds=self.maximum_future_seconds,
            )

        return RuleEvaluation.accepted()

    def _reject(
        self,
        candidate: MeasurementCandidate,
        *,
        code: str,
        message: str,
        **details: object,
    ) -> RuleEvaluation:
        """Build one deterministic timestamp rejection."""

        return RuleEvaluation.rejected(
            ValidationFinding(
                rule_id=self.rule_id,
                code=code,
                message=message,
                severity=ValidationSeverity.ERROR,
                details=_details(candidate, *tuple(details.items())),
            )
        )


@dataclass(frozen=True, slots=True)
class MeasurementAgeRule:
    """Classify measurements as fresh, aged with warning, or stale."""

    fresh_seconds: float = 15.0
    stale_seconds: float = 60.0

    rule_id: ClassVar[str] = "VAL-TIME-002"

    def __post_init__(self) -> None:
        """Normalize age thresholds and require monotonic ordering."""

        fresh = _non_negative_finite(
            self.fresh_seconds,
            "fresh_seconds",
        )
        stale = _non_negative_finite(
            self.stale_seconds,
            "stale_seconds",
        )
        if fresh > stale:
            raise ValueError("fresh_seconds must not exceed stale_seconds")
        object.__setattr__(self, "fresh_seconds", fresh)
        object.__setattr__(self, "stale_seconds", stale)

    @classmethod
    def from_config(cls, value: object) -> MeasurementAgeRule:
        """Build one age rule from a time configuration."""

        normalized = normalize_time_config(value)
        return cls(
            fresh_seconds=normalized["fresh_seconds"],
            stale_seconds=normalized["stale_seconds"],
        )

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Warn after the fresh limit and reject after the stale limit."""

        measured_at = candidate.measured_at
        if measured_at is None or not _is_timezone_aware(measured_at):
            # VAL-TIME-001 owns missing and malformed timestamps.
            return RuleEvaluation.accepted()

        age_seconds = (context.now - measured_at).total_seconds()
        if age_seconds < 0:
            # VAL-TIME-001 owns future timestamps.
            return RuleEvaluation.accepted()

        if age_seconds > self.stale_seconds:
            return RuleEvaluation.rejected(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="measurement_stale",
                    message="Measurement is older than the configured stale limit.",
                    severity=ValidationSeverity.ERROR,
                    details=_details(
                        candidate,
                        ("age_seconds", age_seconds),
                        ("stale_seconds", self.stale_seconds),
                    ),
                )
            )

        if age_seconds > self.fresh_seconds:
            return RuleEvaluation.warning(
                ValidationFinding(
                    rule_id=self.rule_id,
                    code="measurement_aged",
                    message="Measurement is older than the configured fresh limit.",
                    severity=ValidationSeverity.WARNING,
                    details=_details(
                        candidate,
                        ("age_seconds", age_seconds),
                        ("fresh_seconds", self.fresh_seconds),
                        ("stale_seconds", self.stale_seconds),
                    ),
                )
            )

        return RuleEvaluation.accepted()
