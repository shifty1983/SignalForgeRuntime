# src/backtesting/historical_review_queue_audit.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATION_RECORD_FIELDS = {
    "schema_version",
    "operation_type",
    "operation_name",
    "operation_id",
    "operation_status",
    "queue_status",
    "is_blocked",
    "validation_errors",
    "promoted_review",
    "needs_review",
    "blocked_review",
    "review_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "queue_metadata",
    "metadata",
}


def audit_historical_review_queue_record(
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
    if operation_type != "historical_review_queue":
        audit_errors.append(f"operation_record invalid operation_type: {operation_type}")

    operation_status = operation_record.get("operation_status")
    if operation_status not in {"completed", "blocked"}:
        audit_errors.append(
            f"operation_record invalid operation_status: {operation_status}"
        )

    queue_status = operation_record.get("queue_status")
    if queue_status not in {"completed", "blocked"}:
        audit_errors.append(f"operation_record invalid queue_status: {queue_status}")

    if not isinstance(operation_record.get("is_blocked"), bool):
        audit_errors.append("operation_record is_blocked must be a boolean")

    validation_errors = operation_record.get("validation_errors", [])
    warnings = operation_record.get("warnings", [])
    blocked_reasons = operation_record.get("blocked_reasons", [])
    promoted_review = operation_record.get("promoted_review", [])
    needs_review = operation_record.get("needs_review", [])
    blocked_review = operation_record.get("blocked_review", [])
    review_counts = operation_record.get("review_counts", {})

    for list_field, value in [
        ("validation_errors", validation_errors),
        ("warnings", warnings),
        ("blocked_reasons", blocked_reasons),
        ("promoted_review", promoted_review),
        ("needs_review", needs_review),
        ("blocked_review", blocked_review),
    ]:
        if not isinstance(value, list):
            audit_errors.append(f"operation_record {list_field} must be a list")

    if not isinstance(review_counts, Mapping):
        audit_errors.append("operation_record review_counts must be a mapping")
        review_counts = {}

    if operation_status == "completed" and operation_record.get("is_blocked") is True:
        audit_errors.append(
            "operation_record completed status conflicts with is_blocked=True"
        )

    if operation_status == "blocked" and operation_record.get("is_blocked") is False:
        audit_errors.append(
            "operation_record blocked status conflicts with is_blocked=False"
        )

    if queue_status == "blocked" and operation_status != "blocked":
        audit_errors.append(
            "operation_record blocked queue_status must have blocked operation_status"
        )

    expected_counts = {
        "promoted_review": len(promoted_review) if isinstance(promoted_review, list) else 0,
        "needs_review": len(needs_review) if isinstance(needs_review, list) else 0,
        "blocked_review": len(blocked_review) if isinstance(blocked_review, list) else 0,
    }
    expected_counts["total"] = (
        expected_counts["promoted_review"]
        + expected_counts["needs_review"]
        + expected_counts["blocked_review"]
    )

    for key, expected_value in expected_counts.items():
        if review_counts.get(key) != expected_value:
            audit_errors.append(
                f"operation_record review_counts {key} does not match queue contents"
            )

    if operation_status == "completed" and expected_counts["total"] == 0:
        audit_warnings.append("operation_record completed with no review items")

    if operation_status == "completed" and blocked_review:
        audit_warnings.append("operation_record completed with blocked review items")

    if operation_status == "completed" and warnings:
        audit_warnings.append("operation_record completed with warnings")

    return {
        "audit_status": "failed" if audit_errors else "passed",
        "is_audit_passed": not audit_errors,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "summary": {
            "operation_type": operation_type,
            "operation_status": operation_status,
            "queue_status": queue_status,
            "is_blocked": operation_record.get("is_blocked"),
            "validation_error_count": len(validation_errors)
            if isinstance(validation_errors, list)
            else 0,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "blocked_reason_count": len(blocked_reasons)
            if isinstance(blocked_reasons, list)
            else 0,
            "promoted_review_count": expected_counts["promoted_review"],
            "needs_review_count": expected_counts["needs_review"],
            "blocked_review_count": expected_counts["blocked_review"],
            "total_review_count": expected_counts["total"],
        },
    }
