# src/backtesting/historical_research_priority_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "report_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "priority_candidates",
    "needs_review_candidates",
    "blocked_candidates",
    "priority_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "report_metadata",
    "metadata",
}


def audit_historical_research_priority_record(
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
    if operation_type != "historical_research_priority":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    report_status = operation_record.get("report_status")
    if report_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(f"operation_record invalid report_status: {report_status}")

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    priority_candidates = operation_record.get("priority_candidates", [])
    needs_review_candidates = operation_record.get("needs_review_candidates", [])
    blocked_candidates = operation_record.get("blocked_candidates", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("priority_candidates", priority_candidates),
        ("needs_review_candidates", needs_review_candidates),
        ("blocked_candidates", blocked_candidates),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    priority_summary = operation_record.get("priority_summary", {})
    if not isinstance(priority_summary, Mapping):
        audit_errors.append("operation_record priority_summary must be a mapping")
        priority_summary = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if report_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append("operation_record ready report conflicts with is_ready=False")

    if report_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready report conflicts with is_ready=True"
        )

    if report_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked report_status must have blocked operation_status"
        )

    expected_counts = {
        "priority_count": len(priority_candidates)
        if isinstance(priority_candidates, list)
        else 0,
        "needs_review_count": len(needs_review_candidates)
        if isinstance(needs_review_candidates, list)
        else 0,
        "blocked_count": len(blocked_candidates)
        if isinstance(blocked_candidates, list)
        else 0,
    }
    expected_counts["total_count"] = (
        expected_counts["priority_count"]
        + expected_counts["needs_review_count"]
        + expected_counts["blocked_count"]
    )

    for key, expected_value in expected_counts.items():
        if priority_summary.get(key) != expected_value:
            audit_errors.append(
                f"operation_record priority_summary {key} does not match candidates"
            )

    if operation_status == "completed" and expected_counts["total_count"] == 0:
        audit_warnings.append("operation_record completed with no priority candidates")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_candidates:
        audit_warnings.append("operation_record completed with blocked candidates")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "report_status": report_status,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "priority_count": expected_counts["priority_count"],
            "needs_review_count": expected_counts["needs_review_count"],
            "blocked_count": expected_counts["blocked_count"],
            "total_count": expected_counts["total_count"],
        },
    }
