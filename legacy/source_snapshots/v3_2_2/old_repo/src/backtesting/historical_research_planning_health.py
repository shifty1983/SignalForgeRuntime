# src/backtesting/historical_research_planning_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_research_planning_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    planning_queue_status = operation_record.get("planning_queue_status")
    planning_counts = dict(operation_record.get("planning_counts", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if planning_queue_status == "needs_review":
        warnings.append("planning_queue_status requires review")

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    priority_count = int(planning_counts.get("priority", 0))
    needs_review_count = int(planning_counts.get("needs_review", 0))
    blocked_count = int(planning_counts.get("blocked", 0))
    total_count = int(planning_counts.get("total", 0))

    if planning_queue_status == "ready":
        if priority_count <= 0:
            blocked_reasons.append("ready planning queue has no priority items")

        if needs_review_count > 0:
            warnings.append("ready planning queue has needs_review items")

        if blocked_count > 0:
            warnings.append("ready planning queue has blocked items")

    if total_count == 0 and planning_queue_status != "blocked":
        warnings.append("research planning queue has no items")

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
            "planning_queue_status": planning_queue_status,
            "priority_count": priority_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
    }
