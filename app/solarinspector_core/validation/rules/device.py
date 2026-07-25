"""Validate configurable device sentinel values and adapter diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import ClassVar

from solarinspector_core.validation.context import (
    MeasurementCandidate,
    ValidationContext,
)
from solarinspector_core.validation.result import (
    RuleEvaluation,
    ValidationFinding,
    ValidationSeverity,
)


def _finite_real(value: object) -> float | None:
    """Return one finite non-boolean number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _details(
    candidate: MeasurementCandidate,
    *items: tuple[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable device diagnostic details."""

    return (
        ("source_id", candidate.source_id),
        ("role", candidate.role.value),
        ("metric", candidate.metric.value),
        *items,
    )


@dataclass(frozen=True, slots=True)
class KnownDeviceErrorValueRule:
    """Reject configured numeric sentinel values from a device or register."""

    error_values: tuple[float, ...]

    rule_id: ClassVar[str] = "VAL-FMT-002"

    def __post_init__(self) -> None:
        """Require at least one unique finite non-boolean sentinel value."""

        normalized: list[float] = []
        for value in self.error_values:
            finite = _finite_real(value)
            if finite is None:
                raise ValueError("device error values must be finite real numbers")
            if finite not in normalized:
                normalized.append(finite)
        if not normalized:
            raise ValueError("at least one device error value is required")
        object.__setattr__(self, "error_values", tuple(normalized))

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Reject a sentinel in either the raw or normalized candidate value."""

        del context
        raw = _finite_real(candidate.effective_raw_value)
        normalized = _finite_real(candidate.value)

        for field_name, value in (
            ("raw_value", raw),
            ("candidate_value", normalized),
        ):
            if value is not None and value in self.error_values:
                return RuleEvaluation.rejected(
                    ValidationFinding(
                        rule_id=self.rule_id,
                        code="known_device_error_value",
                        message=("Device returned a configured numeric error value."),
                        severity=ValidationSeverity.ERROR,
                        details=_details(
                            candidate,
                            ("matched_field", field_name),
                            ("matched_value", value),
                        ),
                    )
                )

        return RuleEvaluation.accepted()


@dataclass(frozen=True, slots=True)
class DeviceDiagnosticRule:
    """Classify adapter diagnostics using explicit marker lists."""

    warning_markers: tuple[str, ...] = ()
    error_markers: tuple[str, ...] = ()

    rule_id: ClassVar[str] = "VAL-DEVICE-001"

    def __post_init__(self) -> None:
        """Normalize markers and reject an empty rule."""

        warnings = self._normalize_markers(self.warning_markers)
        errors = self._normalize_markers(self.error_markers)
        if not warnings and not errors:
            raise ValueError("at least one warning or error marker is required")
        object.__setattr__(self, "warning_markers", warnings)
        object.__setattr__(self, "error_markers", errors)

    @staticmethod
    def _normalize_markers(values: tuple[str, ...]) -> tuple[str, ...]:
        """Return unique case-folded non-empty marker strings."""

        normalized: list[str] = []
        for value in values:
            marker = value.strip().casefold()
            if marker and marker not in normalized:
                normalized.append(marker)
        return tuple(normalized)

    def evaluate(
        self,
        candidate: MeasurementCandidate,
        context: ValidationContext,
    ) -> RuleEvaluation:
        """Reject error diagnostics and warn for configured warning markers."""

        del context
        for diagnostic in candidate.diagnostics:
            folded = diagnostic.casefold()
            error_marker = next(
                (marker for marker in self.error_markers if marker in folded),
                None,
            )
            if error_marker is not None:
                return RuleEvaluation.rejected(
                    self._finding(
                        candidate,
                        diagnostic=diagnostic,
                        marker=error_marker,
                        severity=ValidationSeverity.ERROR,
                        code="device_diagnostic_error",
                        message=(
                            "Adapter diagnostic matches a configured device error."
                        ),
                    )
                )

        for diagnostic in candidate.diagnostics:
            folded = diagnostic.casefold()
            warning_marker = next(
                (marker for marker in self.warning_markers if marker in folded),
                None,
            )
            if warning_marker is not None:
                return RuleEvaluation.warning(
                    self._finding(
                        candidate,
                        diagnostic=diagnostic,
                        marker=warning_marker,
                        severity=ValidationSeverity.WARNING,
                        code="device_diagnostic_warning",
                        message=(
                            "Adapter diagnostic matches a configured device warning."
                        ),
                    )
                )

        return RuleEvaluation.accepted()

    def _finding(
        self,
        candidate: MeasurementCandidate,
        *,
        diagnostic: str,
        marker: str,
        severity: ValidationSeverity,
        code: str,
        message: str,
    ) -> ValidationFinding:
        """Build one credential-free device diagnostic finding."""

        return ValidationFinding(
            rule_id=self.rule_id,
            code=code,
            message=message,
            severity=severity,
            details=_details(
                candidate,
                ("marker", marker),
                ("diagnostic", diagnostic),
            ),
        )
