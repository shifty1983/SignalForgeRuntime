from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationSeverity(str, Enum):
    """
    Severity levels used by pipeline validation checks.

    INFO:
        Informational result. Never blocks the pipeline.

    WARNING:
        Non-fatal issue. Should be surfaced but does not stop the pipeline.

    ERROR:
        Failed validation. Usually blocks the current pipeline stage.

    CRITICAL:
        Severe failure. Always blocks downstream execution.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ValidationResult:
    """
    Standard result object returned by every hardening validation check.

    This allows all layers to return a consistent structure regardless of
    whether the check validates schemas, missing data, stale features,
    NaN propagation, optimizer feasibility, or reporting integrity.
    """

    passed: bool
    layer: str
    check_name: str
    severity: ValidationSeverity
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocks_pipeline(self) -> bool:
        return self.failed and self.severity in {
            ValidationSeverity.ERROR,
            ValidationSeverity.CRITICAL,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "layer": self.layer,
            "check_name": self.check_name,
            "severity": self.severity.value,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GateReport:
    """
    Aggregated report for all validation checks run at a pipeline gate.
    """

    layer: str
    results: tuple[ValidationResult, ...]

    @property
    def passed(self) -> bool:
        return not any(result.blocks_pipeline for result in self.results)

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_failures(self) -> tuple[ValidationResult, ...]:
        return tuple(result for result in self.results if result.blocks_pipeline)

    @property
    def warnings(self) -> tuple[ValidationResult, ...]:
        return tuple(
            result
            for result in self.results
            if result.severity == ValidationSeverity.WARNING
        )

    @property
    def errors(self) -> tuple[ValidationResult, ...]:
        return tuple(
            result
            for result in self.results
            if result.severity in {
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            }
            and result.failed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
            "blocking_failures": [
                result.to_dict() for result in self.blocking_failures
            ],
            "warnings": [result.to_dict() for result in self.warnings],
        }


def pass_result(
    *,
    layer: str,
    check_name: str,
    message: str = "Validation passed.",
    severity: ValidationSeverity = ValidationSeverity.INFO,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    return ValidationResult(
        passed=True,
        layer=layer,
        check_name=check_name,
        severity=severity,
        message=message,
        metadata=metadata or {},
    )


def fail_result(
    *,
    layer: str,
    check_name: str,
    message: str,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    return ValidationResult(
        passed=False,
        layer=layer,
        check_name=check_name,
        severity=severity,
        message=message,
        metadata=metadata or {},
    )


def warning_result(
    *,
    layer: str,
    check_name: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    return ValidationResult(
        passed=False,
        layer=layer,
        check_name=check_name,
        severity=ValidationSeverity.WARNING,
        message=message,
        metadata=metadata or {},
    )


def build_gate_report(
    *,
    layer: str,
    results: list[ValidationResult] | tuple[ValidationResult, ...],
) -> GateReport:
    return GateReport(layer=layer, results=tuple(results))
