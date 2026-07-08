from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

EXPLICIT_EXCLUSIONS = (
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
)

UNDEFINED_RISK_STRATEGIES = {
    "naked_short_call",
    "naked_short_put",
    "short_straddle",
    "short_strangle",
    "uncovered_ratio_spread",
    "uncovered_call",
}

DEFAULT_MIN_CLOSED_OUTCOMES = 2
DEFAULT_MIN_WIN_RATE = 0.5
DEFAULT_MIN_AVERAGE_RETURN_PCT = 0.0
DEFAULT_MIN_TOTAL_REALIZED_PNL = 0.0


def build_options_edge_validation_review(source: Mapping[str, Any]) -> dict[str, Any]:
    """Classify edge-validation summaries into actionable review conclusions.

    This is a review artifact only. It does not create order intents, submit orders,
    model fills, or perform live execution.
    """

    if not isinstance(source, Mapping):
        return _blocked_review("source must be a mapping")

    summaries = _summary_records(source)
    if not summaries:
        return _blocked_review("missing_options_edge_validation_summary")

    thresholds = _thresholds(source)
    blocked_items: list[dict[str, Any]] = []
    source_statuses: list[str] = []

    aggregate = _empty_aggregate()
    strategy_rows: list[dict[str, Any]] = []
    symbol_rows: list[dict[str, Any]] = []
    setup_family_rows: list[dict[str, Any]] = []

    for summary_index, summary in enumerate(summaries):
        if not isinstance(summary, Mapping):
            blocked_items.append(
                {"reason": "edge_validation_summary_is_not_mapping", "summary_index": summary_index}
            )
            continue

        source_statuses.append(_normalized(summary.get("status")))
        if summary.get("artifact_type") not in (None, "options_edge_validation_summary"):
            blocked_items.append(
                {
                    "reason": "invalid_edge_validation_summary_artifact_type",
                    "summary_index": summary_index,
                    "artifact_type": summary.get("artifact_type"),
                }
            )

        blocked_items.extend(
            _tag_blocked_items(summary.get("blocked_items"), summary_index=summary_index)
        )
        _merge_summary_counts(aggregate, _as_mapping(summary.get("outcome_summary")))
        strategy_rows.extend(_tag_group_rows(summary.get("strategy_performance"), summary_index))
        symbol_rows.extend(_tag_group_rows(summary.get("symbol_performance"), summary_index))
        setup_family_rows.extend(_tag_group_rows(summary.get("setup_family_performance"), summary_index))

    for row in strategy_rows:
        strategy = _normalized(row.get("strategy"))
        if strategy in UNDEFINED_RISK_STRATEGIES:
            blocked_items.append(
                {
                    "reason": "undefined_risk_strategy_blocked",
                    "strategy": strategy,
                    "summary_index": row.get("summary_index"),
                }
            )

    overall_review = _classify_performance(
        label="overall",
        row=aggregate,
        thresholds=thresholds,
    )
    strategy_reviews = _group_reviews(
        strategy_rows,
        key="strategy",
        thresholds=thresholds,
    )
    symbol_reviews = _group_reviews(
        symbol_rows,
        key="symbol",
        thresholds=thresholds,
    )
    setup_family_reviews = _group_reviews(
        setup_family_rows,
        key="setup_family",
        thresholds=thresholds,
    )

    review_actions = _review_actions(
        overall_review=overall_review,
        strategy_reviews=strategy_reviews,
        symbol_reviews=symbol_reviews,
        setup_family_reviews=setup_family_reviews,
        blocked_items=blocked_items,
    )

    status = _status(
        source_statuses=source_statuses,
        overall_review=overall_review,
        strategy_reviews=strategy_reviews,
        symbol_reviews=symbol_reviews,
        setup_family_reviews=setup_family_reviews,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_edge_validation_review",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "review_date": _string_or_none(source.get("review_date") or source.get("summary_date")),
        "source_summary_count": len(summaries),
        "review_thresholds": thresholds,
        "overall_review": overall_review,
        "strategy_reviews": strategy_reviews,
        "symbol_reviews": symbol_reviews,
        "setup_family_reviews": setup_family_reviews,
        "review_actions": review_actions,
        "blocked_items": _sorted_blocked_items(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _summary_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if source.get("artifact_type") == "options_edge_validation_summary":
        return [source]

    for key in (
        "options_edge_validation_summaries",
        "edge_validation_summaries",
        "summaries",
    ):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]

    value = source.get("options_edge_validation_summary")
    if isinstance(value, Mapping):
        return [value]

    return []


def _thresholds(source: Mapping[str, Any]) -> dict[str, Any]:
    raw = _as_mapping(source.get("review_thresholds") or source.get("thresholds"))
    return {
        "min_closed_outcomes": _safe_int(
            raw.get("min_closed_outcomes"), default=DEFAULT_MIN_CLOSED_OUTCOMES
        ),
        "min_win_rate": _safe_float(raw.get("min_win_rate"), default=DEFAULT_MIN_WIN_RATE),
        "min_average_return_pct": _safe_float(
            raw.get("min_average_return_pct"), default=DEFAULT_MIN_AVERAGE_RETURN_PCT
        ),
        "min_total_realized_pnl": _safe_float(
            raw.get("min_total_realized_pnl"), default=DEFAULT_MIN_TOTAL_REALIZED_PNL
        ),
    }


def _empty_aggregate() -> dict[str, Any]:
    return {
        "closed_outcome_count": 0,
        "open_outcome_count": 0,
        "pending_outcome_count": 0,
        "needs_review_outcome_count": 0,
        "blocked_item_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "flat_count": 0,
        "total_realized_pnl": 0.0,
        "average_return_pct": None,
        "average_days_held": None,
        "followed_plan_count": 0,
        "_weighted_return_sum": 0.0,
        "_weighted_return_count": 0,
        "_weighted_days_sum": 0.0,
        "_weighted_days_count": 0,
    }


def _merge_summary_counts(aggregate: dict[str, Any], summary: Mapping[str, Any]) -> None:
    closed_count = _safe_int(summary.get("closed_outcome_count"), default=0)
    aggregate["closed_outcome_count"] += closed_count
    aggregate["open_outcome_count"] += _safe_int(summary.get("open_outcome_count"), default=0)
    aggregate["pending_outcome_count"] += _safe_int(summary.get("pending_outcome_count"), default=0)
    aggregate["needs_review_outcome_count"] += _safe_int(
        summary.get("needs_review_outcome_count"), default=0
    )
    aggregate["blocked_item_count"] += _safe_int(summary.get("blocked_item_count"), default=0)
    aggregate["win_count"] += _safe_int(summary.get("win_count"), default=0)
    aggregate["loss_count"] += _safe_int(summary.get("loss_count"), default=0)
    aggregate["flat_count"] += _safe_int(summary.get("flat_count"), default=0)
    aggregate["total_realized_pnl"] = round(
        float(aggregate["total_realized_pnl"]) + _safe_float(summary.get("total_realized_pnl")),
        4,
    )

    average_return = _float_or_none(summary.get("average_return_pct"))
    if average_return is not None and closed_count > 0:
        aggregate["_weighted_return_sum"] += average_return * closed_count
        aggregate["_weighted_return_count"] += closed_count

    average_days = _float_or_none(summary.get("average_days_held"))
    if average_days is not None and closed_count > 0:
        aggregate["_weighted_days_sum"] += average_days * closed_count
        aggregate["_weighted_days_count"] += closed_count

    aggregate["followed_plan_count"] += _safe_int(summary.get("followed_plan_count"), default=0)
    aggregate["average_return_pct"] = _weighted_average(
        aggregate["_weighted_return_sum"], aggregate["_weighted_return_count"]
    )
    aggregate["average_days_held"] = _weighted_average(
        aggregate["_weighted_days_sum"], aggregate["_weighted_days_count"]
    )


def _classify_performance(
    *, label: str, row: Mapping[str, Any], thresholds: Mapping[str, Any]
) -> dict[str, Any]:
    closed_count = _safe_int(row.get("closed_outcome_count"), default=0)
    wins = _safe_int(row.get("win_count"), default=0)
    losses = _safe_int(row.get("loss_count"), default=0)
    flats = _safe_int(row.get("flat_count"), default=0)
    total_pnl = _safe_float(row.get("total_realized_pnl"))
    average_return = _float_or_none(row.get("average_return_pct"))
    average_days = _float_or_none(row.get("average_days_held"))
    followed_plan_count = _safe_int(row.get("followed_plan_count"), default=0)
    win_rate = round(wins / closed_count, 4) if closed_count else None

    min_closed = _safe_int(thresholds.get("min_closed_outcomes"), default=DEFAULT_MIN_CLOSED_OUTCOMES)
    min_win_rate = _safe_float(thresholds.get("min_win_rate"), default=DEFAULT_MIN_WIN_RATE)
    min_average_return = _safe_float(
        thresholds.get("min_average_return_pct"), default=DEFAULT_MIN_AVERAGE_RETURN_PCT
    )
    min_total_pnl = _safe_float(
        thresholds.get("min_total_realized_pnl"), default=DEFAULT_MIN_TOTAL_REALIZED_PNL
    )

    if closed_count < min_closed:
        classification = "needs_more_data"
        review_status = "needs_review"
        reason = "closed_outcome_count_below_threshold"
    elif total_pnl < min_total_pnl or (average_return is not None and average_return < min_average_return):
        classification = "underperforming"
        review_status = "needs_review"
        reason = "performance_below_return_threshold"
    elif win_rate is not None and win_rate < min_win_rate:
        classification = "underperforming"
        review_status = "needs_review"
        reason = "win_rate_below_threshold"
    else:
        classification = "edge_supported"
        review_status = "ready"
        reason = "performance_meets_review_thresholds"

    return {
        "label": label,
        "review_status": review_status,
        "edge_classification": classification,
        "reason": reason,
        "closed_outcome_count": closed_count,
        "win_count": wins,
        "loss_count": losses,
        "flat_count": flats,
        "win_rate": win_rate,
        "total_realized_pnl": round(total_pnl, 4),
        "average_return_pct": average_return,
        "average_days_held": average_days,
        "followed_plan_count": followed_plan_count,
    }


def _group_reviews(
    rows: Sequence[Mapping[str, Any]], *, key: str, thresholds: Mapping[str, Any]
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for row in rows:
        label = _string_or_none(row.get(key)) or "unknown"
        review = _classify_performance(label=label, row=row, thresholds=thresholds)
        reviews.append({key: label, **review})
    return sorted(reviews, key=lambda item: str(item.get(key, "")))


def _review_actions(
    *,
    overall_review: Mapping[str, Any],
    strategy_reviews: Sequence[Mapping[str, Any]],
    symbol_reviews: Sequence[Mapping[str, Any]],
    setup_family_reviews: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if blocked_items:
        actions.append(
            {
                "action": "review_blocked_edge_validation_inputs",
                "priority": "high",
                "reason": "blocked_items_present",
                "requires_manual_approval": True,
            }
        )

    if overall_review.get("edge_classification") == "edge_supported":
        actions.append(
            {
                "action": "continue_tracking_supported_edge",
                "priority": "normal",
                "reason": "overall_edge_supported",
                "requires_manual_approval": True,
            }
        )
    elif overall_review.get("edge_classification") == "needs_more_data":
        actions.append(
            {
                "action": "collect_more_outcome_data",
                "priority": "normal",
                "reason": "sample_size_below_threshold",
                "requires_manual_approval": True,
            }
        )
    else:
        actions.append(
            {
                "action": "review_underperforming_options_edge",
                "priority": "high",
                "reason": str(overall_review.get("reason")),
                "requires_manual_approval": True,
            }
        )

    for group_name, reviews in (
        ("strategy", strategy_reviews),
        ("symbol", symbol_reviews),
        ("setup_family", setup_family_reviews),
    ):
        for review in reviews:
            if review.get("edge_classification") in {"underperforming", "needs_more_data"}:
                actions.append(
                    {
                        "action": f"review_{group_name}_edge",
                        group_name: review.get(group_name),
                        "priority": "high"
                        if review.get("edge_classification") == "underperforming"
                        else "normal",
                        "reason": review.get("reason"),
                        "requires_manual_approval": True,
                    }
                )

    return sorted(
        actions,
        key=lambda item: (
            0 if item.get("priority") == "high" else 1,
            str(item.get("action", "")),
            str(item.get("strategy") or item.get("symbol") or item.get("setup_family") or ""),
        ),
    )


def _status(
    *,
    source_statuses: Sequence[str],
    overall_review: Mapping[str, Any],
    strategy_reviews: Sequence[Mapping[str, Any]],
    symbol_reviews: Sequence[Mapping[str, Any]],
    setup_family_reviews: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items or "blocked" in source_statuses:
        return "blocked"
    if overall_review.get("review_status") == "needs_review":
        return "needs_review"
    if any(review.get("review_status") == "needs_review" for review in strategy_reviews):
        return "needs_review"
    if any(review.get("review_status") == "needs_review" for review in symbol_reviews):
        return "needs_review"
    if any(review.get("review_status") == "needs_review" for review in setup_family_reviews):
        return "needs_review"
    if "needs_review" in source_statuses:
        return "needs_review"
    return "ready"


def _blocked_review(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_edge_validation_review",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "source_summary_count": 0,
        "review_thresholds": {
            "min_closed_outcomes": DEFAULT_MIN_CLOSED_OUTCOMES,
            "min_win_rate": DEFAULT_MIN_WIN_RATE,
            "min_average_return_pct": DEFAULT_MIN_AVERAGE_RETURN_PCT,
            "min_total_realized_pnl": DEFAULT_MIN_TOTAL_REALIZED_PNL,
        },
        "overall_review": {
            "label": "overall",
            "review_status": "blocked",
            "edge_classification": "blocked",
            "reason": reason,
            "closed_outcome_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "win_rate": None,
            "total_realized_pnl": 0.0,
            "average_return_pct": None,
            "average_days_held": None,
            "followed_plan_count": 0,
        },
        "strategy_reviews": [],
        "symbol_reviews": [],
        "setup_family_reviews": [],
        "review_actions": [
            {
                "action": "review_blocked_edge_validation_inputs",
                "priority": "high",
                "reason": reason,
                "requires_manual_approval": True,
            }
        ],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _tag_blocked_items(value: Any, *, summary_index: int) -> list[dict[str, Any]]:
    return [
        {**dict(item), "summary_index": summary_index}
        for item in _as_list(value)
        if isinstance(item, Mapping)
    ]


def _tag_group_rows(value: Any, summary_index: int) -> list[dict[str, Any]]:
    return [
        {**dict(item), "summary_index": summary_index}
        for item in _as_list(value)
        if isinstance(item, Mapping)
    ]


def _sorted_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("summary_index", "")),
            str(item.get("strategy", "")),
            str(item.get("symbol", "")),
            str(item.get("reason", "")),
        ),
    )


def _weighted_average(total: float, count: int) -> float | None:
    if count <= 0:
        return None
    return round(total / count, 4)


def _safe_int(value: Any, *, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    numeric = _float_or_none(value)
    return default if numeric is None else numeric


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")

