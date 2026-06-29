from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.execution.end_to_end_operation_audit import (
    build_execution_end_to_end_operation_audit_report,
)


def evaluate_execution_end_to_end_operation_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate health gates for the broker-neutral end-to-end execution dry run.
    """

    resolved_audit_report = audit_report or (
        build_execution_end_to_end_operation_audit_report(operation_record)
    )

    failed_checks: list[dict[str, Any]] = []

    status = str(operation_record.get("status", "blocked")).lower()
    is_blocked = bool(operation_record.get("is_blocked", True))

    if status != "completed":
        failed_checks.append(
            {
                "check": "operation_completed",
                "message": f"operation status is not completed: {status}",
            }
        )

    if is_blocked:
        failed_checks.append(
            {
                "check": "operation_not_blocked",
                "message": "operation is blocked",
            }
        )

    if operation_record.get("record_validation_errors"):
        failed_checks.append(
            {
                "check": "record_validation",
                "message": "operation record has validation errors",
                "errors": operation_record.get("record_validation_errors", []),
            }
        )

    if operation_record.get("validation_errors") and status == "completed":
        failed_checks.append(
            {
                "check": "completed_operation_has_no_validation_errors",
                "message": (
                    "completed operation contains validation errors"
                ),
                "errors": operation_record.get("validation_errors", []),
            }
        )

    if not resolved_audit_report.get("is_audit_passed", False):
        failed_checks.append(
            {
                "check": "operation_audit",
                "message": "operation audit failed",
                "finding_count": resolved_audit_report.get(
                    "finding_count",
                    0,
                ),
            }
        )

    dry_run_summary = operation_record.get("dry_run_result", {}).get(
        "summary",
        {},
    )

    if status == "completed":
        if dry_run_summary.get("execution_intent_count", 0) <= 0:
            failed_checks.append(
                {
                    "check": "execution_intents_present",
                    "message": "completed dry run has no execution intents",
                }
            )

        if dry_run_summary.get("planned_instruction_count", 0) <= 0:
            failed_checks.append(
                {
                    "check": "planned_instructions_present",
                    "message": "completed dry run has no planned instructions",
                }
            )

        if dry_run_summary.get("dispatch_intent_count", 0) <= 0:
            failed_checks.append(
                {
                    "check": "dispatch_intents_present",
                    "message": "completed dry run has no dispatch intents",
                }
            )

    health_status = "failed" if failed_checks else "passed"

    return {
        "health_type": "execution_end_to_end_operation_health",
        "operation_id": operation_record.get("operation_id"),
        "dry_run_id": operation_record.get("summary", {}).get("dry_run_id"),
        "health_status": health_status,
        "is_healthy": health_status == "passed",
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "summary": {
            "operation_status": operation_record.get("status"),
            "operation_is_blocked": operation_record.get("is_blocked"),
            "audit_status": resolved_audit_report.get("audit_status"),
            "audit_finding_count": resolved_audit_report.get(
                "finding_count",
                0,
            ),
            "failed_check_count": len(failed_checks),
        },
    }
