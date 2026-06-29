# src/backtesting/historical_strategy_evaluation.py

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable, Mapping


REQUIRED_HISTORICAL_CANDIDATE_FIELDS = {
    "candidate_id",
    "symbol",
    "as_of_date",
    "direction",
    "candidate_status",
    "regime",
    "asset_behavior",
    "forward_return",
}

VALID_DIRECTIONS = {"long", "short", "neutral"}
VALID_CANDIDATE_STATUSES = {"accepted", "rejected"}

BLOCKED_LIVE_OR_BROKER_FIELDS = {
    "broker",
    "broker_id",
    "broker_account",
    "broker_order_id",
    "order_id",
    "order_submission",
    "order_submitted",
    "order_status",
    "fill",
    "fill_price",
    "filled_quantity",
    "route",
    "routing",
    "live_execution",
    "live_order",
    "slippage",
    "slippage_model",
}

OPTION_BEHAVIOR_CONTEXT_FIELDS = (
    "option_behavior_status",
    "option_behavior_state",
    "option_behavior_score",
    "option_strategy_generation_mode",
    "option_strategy_generation_constraints",
    "option_behavior_warnings",
    "option_behavior_blocked_reasons",
    "option_iv_behavior",
    "option_vol_premium_behavior",
    "option_liquidity_behavior",
    "option_skew_behavior",
    "option_term_structure_behavior",
    "option_greek_behavior",
    "option_behavior_blocked",
    "option_behavior_needs_review",
)

OPTION_BEHAVIOR_SUMMARY_FIELDS = (
    "option_behavior_state",
    "option_strategy_generation_mode",
    "option_liquidity_behavior",
    "option_greek_behavior",
)


def validate_historical_candidate_rows(
    historical_candidate_rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    rows = list(historical_candidate_rows)
    validation_errors: list[str] = []

    if not rows:
        return ["historical_candidate_rows must not be empty"]

    seen_candidate_ids: set[str] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            validation_errors.append(f"historical_candidate_rows[{index}] must be a mapping")
            continue

        missing_fields = sorted(REQUIRED_HISTORICAL_CANDIDATE_FIELDS - set(row.keys()))
        if missing_fields:
            validation_errors.append(
                f"historical_candidate_rows[{index}] missing required fields: {missing_fields}"
            )

        blocked_fields = sorted(BLOCKED_LIVE_OR_BROKER_FIELDS & set(row.keys()))
        if blocked_fields:
            validation_errors.append(
                f"historical_candidate_rows[{index}] contains blocked broker/live fields: {blocked_fields}"
            )

        candidate_id = row.get("candidate_id")
        if candidate_id in seen_candidate_ids:
            validation_errors.append(
                f"historical_candidate_rows[{index}] duplicate candidate_id: {candidate_id}"
            )
        elif candidate_id is not None:
            seen_candidate_ids.add(str(candidate_id))

        direction = row.get("direction")
        if direction is not None and direction not in VALID_DIRECTIONS:
            validation_errors.append(
                f"historical_candidate_rows[{index}] invalid direction: {direction}"
            )

        candidate_status = row.get("candidate_status")
        if candidate_status is not None and candidate_status not in VALID_CANDIDATE_STATUSES:
            validation_errors.append(
                f"historical_candidate_rows[{index}] invalid candidate_status: {candidate_status}"
            )

        forward_return = row.get("forward_return")
        if forward_return is not None:
            try:
                numeric_forward_return = float(forward_return)
            except (TypeError, ValueError):
                validation_errors.append(
                    f"historical_candidate_rows[{index}] forward_return must be numeric"
                )
                continue

            if numeric_forward_return != numeric_forward_return:
                validation_errors.append(
                    f"historical_candidate_rows[{index}] forward_return must not be NaN"
                )

    return validation_errors


def compute_direction_adjusted_outcome(
    *,
    direction: str,
    forward_return: float,
    neutral_band: float = 0.01,
) -> float:
    if direction == "long":
        return forward_return

    if direction == "short":
        return -forward_return

    if direction == "neutral":
        return neutral_band - abs(forward_return)

    raise ValueError(f"Unsupported direction: {direction}")


def evaluate_historical_strategy_candidates(
    historical_candidate_rows: Iterable[Mapping[str, Any]],
    *,
    neutral_band: float = 0.01,
) -> dict[str, Any]:
    rows = [dict(row) for row in historical_candidate_rows]

    validation_errors = validate_historical_candidate_rows(rows)

    if neutral_band < 0:
        validation_errors.append("neutral_band must be non-negative")

    if validation_errors:
        return {
            "evaluation_status": "blocked",
            "is_blocked": True,
            "validation_errors": validation_errors,
            "evaluated_rows": [],
            "accepted_vs_rejected": {},
            "by_regime": {},
            "by_asset_behavior": {},
            "by_direction": {},
            "by_regime_asset_behavior_direction": {},
            "by_option_behavior": {},
            "by_option_behavior_asset_behavior_direction": {},
            "summary": {
                "historical_candidate_count": len(rows),
                "evaluated_candidate_count": 0,
            },
        }

    evaluated_rows = []

    for row in rows:
        forward_return = float(row["forward_return"])
        direction = row["direction"]

        adjusted_outcome = compute_direction_adjusted_outcome(
            direction=direction,
            forward_return=forward_return,
            neutral_band=neutral_band,
        )

        evaluated_row = {
            "candidate_id": row["candidate_id"],
            "symbol": row["symbol"],
            "as_of_date": row["as_of_date"],
            "direction": direction,
            "candidate_status": row["candidate_status"],
            "regime": row["regime"],
            "asset_behavior": row["asset_behavior"],
            "forward_return": _round(forward_return),
            "direction_adjusted_outcome": _round(adjusted_outcome),
            "was_profitable": adjusted_outcome > 0,
        }

        evaluated_row.update(_option_behavior_context_from_row(row))

        evaluated_rows.append(evaluated_row)

    evaluated_rows = sorted(
        evaluated_rows,
        key=lambda item: (
            str(item["as_of_date"]),
            str(item["symbol"]),
            str(item["candidate_id"]),
        ),
    )

    accepted_rows = [
        row for row in evaluated_rows if row["candidate_status"] == "accepted"
    ]
    rejected_rows = [
        row for row in evaluated_rows if row["candidate_status"] == "rejected"
    ]

    accepted_summary = _summarize_rows(accepted_rows)
    rejected_summary = _summarize_rows(rejected_rows)

    report = {
        "evaluation_status": "completed",
        "is_blocked": False,
        "validation_errors": [],
        "evaluated_rows": evaluated_rows,
        "accepted_vs_rejected": {
            "accepted": accepted_summary,
            "rejected": rejected_summary,
            "accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
                accepted_summary["avg_direction_adjusted_outcome"]
                - rejected_summary["avg_direction_adjusted_outcome"]
            ),
            "accepted_minus_rejected_hit_rate": _round(
                accepted_summary["hit_rate"] - rejected_summary["hit_rate"]
            ),
        },
        "by_regime": _summarize_by(evaluated_rows, ["regime"]),
        "by_asset_behavior": _summarize_by(evaluated_rows, ["asset_behavior"]),
        "by_direction": _summarize_by(evaluated_rows, ["direction"]),
        "by_regime_asset_behavior_direction": _summarize_by(
            evaluated_rows,
            ["regime", "asset_behavior", "direction"],
        ),
        "by_option_behavior": _summarize_optional_option_behavior_fields(
            evaluated_rows
        ),
        "by_option_behavior_asset_behavior_direction": (
            _summarize_optional_combined_option_behavior_fields(evaluated_rows)
        ),
        "summary": {
            "historical_candidate_count": len(rows),
            "evaluated_candidate_count": len(evaluated_rows),
            "accepted_candidate_count": len(accepted_rows),
            "rejected_candidate_count": len(rejected_rows),
            "overall": _summarize_rows(evaluated_rows),
            "neutral_band": _round(neutral_band),
            "option_behavior_context_count": sum(
                1 for row in evaluated_rows if "option_behavior_state" in row
            ),
        },
    }

    return report

def _option_behavior_context_from_row(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        field_name: row[field_name]
        for field_name in OPTION_BEHAVIOR_CONTEXT_FIELDS
        if field_name in row
    }


def _summarize_optional_option_behavior_fields(
    evaluated_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}

    for field_name in OPTION_BEHAVIOR_SUMMARY_FIELDS:
        rows_with_field = [
            row
            for row in evaluated_rows
            if field_name in row and row[field_name] is not None
        ]

        if rows_with_field:
            summaries[field_name] = _summarize_by(rows_with_field, [field_name])

    return summaries


def _summarize_optional_combined_option_behavior_fields(
    evaluated_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}

    for field_name in OPTION_BEHAVIOR_SUMMARY_FIELDS:
        rows_with_field = [
            row
            for row in evaluated_rows
            if field_name in row and row[field_name] is not None
        ]

        if rows_with_field:
            summaries[field_name] = _summarize_by(
                rows_with_field,
                [field_name, "asset_behavior", "direction"],
            )

    return summaries

def _summarize_by(
    evaluated_rows: list[dict[str, Any]],
    group_fields: list[str],
) -> dict[str, dict[str, Any]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in evaluated_rows:
        group_key = "|".join(str(row[field]) for field in group_fields)
        grouped_rows[group_key].append(row)

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

    adjusted_outcomes = [float(row["direction_adjusted_outcome"]) for row in rows]
    forward_returns = [float(row["forward_return"]) for row in rows]
    profitable_count = sum(1 for row in rows if row["was_profitable"])

    return {
        "count": len(rows),
        "accepted_count": sum(
            1 for row in rows if row["candidate_status"] == "accepted"
        ),
        "rejected_count": sum(
            1 for row in rows if row["candidate_status"] == "rejected"
        ),
        "avg_forward_return": _round(mean(forward_returns)),
        "avg_direction_adjusted_outcome": _round(mean(adjusted_outcomes)),
        "total_direction_adjusted_outcome": _round(sum(adjusted_outcomes)),
        "hit_rate": _round(profitable_count / len(rows)),
    }


def _round(value: float) -> float:
    return round(float(value), 10)
