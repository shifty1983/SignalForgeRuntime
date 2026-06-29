# src/backtesting/historical_research_review_artifact.py

from __future__ import annotations

from typing import Any, Mapping


ARTIFACT_TYPE = "historical_research_review_artifact"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_EXPORT_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "research_plan_export",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_research_review_artifact(
    export_operation_result: Mapping[str, Any],
    *,
    artifact_name: str = ARTIFACT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_export_operation_result(export_operation_result)

    if validation_errors:
        return {
            "artifact_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "artifact_type": ARTIFACT_TYPE,
            "artifact_name": artifact_name,
            "validation_errors": validation_errors,
            "ready_review": [],
            "needs_review": [],
            "blocked_review": [],
            "artifact_summary": {
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

    research_plan_export = dict(export_operation_result.get("research_plan_export", {}))
    operation_record = dict(export_operation_result.get("operation_record", {}))
    health_report = dict(export_operation_result.get("health_report", {}))

    ready_review = _build_review_items(
        research_plan_export.get("ready_research", []),
        review_status="ready",
    )
    needs_review = _build_review_items(
        research_plan_export.get("needs_review_research", []),
        review_status="needs_review",
    )
    blocked_review = _build_review_items(
        research_plan_export.get("blocked_research", []),
        review_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in research_plan_export.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in research_plan_export.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    ready_count = len(ready_review)
    needs_review_count = len(needs_review)
    blocked_count = len(blocked_review)
    total_count = ready_count + needs_review_count + blocked_count

    is_blocked = bool(
        export_operation_result.get("is_blocked")
        or research_plan_export.get("is_blocked")
        or blocked_reasons
    )

    if is_blocked:
        artifact_status = "blocked"
    elif needs_review_count > 0 or warnings:
        artifact_status = "needs_review"
    else:
        artifact_status = "ready"

    return {
        "artifact_status": artifact_status,
        "is_ready": artifact_status == "ready",
        "is_blocked": artifact_status == "blocked",
        "artifact_type": ARTIFACT_TYPE,
        "artifact_name": artifact_name,
        "validation_errors": [],
        "ready_review": ready_review,
        "needs_review": needs_review,
        "blocked_review": blocked_review,
        "artifact_summary": {
            "ready_count": ready_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": export_operation_result.get("operation_name"),
            "runner_status": export_operation_result.get("runner_status"),
            "export_status": research_plan_export.get("export_status"),
            "operation_status": export_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": export_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": export_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": export_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "export_summary": dict(research_plan_export.get("export_summary", {})),
        },
        "metadata": metadata_dict,
    }


def _validate_export_operation_result(
    export_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_EXPORT_OPERATION_FIELDS - set(export_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"export_operation_result missing required fields: {missing_fields}"
        )

    operation_type = export_operation_result.get("operation_type")
    if (
        operation_type is not None
        and operation_type != "historical_research_plan_export"
    ):
        validation_errors.append(
            f"export_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = export_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"export_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in export_operation_result and not isinstance(
        export_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "export_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "research_plan_export",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in export_operation_result and not isinstance(
            export_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"export_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_review_items(
    research_items: list[Mapping[str, Any]],
    *,
    review_status: str,
) -> list[dict[str, Any]]:
    review_items: list[dict[str, Any]] = []

    for item in research_items:
        review_items.append(
            {
                "review_status": review_status,
                "export_status": item.get("export_status"),
                "plan_status": item.get("plan_status"),
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
        review_items,
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
