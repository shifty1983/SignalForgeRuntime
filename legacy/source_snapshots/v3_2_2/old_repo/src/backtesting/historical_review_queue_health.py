# src/backtesting/historical_review_queue_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_review_queue_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    queue_status = operation_record.get("queue_status")
    review_counts = dict(operation_record.get("review_counts", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    promoted_review_count = int(review_counts.get("promoted_review", 0))
    needs_review_count = int(review_counts.get("needs_review", 0))
    blocked_review_count = int(review_counts.get("blocked_review", 0))
    total_review_count = int(review_counts.get("total", 0))

    if queue_status == "completed" and total_review_count == 0:
        warnings.append("review queue completed with no review items")

    if needs_review_count > 0:
        warnings.append("review queue has needs_review items")

    if blocked_review_count > 0:
        warnings.append("review queue has blocked_review items")

    if blocked_reasons:
        health_status = "blocked"
    elif warnings:
        health_status = "warning"
    else:
        health_status = "healthy"

    return {
        "health_status": health_status,
        "is_healthy": health_status == "healthy",
        "is_blocked": health_status == "blocked",
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "summary": {
            "operation_status": operation_status,
            "queue_status": queue_status,
            "promoted_review_count": promoted_review_count,
            "needs_review_count": needs_review_count,
            "blocked_review_count": blocked_review_count,
            "total_review_count": total_review_count,
        },
    }
