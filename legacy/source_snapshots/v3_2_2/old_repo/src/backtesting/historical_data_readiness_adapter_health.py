# src/backtesting/historical_data_readiness_adapter_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_data_readiness_adapter_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    adapter_status = operation_record.get("adapter_status")
    readiness_summary = dict(operation_record.get("readiness_summary", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if adapter_status == "needs_review":
        warnings.append("adapter_status requires review")

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    candidate_count = int(readiness_summary.get("candidate_count", 0))
    price_row_count = int(readiness_summary.get("price_row_count", 0))
    accepted_candidate_count = int(
        readiness_summary.get("accepted_candidate_count", 0)
    )
    rejected_candidate_count = int(
        readiness_summary.get("rejected_candidate_count", 0)
    )

    if adapter_status == "ready":
        if candidate_count <= 0:
            blocked_reasons.append("ready adapter has no candidate rows")

        if price_row_count <= 0:
            blocked_reasons.append("ready adapter has no price rows")

        if accepted_candidate_count <= 0:
            warnings.append("ready adapter has no accepted candidates")

        if rejected_candidate_count <= 0:
            warnings.append("ready adapter has no rejected candidates")

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
            "adapter_status": adapter_status,
            "candidate_count": candidate_count,
            "price_row_count": price_row_count,
            "accepted_candidate_count": accepted_candidate_count,
            "rejected_candidate_count": rejected_candidate_count,
        },
    }
