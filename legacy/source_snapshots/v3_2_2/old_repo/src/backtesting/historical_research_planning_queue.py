# src/backtesting/historical_research_planning_queue.py

from __future__ import annotations

from typing import Any, Mapping


PLANNING_QUEUE_TYPE = "historical_research_planning_queue"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_HANDOFF_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "handoff_bundle",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_research_planning_queue(
    handoff_operation_result: Mapping[str, Any],
    *,
    planning_queue_name: str = PLANNING_QUEUE_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_handoff_operation_result(handoff_operation_result)

    if validation_errors:
        return {
            "planning_queue_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "planning_queue_type": PLANNING_QUEUE_TYPE,
            "planning_queue_name": planning_queue_name,
            "validation_errors": validation_errors,
            "priority_planning": [],
            "needs_review_planning": [],
            "blocked_planning": [],
            "planning_counts": {
                "priority": 0,
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

    handoff_bundle = dict(handoff_operation_result.get("handoff_bundle", {}))
    operation_record = dict(handoff_operation_result.get("operation_record", {}))
    health_report = dict(handoff_operation_result.get("health_report", {}))

    priority_planning = _build_planning_items(
        handoff_bundle.get("priority_research", []),
        planning_status="priority",
    )
    needs_review_planning = _build_planning_items(
        handoff_bundle.get("needs_review_research", []),
        planning_status="needs_review",
    )
    blocked_planning = _build_planning_items(
        handoff_bundle.get("blocked_research", []),
        planning_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in handoff_bundle.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in handoff_bundle.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    priority_count = len(priority_planning)
    needs_review_count = len(needs_review_planning)
    blocked_count = len(blocked_planning)
    total_count = priority_count + needs_review_count + blocked_count

    is_blocked = bool(
        handoff_operation_result.get("is_blocked")
        or handoff_bundle.get("is_blocked")
        or blocked_reasons
    )

    if is_blocked:
        planning_queue_status = "blocked"
    elif needs_review_count > 0 or warnings:
        planning_queue_status = "needs_review"
    else:
        planning_queue_status = "ready"

    return {
        "planning_queue_status": planning_queue_status,
        "is_ready": planning_queue_status == "ready",
        "is_blocked": planning_queue_status == "blocked",
        "planning_queue_type": PLANNING_QUEUE_TYPE,
        "planning_queue_name": planning_queue_name,
        "validation_errors": [],
        "priority_planning": priority_planning,
        "needs_review_planning": needs_review_planning,
        "blocked_planning": blocked_planning,
        "planning_counts": {
            "priority": priority_count,
            "needs_review": needs_review_count,
            "blocked": blocked_count,
            "total": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": handoff_operation_result.get("operation_name"),
            "runner_status": handoff_operation_result.get("runner_status"),
            "bundle_status": handoff_bundle.get("bundle_status"),
            "operation_status": handoff_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": handoff_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": handoff_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": handoff_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "handoff_summary": dict(handoff_bundle.get("handoff_summary", {})),
        },
        "metadata": metadata_dict,
    }


def _validate_handoff_operation_result(
    handoff_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_HANDOFF_OPERATION_FIELDS - set(handoff_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"handoff_operation_result missing required fields: {missing_fields}"
        )

    operation_type = handoff_operation_result.get("operation_type")
    if operation_type is not None and operation_type != "historical_research_handoff":
        validation_errors.append(
            f"handoff_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = handoff_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"handoff_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in handoff_operation_result and not isinstance(
        handoff_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "handoff_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "handoff_bundle",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in handoff_operation_result and not isinstance(
            handoff_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"handoff_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_planning_items(
    research_items: list[Mapping[str, Any]],
    *,
    planning_status: str,
) -> list[dict[str, Any]]:
    planning_items: list[dict[str, Any]] = []

    for item in research_items:
        priority_score = _round(item.get("priority_score", 0.0))

        planning_items.append(
            {
                "planning_status": planning_status,
                "planning_rank": item.get("priority_rank"),
                "research_action": _research_action_for(planning_status),
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
                "priority_score": priority_score,
                "option_behavior_review": dict(item.get("option_behavior_review", {})),
                "warnings": list(item.get("warnings", [])),
                "blocked_reasons": list(item.get("blocked_reasons", [])),
                "metadata": dict(item.get("metadata", {})),
            }
        )

    return sorted(
        planning_items,
        key=lambda item: (
            int(item["planning_rank"] or 999999),
            -float(item["priority_score"]),
            str(item["export_name"]),
        ),
    )


def _research_action_for(planning_status: str) -> str:
    if planning_status == "priority":
        return "prepare_deeper_research_plan"

    if planning_status == "needs_review":
        return "review_historical_validation_warnings"

    return "resolve_blocked_historical_validation"


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
