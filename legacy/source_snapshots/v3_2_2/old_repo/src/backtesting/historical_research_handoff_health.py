# src/backtesting/historical_research_handoff_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_research_handoff_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    bundle_status = operation_record.get("bundle_status")
    handoff_summary = dict(operation_record.get("handoff_summary", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if bundle_status == "needs_review":
        warnings.append("bundle_status requires review")

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    priority_count = int(handoff_summary.get("priority_count", 0))
    needs_review_count = int(handoff_summary.get("needs_review_count", 0))
    blocked_count = int(handoff_summary.get("blocked_count", 0))
    total_count = int(handoff_summary.get("total_count", 0))

    if bundle_status == "ready":
        if priority_count <= 0:
            blocked_reasons.append("ready handoff has no priority research payloads")

        if needs_review_count > 0:
            warnings.append("ready handoff has needs_review research payloads")

        if blocked_count > 0:
            warnings.append("ready handoff has blocked research payloads")

    if total_count == 0 and bundle_status != "blocked":
        warnings.append("research handoff has no payloads")

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
            "bundle_status": bundle_status,
            "priority_count": priority_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
    }
