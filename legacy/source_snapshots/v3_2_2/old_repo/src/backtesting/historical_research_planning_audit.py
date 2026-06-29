# src/backtesting/historical_research_planning_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "planning_queue_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "priority_planning",
    "needs_review_planning",
    "blocked_planning",
    "planning_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "queue_metadata",
    "metadata",
}


def audit_historical_research_planning_record(
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
    if operation_type != "historical_research_planning":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    planning_queue_status = operation_record.get("planning_queue_status")
    if planning_queue_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(
            f"operation_record invalid planning_queue_status: {planning_queue_status}"
        )

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    priority_planning = operation_record.get("priority_planning", [])
    needs_review_planning = operation_record.get("needs_review_planning", [])
    blocked_planning = operation_record.get("blocked_planning", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("priority_planning", priority_planning),
        ("needs_review_planning", needs_review_planning),
        ("blocked_planning", blocked_planning),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    planning_counts = operation_record.get("planning_counts", {})
    if not isinstance(planning_counts, Mapping):
        audit_errors.append("operation_record planning_counts must be a mapping")
        planning_counts = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if planning_queue_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append(
            "operation_record ready planning_queue conflicts with is_ready=False"
        )

    if planning_queue_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready planning_queue conflicts with is_ready=True"
        )

    if planning_queue_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked planning_queue_status must have blocked operation_status"
        )

    expected_counts = {
        "priority": len(priority_planning) if isinstance(priority_planning, list) else 0,
        "needs_review": (
            len(needs_review_planning)
            if isinstance(needs_review_planning, list)
            else 0
        ),
        "blocked": len(blocked_planning) if isinstance(blocked_planning, list) else 0,
    }
    expected_counts["total"] = (
        expected_counts["priority"]
        + expected_counts["needs_review"]
        + expected_counts["blocked"]
    )

    for key, expected_value in expected_counts.items():
        if planning_counts.get(key) != expected_value:
            audit_errors.append(
                f"operation_record planning_counts {key} does not match planning payloads"
            )

    if operation_status == "completed" and expected_counts["total"] == 0:
        audit_warnings.append("operation_record completed with no planning payloads")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_planning:
        audit_warnings.append("operation_record completed with blocked planning payloads")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "planning_queue_status": planning_queue_status,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "priority_count": expected_counts["priority"],
            "needs_review_count": expected_counts["needs_review"],
            "blocked_count": expected_counts["blocked"],
            "total_count": expected_counts["total"],
        },
    }
