from __future__ import annotations

from typing import Any, Mapping

from src.execution.dispatch_contract import DISPATCH_STATUS_DRY_RUN_ONLY
from src.execution.dispatch_operation_audit import (
    audit_execution_dispatch_operation_record,
)
from src.execution.dispatch_operation_record import (
    DISPATCH_OPERATION_STATUS_COMPLETED,
    DISPATCH_OPERATION_TYPE,
)


def evaluate_execution_dispatch_operation_health(
    operation_record: Mapping[str, Any],
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit_report = (
        dict(audit_report)
        if audit_report is not None
        else audit_execution_dispatch_operation_record(operation_record)
    )

    dispatch_intent_rows = operation_record.get("dispatch_intent_rows", [])
    validation_errors = list(operation_record.get("validation_errors", []))

    dry_run_only = (
        isinstance(dispatch_intent_rows, list)
        and bool(dispatch_intent_rows)
        and all(
            isinstance(row, Mapping)
            and row.get("dispatch_status") == DISPATCH_STATUS_DRY_RUN_ONLY
            for row in dispatch_intent_rows
        )
    )

    summary = operation_record.get("summary", {})
    summary_count_matches = (
        isinstance(summary, Mapping)
        and summary.get("dispatch_count") == operation_record.get("dispatch_intent_count")
        and operation_record.get("dispatch_intent_count") == len(dispatch_intent_rows)
    )

    checks = {
        "operation_type_is_dispatch": (
            operation_record.get("operation_type") == DISPATCH_OPERATION_TYPE
        ),
        "operation_completed": (
            operation_record.get("status") == DISPATCH_OPERATION_STATUS_COMPLETED
        ),
        "operation_not_blocked": not bool(operation_record.get("is_blocked")),
        "dispatch_intents_present": bool(dispatch_intent_rows),
        "dispatch_validation_passed": not validation_errors,
        "audit_passed": audit_report.get("audit_status") == "passed",
        "dry_run_only": dry_run_only,
        "summary_count_matches": summary_count_matches,
    }

    failures = [
        f"health check failed: {check_name}"
        for check_name, passed in checks.items()
        if not passed
    ]

    audit_issues = list(audit_report.get("issues", []))
    failures.extend(audit_issues)

    is_healthy = not failures

    return {
        "operation_id": operation_record.get("operation_id"),
        "operation_type": operation_record.get("operation_type"),
        "run_id": operation_record.get("run_id"),
        "health_status": "passed" if is_healthy else "failed",
        "is_healthy": is_healthy,
        "checks": checks,
        "failures": failures,
        "failure_count": len(failures),
        "audit_status": audit_report.get("audit_status"),
    }
