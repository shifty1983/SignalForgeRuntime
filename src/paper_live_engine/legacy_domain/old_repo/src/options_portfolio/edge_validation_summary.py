from __future__ import annotations

from collections import defaultdict
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


def build_options_edge_validation_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build an edge-validation summary from manual options outcome records.

    This module summarizes manual outcome artifacts only. It does not create order intents,
    submit orders, model fills, or perform live execution.
    """

    if not isinstance(source, Mapping):
        return _blocked_summary("source must be a mapping")

    outcome_records = _outcome_records(source)
    if not outcome_records:
        return _blocked_summary("missing_options_manual_action_outcome_records")

    closed_outcomes: list[dict[str, Any]] = []
    open_outcomes: list[dict[str, Any]] = []
    pending_outcomes: list[dict[str, Any]] = []
    needs_review_outcomes: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    source_statuses: list[str] = []

    for record_index, record in enumerate(outcome_records):
        if not isinstance(record, Mapping):
            blocked_items.append({"reason": "outcome_record_is_not_mapping", "record_index": record_index})
            continue

        source_statuses.append(_normalized(record.get("status")))
        if record.get("artifact_type") not in (None, "options_manual_action_outcome_record"):
            blocked_items.append(
                {
                    "reason": "invalid_outcome_record_artifact_type",
                    "record_index": record_index,
                    "artifact_type": record.get("artifact_type"),
                }
            )

        closed_outcomes.extend(_tag_record_items(record, "closed_outcomes", record_index))
        open_outcomes.extend(_tag_record_items(record, "open_outcomes", record_index))
        pending_outcomes.extend(_tag_record_items(record, "pending_outcomes", record_index))
        needs_review_outcomes.extend(_tag_record_items(record, "needs_review_outcomes", record_index))
        blocked_items.extend(_tag_record_items(record, "blocked_items", record_index))

    all_items = closed_outcomes + open_outcomes + pending_outcomes + needs_review_outcomes
    for item in all_items:
        strategy = _normalized(item.get("strategy"))
        if strategy in UNDEFINED_RISK_STRATEGIES:
            blocked_items.append(
                {
                    "reason": "undefined_risk_strategy_blocked",
                    "strategy": strategy,
                    "symbol": item.get("symbol"),
                    "action_key": item.get("action_key"),
                    "record_index": item.get("record_index"),
                }
            )

    outcome_summary = _summary_counts(
        outcome_records=outcome_records,
        closed_outcomes=closed_outcomes,
        open_outcomes=open_outcomes,
        pending_outcomes=pending_outcomes,
        needs_review_outcomes=needs_review_outcomes,
        blocked_items=blocked_items,
    )

    status = _status(
        source_statuses=source_statuses,
        open_outcomes=open_outcomes,
        pending_outcomes=pending_outcomes,
        needs_review_outcomes=needs_review_outcomes,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_edge_validation_summary",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "summary_date": _string_or_none(source.get("summary_date")),
        "source_record_count": len(outcome_records),
        "outcome_summary": outcome_summary,
        "strategy_performance": _performance_by_key(closed_outcomes, key="strategy"),
        "symbol_performance": _performance_by_key(closed_outcomes, key="symbol"),
        "setup_family_performance": _performance_by_key(closed_outcomes, key="setup_family"),
        "open_outcomes": _sorted_items(open_outcomes),
        "pending_outcomes": _sorted_items(pending_outcomes),
        "needs_review_outcomes": _sorted_items(needs_review_outcomes),
        "blocked_items": _sorted_items(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _outcome_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if source.get("artifact_type") == "options_manual_action_outcome_record":
        return [source]

    for key in (
        "options_manual_action_outcome_records",
        "manual_action_outcome_records",
        "outcome_records",
    ):
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]

    value = source.get("options_manual_action_outcome_record")
    if isinstance(value, Mapping):
        return [value]

    return []


def _tag_record_items(record: Mapping[str, Any], key: str, record_index: int) -> list[dict[str, Any]]:
    items = _as_list(record.get(key))
    return [{**dict(item), "record_index": record_index} for item in items if isinstance(item, Mapping)]


def _summary_counts(
    *,
    outcome_records: Sequence[Mapping[str, Any]],
    closed_outcomes: Sequence[Mapping[str, Any]],
    open_outcomes: Sequence[Mapping[str, Any]],
    pending_outcomes: Sequence[Mapping[str, Any]],
    needs_review_outcomes: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "source_record_count": len(outcome_records),
        "closed_outcome_count": len(closed_outcomes),
        "open_outcome_count": len(open_outcomes),
        "pending_outcome_count": len(pending_outcomes),
        "needs_review_outcome_count": len(needs_review_outcomes),
        "blocked_item_count": len(blocked_items),
        "win_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "win"),
        "loss_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "loss"),
        "flat_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "flat"),
        "total_realized_pnl": _sum_numeric(item.get("realized_pnl") for item in closed_outcomes),
        "average_return_pct": _average_numeric(item.get("return_pct") for item in closed_outcomes),
        "average_days_held": _average_numeric(item.get("days_held") for item in closed_outcomes),
        "followed_plan_count": sum(
            1 for item in closed_outcomes if item.get("followed_plan") is True
        ),
    }


def _performance_by_key(items: Sequence[Mapping[str, Any]], *, key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        group_key = _string_or_none(item.get(key)) or "unknown"
        grouped[group_key].append(item)

    results: list[dict[str, Any]] = []
    for group_key, group_items in grouped.items():
        wins = sum(1 for item in group_items if item.get("outcome_label") == "win")
        losses = sum(1 for item in group_items if item.get("outcome_label") == "loss")
        flats = sum(1 for item in group_items if item.get("outcome_label") == "flat")
        total = len(group_items)
        results.append(
            {
                key: group_key,
                "closed_outcome_count": total,
                "win_count": wins,
                "loss_count": losses,
                "flat_count": flats,
                "win_rate": round(wins / total, 4) if total else None,
                "total_realized_pnl": _sum_numeric(item.get("realized_pnl") for item in group_items),
                "average_return_pct": _average_numeric(item.get("return_pct") for item in group_items),
                "average_days_held": _average_numeric(item.get("days_held") for item in group_items),
                "followed_plan_count": sum(
                    1 for item in group_items if item.get("followed_plan") is True
                ),
            }
        )

    return sorted(results, key=lambda item: str(item.get(key, "")))


def _status(
    *,
    source_statuses: Sequence[str],
    open_outcomes: Sequence[Mapping[str, Any]],
    pending_outcomes: Sequence[Mapping[str, Any]],
    needs_review_outcomes: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if blocked_items or "blocked" in source_statuses:
        return "blocked"
    if open_outcomes or pending_outcomes or needs_review_outcomes or "needs_review" in source_statuses:
        return "needs_review"
    return "ready"


def _blocked_summary(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_edge_validation_summary",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "source_record_count": 0,
        "outcome_summary": {
            "source_record_count": 0,
            "closed_outcome_count": 0,
            "open_outcome_count": 0,
            "pending_outcome_count": 0,
            "needs_review_outcome_count": 0,
            "blocked_item_count": 1,
            "win_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "total_realized_pnl": 0.0,
            "average_return_pct": None,
            "average_days_held": None,
            "followed_plan_count": 0,
        },
        "strategy_performance": [],
        "symbol_performance": [],
        "setup_family_performance": [],
        "open_outcomes": [],
        "pending_outcomes": [],
        "needs_review_outcomes": [],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _sorted_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("record_index", "")),
            str(item.get("symbol", "")),
            str(item.get("strategy", "")),
            str(item.get("action_key", "")),
            str(item.get("reason", "")),
        ),
    )


def _sum_numeric(values: Sequence[Any]) -> float:
    total = 0.0
    for value in values:
        numeric = _number_or_none(value)
        if numeric is not None:
            total += numeric
    return round(total, 4)


def _average_numeric(values: Sequence[Any]) -> float | None:
    numeric_values = [numeric for value in values if (numeric := _number_or_none(value)) is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 4)


def _number_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

