# src/backtesting/historical_research_final_review_summary.py

from __future__ import annotations

from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)


SUMMARY_TYPE = "historical_research_final_review_summary"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_REVIEW_ARTIFACT_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "review_artifact",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def build_historical_research_final_review_summary(
    review_artifact_operation_result: Mapping[str, Any],
    *,
    summary_name: str = SUMMARY_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_review_artifact_operation_result(
        review_artifact_operation_result
    )

    if validation_errors:
        return {
            "summary_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "summary_type": SUMMARY_TYPE,
            "summary_name": summary_name,
            "validation_errors": validation_errors,
            "ready_items": [],
            "needs_review_items": [],
            "blocked_items": [],
            "final_counts": {
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
            "matrix_metadata_summary": _build_matrix_metadata_summary([]),
            "exact_matrix_cell_ready_record_count": 0,
            "matrix_metadata_needs_review_record_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
            "recommended_next_step": "resolve_historical_research_final_review_summary_blockers",
        }

    review_artifact = dict(review_artifact_operation_result.get("review_artifact", {}))
    operation_record = dict(review_artifact_operation_result.get("operation_record", {}))
    health_report = dict(review_artifact_operation_result.get("health_report", {}))

    ready_items = _build_summary_items(
        review_artifact.get("ready_review", []),
        final_status="ready",
    )
    needs_review_items = _build_summary_items(
        review_artifact.get("needs_review", []),
        final_status="needs_review",
    )
    blocked_items = _build_summary_items(
        review_artifact.get("blocked_review", []),
        final_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in review_artifact.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in review_artifact.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    matrix_metadata_summary = _build_matrix_metadata_summary(
        [*ready_items, *needs_review_items, *blocked_items]
    )

    ready_count = len(ready_items)
    needs_review_count = len(needs_review_items)
    blocked_count = len(blocked_items)
    total_count = ready_count + needs_review_count + blocked_count

    is_blocked = bool(
        review_artifact_operation_result.get("is_blocked")
        or review_artifact.get("is_blocked")
        or blocked_reasons
    )

    if is_blocked:
        summary_status = "blocked"
    elif needs_review_count > 0 or warnings:
        summary_status = "needs_review"
    else:
        summary_status = "ready"

    return {
        "summary_status": summary_status,
        "is_ready": summary_status == "ready",
        "is_blocked": summary_status == "blocked",
        "summary_type": SUMMARY_TYPE,
        "summary_name": summary_name,
        "validation_errors": [],
        "ready_items": ready_items,
        "needs_review_items": needs_review_items,
        "blocked_items": blocked_items,
        "final_counts": {
            "ready": ready_count,
            "needs_review": needs_review_count,
            "blocked": blocked_count,
            "total": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "operation_name": review_artifact_operation_result.get("operation_name"),
            "runner_status": review_artifact_operation_result.get("runner_status"),
            "artifact_status": review_artifact.get("artifact_status"),
            "operation_status": review_artifact_operation_result.get("summary", {}).get(
                "operation_status"
            ),
            "audit_status": review_artifact_operation_result.get("summary", {}).get(
                "audit_status"
            ),
            "health_status": review_artifact_operation_result.get("summary", {}).get(
                "health_status"
            ),
            "log_status": review_artifact_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "artifact_summary": dict(review_artifact.get("artifact_summary", {})),
        },
        "metadata": metadata_dict,
        "matrix_metadata_summary": matrix_metadata_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_summary[
            "exact_matrix_cell_ready_record_count"
        ],
        "matrix_metadata_needs_review_record_count": matrix_metadata_summary[
            "needs_review_record_count"
        ],
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_summary[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "recommended_next_step": (
            "historical_research_final_review_matrix_edge_ready"
            if matrix_metadata_summary["ready_to_build_exact_matrix_edge_summary"]
            else "ensure_historical_final_review_items_include_matrix_metadata"
        ),
    }


def _validate_review_artifact_operation_result(
    review_artifact_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_REVIEW_ARTIFACT_OPERATION_FIELDS
        - set(review_artifact_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"review_artifact_operation_result missing required fields: {missing_fields}"
        )

    operation_type = review_artifact_operation_result.get("operation_type")
    if (
        operation_type is not None
        and operation_type != "historical_research_review_artifact"
    ):
        validation_errors.append(
            f"review_artifact_operation_result invalid operation_type: {operation_type}"
        )

    runner_status = review_artifact_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"review_artifact_operation_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in review_artifact_operation_result and not isinstance(
        review_artifact_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "review_artifact_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "review_artifact",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in review_artifact_operation_result and not isinstance(
            review_artifact_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"review_artifact_operation_result {mapping_field} must be a mapping"
            )

    return validation_errors


def _build_summary_items(
    review_items: list[Mapping[str, Any]],
    *,
    final_status: str,
) -> list[dict[str, Any]]:
    summary_items: list[dict[str, Any]] = []

    for item in review_items:
        summary_item = {
            "final_status": final_status,
            "review_status": item.get("review_status"),
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
            "symbol": item.get("symbol"),
            "horizon_days": item.get("horizon_days") or item.get("horizon"),
            "regime_state": item.get("regime_state") or item.get("regime"),
            "asset_behavior_state": item.get("asset_behavior_state")
            or item.get("asset_behavior"),
            "option_behavior_state": item.get("option_behavior_state")
            or item.get("option_behavior"),
            "strategy_id": item.get("strategy_id"),
            "strategy_family": item.get("strategy_family"),
            "warnings": list(item.get("warnings", [])),
            "blocked_reasons": list(item.get("blocked_reasons", [])),
            "metadata": dict(item.get("metadata", {})),
        }
        summary_items.append(
            stamp_matrix_metadata(
                summary_item,
                source_refs={
                    "source_stage": "historical_research_final_review_summary",
                    "export_name": item.get("export_name"),
                },
            )
        )

    return sorted(
        summary_items,
        key=lambda item: (
            int(item["planning_rank"] or 999999),
            -float(item["priority_score"]),
            str(item["export_name"]),
        ),
    )


def _build_matrix_metadata_summary(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(items)
    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_metadata_state_key": MATRIX_METADATA_STATE_KEY,
        "matrix_metadata_missing_fields_key": MATRIX_METADATA_MISSING_FIELDS_KEY,
        "matrix_metadata_source_refs_key": MATRIX_METADATA_SOURCE_REFS_KEY,
        "matrix_cell_key_key": MATRIX_CELL_KEY_KEY,
        "total_record_count": int(coverage.get("total_record_count", 0)),
        "exact_matrix_cell_ready_record_count": int(
            coverage.get("exact_matrix_cell_ready_record_count", 0)
        ),
        "needs_review_record_count": int(coverage.get("needs_review_record_count", 0)),
        "mapped_required_field_counts": dict(
            coverage.get("mapped_required_field_counts", {})
        ),
        "missing_required_field_counts": dict(
            coverage.get("missing_required_field_counts", {})
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            coverage.get("ready_to_build_exact_matrix_edge_summary")
        ),
    }


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
