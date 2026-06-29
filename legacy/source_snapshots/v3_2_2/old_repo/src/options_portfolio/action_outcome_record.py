from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from src.options_strategy.catalog import is_defined_risk_strategy


EXPLICIT_EXCLUSIONS: tuple[str, ...] = (
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

CLOSED_OUTCOME_STATUSES = {
    "closed",
    "complete",
    "completed",
    "exited",
    "profit_taken",
    "stopped",
    "expired",
    "assigned_manually_reviewed",
}
OPEN_OUTCOME_STATUSES = {"open", "still_open", "holding", "monitoring"}
PENDING_OUTCOME_STATUSES = {"pending", "not_yet_known", "unknown", "awaiting_outcome"}
REVIEW_OUTCOME_STATUSES = {"needs_review", "review", "requires_review"}
BLOCKED_OUTCOME_STATUSES = {"block", "blocked", "invalid"}

WIN_LABELS = {"win", "winner", "profit", "gain", "positive"}
LOSS_LABELS = {"loss", "loser", "negative"}
FLAT_LABELS = {"flat", "scratch", "breakeven", "break_even"}


def build_options_manual_action_outcome_record(source: Mapping[str, Any]) -> dict[str, Any]:
    """Record outcomes after approved actions were handled manually.

    This artifact is for analysis and edge validation. It never creates order
    intents, routes orders, calls broker APIs, syncs broker order state, models
    fills, performs live execution, or creates automatic close/roll/defense
    orders.
    """

    if not isinstance(source, Mapping):
        return _blocked_result(reason="source must be a mapping")

    execution_record = _mapping(
        source.get("options_manual_execution_record")
        or source.get("manual_execution_record")
        or source.get("execution_record")
    )
    if not execution_record:
        return _blocked_result(
            outcome_recorded_at=_string_or_none(source.get("outcome_recorded_at")),
            reason="missing_options_manual_execution_record",
        )

    outcome_recorded_at = _string_or_none(
        source.get("outcome_recorded_at")
        or source.get("recorded_at")
        or execution_record.get("execution_recorded_at")
    )
    recorder = _string_or_none(source.get("recorder") or execution_record.get("recorder"))

    completed_actions = _list_of_mappings(execution_record.get("completed_manual_actions"))
    skipped_actions = _list_of_mappings(execution_record.get("skipped_manual_actions"))
    deferred_actions = _list_of_mappings(execution_record.get("deferred_manual_actions"))
    pending_actions = _list_of_mappings(execution_record.get("pending_manual_actions"))
    needs_review_source_actions = _list_of_mappings(execution_record.get("needs_review_actions"))
    source_blocked_items = _list_of_mappings(execution_record.get("blocked_items"))
    outcome_records = _outcome_records(source.get("outcome_records") or source.get("manual_outcome_records"))

    closed_outcomes: list[dict[str, Any]] = []
    open_outcomes: list[dict[str, Any]] = []
    pending_outcomes: list[dict[str, Any]] = []
    needs_review_outcomes: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    used_outcome_indexes: set[int] = set()

    for completed_index, action in enumerate(completed_actions):
        keyed_action = _with_action_key(action, completed_index=completed_index)
        strategy = _string_or_none(keyed_action.get("strategy"))

        if strategy and not is_defined_risk_strategy(strategy):
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason="undefined_risk_strategy_blocked",
                    recorder=recorder,
                    outcome_recorded_at=outcome_recorded_at,
                )
            )
            continue

        matched_index, outcome = _find_outcome_record(keyed_action, outcome_records)
        if matched_index is not None:
            used_outcome_indexes.add(matched_index)

        if outcome is None:
            pending_outcomes.append(
                _outcome_item(
                    keyed_action,
                    recorder=recorder,
                    outcome_recorded_at=outcome_recorded_at,
                    outcome_status="pending_outcome",
                    outcome_note="no outcome record provided",
                )
            )
            continue

        normalized_status = _normalize_status(
            outcome.get("outcome_status")
            or outcome.get("status")
            or outcome.get("result_status")
        )
        outcome_item = _outcome_item_from_record(
            keyed_action,
            outcome,
            recorder=recorder,
            outcome_recorded_at=outcome_recorded_at,
            normalized_status=normalized_status,
        )

        if normalized_status in CLOSED_OUTCOME_STATUSES:
            closed_outcomes.append({**outcome_item, "outcome_status": "closed_outcome_recorded"})
        elif normalized_status in OPEN_OUTCOME_STATUSES:
            open_outcomes.append({**outcome_item, "outcome_status": "open_outcome_monitoring"})
        elif normalized_status in PENDING_OUTCOME_STATUSES:
            pending_outcomes.append({**outcome_item, "outcome_status": "pending_outcome"})
        elif normalized_status in BLOCKED_OUTCOME_STATUSES:
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason=_string_or_none(outcome.get("reason") or outcome.get("note")) or "manual_outcome_blocked",
                    recorder=recorder,
                    outcome_recorded_at=outcome_recorded_at,
                )
            )
        else:
            needs_review_outcomes.append({**outcome_item, "outcome_status": "needs_review"})

    for skipped_index, action in enumerate(skipped_actions):
        pending_outcomes.append(
            _outcome_item(
                _with_action_key(action, skipped_index=skipped_index),
                recorder=recorder,
                outcome_recorded_at=outcome_recorded_at,
                outcome_status="skipped_manual_action_no_trade_outcome",
                outcome_note="manual action was skipped",
            )
        )

    for deferred_index, action in enumerate(deferred_actions):
        pending_outcomes.append(
            _outcome_item(
                _with_action_key(action, deferred_index=deferred_index),
                recorder=recorder,
                outcome_recorded_at=outcome_recorded_at,
                outcome_status="deferred_manual_action_pending",
                outcome_note="manual action was deferred",
            )
        )

    for pending_index, action in enumerate(pending_actions):
        pending_outcomes.append(
            _outcome_item(
                _with_action_key(action, pending_index=pending_index),
                recorder=recorder,
                outcome_recorded_at=outcome_recorded_at,
                outcome_status="pending_manual_action",
                outcome_note="manual action is still pending",
            )
        )

    for review_index, action in enumerate(needs_review_source_actions):
        needs_review_outcomes.append(
            _outcome_item(
                _with_action_key(action, review_index=review_index),
                recorder=recorder,
                outcome_recorded_at=outcome_recorded_at,
                outcome_status="needs_review",
                outcome_note="source manual execution action needs review",
            )
        )

    for outcome_index, outcome in enumerate(outcome_records):
        if outcome_index in used_outcome_indexes:
            continue
        blocked_items.append(
            {
                "reason": "unmatched_manual_outcome_record",
                "outcome_record_index": outcome_index,
                "action_key": _string_or_none(outcome.get("action_key") or outcome.get("action_id")),
                "queue_index": outcome.get("queue_index"),
                "approved_index": outcome.get("approved_index"),
                "completed_index": outcome.get("completed_index"),
                "recorder": recorder,
                "outcome_recorded_at": outcome_recorded_at,
            }
        )

    blocked_items.extend(
        _blocked_item(item, reason=_string_or_none(item.get("reason")) or "source_blocked_item")
        for item in source_blocked_items
    )

    status = _status(
        execution_status=_string_or_none(execution_record.get("status")),
        completed_actions=completed_actions,
        closed_outcomes=closed_outcomes,
        open_outcomes=open_outcomes,
        pending_outcomes=pending_outcomes,
        needs_review_outcomes=needs_review_outcomes,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "options_manual_action_outcome_record",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "queue_date": _string_or_none(source.get("queue_date") or execution_record.get("queue_date")),
        "reviewed_at": _string_or_none(source.get("reviewed_at") or execution_record.get("reviewed_at")),
        "execution_recorded_at": _string_or_none(
            source.get("execution_recorded_at") or execution_record.get("execution_recorded_at")
        ),
        "outcome_recorded_at": outcome_recorded_at,
        "recorder": recorder,
        "closed_outcomes": _sort_outcome_items(closed_outcomes),
        "open_outcomes": _sort_outcome_items(open_outcomes),
        "pending_outcomes": _sort_outcome_items(pending_outcomes),
        "needs_review_outcomes": _sort_outcome_items(needs_review_outcomes),
        "blocked_items": _sort_blocked_items(blocked_items),
        "outcome_summary": {
            "source_completed_action_count": len(completed_actions),
            "manual_outcome_record_count": len(outcome_records),
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
        },
        "edge_validation_inputs": {
            "closed_action_count": len(closed_outcomes),
            "open_action_count": len(open_outcomes),
            "pending_action_count": len(pending_outcomes),
            "win_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "win"),
            "loss_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "loss"),
            "flat_count": sum(1 for item in closed_outcomes if item.get("outcome_label") == "flat"),
            "total_realized_pnl": _sum_numeric(item.get("realized_pnl") for item in closed_outcomes),
            "average_return_pct": _average_numeric(item.get("return_pct") for item in closed_outcomes),
            "average_days_held": _average_numeric(item.get("days_held") for item in closed_outcomes),
            "followed_plan_count": sum(
                1 for item in closed_outcomes if item.get("followed_plan") is True
            )
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _outcome_item_from_record(
    action: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    recorder: str | None,
    outcome_recorded_at: str | None,
    normalized_status: str,
) -> dict[str, Any]:
    realized_pnl = _number_or_none(outcome.get("realized_pnl") or outcome.get("pnl"))
    return_pct = _number_or_none(outcome.get("return_pct") or outcome.get("return_percent"))
    label = _outcome_label(
        outcome.get("outcome_label")
        or outcome.get("result")
        or outcome.get("classification"),
        realized_pnl=realized_pnl,
        return_pct=return_pct,
    )
    return _outcome_item(
        action,
        recorder=recorder,
        outcome_recorded_at=_string_or_none(outcome.get("outcome_recorded_at") or outcome_recorded_at),
        outcome_status=normalized_status,
        outcome_note=_string_or_none(outcome.get("note") or outcome.get("comment") or outcome.get("reason")),
        outcome_reference=_string_or_none(
            outcome.get("outcome_reference") or outcome.get("external_reference") or outcome.get("reference")
        ),
        exit_reason=_string_or_none(outcome.get("exit_reason")),
        realized_pnl=realized_pnl,
        return_pct=return_pct,
        outcome_label=label,
        days_held=_number_or_none(outcome.get("days_held") or outcome.get("holding_period_days")),
        max_adverse_excursion=_number_or_none(outcome.get("max_adverse_excursion")),
        max_favorable_excursion=_number_or_none(outcome.get("max_favorable_excursion")),
        followed_plan=_bool_or_none(outcome.get("followed_plan")),
    )


def _outcome_item(
    action: Mapping[str, Any],
    *,
    recorder: str | None,
    outcome_recorded_at: str | None,
    outcome_status: str,
    outcome_note: str | None = None,
    outcome_reference: str | None = None,
    exit_reason: str | None = None,
    realized_pnl: float | None = None,
    return_pct: float | None = None,
    outcome_label: str | None = None,
    days_held: float | None = None,
    max_adverse_excursion: float | None = None,
    max_favorable_excursion: float | None = None,
    followed_plan: bool | None = None,
) -> dict[str, Any]:
    return {
        "action_key": _string_or_none(action.get("action_key")) or _stable_action_key(action),
        "queue_index": action.get("queue_index"),
        "approved_index": action.get("approved_index"),
        "completed_index": action.get("completed_index"),
        "symbol": _string_or_none(action.get("symbol")),
        "strategy": _string_or_none(action.get("strategy")),
        "action": _string_or_none(action.get("action") or action.get("recommended_action")),
        "action_source": _string_or_none(action.get("action_source")),
        "urgency": _string_or_none(action.get("urgency")),
        "recorder": recorder,
        "outcome_recorded_at": outcome_recorded_at,
        "outcome_status": outcome_status,
        "outcome_note": outcome_note,
        "outcome_reference": outcome_reference,
        "exit_reason": exit_reason,
        "realized_pnl": realized_pnl,
        "return_pct": return_pct,
        "outcome_label": outcome_label,
        "days_held": days_held,
        "max_adverse_excursion": max_adverse_excursion,
        "max_favorable_excursion": max_favorable_excursion,
        "followed_plan": followed_plan,
        "manual_only": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _edge_validation_inputs(
    closed_outcomes: Sequence[Mapping[str, Any]],
    open_outcomes: Sequence[Mapping[str, Any]],
    pending_outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "closed_action_count": len(closed_outcomes),
        "open_action_count": len(open_outcomes),
        "pending_action_count": len(pending_outcomes),
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


def _status(
    *,
    execution_status: str | None,
    completed_actions: Sequence[Mapping[str, Any]],
    closed_outcomes: Sequence[Mapping[str, Any]],
    open_outcomes: Sequence[Mapping[str, Any]],
    pending_outcomes: Sequence[Mapping[str, Any]],
    needs_review_outcomes: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> str:
    if execution_status == "blocked" and not completed_actions:
        return "blocked"
    if blocked_items and not (closed_outcomes or open_outcomes or pending_outcomes):
        return "blocked"
    if needs_review_outcomes or blocked_items:
        return "needs_review"
    if closed_outcomes or open_outcomes or pending_outcomes:
        return "ready"
    return "needs_review"


def _find_outcome_record(
    action: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> tuple[int | None, Mapping[str, Any] | None]:
    action_key = _string_or_none(action.get("action_key"))
    queue_index = action.get("queue_index")
    approved_index = action.get("approved_index")
    completed_index = action.get("completed_index")

    for index, record in enumerate(records):
        record_key = _string_or_none(record.get("action_key") or record.get("action_id"))
        if action_key and record_key and action_key == record_key:
            return index, record
        if completed_index is not None and record.get("completed_index") == completed_index:
            return index, record
        if approved_index is not None and record.get("approved_index") == approved_index:
            return index, record
        if queue_index is not None and record.get("queue_index") == queue_index:
            return index, record
    return None, None


def _with_action_key(action: Mapping[str, Any], **extra: int) -> dict[str, Any]:
    item = dict(action)
    for key, value in extra.items():
        item.setdefault(key, value)
    item.setdefault("action_key", _stable_action_key(item))
    return item


def _stable_action_key(action: Mapping[str, Any]) -> str:
    parts = [
        str(action.get("queue_index", "")),
        str(action.get("approved_index", "")),
        str(action.get("completed_index", "")),
        str(action.get("symbol", "")),
        str(action.get("strategy", "")),
        str(action.get("action") or action.get("recommended_action") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _blocked_result(
    *,
    reason: str,
    outcome_recorded_at: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "options_manual_action_outcome_record",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "outcome_recorded_at": outcome_recorded_at,
        "closed_outcomes": [],
        "open_outcomes": [],
        "pending_outcomes": [],
        "needs_review_outcomes": [],
        "blocked_items": [{"reason": reason}],
        "outcome_summary": {
            "source_completed_action_count": 0,
            "manual_outcome_record_count": 0,
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
        },
        "edge_validation_inputs": {"closed_action_count": 0, "open_action_count": 0, "pending_action_count": 0, "closed_actions": []},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _blocked_item(
    item: Mapping[str, Any], *, reason: str, recorder: str | None = None, outcome_recorded_at: str | None = None
) -> dict[str, Any]:
    return {
        "reason": reason,
        "action_key": _string_or_none(item.get("action_key")) or _stable_action_key(item),
        "queue_index": item.get("queue_index"),
        "approved_index": item.get("approved_index"),
        "completed_index": item.get("completed_index"),
        "symbol": _string_or_none(item.get("symbol")),
        "strategy": _string_or_none(item.get("strategy")),
        "action": _string_or_none(item.get("action") or item.get("recommended_action")),
        "recorder": recorder,
        "outcome_recorded_at": outcome_recorded_at,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
    }


def _outcome_label(value: Any, *, realized_pnl: float | None, return_pct: float | None) -> str | None:
    normalized = _normalize_status(value)
    if normalized in WIN_LABELS:
        return "win"
    if normalized in LOSS_LABELS:
        return "loss"
    if normalized in FLAT_LABELS:
        return "flat"
    metric = realized_pnl if realized_pnl is not None else return_pct
    if metric is None:
        return None
    if metric > 0:
        return "win"
    if metric < 0:
        return "loss"
    return "flat"


def _sort_outcome_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: (str(item.get("symbol") or ""), str(item.get("strategy") or ""), str(item.get("action_key") or "")))]


def _sort_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: (str(item.get("reason") or ""), str(item.get("symbol") or ""), str(item.get("action_key") or "")))]


def _execution_records(value: Any) -> list[Mapping[str, Any]]:
    return _list_of_mappings(value)


def _outcome_records(value: Any) -> list[Mapping[str, Any]]:
    return _list_of_mappings(value)


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _sum_numeric(values: Sequence[Any]) -> float:
    return float(sum(value for value in (_number_or_none(item) for item in values) if value is not None))


def _average_numeric(values: Sequence[Any]) -> float | None:
    numbers = [value for value in (_number_or_none(item) for item in values) if value is not None]
    if not numbers:
        return None
    return float(sum(numbers) / len(numbers))

def _total_realized_pnl(items: Sequence[Mapping[str, Any]]) -> float:
    return round(
        sum(
            float(item.get("realized_pnl") or 0)
            for item in items
            if item.get("realized_pnl") is not None
        ),
        4,
    )


def _average_return_pct(items: Sequence[Mapping[str, Any]]) -> float | None:
    values = [
        float(item.get("return_pct"))
        for item in items
        if item.get("return_pct") is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 4)

