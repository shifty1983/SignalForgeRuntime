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

APPROVE_DECISIONS = {"approve", "approved", "approved_for_manual_action", "approved_for_manual_handling"}
DEFER_DECISIONS = {"defer", "deferred", "defer_for_later"}
REJECT_DECISIONS = {"reject", "rejected", "decline", "declined"}
REVIEW_DECISIONS = {"needs_review", "needs_more_info", "review"}
BLOCK_DECISIONS = {"block", "blocked"}


def build_options_manual_action_review(source: Mapping[str, Any]) -> dict[str, Any]:
    """Apply human review decisions to an options manual action queue.

    The output is a review artifact only. Approved actions are marked as
    approved for manual handling, but this function never creates order intents,
    routes orders, or performs broker actions.
    """

    if not isinstance(source, Mapping):
        return _blocked_result(reason="source must be a mapping")

    queue = _mapping(source.get("options_manual_action_queue") or source.get("manual_action_queue"))
    if not queue:
        return _blocked_result(
            queue_date=_string_or_none(source.get("queue_date")),
            reviewed_at=_string_or_none(source.get("reviewed_at")),
            reason="missing_options_manual_action_queue",
        )

    queue_date = _string_or_none(source.get("queue_date") or queue.get("queue_date"))
    reviewed_at = _string_or_none(source.get("reviewed_at") or source.get("review_timestamp"))
    reviewer = _string_or_none(source.get("reviewer"))

    decisions = _decision_index(source.get("review_decisions") or source.get("decisions"))
    priority_actions = _list_of_mappings(queue.get("priority_actions"))

    approved_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []
    deferred_actions: list[dict[str, Any]] = []
    needs_review_actions: list[dict[str, Any]] = []
    pending_actions: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    for index, action in enumerate(priority_actions):
        keyed_action = _with_action_key(action, index=index)
        strategy = _string_or_none(keyed_action.get("strategy"))

        if strategy and not is_defined_risk_strategy(strategy):
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason="undefined_risk_strategy_blocked",
                    reviewer=reviewer,
                    reviewed_at=reviewed_at,
                )
            )
            continue

        decision = _find_decision(keyed_action, decisions)
        if not decision:
            pending_actions.append(_review_item(keyed_action, reviewer=reviewer, reviewed_at=reviewed_at))
            continue

        normalized_decision = _normalize_decision(decision.get("decision") or decision.get("status"))
        review_item = _review_item(
            keyed_action,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            decision=normalized_decision,
            decision_note=_string_or_none(decision.get("note") or decision.get("comment") or decision.get("reason")),
        )

        if normalized_decision in APPROVE_DECISIONS:
            approved_actions.append(
                {
                    **review_item,
                    "review_status": "approved_for_manual_handling",
                    "approved_for_manual_handling": True,
                    "requires_manual_approval": True,
                    "order_intent": None,
                    "automatic_action": None,
                }
            )
        elif normalized_decision in DEFER_DECISIONS:
            deferred_actions.append({**review_item, "review_status": "deferred"})
        elif normalized_decision in REJECT_DECISIONS:
            rejected_actions.append({**review_item, "review_status": "rejected"})
        elif normalized_decision in BLOCK_DECISIONS:
            blocked_items.append(
                _blocked_item(
                    keyed_action,
                    reason=_string_or_none(decision.get("reason")) or "manually_blocked",
                    reviewer=reviewer,
                    reviewed_at=reviewed_at,
                )
            )
        else:
            needs_review_actions.append({**review_item, "review_status": "needs_review"})

    queue_blocked_items = [
        _blocked_item(item, reason=_string_or_none(item.get("reason")) or "source_blocked_item")
        for item in _list_of_mappings(queue.get("blocked_items"))
    ]
    blocked_items.extend(queue_blocked_items)

    status = _status(
        approved_actions=approved_actions,
        pending_actions=pending_actions,
        needs_review_actions=needs_review_actions,
        blocked_items=blocked_items,
        queue_status=_string_or_none(queue.get("status")),
    )

    return {
        "artifact_type": "options_manual_action_review",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "queue_date": queue_date,
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        "approved_actions": _sort_review_items(approved_actions),
        "rejected_actions": _sort_review_items(rejected_actions),
        "deferred_actions": _sort_review_items(deferred_actions),
        "needs_review_actions": _sort_review_items(needs_review_actions),
        "pending_actions": _sort_review_items(pending_actions),
        "blocked_items": _sort_blocked_items(blocked_items),
        "review_summary": {
            "source_priority_action_count": len(priority_actions),
            "approved_action_count": len(approved_actions),
            "rejected_action_count": len(rejected_actions),
            "deferred_action_count": len(deferred_actions),
            "needs_review_action_count": len(needs_review_actions),
            "pending_action_count": len(pending_actions),
            "blocked_item_count": len(blocked_items),
        },
        "source_queue_summary": {
            "artifact_type": _string_or_none(queue.get("artifact_type")),
            "status": _string_or_none(queue.get("status")),
            "queue_date": _string_or_none(queue.get("queue_date")),
            "priority_action_count": len(priority_actions),
            "monitor_item_count": len(_list_of_mappings(queue.get("monitor_items"))),
            "deferred_action_count": len(_list_of_mappings(queue.get("deferred_actions"))),
            "blocked_item_count": len(_list_of_mappings(queue.get("blocked_items"))),
        },
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def make_manual_action_key(action: Mapping[str, Any], *, index: int | None = None) -> str:
    if not isinstance(action, Mapping):
        return "manual_action_invalid"

    existing = _string_or_none(action.get("action_key") or action.get("action_id") or action.get("id"))
    if existing:
        return existing

    parts = [
        _string_or_none(action.get("action_source")) or "",
        _string_or_none(action.get("action_type")) or "",
        _string_or_none(action.get("symbol")) or "",
        _string_or_none(action.get("position_id")) or "",
        _string_or_none(action.get("strategy")) or "",
        _string_or_none(action.get("action")) or "",
    ]
    if index is not None:
        parts.append(str(index))

    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"manual_action_{digest}"


def _with_action_key(action: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    result = dict(action)
    result["action_key"] = make_manual_action_key(action, index=index)
    result["queue_index"] = index
    return result


def _decision_index(decisions: Any) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for index, decision in enumerate(_list_of_mappings(decisions)):
        result = dict(decision)
        result["_decision_index"] = index
        indexed.append(result)
    return indexed


def _find_decision(action: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    action_key = _string_or_none(action.get("action_key"))
    action_index = action.get("queue_index")

    for decision in decisions:
        decision_key = _string_or_none(decision.get("action_key") or decision.get("action_id"))
        if decision_key and action_key and decision_key == action_key:
            return decision

        decision_index = decision.get("queue_index")
        if isinstance(decision_index, int) and isinstance(action_index, int) and decision_index == action_index:
            return decision

        if _decision_matches_action(decision, action):
            return decision

    return None


def _decision_matches_action(decision: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    comparable_fields = ("action_source", "action_type", "symbol", "position_id", "strategy", "action")
    populated = [field for field in comparable_fields if _string_or_none(decision.get(field))]
    if not populated:
        return False
    return all(_string_or_none(decision.get(field)) == _string_or_none(action.get(field)) for field in populated)


def _review_item(
    action: Mapping[str, Any],
    *,
    reviewer: str | None,
    reviewed_at: str | None,
    decision: str | None = None,
    decision_note: str | None = None,
) -> dict[str, Any]:
    return {
        "action_key": _string_or_none(action.get("action_key")),
        "queue_index": action.get("queue_index"),
        "action_source": _string_or_none(action.get("action_source")),
        "action_type": _string_or_none(action.get("action_type")),
        "urgency": _urgency(action),
        "symbol": _string_or_none(action.get("symbol")),
        "position_id": _string_or_none(action.get("position_id")),
        "strategy": _string_or_none(action.get("strategy")),
        "action": _string_or_none(action.get("action")),
        "reason": _string_or_none(action.get("reason")),
        "review_triggers": _strings(action.get("review_triggers")),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "decision": decision,
        "decision_note": decision_note,
        "source_action": dict(action),
    }


def _blocked_item(
    item: Mapping[str, Any],
    *,
    reason: str,
    reviewer: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "action_key": _string_or_none(item.get("action_key")),
        "symbol": _string_or_none(item.get("symbol")),
        "position_id": _string_or_none(item.get("position_id")),
        "strategy": _string_or_none(item.get("strategy")),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "source_item": dict(item),
    }


def _blocked_result(
    *,
    reason: str,
    queue_date: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "options_manual_action_review",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "queue_date": queue_date,
        "reviewed_at": reviewed_at,
        "reviewer": None,
        "approved_actions": [],
        "rejected_actions": [],
        "deferred_actions": [],
        "needs_review_actions": [],
        "pending_actions": [],
        "blocked_items": [{"reason": reason, "source": "options_manual_action_review"}],
        "review_summary": {
            "source_priority_action_count": 0,
            "approved_action_count": 0,
            "rejected_action_count": 0,
            "deferred_action_count": 0,
            "needs_review_action_count": 0,
            "pending_action_count": 0,
            "blocked_item_count": 1,
        },
        "source_queue_summary": {},
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _status(
    *,
    approved_actions: Sequence[Mapping[str, Any]],
    pending_actions: Sequence[Mapping[str, Any]],
    needs_review_actions: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
    queue_status: str | None,
) -> str:
    if queue_status == "blocked" and not approved_actions:
        return "blocked"
    if blocked_items and not approved_actions and not pending_actions and not needs_review_actions:
        return "blocked"
    if pending_actions or needs_review_actions or blocked_items or queue_status == "needs_review":
        return "needs_review"
    return "ready"


def _normalize_decision(value: Any) -> str:
    decision = _string_or_none(value)
    if decision is None:
        return "needs_review"
    return decision.strip().lower()


def _sort_review_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in items),
        key=lambda item: (
            _urgency_rank(_string_or_none(item.get("urgency"))),
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
            _string_or_none(item.get("action_key")) or "",
        ),
    )


def _sort_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in items),
        key=lambda item: (
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
            _string_or_none(item.get("reason")) or "",
        ),
    )


def _urgency(value: Mapping[str, Any], default: str = "normal") -> str:
    return _string_or_none(value.get("urgency") or value.get("priority")) or default


def _urgency_rank(urgency: str | None) -> int:
    ranks = {
        "critical": 0,
        "high": 1,
        "urgent": 1,
        "medium": 2,
        "normal": 3,
        "low": 4,
        "monitor": 5,
    }
    return ranks.get((urgency or "normal").lower(), 3)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []

