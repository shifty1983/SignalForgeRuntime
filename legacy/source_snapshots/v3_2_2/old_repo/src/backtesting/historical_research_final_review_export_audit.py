# src/backtesting/historical_research_final_review_export_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "export_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "ready_final_review",
    "needs_review_final_review",
    "blocked_final_review",
    "export_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "export_metadata",
    "metadata",
}


def audit_historical_research_final_review_export_record(
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
    if operation_type != "historical_research_final_review_export":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    export_status = operation_record.get("export_status")
    if export_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(f"operation_record invalid export_status: {export_status}")

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    ready_final_review = operation_record.get("ready_final_review", [])
    needs_review_final_review = operation_record.get("needs_review_final_review", [])
    blocked_final_review = operation_record.get("blocked_final_review", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("ready_final_review", ready_final_review),
        ("needs_review_final_review", needs_review_final_review),
        ("blocked_final_review", blocked_final_review),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    export_summary = operation_record.get("export_summary", {})
    if not isinstance(export_summary, Mapping):
        audit_errors.append("operation_record export_summary must be a mapping")
        export_summary = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if export_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append("operation_record ready export conflicts with is_ready=False")

    if export_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready export conflicts with is_ready=True"
        )

    if export_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked export_status must have blocked operation_status"
        )

    expected_counts = {
        "ready_count": (
            len(ready_final_review) if isinstance(ready_final_review, list) else 0
        ),
        "needs_review_count": (
            len(needs_review_final_review)
            if isinstance(needs_review_final_review, list)
            else 0
        ),
        "blocked_count": (
            len(blocked_final_review)
            if isinstance(blocked_final_review, list)
            else 0
        ),
    }
    expected_counts["total_count"] = (
        expected_counts["ready_count"]
        + expected_counts["needs_review_count"]
        + expected_counts["blocked_count"]
    )

    for key, expected_value in expected_counts.items():
        if export_summary.get(key) != expected_value:
            audit_errors.append(
                f"operation_record export_summary {key} does not match final review export payloads"
            )

    if operation_status == "completed" and expected_counts["total_count"] == 0:
        audit_warnings.append("operation_record completed with no final review export payloads")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_final_review:
        audit_warnings.append(
            "operation_record completed with blocked final review export payloads"
        )

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "export_status": export_status,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "ready_count": expected_counts["ready_count"],
            "needs_review_count": expected_counts["needs_review_count"],
            "blocked_count": expected_counts["blocked_count"],
            "total_count": expected_counts["total_count"],
        },
    }
