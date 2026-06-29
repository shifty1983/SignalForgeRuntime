# src/backtesting/historical_research_handoff_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "bundle_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "priority_research",
    "needs_review_research",
    "blocked_research",
    "handoff_summary",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "bundle_metadata",
    "metadata",
}


def audit_historical_research_handoff_record(
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
    if operation_type != "historical_research_handoff":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    bundle_status = operation_record.get("bundle_status")
    if bundle_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(f"operation_record invalid bundle_status: {bundle_status}")

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    priority_research = operation_record.get("priority_research", [])
    needs_review_research = operation_record.get("needs_review_research", [])
    blocked_research = operation_record.get("blocked_research", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("priority_research", priority_research),
        ("needs_review_research", needs_review_research),
        ("blocked_research", blocked_research),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    handoff_summary = operation_record.get("handoff_summary", {})
    if not isinstance(handoff_summary, Mapping):
        audit_errors.append("operation_record handoff_summary must be a mapping")
        handoff_summary = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if bundle_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append("operation_record ready bundle conflicts with is_ready=False")

    if bundle_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready bundle conflicts with is_ready=True"
        )

    if bundle_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked bundle_status must have blocked operation_status"
        )

    expected_counts = {
        "priority_count": len(priority_research)
        if isinstance(priority_research, list)
        else 0,
        "needs_review_count": len(needs_review_research)
        if isinstance(needs_review_research, list)
        else 0,
        "blocked_count": len(blocked_research)
        if isinstance(blocked_research, list)
        else 0,
    }
    expected_counts["total_count"] = (
        expected_counts["priority_count"]
        + expected_counts["needs_review_count"]
        + expected_counts["blocked_count"]
    )

    for key, expected_value in expected_counts.items():
        if handoff_summary.get(key) != expected_value:
            audit_errors.append(
                f"operation_record handoff_summary {key} does not match payloads"
            )

    if operation_status == "completed" and expected_counts["total_count"] == 0:
        audit_warnings.append("operation_record completed with no handoff payloads")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_research:
        audit_warnings.append("operation_record completed with blocked research payloads")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "bundle_status": bundle_status,
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
