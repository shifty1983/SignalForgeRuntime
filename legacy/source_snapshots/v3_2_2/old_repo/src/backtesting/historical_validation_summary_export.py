# src/backtesting/historical_validation_summary_export.py

from __future__ import annotations

from typing import Any, Mapping


SUMMARY_TYPE = "historical_validation_summary"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_VALIDATION_RESULT_FIELDS = {
    "operation_type",
    "operation_name",
    "validation_status",
    "is_validated",
    "is_blocked",
    "matrix_result",
    "diagnostics_report",
    "blocked_reasons",
    "warnings",
    "summary",
}

REQUIRED_PROMOTION_RESULT_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "promotion_status",
    "is_promoted",
    "is_blocked",
    "promotion_result",
    "operation_record",
    "log_result",
    "audit_report",
    "health_report",
    "summary",
}


def export_historical_validation_summary(
    validation_result: Mapping[str, Any],
    promotion_operation_result: Mapping[str, Any],
    *,
    option_behavior_summary_export: Mapping[str, Any] | None = None,
    export_name: str = SUMMARY_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = [
        *_validate_validation_result_shape(validation_result),
        *_validate_promotion_operation_result_shape(promotion_operation_result),
        *_validate_option_behavior_summary_export_shape(
            option_behavior_summary_export
        ),
    ]

    if validation_errors:
        return {
            "export_status": "blocked",
            "is_blocked": True,
            "summary_type": SUMMARY_TYPE,
            "export_name": export_name,
            "validation_errors": validation_errors,
            "validation_summary": {},
            "promotion_summary": {},
            "edge_summary": {},
            "option_behavior_review": {},
            "review_flags": {
                "has_warnings": False,
                "has_blocked_reasons": True,
                "requires_review": True,
                "is_promoted": False,
                "is_validated": False,
            },
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "metadata": metadata_dict,
        }

    validation_summary_source = dict(validation_result.get("summary", {}))
    promotion_summary_source = dict(promotion_operation_result.get("summary", {}))
    diagnostics_report = dict(validation_result.get("diagnostics_report", {}))
    diagnostics_summary = dict(diagnostics_report.get("summary", {}))
    promotion_result = dict(promotion_operation_result.get("promotion_result", {}))
    promotion_metrics = dict(promotion_result.get("promotion_metrics", {}))
    option_behavior_review = _build_option_behavior_review(
        option_behavior_summary_export
    )
    
    warnings = _unique_ordered(
        [
            *[str(item) for item in validation_result.get("warnings", [])],
            *[str(item) for item in promotion_result.get("warnings", [])],
            *[
                str(item)
                for item in promotion_operation_result.get("health_report", {}).get(
                    "warnings",
                    [],
                )
            ],
            *[str(item) for item in option_behavior_review.get("warnings", [])],
        ]
    )

    blocked_reasons = _unique_ordered(
        [
            *[str(item) for item in validation_result.get("blocked_reasons", [])],
            *[str(item) for item in promotion_result.get("blocked_reasons", [])],
            *[
                str(item)
                for item in promotion_operation_result.get("health_report", {}).get(
                    "blocked_reasons",
                    [],
                )
            ],
            *[
                str(item)
                for item in option_behavior_review.get("blocked_reasons", [])
            ],
        ]
    )

    is_blocked = bool(
        validation_result.get("is_blocked")
        or promotion_operation_result.get("is_blocked")
        or blocked_reasons
    )

    is_promoted = bool(promotion_operation_result.get("is_promoted"))
    is_validated = bool(validation_result.get("is_validated"))
    requires_review = (
        not is_promoted
        or bool(warnings)
        or validation_result.get("validation_status") == "needs_review"
        or promotion_operation_result.get("promotion_status") == "needs_review"
        or bool(option_behavior_review.get("requires_review"))
    )

    export_status = "blocked" if is_blocked else "completed"

    return {
        "export_status": export_status,
        "is_blocked": is_blocked,
        "summary_type": SUMMARY_TYPE,
        "export_name": export_name,
        "validation_errors": [],
        "validation_summary": {
            "operation_name": validation_result.get("operation_name"),
            "validation_status": validation_result.get("validation_status"),
            "is_validated": is_validated,
            "is_blocked": bool(validation_result.get("is_blocked")),
            "candidate_count": validation_summary_source.get("candidate_count", 0),
            "price_row_count": validation_summary_source.get("price_row_count", 0),
            "forward_windows": list(
                validation_summary_source.get("forward_windows", [])
            ),
            "neutral_bands": list(validation_summary_source.get("neutral_bands", [])),
            "matrix_run_count": validation_summary_source.get("matrix_run_count", 0),
            "completed_run_count": validation_summary_source.get(
                "completed_run_count",
                0,
            ),
            "blocked_run_count": validation_summary_source.get(
                "blocked_run_count",
                0,
            ),
            "stable_run_count": validation_summary_source.get("stable_run_count", 0),
            "diagnostic_status": validation_summary_source.get("diagnostic_status"),
            "best_run": validation_summary_source.get("best_run"),
            "worst_run": validation_summary_source.get("worst_run"),
        },
        "promotion_summary": {
            "operation_name": promotion_operation_result.get("operation_name"),
            "runner_status": promotion_operation_result.get("runner_status"),
            "promotion_status": promotion_operation_result.get("promotion_status"),
            "is_promoted": is_promoted,
            "is_blocked": bool(promotion_operation_result.get("is_blocked")),
            "operation_status": promotion_summary_source.get("operation_status"),
            "audit_status": promotion_summary_source.get("audit_status"),
            "health_status": promotion_summary_source.get("health_status"),
            "log_status": promotion_summary_source.get("log_status"),
            "completed_run_ratio": promotion_metrics.get("completed_run_ratio", 0.0),
            "stable_run_ratio": promotion_metrics.get("stable_run_ratio", 0.0),
            "positive_edge_run_ratio": promotion_metrics.get(
                "positive_edge_run_ratio",
                0.0,
            ),
            "positive_hit_rate_edge_run_ratio": promotion_metrics.get(
                "positive_hit_rate_edge_run_ratio",
                0.0,
            ),
        },
        "edge_summary": {
            "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
                diagnostics_summary.get(
                    "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                    0.0,
                )
            ),
            "overall_avg_accepted_minus_rejected_hit_rate": _round(
                diagnostics_summary.get(
                    "overall_avg_accepted_minus_rejected_hit_rate",
                    0.0,
                )
            ),
            "positive_edge_run_count": validation_summary_source.get(
                "positive_edge_run_count",
                0,
            ),
            "positive_hit_rate_edge_run_count": validation_summary_source.get(
                "positive_hit_rate_edge_run_count",
                0,
            ),
            "best_run": diagnostics_summary.get("best_run"),
            "worst_run": diagnostics_summary.get("worst_run"),
            "by_forward_window": dict(diagnostics_report.get("by_forward_window", {})),
            "by_neutral_band": dict(diagnostics_report.get("by_neutral_band", {})),
        },
        "option_behavior_review": option_behavior_review,
        "review_flags": {
            "has_warnings": bool(warnings),
            "has_blocked_reasons": bool(blocked_reasons),
            "requires_review": requires_review,
            "is_promoted": is_promoted,
            "is_validated": is_validated,
            "warnings": warnings,
            "blocked_reasons": blocked_reasons,
            "has_option_behavior_context": bool(
                option_behavior_review.get("has_option_behavior_context")
            ),
            "has_blocked_option_context": bool(
                option_behavior_review.get("has_blocked_option_context")
            ),
            "best_option_behavior_state": option_behavior_review.get(
                "best_option_behavior_state"
            ),
            "worst_option_behavior_state": option_behavior_review.get(
                "worst_option_behavior_state"
            ),
            
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _validate_validation_result_shape(
    validation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_VALIDATION_RESULT_FIELDS - set(validation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"validation_result missing required fields: {missing_fields}"
        )

    validation_status = validation_result.get("validation_status")
    if validation_status is not None and validation_status not in {
        "validated",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"validation_result invalid validation_status: {validation_status}"
        )

    if "is_validated" in validation_result and not isinstance(
        validation_result["is_validated"],
        bool,
    ):
        validation_errors.append("validation_result is_validated must be a boolean")

    if "is_blocked" in validation_result and not isinstance(
        validation_result["is_blocked"],
        bool,
    ):
        validation_errors.append("validation_result is_blocked must be a boolean")

    if "summary" in validation_result and not isinstance(
        validation_result["summary"],
        Mapping,
    ):
        validation_errors.append("validation_result summary must be a mapping")

    if "diagnostics_report" in validation_result and not isinstance(
        validation_result["diagnostics_report"],
        Mapping,
    ):
        validation_errors.append(
            "validation_result diagnostics_report must be a mapping"
        )

    return validation_errors


def _validate_promotion_operation_result_shape(
    promotion_operation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_PROMOTION_RESULT_FIELDS - set(promotion_operation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"promotion_operation_result missing required fields: {missing_fields}"
        )

    promotion_status = promotion_operation_result.get("promotion_status")
    if promotion_status is not None and promotion_status not in {
        "promoted",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"promotion_operation_result invalid promotion_status: {promotion_status}"
        )

    runner_status = promotion_operation_result.get("runner_status")
    if runner_status is not None and runner_status not in {
        "completed",
        "blocked",
    }:
        validation_errors.append(
            f"promotion_operation_result invalid runner_status: {runner_status}"
        )

    if "is_promoted" in promotion_operation_result and not isinstance(
        promotion_operation_result["is_promoted"],
        bool,
    ):
        validation_errors.append(
            "promotion_operation_result is_promoted must be a boolean"
        )

    if "is_blocked" in promotion_operation_result and not isinstance(
        promotion_operation_result["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "promotion_operation_result is_blocked must be a boolean"
        )

    if "summary" in promotion_operation_result and not isinstance(
        promotion_operation_result["summary"],
        Mapping,
    ):
        validation_errors.append(
            "promotion_operation_result summary must be a mapping"
        )

    if "promotion_result" in promotion_operation_result and not isinstance(
        promotion_operation_result["promotion_result"],
        Mapping,
    ):
        validation_errors.append(
            "promotion_operation_result promotion_result must be a mapping"
        )

    return validation_errors

def _validate_option_behavior_summary_export_shape(
    option_behavior_summary_export: Mapping[str, Any] | None,
) -> list[str]:
    if option_behavior_summary_export is None:
        return []

    validation_errors: list[str] = []

    if not isinstance(option_behavior_summary_export, Mapping):
        return ["option_behavior_summary_export must be a mapping"]

    required_fields = {
        "export_status",
        "is_blocked",
        "summary_type",
        "option_behavior_summary",
        "option_behavior_ranking",
        "review_flags",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    }

    missing_fields = sorted(required_fields - set(option_behavior_summary_export.keys()))

    if missing_fields:
        validation_errors.append(
            f"option_behavior_summary_export missing required fields: {missing_fields}"
        )

    export_status = option_behavior_summary_export.get("export_status")
    if export_status is not None and export_status not in {
        "completed",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"option_behavior_summary_export invalid export_status: {export_status}"
        )

    summary_type = option_behavior_summary_export.get("summary_type")
    if summary_type is not None and summary_type != "historical_option_behavior_summary":
        validation_errors.append(
            f"option_behavior_summary_export invalid summary_type: {summary_type}"
        )

    if "is_blocked" in option_behavior_summary_export and not isinstance(
        option_behavior_summary_export["is_blocked"],
        bool,
    ):
        validation_errors.append(
            "option_behavior_summary_export is_blocked must be a boolean"
        )

    for mapping_field in [
        "option_behavior_summary",
        "option_behavior_ranking",
        "review_flags",
    ]:
        if mapping_field in option_behavior_summary_export and not isinstance(
            option_behavior_summary_export[mapping_field],
            Mapping,
        ):
            validation_errors.append(
                f"option_behavior_summary_export {mapping_field} must be a mapping"
            )

    for list_field in ["warnings", "blocked_reasons", "explicit_exclusions"]:
        if list_field in option_behavior_summary_export and not isinstance(
            option_behavior_summary_export[list_field],
            list,
        ):
            validation_errors.append(
                f"option_behavior_summary_export {list_field} must be a list"
            )

    explicit_exclusions = option_behavior_summary_export.get("explicit_exclusions")

    if explicit_exclusions is not None:
        normalized_actual_exclusions = [
            str(item)
            for item in explicit_exclusions
        ]

        normalized_required_exclusions = [
            str(item)
            for item in EXPLICIT_EXCLUSIONS
        ]

        if normalized_actual_exclusions != normalized_required_exclusions:
            validation_errors.append(
                "option_behavior_summary_export explicit_exclusions do not match required exclusions"
            )

    return validation_errors


def _build_option_behavior_review(
    option_behavior_summary_export: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if option_behavior_summary_export is None:
        return {
            "attached": False,
            "export_status": None,
            "is_blocked": False,
            "requires_review": False,
            "has_option_behavior_context": False,
            "has_blocked_option_context": False,
            "option_behavior_context_count": 0,
            "option_behavior_context_ratio": 0.0,
            "best_option_behavior_state": None,
            "worst_option_behavior_state": None,
            "ranked_option_behavior_states": [],
            "warnings": [],
            "blocked_reasons": [],
        }

    summary = dict(option_behavior_summary_export.get("option_behavior_summary", {}))
    ranking = dict(option_behavior_summary_export.get("option_behavior_ranking", {}))
    review_flags = dict(option_behavior_summary_export.get("review_flags", {}))

    warnings = [str(item) for item in option_behavior_summary_export.get("warnings", [])]
    blocked_reasons = [
        str(item) for item in option_behavior_summary_export.get("blocked_reasons", [])
    ]

    is_blocked = bool(
        option_behavior_summary_export.get("is_blocked")
        or option_behavior_summary_export.get("export_status") == "blocked"
        or blocked_reasons
    )

    requires_review = bool(
        is_blocked
        or option_behavior_summary_export.get("export_status") == "needs_review"
        or review_flags.get("requires_review")
        or warnings
        or review_flags.get("has_blocked_option_context")
    )

    return {
        "attached": True,
        "export_status": option_behavior_summary_export.get("export_status"),
        "is_blocked": is_blocked,
        "requires_review": requires_review,
        "has_option_behavior_context": bool(
            review_flags.get("has_option_behavior_context")
        ),
        "has_blocked_option_context": bool(
            review_flags.get("has_blocked_option_context")
        ),
        "option_behavior_context_count": int(
            summary.get("option_behavior_context_count", 0)
        ),
        "option_behavior_context_ratio": _round(
            summary.get("option_behavior_context_ratio", 0.0)
        ),
        "best_option_behavior_state": ranking.get("best_option_behavior_state"),
        "worst_option_behavior_state": ranking.get("worst_option_behavior_state"),
        "ranked_option_behavior_states": list(
            ranking.get("ranked_option_behavior_states", [])
        ),
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
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
