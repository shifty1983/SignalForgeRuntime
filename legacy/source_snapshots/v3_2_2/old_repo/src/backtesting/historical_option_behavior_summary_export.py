# src/backtesting/historical_option_behavior_summary_export.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SUMMARY_TYPE = "historical_option_behavior_summary"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

OPTION_BEHAVIOR_SLICE_FIELDS = {
    "option_behavior_state": "by_option_behavior_state",
    "option_strategy_generation_mode": "by_strategy_generation_mode",
    "option_liquidity_behavior": "by_option_liquidity_behavior",
    "option_greek_behavior": "by_option_greek_behavior",
}

REQUIRED_EVALUATION_REPORT_FIELDS = {
    "evaluation_status",
    "is_blocked",
    "summary",
    "evaluated_rows",
}


def export_historical_option_behavior_summary(
    evaluation_report: Mapping[str, Any],
    *,
    export_name: str = SUMMARY_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Export compact option-behavior historical slices from a historical strategy
    evaluation report.

    This is a pure review artifact. It does not attach outcomes, recompute
    historical returns, promote candidates, create operation records, write logs,
    audit results, route orders, submit orders, model fills, model slippage, or
    perform live execution.
    """

    metadata_dict = dict(metadata or {})

    validation_errors = _validate_evaluation_report_shape(evaluation_report)

    if validation_errors:
        return _blocked_export(
            export_name=export_name,
            metadata=metadata_dict,
            blocked_reasons=validation_errors,
        )

    evaluated_rows = [
        dict(row)
        for row in evaluation_report.get("evaluated_rows", [])
        if isinstance(row, Mapping)
    ]

    summary_source = dict(evaluation_report.get("summary", {}))
    by_option_behavior = _safe_mapping(evaluation_report.get("by_option_behavior"))
    by_option_behavior_asset_behavior_direction = _safe_mapping(
        evaluation_report.get("by_option_behavior_asset_behavior_direction")
    )

    option_behavior_context_count = _option_behavior_context_count(
        evaluated_rows=evaluated_rows,
        summary_source=summary_source,
    )

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if option_behavior_context_count == 0:
        warnings.append("no option behavior context found in historical evaluation")

    if bool(evaluation_report.get("is_blocked")):
        blocked_reasons.append("source historical strategy evaluation is blocked")

    option_behavior_slices = _build_option_behavior_slices(
        evaluated_rows=evaluated_rows,
        by_option_behavior=by_option_behavior,
    )

    combined_slices = _build_combined_option_behavior_slices(
        evaluated_rows=evaluated_rows,
        by_option_behavior_asset_behavior_direction=(
            by_option_behavior_asset_behavior_direction
        ),
    )

    state_summary = option_behavior_slices.get("by_option_behavior_state", {})

    ranking = _rank_option_behavior_state_slices(state_summary)

    has_blocked_context = _has_blocked_option_context(evaluated_rows)

    requires_review = bool(warnings or blocked_reasons or has_blocked_context)

    export_status = (
        "blocked"
        if blocked_reasons
        else "needs_review"
        if requires_review
        else "completed"
    )

    return {
        "export_status": export_status,
        "is_blocked": bool(blocked_reasons),
        "summary_type": SUMMARY_TYPE,
        "export_name": export_name,
        "option_behavior_summary": {
            "evaluation_status": evaluation_report.get("evaluation_status"),
            "source_is_blocked": bool(evaluation_report.get("is_blocked")),
            "historical_candidate_count": summary_source.get(
                "historical_candidate_count",
                len(evaluated_rows),
            ),
            "evaluated_candidate_count": summary_source.get(
                "evaluated_candidate_count",
                len(evaluated_rows),
            ),
            "accepted_candidate_count": summary_source.get(
                "accepted_candidate_count",
                _count_by_status(evaluated_rows, "accepted"),
            ),
            "rejected_candidate_count": summary_source.get(
                "rejected_candidate_count",
                _count_by_status(evaluated_rows, "rejected"),
            ),
            "option_behavior_context_count": option_behavior_context_count,
            "option_behavior_context_ratio": _ratio(
                option_behavior_context_count,
                summary_source.get("evaluated_candidate_count", len(evaluated_rows)),
            ),
            "option_behavior_state_count": len(state_summary),
        },
        "option_behavior_slices": option_behavior_slices,
        "option_behavior_asset_behavior_direction_slices": combined_slices,
        "option_behavior_ranking": ranking,
        "review_flags": {
            "has_option_behavior_context": option_behavior_context_count > 0,
            "has_blocked_option_context": has_blocked_context,
            "requires_review": requires_review,
            "has_warnings": bool(warnings),
            "has_blocked_reasons": bool(blocked_reasons),
            "best_option_behavior_state": ranking.get("best_option_behavior_state"),
            "worst_option_behavior_state": ranking.get("worst_option_behavior_state"),
        },
        "warnings": _unique_ordered(warnings),
        "blocked_reasons": _unique_ordered(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _blocked_export(
    *,
    export_name: str,
    metadata: dict[str, Any],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    return {
        "export_status": "blocked",
        "is_blocked": True,
        "summary_type": SUMMARY_TYPE,
        "export_name": export_name,
        "option_behavior_summary": {
            "evaluation_status": None,
            "source_is_blocked": True,
            "historical_candidate_count": 0,
            "evaluated_candidate_count": 0,
            "accepted_candidate_count": 0,
            "rejected_candidate_count": 0,
            "option_behavior_context_count": 0,
            "option_behavior_context_ratio": 0.0,
            "option_behavior_state_count": 0,
        },
        "option_behavior_slices": {},
        "option_behavior_asset_behavior_direction_slices": {},
        "option_behavior_ranking": {
            "best_option_behavior_state": None,
            "worst_option_behavior_state": None,
            "ranked_option_behavior_states": [],
        },
        "review_flags": {
            "has_option_behavior_context": False,
            "has_blocked_option_context": False,
            "requires_review": True,
            "has_warnings": False,
            "has_blocked_reasons": True,
            "best_option_behavior_state": None,
            "worst_option_behavior_state": None,
        },
        "warnings": [],
        "blocked_reasons": _unique_ordered(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata,
    }


def _validate_evaluation_report_shape(
    evaluation_report: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    if not isinstance(evaluation_report, Mapping):
        return ["evaluation_report must be a mapping"]

    missing_fields = sorted(
        REQUIRED_EVALUATION_REPORT_FIELDS - set(evaluation_report.keys())
    )

    if missing_fields:
        validation_errors.append(
            f"evaluation_report missing required fields: {missing_fields}"
        )

    if "summary" in evaluation_report and not isinstance(
        evaluation_report["summary"],
        Mapping,
    ):
        validation_errors.append("evaluation_report summary must be a mapping")

    if "evaluated_rows" in evaluation_report and not isinstance(
        evaluation_report["evaluated_rows"],
        list,
    ):
        validation_errors.append("evaluation_report evaluated_rows must be a list")

    if "is_blocked" in evaluation_report and not isinstance(
        evaluation_report["is_blocked"],
        bool,
    ):
        validation_errors.append("evaluation_report is_blocked must be a boolean")

    return validation_errors


def _build_option_behavior_slices(
    *,
    evaluated_rows: list[dict[str, Any]],
    by_option_behavior: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    slices: dict[str, dict[str, Any]] = {}

    for source_field, output_field in OPTION_BEHAVIOR_SLICE_FIELDS.items():
        source_summary = by_option_behavior.get(source_field)

        if isinstance(source_summary, Mapping):
            slices[output_field] = _normalize_summary_mapping(source_summary)
            continue

        rows_with_field = [
            row
            for row in evaluated_rows
            if row.get(source_field) is not None
        ]

        if rows_with_field:
            slices[output_field] = _summarize_by(rows_with_field, [source_field])

    return slices


def _build_combined_option_behavior_slices(
    *,
    evaluated_rows: list[dict[str, Any]],
    by_option_behavior_asset_behavior_direction: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}

    for source_field, output_field in OPTION_BEHAVIOR_SLICE_FIELDS.items():
        source_summary = by_option_behavior_asset_behavior_direction.get(source_field)

        if isinstance(source_summary, Mapping):
            combined[output_field] = _normalize_summary_mapping(source_summary)
            continue

        rows_with_field = [
            row
            for row in evaluated_rows
            if row.get(source_field) is not None
        ]

        if rows_with_field:
            combined[output_field] = _summarize_by(
                rows_with_field,
                [source_field, "asset_behavior", "direction"],
            )

    return combined


def _rank_option_behavior_state_slices(
    state_summary: Mapping[str, Any],
) -> dict[str, Any]:
    ranked_states = []

    for state, summary in state_summary.items():
        if not isinstance(summary, Mapping):
            continue

        ranked_states.append(
            {
                "option_behavior_state": state,
                "count": int(summary.get("count", 0)),
                "accepted_count": int(summary.get("accepted_count", 0)),
                "rejected_count": int(summary.get("rejected_count", 0)),
                "avg_direction_adjusted_outcome": _round(
                    summary.get("avg_direction_adjusted_outcome", 0.0)
                ),
                "hit_rate": _round(summary.get("hit_rate", 0.0)),
            }
        )

    ranked_states = sorted(
        ranked_states,
        key=lambda item: (
            -float(item["avg_direction_adjusted_outcome"]),
            -float(item["hit_rate"]),
            str(item["option_behavior_state"]),
        ),
    )

    best_state = (
        ranked_states[0]["option_behavior_state"]
        if ranked_states
        else None
    )

    worst_state = (
        ranked_states[-1]["option_behavior_state"]
        if ranked_states
        else None
    )

    return {
        "best_option_behavior_state": best_state,
        "worst_option_behavior_state": worst_state,
        "ranked_option_behavior_states": ranked_states,
    }


def _summarize_by(
    evaluated_rows: list[dict[str, Any]],
    group_fields: list[str],
) -> dict[str, dict[str, Any]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = {}

    for row in evaluated_rows:
        if any(field not in row for field in group_fields):
            continue

        group_key = "|".join(str(row[field]) for field in group_fields)
        grouped_rows.setdefault(group_key, []).append(row)

    return {
        group_key: _summarize_rows(rows)
        for group_key, rows in sorted(grouped_rows.items(), key=lambda item: item[0])
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "avg_forward_return": 0.0,
            "avg_direction_adjusted_outcome": 0.0,
            "total_direction_adjusted_outcome": 0.0,
            "hit_rate": 0.0,
        }

    forward_returns = [
        float(row.get("forward_return", 0.0))
        for row in rows
    ]
    adjusted_outcomes = [
        float(row.get("direction_adjusted_outcome", 0.0))
        for row in rows
    ]
    profitable_count = sum(1 for row in rows if bool(row.get("was_profitable")))

    return {
        "count": len(rows),
        "accepted_count": _count_by_status(rows, "accepted"),
        "rejected_count": _count_by_status(rows, "rejected"),
        "avg_forward_return": _round(sum(forward_returns) / len(forward_returns)),
        "avg_direction_adjusted_outcome": _round(
            sum(adjusted_outcomes) / len(adjusted_outcomes)
        ),
        "total_direction_adjusted_outcome": _round(sum(adjusted_outcomes)),
        "hit_rate": _round(profitable_count / len(rows)),
    }


def _normalize_summary_mapping(
    summary: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}

    for key, value in summary.items():
        if isinstance(value, Mapping):
            normalized[str(key)] = dict(value)

    return {
        key: normalized[key]
        for key in sorted(normalized)
    }


def _option_behavior_context_count(
    *,
    evaluated_rows: list[dict[str, Any]],
    summary_source: Mapping[str, Any],
) -> int:
    summary_count = summary_source.get("option_behavior_context_count")

    if isinstance(summary_count, int):
        return summary_count

    return sum(
        1
        for row in evaluated_rows
        if row.get("option_behavior_state") is not None
    )


def _has_blocked_option_context(
    evaluated_rows: list[dict[str, Any]],
) -> bool:
    for row in evaluated_rows:
        if row.get("option_behavior_blocked") is True:
            return True

        if row.get("option_behavior_state") == "constrained":
            return True

        constraints = row.get("option_strategy_generation_constraints")

        if isinstance(constraints, list) and "block_options_candidate_generation" in constraints:
            return True

    return False


def _count_by_status(
    rows: list[dict[str, Any]],
    status: str,
) -> int:
    return sum(1 for row in rows if row.get("candidate_status") == status)


def _safe_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    return {}


def _ratio(
    numerator: int,
    denominator: Any,
) -> float:
    try:
        denominator_value = int(denominator)
    except (TypeError, ValueError):
        denominator_value = 0

    if denominator_value <= 0:
        return 0.0

    return _round(numerator / denominator_value)


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)

    return unique_values


def _round(value: Any) -> float:
    return round(float(value), 10)
