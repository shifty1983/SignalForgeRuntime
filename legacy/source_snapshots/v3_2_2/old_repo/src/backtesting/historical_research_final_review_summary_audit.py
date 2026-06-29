# src/backtesting/historical_research_final_review_summary_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "summary_status",
    "is_ready",
    "is_blocked",
    "validation_errors",
    "ready_items",
    "needs_review_items",
    "blocked_items",
    "final_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "summary_metadata",
    "metadata",
}


def audit_historical_research_final_review_summary_record(
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
    if operation_type != "historical_research_final_review_summary":
        audit_errors.append(
            f"operation_record invalid operation_type: {operation_type}"
        )

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    summary_status = operation_record.get("summary_status")
    if summary_status not in {"ready", "needs_review", "blocked"}:
        audit_errors.append(
            f"operation_record invalid summary_status: {summary_status}"
        )

    if not isinstance(operation_record.get("is_ready"), bool):
        audit_errors.append("operation_record is_ready must be a boolean")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    ready_items = operation_record.get("ready_items", [])
    needs_review_items = operation_record.get("needs_review_items", [])
    blocked_items = operation_record.get("blocked_items", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("ready_items", ready_items),
        ("needs_review_items", needs_review_items),
        ("blocked_items", blocked_items),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    final_counts = operation_record.get("final_counts", {})
    if not isinstance(final_counts, Mapping):
        audit_errors.append("operation_record final_counts must be a mapping")
        final_counts = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if summary_status == "ready" and operation_record.get("is_ready") is not True:
        audit_errors.append(
            "operation_record ready summary conflicts with is_ready=False"
        )

    if summary_status != "ready" and operation_record.get("is_ready") is True:
        audit_errors.append(
            "operation_record non-ready summary conflicts with is_ready=True"
        )

    if summary_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked summary_status must have blocked operation_status"
        )

    expected_counts = {
        "ready": len(ready_items) if isinstance(ready_items, list) else 0,
        "needs_review": (
            len(needs_review_items)
            if isinstance(needs_review_items, list)
            else 0
        ),
        "blocked": len(blocked_items) if isinstance(blocked_items, list) else 0,
    }
    expected_counts["total"] = (
        expected_counts["ready"]
        + expected_counts["needs_review"]
        + expected_counts["blocked"]
    )

    for key, expected_value in expected_counts.items():
        if final_counts.get(key) != expected_value:
            audit_errors.append(
                f"operation_record final_counts {key} does not match final review items"
            )

    if operation_status == "completed" and expected_counts["total"] == 0:
        audit_warnings.append("operation_record completed with no final review items")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    if operation_status == "completed" and blocked_items:
        audit_warnings.append("operation_record completed with blocked final review items")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "summary_status": summary_status,
            "is_ready": operation_record.get("is_ready"),
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "ready_count": expected_counts["ready"],
            "needs_review_count": expected_counts["needs_review"],
            "blocked_count": expected_counts["blocked"],
            "total_count": expected_counts["total"],
        },
    }
