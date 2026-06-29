from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from typing import Any, Mapping

from src.execution.operation_record import (
    BLOCKED_STATUS,
    COMPLETED_STATUS,
    EXECUTION_PLANNING_OPERATION_TYPE,
    FORBIDDEN_EXECUTION_FIELDS,
)


@dataclass(frozen=True)
class ExecutionPlanningAudit:
    operation_id: str | None
    status: str | None
    passed: bool
    finding_count: int
    findings: list[dict[str, Any]]
    summary: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_execution_planning_operation_record(record: Any) -> ExecutionPlanningAudit:
    normalized_record = _json_safe_record(record)

    findings: list[dict[str, Any]] = []

    operation_id = normalized_record.get("operation_id")
    status = normalized_record.get("status")
    operation_type = normalized_record.get("operation_type")
    summary = _json_safe(normalized_record.get("summary", {}))
    metadata = _json_safe(normalized_record.get("metadata", {}))

    execution_intent_rows = normalized_record.get("execution_intent_rows", [])
    planned_order_instructions = normalized_record.get(
        "planned_order_instructions", []
    )
    validation_errors = normalized_record.get("validation_errors", [])

    if operation_type != EXECUTION_PLANNING_OPERATION_TYPE:
        findings.append(
            _finding(
                severity="error",
                code="invalid_operation_type",
                message=(
                    "Execution planning audit expected operation_type "
                    f"{EXECUTION_PLANNING_OPERATION_TYPE!r}, got {operation_type!r}"
                ),
            )
        )

    if status not in {COMPLETED_STATUS, BLOCKED_STATUS}:
        findings.append(
            _finding(
                severity="error",
                code="invalid_status",
                message=(
                    f"Execution planning status must be {COMPLETED_STATUS!r} "
                    f"or {BLOCKED_STATUS!r}"
                ),
            )
        )

    if status == BLOCKED_STATUS:
        findings.append(
            _finding(
                severity="error",
                code="operation_blocked",
                message="Execution planning operation is blocked",
            )
        )

    if status == COMPLETED_STATUS and validation_errors:
        findings.append(
            _finding(
                severity="error",
                code="completed_with_validation_errors",
                message=(
                    "Execution planning operation is completed but contains "
                    "validation errors"
                ),
            )
        )

    if status == BLOCKED_STATUS and not validation_errors:
        findings.append(
            _finding(
                severity="error",
                code="blocked_without_validation_errors",
                message=(
                    "Execution planning operation is blocked but does not contain "
                    "validation errors"
                ),
            )
        )

    for validation_error in validation_errors:
        findings.append(
            _finding(
                severity="error",
                code="validation_error",
                message=str(validation_error),
            )
        )

    _audit_summary_count(
        findings=findings,
        summary=summary,
        summary_key="intent_count",
        actual_count=len(execution_intent_rows),
    )
    _audit_summary_count(
        findings=findings,
        summary=summary,
        summary_key="planned_instruction_count",
        actual_count=len(planned_order_instructions),
    )
    _audit_summary_count(
        findings=findings,
        summary=summary,
        summary_key="validation_error_count",
        actual_count=len(validation_errors),
    )

    for index, instruction in enumerate(planned_order_instructions):
        instruction_record = _json_safe_record(instruction)

        for field in FORBIDDEN_EXECUTION_FIELDS:
            if field in instruction_record:
                findings.append(
                    _finding(
                        severity="error",
                        code="forbidden_execution_field",
                        message=(
                            f"planned_order_instructions[{index}] contains "
                            f"broker/execution field: {field}"
                        ),
                    )
                )

    passed = not any(finding["severity"] == "error" for finding in findings)

    return ExecutionPlanningAudit(
        operation_id=str(operation_id) if operation_id is not None else None,
        status=str(status) if status is not None else None,
        passed=passed,
        finding_count=len(findings),
        findings=findings,
        summary=summary,
        metadata=metadata,
    )


def _audit_summary_count(
    *,
    findings: list[dict[str, Any]],
    summary: Mapping[str, Any],
    summary_key: str,
    actual_count: int,
) -> None:
    if summary.get(summary_key) != actual_count:
        findings.append(
            _finding(
                severity="error",
                code="summary_count_mismatch",
                message=(
                    f"summary[{summary_key!r}] expected {actual_count}, "
                    f"got {summary.get(summary_key)!r}"
                ),
            )
        )


def _finding(*, severity: str, code: str, message: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
    }


def _json_safe_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_dict(asdict(value))

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe_record(value.to_dict())

    if hasattr(value, "__dict__"):
        return _json_safe_dict(vars(value))

    raise TypeError(f"Unsupported record type: {type(value).__name__}")


def _json_safe_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(item) for key, item in value.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_dict(asdict(value))

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value
