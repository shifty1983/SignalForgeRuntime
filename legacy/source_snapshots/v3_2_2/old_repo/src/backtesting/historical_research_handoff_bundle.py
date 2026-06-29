# src/backtesting/historical_research_handoff_bundle.py

from __future__ import annotations

from typing import Any, Mapping


BUNDLE_TYPE = "historical_research_handoff_bundle"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_PRIORITY_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "priority_report",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_research_handoff_bundle(
    priority_operation_result: Mapping[str, Any],
    *,
    bundle_name: str = BUNDLE_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_priority_operation_result(
        priority_operation_result
    )

    if validation_errors:
        return {
            "bundle_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "bundle_type": BUNDLE_TYPE,
            "bundle_name": bundle_name,
            "validation_errors": validation_errors,
            "priority_research": [],
            "needs_review_research": [],
            "blocked_research": [],
            "handoff_summary": {
                "priority_count": 0,
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

    priority_report = dict(priority_operation_result.get("priority_report", {}))
    health_report = dict(priority_operation_result.get("health_report", {}))
    operation_record = dict(priority_operation_result.get("operation_record", {}))

    priority_research = _build_research_items(
        priority_report.get("priority_candidates", []),
        handoff_status="priority",
    )
    needs_review_research = _build_research_items(
        priority_report.get("needs_review_candidates", []),
        handoff_status="needs_review",
    )
    blocked_research = _build_research_items(
        priority_report.get("blocked_candidates", []),
        handoff_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in priority_report.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )
    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in priority_report.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    priority_count = len(priority_research)
    needs_review_count = len(needs_review_research)
    blocked_count = len(blocked_research)
    total_count = priority_count + needs_review_count + blocked_count

    is_blocked = bool(
        priority_operation_result.get("is_blocked")
        or priority_report.get("is_blocked")
        or blocked_reasons
    )

    if is_blocked:
        bundle_status = "blocked"
    elif needs_review_count > 0 or warnings:
        bundle_status = "needs_review"
    else:
        bundle_status = "ready"

    return {
        "bundle_status": bundle_status,
        "is_ready": bundle_status == "ready",
        "is_blocked": bundle_status == "blocked",
        "bundle_type": BUNDLE_TYPE,
        "bundle_name": bundle_name,
        "validation_errors": [],
        "priority_research": priority_research,
        "needs_review_research": needs_review_research,
        "blocked_research": blocked_research,
        "handoff_summary": {
            "priority_count": priority_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": priority_operation_result.get("operation_name"),
            "runner_status": priority_operation_result.get("runner_status"),
            "report_status": priority_report.get("report_status"),
            "operation_status": priority_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": priority_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": priority_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": priority_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "priority_summary": dict(priority_report.get("priority_summary", {})),
        },
        "metadata": metadata_dict,
    }


def _validate_priority_operation_result(
    priority_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PRIORITY_OPERATION_FIELDS - set(priority_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"priority_operation_result missing required fields: {missing_fields}"
        )

    operation_type = priority_operation_result.get("operation_type")
    if operation_type is not None and operation_type != "historical_research_priority":
        validation_errors.append(
            f"priority_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = priority_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"priority_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in priority_operation_result and not isinstance(
        priority_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "priority_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "priority_report",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in priority_operation_result and not isinstance(
            priority_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"priority_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_research_items(
    candidates: list[Mapping[str, Any]],
    *,
    handoff_status: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for candidate in candidates:
        items.append(
            {
                "handoff_status": handoff_status,
                "priority_rank": candidate.get("priority_rank"),
                "priority_status": candidate.get("priority_status"),
                "export_name": candidate.get("export_name"),
                "validation_status": candidate.get("validation_status"),
                "promotion_status": candidate.get("promotion_status"),
                "is_validated": bool(candidate.get("is_validated")),
                "is_promoted": bool(candidate.get("is_promoted")),
                "requires_review": bool(candidate.get("requires_review")),
                "matrix_run_count": int(candidate.get("matrix_run_count", 0)),
                "completed_run_count": int(candidate.get("completed_run_count", 0)),
                "blocked_run_count": int(candidate.get("blocked_run_count", 0)),
                "stable_run_count": int(candidate.get("stable_run_count", 0)),
                "completed_run_ratio": _round(candidate.get("completed_run_ratio", 0.0)),
                "stable_run_ratio": _round(candidate.get("stable_run_ratio", 0.0)),
                "positive_edge_run_ratio": _round(
                    candidate.get("positive_edge_run_ratio", 0.0)
                ),
                "positive_hit_rate_edge_run_ratio": _round(
                    candidate.get("positive_hit_rate_edge_run_ratio", 0.0)
                ),
                "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
                    candidate.get(
                        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                        0.0,
                    )
                ),
                "overall_avg_accepted_minus_rejected_hit_rate": _round(
                    candidate.get(
                        "overall_avg_accepted_minus_rejected_hit_rate",
                        0.0,
                    )
                ),
                "priority_score": _round(candidate.get("priority_score", 0.0)),
                "option_behavior_review": dict(candidate.get("option_behavior_review", {})),
                "warnings": list(candidate.get("warnings", [])),
                "blocked_reasons": list(candidate.get("blocked_reasons", [])),
                "metadata": dict(candidate.get("metadata", {})),
            }
        )

    return sorted(
        items,
        key=lambda item: (
            int(item["priority_rank"] or 999999),
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
