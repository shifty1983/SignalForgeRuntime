# src/backtesting/historical_research_final_review_summary_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_research_final_review_summary_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    summary_status = operation_record.get("summary_status")
    final_counts = dict(operation_record.get("final_counts", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if summary_status == "needs_review":
        warnings.append("summary_status requires review")

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    ready_count = int(final_counts.get("ready", 0))
    needs_review_count = int(final_counts.get("needs_review", 0))
    blocked_count = int(final_counts.get("blocked", 0))
    total_count = int(final_counts.get("total", 0))

    if summary_status == "ready":
        if ready_count <= 0:
            blocked_reasons.append("ready final review summary has no ready items")

        if needs_review_count > 0:
            warnings.append("ready final review summary has needs_review items")

        if blocked_count > 0:
            warnings.append("ready final review summary has blocked items")

    if total_count == 0 and summary_status != "blocked":
        warnings.append("final review summary has no items")

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
            "summary_status": summary_status,
            "ready_count": ready_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
    }
