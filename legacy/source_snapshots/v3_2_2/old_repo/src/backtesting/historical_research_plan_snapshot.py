# src/backtesting/historical_research_plan_snapshot.py

from __future__ import annotations

from typing import Any, Mapping


SNAPSHOT_TYPE = "historical_research_plan_snapshot"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_PLANNING_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "planning_queue",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_research_plan_snapshot(
    planning_operation_result: Mapping[str, Any],
    *,
    snapshot_name: str = SNAPSHOT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_planning_operation_result(
        planning_operation_result
    )

    if validation_errors:
        return {
            "snapshot_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "snapshot_type": SNAPSHOT_TYPE,
            "snapshot_name": snapshot_name,
            "validation_errors": validation_errors,
            "ready_research_plans": [],
            "needs_review_research_plans": [],
            "blocked_research_plans": [],
            "plan_counts": {
                "ready": 0,
                "needs_review": 0,
                "blocked": 0,
                "total": 0,
            },
            "warnings": [],
            "blocked_reasons": validation_errors,
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "source_summary": {},
            "metadata": metadata_dict,
        }

    planning_queue = dict(planning_operation_result.get("planning_queue", {}))
    operation_record = dict(planning_operation_result.get("operation_record", {}))
    health_report = dict(planning_operation_result.get("health_report", {}))

    ready_research_plans = _build_plan_items(
        planning_queue.get("priority_planning", []),
        plan_status="ready",
    )
    needs_review_research_plans = _build_plan_items(
        planning_queue.get("needs_review_planning", []),
        plan_status="needs_review",
    )
    blocked_research_plans = _build_plan_items(
        planning_queue.get("blocked_planning", []),
        plan_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in planning_queue.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in planning_queue.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    ready_count = len(ready_research_plans)
    needs_review_count = len(needs_review_research_plans)
    blocked_count = len(blocked_research_plans)
    total_count = ready_count + needs_review_count + blocked_count

    is_blocked = bool(
        planning_operation_result.get("is_blocked")
        or planning_queue.get("is_blocked")
        or blocked_reasons
    )

    if is_blocked:
        snapshot_status = "blocked"
    elif needs_review_count > 0 or warnings:
        snapshot_status = "needs_review"
    else:
        snapshot_status = "ready"

    return {
        "snapshot_status": snapshot_status,
        "is_ready": snapshot_status == "ready",
        "is_blocked": snapshot_status == "blocked",
        "snapshot_type": SNAPSHOT_TYPE,
        "snapshot_name": snapshot_name,
        "validation_errors": [],
        "ready_research_plans": ready_research_plans,
        "needs_review_research_plans": needs_review_research_plans,
        "blocked_research_plans": blocked_research_plans,
        "plan_counts": {
            "ready": ready_count,
            "needs_review": needs_review_count,
            "blocked": blocked_count,
            "total": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": planning_operation_result.get("operation_name"),
            "runner_status": planning_operation_result.get("runner_status"),
            "planning_queue_status": planning_queue.get("planning_queue_status"),
            "operation_status": planning_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": planning_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": planning_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": planning_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "planning_counts": dict(planning_queue.get("planning_counts", {})),
        },
        "metadata": metadata_dict,
    }


def _validate_planning_operation_result(
    planning_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PLANNING_OPERATION_FIELDS - set(planning_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"planning_operation_result missing required fields: {missing_fields}"
        )

    operation_type = planning_operation_result.get("operation_type")
    if (
        operation_type is not None
        and operation_type != "historical_research_planning"
    ):
        validation_errors.append(
            f"planning_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = planning_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"planning_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in planning_operation_result and not isinstance(
        planning_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "planning_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "planning_queue",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in planning_operation_result and not isinstance(
            planning_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"planning_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_plan_items(
    planning_items: list[Mapping[str, Any]],
    *,
    plan_status: str,
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []

    for item in planning_items:
        plans.append(
            {
                "plan_status": plan_status,
                "planning_status": item.get("planning_status"),
                "planning_rank": item.get("planning_rank"),
                "research_action": item.get("research_action"),
                "handoff_status": item.get("handoff_status"),
                "priority_status": item.get("priority_status"),
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
                    item.get(
                        "overall_avg_accepted_minus_rejected_hit_rate",
                        0.0,
                    )
                ),
                "priority_score": _round(item.get("priority_score", 0.0)),
                "option_behavior_review": dict(item.get("option_behavior_review", {})),
                "warnings": list(item.get("warnings", [])),
                "blocked_reasons": list(item.get("blocked_reasons", [])),
                "metadata": dict(item.get("metadata", {})),
            }
        )

    return sorted(
        plans,
        key=lambda plan: (
            int(plan["planning_rank"] or 999999),
            -float(plan["priority_score"]),
            str(plan["export_name"]),
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
