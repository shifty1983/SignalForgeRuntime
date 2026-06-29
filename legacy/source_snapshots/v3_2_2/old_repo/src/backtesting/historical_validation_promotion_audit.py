# src/backtesting/historical_validation_promotion_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "promotion_status",
    "is_promoted",
    "is_blocked",
    "validation_errors",
    "blocked_reasons",
    "warnings",
    "promotion_metrics",
    "summary",
    "metadata",
}


def audit_historical_validation_promotion_record(
    operation_record: Mapping[str, Any],
) -> dict[str, Any]:
    audit_errors: list[str] = []
    audit_warnings: list[str] = []

    missing_fields = sorted(
        REQUIRED_OPERATION_RECORD_FIELDS - set(operation_record.keys())
    )
    if missing_fields:
        audit_errors.append(
            f"operation_record missing required fields: {missing_fields}"
        )

    operation_type = operation_record.get("operation_type")
    if operation_type != "historical_validation_promotion":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    promotion_status = operation_record.get("promotion_status")
    if promotion_status not in {"promoted", "needs_review", "blocked"}:
        audit_errors.append(
            f"operation_record invalid promotion_status: {promotion_status}"
        )

    if not isinstance(operation_record.get("is_promoted"), bool):
        audit_errors.append("operation_record is_promoted must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    if not isinstance(validation_errors, list):
        audit_errors.append("operation_record validation_errors must be a list")
        validation_errors = []

    blocked_reasons = operation_record.get("blocked_reasons", [])
    if not isinstance(blocked_reasons, list):
        audit_errors.append("operation_record blocked_reasons must be a list")
        blocked_reasons = []

    warnings = operation_record.get("warnings", [])
    if not isinstance(warnings, list):
        audit_errors.append("operation_record warnings must be a list")
        warnings = []

    promotion_metrics = operation_record.get("promotion_metrics", {})
    if not isinstance(promotion_metrics, Mapping):
        audit_errors.append("operation_record promotion_metrics must be a mapping")
        promotion_metrics = {}

    summary = operation_record.get("summary", {})
    if not isinstance(summary, Mapping):
        audit_errors.append("operation_record summary must be a mapping")
        summary = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if promotion_status == "promoted" and operation_record.get("is_promoted") is False:
        audit_errors.append(
            "operation_record promoted status conflicts with is_promoted=False"
        )

    if promotion_status != "promoted" and operation_record.get("is_promoted") is True:
        audit_errors.append(
            "operation_record non-promoted status conflicts with is_promoted=True"
        )

    if promotion_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked promotion_status must have blocked operation_status"
        )

    if promotion_status == "needs_review" and not warnings:
        audit_warnings.append(
            "operation_record needs_review promotion_status has no warnings"
        )

    if promotion_status == "blocked" and not blocked_reasons:
        audit_warnings.append(
            "operation_record blocked promotion_status has no blocked_reasons"
        )

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "promotion_status": promotion_status,
            "is_promoted": operation_record.get("is_promoted"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors),
            "blocked_reason_count": len(blocked_reasons),
            "warning_count": len(warnings),
            "matrix_run_count": promotion_metrics.get("matrix_run_count", 0),
            "completed_run_count": promotion_metrics.get("completed_run_count", 0),
            "stable_run_count": promotion_metrics.get("stable_run_count", 0),
            "validation_status": summary.get("validation_status"),
            "diagnostic_status": summary.get("diagnostic_status"),
        },
    }
