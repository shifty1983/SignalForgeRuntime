# src/backtesting/historical_research_plan_export.py

from __future__ import annotations

from typing import Any, Mapping


EXPORT_TYPE = "historical_research_plan_export"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_PLAN_SNAPSHOT_FIELDS = {
    "snapshot_status",
    "is_ready",
    "is_blocked",
    "snapshot_type",
    "snapshot_name",
    "validation_errors",
    "ready_research_plans",
    "needs_review_research_plans",
    "blocked_research_plans",
    "plan_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}


def export_historical_research_plan(
    plan_snapshot: Mapping[str, Any],
    *,
    export_name: str = EXPORT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_plan_snapshot(plan_snapshot)

    if validation_errors:
        return {
            "export_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "export_type": EXPORT_TYPE,
            "export_name": export_name,
            "validation_errors": validation_errors,
            "ready_research": [],
            "needs_review_research": [],
            "blocked_research": [],
            "export_summary": {
                "ready_count": 0,
                "needs_review_count": 0,
                "blocked_count": 0,
                "total_count": 0,
            },
            "warnings": [],
            "blocked_reasons": validation_errors,
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "source_summary": {},
            "metadata": metadata_dict,
        }

    ready_research = _build_export_items(
        plan_snapshot.get("ready_research_plans", []),
        export_status="ready",
    )
    needs_review_research = _build_export_items(
        plan_snapshot.get("needs_review_research_plans", []),
        export_status="needs_review",
    )
    blocked_research = _build_export_items(
        plan_snapshot.get("blocked_research_plans", []),
        export_status="blocked",
    )

    warnings = _unique_ordered(
        [str(item) for item in plan_snapshot.get("warnings", [])]
    )
    blocked_reasons = _unique_ordered(
        [str(item) for item in plan_snapshot.get("blocked_reasons", [])]
    )

    ready_count = len(ready_research)
    needs_review_count = len(needs_review_research)
    blocked_count = len(blocked_research)
    total_count = ready_count + needs_review_count + blocked_count

    is_blocked = bool(plan_snapshot.get("is_blocked") or blocked_reasons)

    if is_blocked:
        export_status = "blocked"
    elif needs_review_count > 0 or warnings:
        export_status = "needs_review"
    else:
        export_status = "ready"

    return {
        "export_status": export_status,
        "is_ready": export_status == "ready",
        "is_blocked": export_status == "blocked",
        "export_type": EXPORT_TYPE,
        "export_name": export_name,
        "validation_errors": [],
        "ready_research": ready_research,
        "needs_review_research": needs_review_research,
        "blocked_research": blocked_research,
        "export_summary": {
            "ready_count": ready_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "snapshot_name": plan_snapshot.get("snapshot_name"),
            "snapshot_status": plan_snapshot.get("snapshot_status"),
            "is_ready": bool(plan_snapshot.get("is_ready")),
            "is_blocked": bool(plan_snapshot.get("is_blocked")),
            "plan_counts": dict(plan_snapshot.get("plan_counts", {})),
            "source_operation_summary": dict(
                plan_snapshot.get("source_summary", {})
            ),
        },
        "metadata": metadata_dict,
    }


def _validate_plan_snapshot(plan_snapshot: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_PLAN_SNAPSHOT_FIELDS - set(plan_snapshot.keys()))
    if missing_fields:
        validation_errors.append(
            f"plan_snapshot missing required fields: {missing_fields}"
        )

    snapshot_status = plan_snapshot.get("snapshot_status")
    if snapshot_status is not None and snapshot_status not in {
        "ready",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"plan_snapshot invalid snapshot_status: {snapshot_status}"
        )

    if "is_ready" in plan_snapshot and not isinstance(
        plan_snapshot["is_ready"],
        bool,
    ):
        validation_errors.append("plan_snapshot is_ready must be a boolean")

    if "is_blocked" in plan_snapshot and not isinstance(
        plan_snapshot["is_blocked"],
        bool,
    ):
        validation_errors.append("plan_snapshot is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "ready_research_plans",
        "needs_review_research_plans",
        "blocked_research_plans",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in plan_snapshot and not isinstance(
            plan_snapshot[list_field],
            list,
        ):
            validation_errors.append(f"plan_snapshot {list_field} must be a list")

    for mapping_field in ["plan_counts", "source_summary", "metadata"]:
        if mapping_field in plan_snapshot and not isinstance(
            plan_snapshot[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"plan_snapshot {mapping_field} must be a mapping"
            )

    explicit_exclusions = plan_snapshot.get("explicit_exclusions")
    if explicit_exclusions is not None and list(explicit_exclusions) != EXPLICIT_EXCLUSIONS:
        validation_errors.append(
            "plan_snapshot explicit_exclusions do not match required exclusions"
        )

    return validation_errors


def _build_export_items(
    research_plans: list[Mapping[str, Any]],
    *,
    export_status: str,
) -> list[dict[str, Any]]:
    export_items: list[dict[str, Any]] = []

    for plan in research_plans:
        export_items.append(
            {
                "export_status": export_status,
                "plan_status": plan.get("plan_status"),
                "planning_status": plan.get("planning_status"),
                "planning_rank": plan.get("planning_rank"),
                "research_action": plan.get("research_action"),
                "handoff_status": plan.get("handoff_status"),
                "priority_status": plan.get("priority_status"),
                "export_name": plan.get("export_name"),
                "validation_status": plan.get("validation_status"),
                "promotion_status": plan.get("promotion_status"),
                "is_validated": bool(plan.get("is_validated")),
                "is_promoted": bool(plan.get("is_promoted")),
                "requires_review": bool(plan.get("requires_review")),
                "matrix_run_count": int(plan.get("matrix_run_count", 0)),
                "completed_run_count": int(plan.get("completed_run_count", 0)),
                "blocked_run_count": int(plan.get("blocked_run_count", 0)),
                "stable_run_count": int(plan.get("stable_run_count", 0)),
                "completed_run_ratio": _round(plan.get("completed_run_ratio", 0.0)),
                "stable_run_ratio": _round(plan.get("stable_run_ratio", 0.0)),
                "positive_edge_run_ratio": _round(
                    plan.get("positive_edge_run_ratio", 0.0)
                ),
                "positive_hit_rate_edge_run_ratio": _round(
                    plan.get("positive_hit_rate_edge_run_ratio", 0.0)
                ),
                "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
                    plan.get(
                        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                        0.0,
                    )
                ),
                "overall_avg_accepted_minus_rejected_hit_rate": _round(
                    plan.get(
                        "overall_avg_accepted_minus_rejected_hit_rate",
                        0.0,
                    )
                ),
                "priority_score": _round(plan.get("priority_score", 0.0)),
                "option_behavior_review": dict(plan.get("option_behavior_review", {})),
                "warnings": list(plan.get("warnings", [])),
                "blocked_reasons": list(plan.get("blocked_reasons", [])),
                "metadata": dict(plan.get("metadata", {})),
            }
        )

    return sorted(
        export_items,
        key=lambda item: (
            int(item["planning_rank"] or 999999),
            -float(item["priority_score"]),
            str(item["export_name"]),
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
