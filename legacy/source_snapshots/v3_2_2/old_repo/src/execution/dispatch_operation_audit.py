from __future__ import annotations

from typing import Any, Mapping

from src.execution.dispatch_contract import (
    DISPATCH_STATUS_DRY_RUN_ONLY,
    FORBIDDEN_DISPATCH_FIELDS,
)
from src.execution.dispatch_operation_record import (
    DISPATCH_OPERATION_TYPE,
    validate_execution_dispatch_operation_record,
)


def _find_forbidden_fields(
    value: Any,
    *,
    path: str,
) -> list[str]:
    issues: list[str] = []

    if isinstance(value, Mapping):
        for key, item in value.items():
            current_path = f"{path}.{key}"

            if key in FORBIDDEN_DISPATCH_FIELDS:
                issues.append(f"{path} contains forbidden dispatch field: {key}")

            issues.extend(_find_forbidden_fields(item, path=current_path))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_find_forbidden_fields(item, path=f"{path}[{index}]"))

    return issues


def audit_execution_dispatch_operation_record(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []

    record_validation_errors = validate_execution_dispatch_operation_record(
        operation_record
    )
    issues.extend(record_validation_errors)

    dispatch_intent_rows = operation_record.get("dispatch_intent_rows", [])
    validation_errors = list(operation_record.get("validation_errors", []))

    forbidden_field_issues = _find_forbidden_fields(
        operation_record,
        path="operation_record",
    )
    issues.extend(forbidden_field_issues)

    has_dispatch_intents = bool(dispatch_intent_rows)
    validation_passed = not validation_errors
    record_validation_passed = not record_validation_errors
    no_forbidden_fields = not forbidden_field_issues

    dry_run_only = True
    if isinstance(dispatch_intent_rows, list):
        dry_run_only = all(
            isinstance(row, Mapping)
            and row.get("dispatch_status") == DISPATCH_STATUS_DRY_RUN_ONLY
            for row in dispatch_intent_rows
        )
    else:
        dry_run_only = False

    operation_type_is_dispatch = (
        operation_record.get("operation_type") == DISPATCH_OPERATION_TYPE
    )

    checks = {
        "operation_type_is_dispatch": operation_type_is_dispatch,
        "has_dispatch_intents": has_dispatch_intents,
        "record_validation_passed": record_validation_passed,
        "dispatch_validation_passed": validation_passed,
        "dry_run_only": dry_run_only,
        "no_forbidden_broker_or_live_execution_fields": no_forbidden_fields,
    }

    for check_name, passed in checks.items():
        if not passed:
            issues.append(f"audit check failed: {check_name}")

    audit_status = "passed" if all(checks.values()) and not issues else "failed"

    return {
        "operation_id": operation_record.get("operation_id"),
        "operation_type": operation_record.get("operation_type"),
        "run_id": operation_record.get("run_id"),
        "audit_status": audit_status,
        "is_blocked": bool(operation_record.get("is_blocked")),
        "checks": checks,
        "issues": issues,
        "issue_count": len(issues),
    }
