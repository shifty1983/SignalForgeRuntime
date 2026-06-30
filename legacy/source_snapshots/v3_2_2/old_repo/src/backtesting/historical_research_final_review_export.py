# src/backtesting/historical_research_final_review_export.py

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


EXPORT_TYPE = "historical_research_final_review_export"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_FINAL_REVIEW_SUMMARY_OPERATION_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "final_review_summary",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}

REQUIRED_FINAL_REVIEW_SUMMARY_FIELDS = {
    "summary_status",
    "is_ready",
    "is_blocked",
    "summary_type",
    "summary_name",
    "validation_errors",
    "ready_items",
    "needs_review_items",
    "blocked_items",
    "final_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
    "source_summary",
    "metadata",
}


def export_historical_research_final_review(
    final_review_summary_operation_result: Mapping[str, Any],
    *,
    export_name: str = EXPORT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_final_review_summary_operation_result(
        final_review_summary_operation_result
    )

    if validation_errors:
        return {
            "export_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "export_type": EXPORT_TYPE,
            "export_name": export_name,
            "validation_errors": validation_errors,
            "ready_final_review": [],
            "needs_review_final_review": [],
            "blocked_final_review": [],
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
            "matrix_metadata_summary": _build_matrix_metadata_summary([]),
            "exact_matrix_cell_ready_record_count": 0,
            "matrix_metadata_needs_review_record_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
            "recommended_next_step": "resolve_historical_research_final_review_export_blockers",
        }

    final_review_summary = dict(
        final_review_summary_operation_result.get("final_review_summary", {})
    )
    operation_record = dict(
        final_review_summary_operation_result.get("operation_record", {})
    )
    health_report = dict(final_review_summary_operation_result.get("health_report", {}))

    ready_final_review = _build_export_items(
        final_review_summary.get("ready_items", []),
        final_export_status="ready",
    )
    needs_review_final_review = _build_export_items(
        final_review_summary.get("needs_review_items", []),
        final_export_status="needs_review",
    )
    blocked_final_review = _build_export_items(
        final_review_summary.get("blocked_items", []),
        final_export_status="blocked",
    )

    warnings = _unique_ordered(
        [
            *[str(item) for item in final_review_summary.get("warnings", [])],
            *[str(item) for item in operation_record.get("warnings", [])],
            *[str(item) for item in health_report.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in final_review_summary.get("blocked_reasons", [])],
            *[str(item) for item in operation_record.get("blocked_reasons", [])],
            *[str(item) for item in health_report.get("blocked_reasons", [])],
        ]
    )

    matrix_metadata_summary = _build_matrix_metadata_summary(
        [*ready_final_review, *needs_review_final_review, *blocked_final_review]
    )

    ready_count = len(ready_final_review)
    needs_review_count = len(needs_review_final_review)
    blocked_count = len(blocked_final_review)
    total_count = ready_count + needs_review_count + blocked_count

    is_blocked = bool(
        final_review_summary_operation_result.get("is_blocked")
        or final_review_summary.get("is_blocked")
        or blocked_reasons
    )

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
        "ready_final_review": ready_final_review,
        "needs_review_final_review": needs_review_final_review,
        "blocked_final_review": blocked_final_review,
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
            "operation_name": final_review_summary_operation_result.get("operation_name"),
            "runner_status": final_review_summary_operation_result.get("runner_status"),
            "summary_status": final_review_summary.get("summary_status"),
            "operation_status": final_review_summary_operation_result.get(
                "summary", {}
            ).get("operation_status"),
            "audit_status": final_review_summary_operation_result.get(
                "summary", {}
            ).get("audit_status"),
            "health_status": final_review_summary_operation_result.get(
                "summary", {}
            ).get("health_status"),
            "log_status": final_review_summary_operation_result.get("summary", {}).get(
                "log_status"
            ),
            "final_counts": dict(final_review_summary.get("final_counts", {})),
            "source_summary": dict(final_review_summary.get("source_summary", {})),
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
            "historical_research_final_review_exact_matrix_edge_ready"
            if matrix_metadata_summary["ready_to_build_exact_matrix_edge_summary"]
            else "ensure_historical_final_review_export_items_include_matrix_metadata"
        ),
    }


def _validate_final_review_summary_operation_result(
    final_review_summary_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_FINAL_REVIEW_SUMMARY_OPERATION_FIELDS
        - set(final_review_summary_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            "final_review_summary_operation_result missing required fields: "
            f"{missing_fields}"
        )

    operation_type = final_review_summary_operation_result.get("operation_type")
    if (
        operation_type is not None
        and operation_type != "historical_research_final_review_summary"
    ):
        validation_errors.append(
            "final_review_summary_operation_result invalid operation_type: "
            f"{operation_type}"
        )

    runner_status = final_review_summary_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            "final_review_summary_operation_result invalid runner_status: "
            f"{runner_status}"
        )

    if "is_blocked" in final_review_summary_operation_result and not isinstance(
        final_review_summary_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "final_review_summary_operation_result is_blocked must be a boolean"
        )

    for mapping_field in [
        "final_review_summary",
        "operation_record",
        "log_result",
        "audit_report",
        "health_report",
        "summary",
    ]:
        if mapping_field in final_review_summary_operation_result and not isinstance(
            final_review_summary_operation_result[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                "final_review_summary_operation_result "
                f"{mapping_field} must be a mapping"
            )

    final_review_summary = final_review_summary_operation_result.get(
        "final_review_summary"
    )
    if isinstance(final_review_summary, Mapping):
        validation_errors.extend(_validate_final_review_summary(final_review_summary))

    return validation_errors


def _validate_final_review_summary(
    final_review_summary: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_FINAL_REVIEW_SUMMARY_FIELDS - set(final_review_summary.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"final_review_summary missing required fields: {missing_fields}"
        )

    summary_status = final_review_summary.get("summary_status")
    if summary_status is not None and summary_status not in {
        "ready",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"final_review_summary invalid summary_status: {summary_status}"
        )

    if "is_ready" in final_review_summary and not isinstance(
        final_review_summary["is_ready"],
        bool,
    ):
        validation_errors.append("final_review_summary is_ready must be a boolean")

    if "is_blocked" in final_review_summary and not isinstance(
        final_review_summary["is_blocked"],
        bool,
    ):
        validation_errors.append("final_review_summary is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "ready_items",
        "needs_review_items",
        "blocked_items",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in final_review_summary and not isinstance(
            final_review_summary[list_field],
            list,
        ):
            validation_errors.append(
                f"final_review_summary {list_field} must be a list"
            )

    for mapping_field in ["final_counts", "source_summary", "metadata"]:
        if mapping_field in final_review_summary and not isinstance(
            final_review_summary[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"final_review_summary {mapping_field} must be a mapping"
            )

    explicit_exclusions = final_review_summary.get("explicit_exclusions")
    if explicit_exclusions is not None and list(explicit_exclusions) != EXPLICIT_EXCLUSIONS:
        validation_errors.append(
            "final_review_summary explicit_exclusions do not match required exclusions"
        )

    return validation_errors


def _build_export_items(
    final_review_items: list[Mapping[str, Any]],
    *,
    final_export_status: str,
) -> list[dict[str, Any]]:
    export_items: list[dict[str, Any]] = []

    for item in final_review_items:
        export_item = {
            "final_export_status": final_export_status,
            "final_status": item.get("final_status"),
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
        export_items.append(
            stamp_matrix_metadata(
                export_item,
                source_refs={
                    "source_stage": "historical_research_final_review_export",
                    "export_name": item.get("export_name"),
                },
            )
        )

    return sorted(
        export_items,
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
