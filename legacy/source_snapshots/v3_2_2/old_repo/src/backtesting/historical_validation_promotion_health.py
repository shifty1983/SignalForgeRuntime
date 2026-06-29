# src/backtesting/historical_validation_promotion_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_validation_promotion_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    operation_status = operation_record.get("operation_status")
    promotion_status = operation_record.get("promotion_status")
    promotion_metrics = dict(operation_record.get("promotion_metrics", {}))

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if operation_record.get("validation_errors"):
        blocked_reasons.append("operation_record has validation errors")

    if operation_record.get("blocked_reasons"):
        blocked_reasons.extend(
            str(reason) for reason in operation_record.get("blocked_reasons", [])
        )

    if promotion_status == "needs_review":
        warnings.append("promotion_status requires review")

    if operation_record.get("warnings"):
        warnings.extend(str(item) for item in operation_record.get("warnings", []))

    if promotion_status == "promoted" and operation_record.get("is_promoted") is not True:
        blocked_reasons.append("promoted record is not marked as promoted")

    if promotion_status != "promoted" and operation_record.get("is_promoted") is True:
        blocked_reasons.append("non-promoted record is marked as promoted")

    matrix_run_count = int(promotion_metrics.get("matrix_run_count", 0))
    completed_run_ratio = float(promotion_metrics.get("completed_run_ratio", 0.0))
    stable_run_ratio = float(promotion_metrics.get("stable_run_ratio", 0.0))
    positive_edge_run_ratio = float(
        promotion_metrics.get("positive_edge_run_ratio", 0.0)
    )
    positive_hit_rate_edge_run_ratio = float(
        promotion_metrics.get("positive_hit_rate_edge_run_ratio", 0.0)
    )

    if promotion_status == "promoted":
        if matrix_run_count <= 0:
            blocked_reasons.append("promoted record has no matrix runs")

        if completed_run_ratio < 1.0:
            warnings.append("promoted record completed_run_ratio is below 1.0")

        if stable_run_ratio < 1.0:
            warnings.append("promoted record stable_run_ratio is below 1.0")

        if positive_edge_run_ratio < 1.0:
            warnings.append("promoted record positive_edge_run_ratio is below 1.0")

        if positive_hit_rate_edge_run_ratio < 1.0:
            warnings.append(
                "promoted record positive_hit_rate_edge_run_ratio is below 1.0"
            )

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
            "promotion_status": promotion_status,
            "is_promoted": bool(operation_record.get("is_promoted")),
            "matrix_run_count": matrix_run_count,
            "completed_run_ratio": completed_run_ratio,
            "stable_run_ratio": stable_run_ratio,
            "positive_edge_run_ratio": positive_edge_run_ratio,
            "positive_hit_rate_edge_run_ratio": positive_hit_rate_edge_run_ratio,
        },
    }
