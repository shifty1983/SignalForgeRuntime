"""Build a unified manual action queue for options portfolio review.

This module combines safe review artifacts from weekend planning and weekday
monitoring into one manual queue. It does not submit orders or create broker
instructions. Every output remains a review item that requires manual approval.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.options_strategy.catalog import is_defined_risk_strategy

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
]

URGENCY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "normal": 3,
    "low": 4,
    "monitor": 5,
}

SOURCE_RANK = {
    "position_risk_monitor": 0,
    "defense_review": 1,
    "weekly_trade_plan": 2,
    "monitor": 3,
}


def build_options_manual_action_queue(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build a manual options action queue from planning and monitoring artifacts.

    Parameters
    ----------
    source:
        Mapping with optional keys:
        - queue_date
        - evaluation_timestamp
        - portfolio_snapshot
        - weekly_option_trade_plan
        - options_strategy_defense_review
        - options_position_risk_monitor
        - max_priority_actions
        - max_new_trade_actions
        - max_defense_actions
        - include_monitor_items

    Returns
    -------
    dict
        A deterministic review artifact with priority actions, monitor items,
        deferred actions, blocked items, summaries, and explicit exclusions.
    """

    if not isinstance(source, Mapping):
        return _blocked_result(
            queue_date=None,
            evaluation_timestamp=None,
            reason="source must be a mapping",
        )

    queue_date = _string_or_none(source.get("queue_date") or source.get("plan_date"))
    evaluation_timestamp = _string_or_none(source.get("evaluation_timestamp"))

    weekly_plan = _mapping(source.get("weekly_option_trade_plan"))
    defense_review = _mapping(source.get("options_strategy_defense_review"))
    risk_monitor = _mapping(source.get("options_position_risk_monitor"))

    max_priority_actions = _non_negative_int(source.get("max_priority_actions"), default=10)
    max_new_trade_actions = _non_negative_int(source.get("max_new_trade_actions"), default=3)
    max_defense_actions = _non_negative_int(source.get("max_defense_actions"), default=7)
    include_monitor_items = bool(source.get("include_monitor_items", True))

    priority_candidates: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    deferred_actions: list[dict[str, Any]] = []
    monitor_items: list[dict[str, Any]] = []

    risk_actions, risk_blocked = _actions_from_risk_monitor(risk_monitor, limit=max_defense_actions)
    priority_candidates.extend(risk_actions)
    blocked_items.extend(risk_blocked)

    defense_actions, defense_blocked = _actions_from_defense_review(
        defense_review,
        limit=max_defense_actions,
    )
    priority_candidates.extend(defense_actions)
    blocked_items.extend(defense_blocked)

    trade_actions, trade_deferred, trade_blocked = _actions_from_weekly_plan(
        weekly_plan,
        limit=max_new_trade_actions,
    )
    priority_candidates.extend(trade_actions)
    deferred_actions.extend(trade_deferred)
    blocked_items.extend(trade_blocked)

    blocked_items.extend(_source_blocked_items(weekly_plan, source_name="weekly_trade_plan"))
    blocked_items.extend(_source_blocked_items(defense_review, source_name="defense_review"))
    blocked_items.extend(_source_blocked_items(risk_monitor, source_name="position_risk_monitor"))

    if include_monitor_items:
        monitor_items.extend(
            _monitor_items_from_source(
                risk_monitor.get("monitor_items"),
                source_name="position_risk_monitor",
            )
        )
        monitor_items.extend(
            _monitor_items_from_source(
                defense_review.get("monitor_items"),
                source_name="defense_review",
            )
        )
        monitor_items.extend(
            _monitor_items_from_source(
                weekly_plan.get("monitor_items"),
                source_name="weekly_trade_plan",
            )
        )

    priority_candidates = _dedupe_items(priority_candidates)
    priority_actions = _rank_actions(priority_candidates)[:max_priority_actions]
    deferred_actions.extend(_rank_actions(priority_candidates)[len(priority_actions) :])

    deferred_actions = _dedupe_items(deferred_actions)
    blocked_items = _dedupe_items(blocked_items)
    monitor_items = _dedupe_items(monitor_items)

    status = _status(
        priority_actions=priority_actions,
        blocked_items=blocked_items,
        source_statuses=[
            _string_or_none(weekly_plan.get("status")),
            _string_or_none(defense_review.get("status")),
            _string_or_none(risk_monitor.get("status")),
        ],
    )

    return {
        "artifact_type": "options_manual_action_queue",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "queue_date": queue_date,
        "evaluation_timestamp": evaluation_timestamp,
        "portfolio_snapshot_summary": _summarize_portfolio(source.get("portfolio_snapshot")),
        "priority_actions": priority_actions,
        "monitor_items": _rank_monitor_items(monitor_items),
        "deferred_actions": _rank_actions(deferred_actions),
        "blocked_items": _rank_blocked_items(blocked_items),
        "action_summary": {
            "priority_action_count": len(priority_actions),
            "risk_monitor_action_count": sum(
                1 for action in priority_actions if action.get("action_source") == "position_risk_monitor"
            ),
            "defense_review_action_count": sum(
                1 for action in priority_actions if action.get("action_source") == "defense_review"
            ),
            "new_trade_action_count": sum(
                1 for action in priority_actions if action.get("action_source") == "weekly_trade_plan"
            ),
            "monitor_item_count": len(monitor_items),
            "deferred_action_count": len(deferred_actions),
            "blocked_item_count": len(blocked_items),
        },
        "source_summaries": {
            "weekly_option_trade_plan": _source_summary(weekly_plan),
            "options_strategy_defense_review": _source_summary(defense_review),
            "options_position_risk_monitor": _source_summary(risk_monitor),
        },
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _actions_from_risk_monitor(
    risk_monitor: Mapping[str, Any], *, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for alert in _list_of_mappings(risk_monitor.get("risk_alerts")):
        strategy = _strategy(alert)
        if strategy and not is_defined_risk_strategy(strategy):
            blocked.append(_blocked_item(alert, source="position_risk_monitor", reason="undefined_risk_strategy_blocked"))
            continue

        actions.append(
            _manual_action(
                source="position_risk_monitor",
                action_type="position_risk_alert",
                item=alert,
                strategy=strategy,
                action=_string_or_none(alert.get("candidate_action"))
                or _string_or_none(alert.get("action"))
                or "review_position_risk_alert",
                reason=_string_or_none(alert.get("reason")) or "risk monitor alert requires manual review",
                urgency=_urgency(alert),
            )
        )

    return _rank_actions(actions)[:limit], blocked


def _actions_from_defense_review(
    defense_review: Mapping[str, Any], *, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for candidate in _list_of_mappings(defense_review.get("review_candidates")):
        strategy = _strategy(candidate)
        if strategy and not is_defined_risk_strategy(strategy):
            blocked.append(_blocked_item(candidate, source="defense_review", reason="undefined_risk_strategy_blocked"))
            continue

        actions.append(
            _manual_action(
                source="defense_review",
                action_type="defense_review_candidate",
                item=candidate,
                strategy=strategy,
                action=_string_or_none(candidate.get("candidate_action"))
                or _string_or_none(candidate.get("action"))
                or "review_defense_candidate",
                reason=_string_or_none(candidate.get("reason"))
                or _string_or_none(candidate.get("candidate_reason"))
                or "strategy defense candidate requires manual review",
                urgency=_urgency(candidate),
            )
        )

    return _rank_actions(actions)[:limit], blocked


def _actions_from_weekly_plan(
    weekly_plan: Mapping[str, Any], *, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for item in _list_of_mappings(weekly_plan.get("new_trade_actions")):
        strategy = _strategy(item)
        if strategy and not is_defined_risk_strategy(strategy):
            blocked.append(_blocked_item(item, source="weekly_trade_plan", reason="undefined_risk_strategy_blocked"))
            continue

        actions.append(
            _manual_action(
                source="weekly_trade_plan",
                action_type="new_trade_review",
                item=item,
                strategy=strategy,
                action=_string_or_none(item.get("action")) or "review_new_defined_risk_trade",
                reason=_string_or_none(item.get("reason"))
                or _string_or_none(item.get("selection_reason"))
                or "weekly trade plan candidate requires manual review",
                urgency=_urgency(item, default="normal"),
            )
        )

    ranked = _rank_actions(actions)
    return ranked[:limit], ranked[limit:], blocked


def _manual_action(
    *,
    source: str,
    action_type: str,
    item: Mapping[str, Any],
    strategy: str | None,
    action: str,
    reason: str,
    urgency: str,
) -> dict[str, Any]:
    return {
        "action_source": source,
        "action_type": action_type,
        "urgency": urgency,
        "symbol": _string_or_none(item.get("symbol")),
        "position_id": _string_or_none(item.get("position_id")),
        "strategy": strategy,
        "action": action,
        "reason": reason,
        "review_triggers": _strings(item.get("review_triggers")),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "source_item": dict(item),
    }


def _blocked_result(
    *, queue_date: str | None, evaluation_timestamp: str | None, reason: str
) -> dict[str, Any]:
    return {
        "artifact_type": "options_manual_action_queue",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "queue_date": queue_date,
        "evaluation_timestamp": evaluation_timestamp,
        "portfolio_snapshot_summary": {},
        "priority_actions": [],
        "monitor_items": [],
        "deferred_actions": [],
        "blocked_items": [
            {
                "reason": reason,
                "source": "options_manual_action_queue",
            }
        ],
        "action_summary": {
            "priority_action_count": 0,
            "risk_monitor_action_count": 0,
            "defense_review_action_count": 0,
            "new_trade_action_count": 0,
            "monitor_item_count": 0,
            "deferred_action_count": 0,
            "blocked_item_count": 1,
        },
        "source_summaries": {},
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_item(item: Mapping[str, Any], *, source: str, reason: str) -> dict[str, Any]:
    return {
        "source": source,
        "reason": reason,
        "symbol": _string_or_none(item.get("symbol")),
        "position_id": _string_or_none(item.get("position_id")),
        "strategy": _strategy(item),
        "source_item": dict(item),
    }


def _source_blocked_items(source: Mapping[str, Any], *, source_name: str) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for item in _list_of_mappings(source.get("blocked_items")):
        blocked.append(
            {
                "source": source_name,
                "reason": _string_or_none(item.get("reason"))
                or _string_or_none(item.get("blocked_reason"))
                or "source_blocked_item",
                "symbol": _string_or_none(item.get("symbol")),
                "position_id": _string_or_none(item.get("position_id")),
                "strategy": _strategy(item),
                "source_item": dict(item),
            }
        )
    return blocked


def _monitor_items_from_source(items: Any, *, source_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _list_of_mappings(items):
        result.append(
            {
                "source": source_name,
                "urgency": _urgency(item, default="monitor"),
                "symbol": _string_or_none(item.get("symbol")),
                "position_id": _string_or_none(item.get("position_id")),
                "strategy": _strategy(item),
                "reason": _string_or_none(item.get("monitor_reason"))
                or _string_or_none(item.get("reason"))
                or "continue monitoring",
                "source_item": dict(item),
            }
        )
    return result


def _summarize_portfolio(portfolio_snapshot: Any) -> dict[str, Any]:
    if not isinstance(portfolio_snapshot, Mapping):
        return {}
    return {
        "account_id": _string_or_none(portfolio_snapshot.get("account_id")),
        "cash": portfolio_snapshot.get("cash"),
        "net_liquidation": portfolio_snapshot.get("net_liquidation"),
        "buying_power": portfolio_snapshot.get("buying_power"),
        "open_position_count": _non_negative_int(portfolio_snapshot.get("open_position_count"), default=0),
    }


def _source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not source:
        return {"provided": False}
    return {
        "provided": True,
        "artifact_type": _string_or_none(source.get("artifact_type")),
        "status": _string_or_none(source.get("status")),
        "risk_alert_count": _non_negative_int(source.get("risk_alert_count"), default=0),
        "review_candidate_count": _count(source.get("review_candidates")),
        "new_trade_action_count": _count(source.get("new_trade_actions")),
        "monitor_item_count": _count(source.get("monitor_items")),
        "blocked_item_count": _count(source.get("blocked_items")),
    }


def _status(*, priority_actions: Sequence[Mapping[str, Any]], blocked_items: Sequence[Mapping[str, Any]], source_statuses: Sequence[str | None]) -> str:
    if blocked_items and not priority_actions:
        return "blocked"
    if any(status == "blocked" for status in source_statuses if status):
        return "needs_review" if priority_actions else "blocked"
    if priority_actions or any(status == "needs_review" for status in source_statuses if status):
        return "needs_review"
    return "ready"


def _rank_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(action) for action in actions],
        key=lambda action: (
            URGENCY_RANK.get(str(action.get("urgency") or "normal"), 99),
            SOURCE_RANK.get(str(action.get("action_source") or "monitor"), 99),
            str(action.get("symbol") or ""),
            str(action.get("position_id") or ""),
            str(action.get("strategy") or ""),
            str(action.get("action") or ""),
        ),
    )


def _rank_monitor_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            URGENCY_RANK.get(str(item.get("urgency") or "monitor"), 99),
            str(item.get("symbol") or ""),
            str(item.get("position_id") or ""),
            str(item.get("strategy") or ""),
        ),
    )


def _rank_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("source") or ""),
            str(item.get("symbol") or ""),
            str(item.get("position_id") or ""),
            str(item.get("strategy") or ""),
            str(item.get("reason") or ""),
        ),
    )


def _dedupe_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (
            item.get("action_source") or item.get("source"),
            item.get("action_type") or item.get("reason"),
            item.get("symbol"),
            item.get("position_id"),
            item.get("strategy"),
            item.get("action") or item.get("reason"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strategy(item: Mapping[str, Any]) -> str | None:
    return _clean(item.get("strategy") or item.get("strategy_type"))


def _urgency(item: Mapping[str, Any], *, default: str = "medium") -> str:
    raw = _clean(item.get("urgency") or item.get("priority")) or default
    return raw if raw in URGENCY_RANK else default


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return sorted({_clean(item) for item in value if _clean(item)})


def _string_or_none(value: Any) -> str | None:
    text = _clean(value)
    return text or None


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _non_negative_int(value: Any, *, default: int) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, integer)


def _count(value: Any) -> int:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return 0
    return sum(1 for item in value if isinstance(item, Mapping))

