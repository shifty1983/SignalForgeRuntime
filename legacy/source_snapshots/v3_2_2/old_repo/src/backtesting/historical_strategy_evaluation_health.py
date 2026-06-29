# src/backtesting/historical_strategy_evaluation_health.py

from __future__ import annotations

from typing import Any, Mapping


def evaluate_historical_strategy_evaluation_health(
    operation_record: Mapping[str, Any],
    *,
    audit_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    operation_status = operation_record.get("operation_status")
    validation_errors = operation_record.get("validation_errors", [])
    evaluated_rows = operation_record.get("evaluated_rows", [])
    summary = operation_record.get("summary", {})
    accepted_vs_rejected = operation_record.get("accepted_vs_rejected", {})

    if audit_report is not None and not audit_report.get("is_audit_passed", False):
        blocked_reasons.append("audit_report failed")

    if operation_status == "blocked" or operation_record.get("is_blocked") is True:
        blocked_reasons.append("operation_record is blocked")

    if validation_errors:
        blocked_reasons.append("operation_record has validation errors")

    if not evaluated_rows:
        blocked_reasons.append("operation_record has no evaluated rows")

    accepted_candidate_count = int(summary.get("accepted_candidate_count", 0))
    rejected_candidate_count = int(summary.get("rejected_candidate_count", 0))

    if accepted_candidate_count == 0:
        blocked_reasons.append("operation_record has no accepted candidates")

    if rejected_candidate_count == 0:
        warnings.append("operation_record has no rejected candidates")

    accepted_summary = accepted_vs_rejected.get("accepted", {})
    rejected_summary = accepted_vs_rejected.get("rejected", {})

    accepted_avg_outcome = float(
        accepted_summary.get("avg_direction_adjusted_outcome", 0.0)
    )
    rejected_avg_outcome = float(
        rejected_summary.get("avg_direction_adjusted_outcome", 0.0)
    )

    accepted_hit_rate = float(accepted_summary.get("hit_rate", 0.0))
    rejected_hit_rate = float(rejected_summary.get("hit_rate", 0.0))

    if accepted_candidate_count > 0 and rejected_candidate_count > 0:
        if accepted_avg_outcome <= rejected_avg_outcome:
            warnings.append(
                "accepted avg direction-adjusted outcome is not greater than rejected avg direction-adjusted outcome"
            )

        if accepted_hit_rate <= rejected_hit_rate:
            warnings.append(
                "accepted hit rate is not greater than rejected hit rate"
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
        "is_blocked": bool(blocked_reasons),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "summary": {
            "operation_status": operation_status,
            "accepted_candidate_count": accepted_candidate_count,
            "rejected_candidate_count": rejected_candidate_count,
            "evaluated_candidate_count": int(
                summary.get("evaluated_candidate_count", len(evaluated_rows))
            ),
            "accepted_avg_direction_adjusted_outcome": accepted_avg_outcome,
            "rejected_avg_direction_adjusted_outcome": rejected_avg_outcome,
            "accepted_hit_rate": accepted_hit_rate,
            "rejected_hit_rate": rejected_hit_rate,
        },
    }
