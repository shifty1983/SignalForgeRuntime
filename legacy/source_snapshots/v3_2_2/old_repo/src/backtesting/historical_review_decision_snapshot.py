# src/backtesting/historical_review_decision_snapshot.py

from __future__ import annotations

from typing import Any, Mapping


SNAPSHOT_TYPE = "historical_review_decision_snapshot"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_REVIEW_QUEUE_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "queue_result",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_review_decision_snapshot(
    review_queue_operation_result: Mapping[str, Any],
    *,
    snapshot_name: str = SNAPSHOT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_review_queue_operation_shape(
        review_queue_operation_result
    )

    if validation_errors:
        return {
            "snapshot_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "snapshot_type": SNAPSHOT_TYPE,
            "snapshot_name": snapshot_name,
            "validation_errors": validation_errors,
            "promoted_decisions": [],
            "needs_review_decisions": [],
            "blocked_decisions": [],
            "decision_counts": {
                "promoted": 0,
                "needs_review": 0,
                "blocked": 0,
                "total": 0,
            },
            "warnings": [],
            "blocked_reasons": validation_errors,
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "metadata": metadata_dict,
        }

    queue_result = dict(review_queue_operation_result.get("queue_result", {}))
    operation_record = dict(review_queue_operation_result.get("operation_record", {}))
    health_report = dict(review_queue_operation_result.get("health_report", {}))

    promoted_decisions = _build_decisions(
        queue_result.get("promoted_review", []),
        decision_status="promoted",
    )
    needs_review_decisions = _build_decisions(
        queue_result.get("needs_review", []),
        decision_status="needs_review",
    )
    blocked_decisions = _build_decisions(
        queue_result.get("blocked_review", []),
        decision_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in queue_result.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in queue_result.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    promoted_count = len(promoted_decisions)
    needs_review_count = len(needs_review_decisions)
    blocked_count = len(blocked_decisions)
    total_count = promoted_count + needs_review_count + blocked_count

    is_blocked = bool(
        review_queue_operation_result.get("is_blocked")
        or blocked_reasons
        or review_queue_operation_result.get("runner_status") == "blocked"
    )

    if is_blocked:
        snapshot_status = "blocked"
    elif needs_review_count > 0 or warnings:
        snapshot_status = "needs_review"
    else:
        snapshot_status = "ready"

    is_ready = snapshot_status == "ready"

    return {
        "snapshot_status": snapshot_status,
        "is_ready": is_ready,
        "is_blocked": is_blocked,
        "snapshot_type": SNAPSHOT_TYPE,
        "snapshot_name": snapshot_name,
        "validation_errors": [],
        "promoted_decisions": promoted_decisions,
        "needs_review_decisions": needs_review_decisions,
        "blocked_decisions": blocked_decisions,
        "decision_counts": {
            "promoted": promoted_count,
            "needs_review": needs_review_count,
            "blocked": blocked_count,
            "total": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": review_queue_operation_result.get("operation_name"),
            "runner_status": review_queue_operation_result.get("runner_status"),
            "queue_status": review_queue_operation_result.get("summary", {}).get(
                "queue_status"
            ),
            "operation_status": review_queue_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": review_queue_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": review_queue_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": review_queue_operation_result.get("summary", {}).get(
                "log_status"
            ),
        },
        "metadata": metadata_dict,
    }


def _validate_review_queue_operation_shape(
    review_queue_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_REVIEW_QUEUE_OPERATION_FIELDS
        - set(review_queue_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"review_queue_operation_result missing required fields: {missing_fields}"
        )

    operation_type = review_queue_operation_result.get("operation_type")
    if operation_type is not None and operation_type != "historical_review_queue":
        validation_errors.append(
            f"review_queue_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = review_queue_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"review_queue_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in review_queue_operation_result and not isinstance(
        review_queue_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "review_queue_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "queue_result",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in review_queue_operation_result and not isinstance(
            review_queue_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"review_queue_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_decisions(
    review_items: list[Mapping[str, Any]],
    *,
    decision_status: str,
) -> list[dict[str, Any]]:
    decisions = []

    for item in review_items:
        decisions.append(
            {
                "decision_status": decision_status,
                "export_name": item.get("export_name"),
                "validation_status": item.get("validation_status"),
                "promotion_status": item.get("promotion_status"),
                "is_validated": bool(item.get("is_validated")),
                "is_promoted": bool(item.get("is_promoted")),
                "requires_review": bool(item.get("requires_review")),
                "matrix_run_count": int(item.get("matrix_run_count", 0)),
                "completed_run_count": int(item.get("completed_run_count", 0)),
                "blocked_run_count": int(item.get("blocked_run_count", 0)),
                "stable_run_count": int(item.get("stable_run_count", 0)),
                "completed_run_ratio": _round(item.get("completed_run_ratio", 0.0)),
                "stable_run_ratio": _round(item.get("stable_run_ratio", 0.0)),
                "positive_edge_run_ratio": _round(
                    item.get("positive_edge_run_ratio", 0.0)
                ),
                "positive_hit_rate_edge_run_ratio": _round(
                    item.get("positive_hit_rate_edge_run_ratio", 0.0)
                ),
                "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
                    item.get(
                        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                        0.0,
                    )
                ),
                "overall_avg_accepted_minus_rejected_hit_rate": _round(
                    item.get("overall_avg_accepted_minus_rejected_hit_rate", 0.0)
                ),
                "warnings": list(item.get("warnings", [])),
                "blocked_reasons": list(item.get("blocked_reasons", [])),
                "option_behavior_review": dict(item.get("option_behavior_review", {})),
                "metadata": dict(item.get("metadata", {})),
            }
        )

    return sorted(
        decisions,
        key=lambda decision: (
            -float(
                decision[
                    "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome"
                ]
            ),
            -float(decision["overall_avg_accepted_minus_rejected_hit_rate"]),
            str(decision["export_name"]),
        ),
    )


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def _round(value: Any) -> float:
    return round(float(value or 0.0), 10)
