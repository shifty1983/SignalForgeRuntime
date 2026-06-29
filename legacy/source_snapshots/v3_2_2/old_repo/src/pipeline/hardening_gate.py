from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from src.pipeline.validation import (
    GateReport,
    ValidationResult,
    ValidationSeverity,
    build_gate_report,
    fail_result,
)

ValidationCheck = Callable[[Any], ValidationResult]


def _check_name(check: ValidationCheck) -> str:
    return getattr(check, "__name__", check.__class__.__name__)


def _invalid_check_result(
    *,
    layer: str,
    check_name: str,
    result: Any,
) -> ValidationResult:
    return fail_result(
        layer=layer,
        check_name=check_name,
        message=(
            "Validation check returned an invalid result. "
            "Expected ValidationResult."
        ),
        severity=ValidationSeverity.CRITICAL,
        metadata={
            "returned_type": type(result).__name__,
        },
    )


def _exception_result(
    *,
    layer: str,
    check_name: str,
    error: Exception,
) -> ValidationResult:
    return fail_result(
        layer=layer,
        check_name=check_name,
        message=f"Validation check raised an exception: {error}",
        severity=ValidationSeverity.CRITICAL,
        metadata={
            "exception_type": type(error).__name__,
        },
    )


def run_hardening_gate(
    *,
    layer: str,
    data: Any,
    checks: Iterable[ValidationCheck],
    fail_fast: bool = False,
) -> GateReport:
    results: list[ValidationResult] = []

    for check in checks:
        name = _check_name(check)

        try:
            result = check(data)
        except Exception as error:
            result = _exception_result(
                layer=layer,
                check_name=name,
                error=error,
            )

        if not isinstance(result, ValidationResult):
            result = _invalid_check_result(
                layer=layer,
                check_name=name,
                result=result,
            )

        results.append(result)

        if fail_fast and result.blocks_pipeline:
            break

    return build_gate_report(layer=layer, results=results)


def gate_passed(report: GateReport) -> bool:
    return report.passed


def gate_failed(report: GateReport) -> bool:
    return report.failed
