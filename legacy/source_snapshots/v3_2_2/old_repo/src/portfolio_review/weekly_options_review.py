"""Build a combined weekly options portfolio review artifact.

This module combines two already-safe review artifacts:

- weekly option trade plan actions for new opportunities
- options strategy defense review candidates for open positions

It intentionally does not submit orders or create broker instructions. The output is a
weekend review artifact that helps prioritize manual review actions across new trades
and existing-position maintenance/defense.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

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

URGGENCY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "normal": 3,
    "low": 4,
    "monitor": 5,
}

STATUS_RANK = {
    "blocked": 0,
    "needs_review": 1,
    "ready": 2,
}


def build_weekly_options_portfolio_review(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build a combined weekly options portfolio review from plan/review artifacts.

    Parameters
    ----------
    source:
        Mapping with optional keys:
        - plan_date
        - portfolio_snapshot
        - weekly_option_trade_plan
        - options_strategy_defense_review
        - max_new_trade_actions
        - max_defense_review_actions
        - max_total_priority_actions
        - prioritize_defense

    Returns
    -------
    dict
        Deterministic artifact with priority actions, monitor items, deferred actions,
        blocked items, summary counts, source summaries, and explicit exclusions.
    """

    if not isinstance(source, Mapping):
        return _blocked_result(
            plan_date=None,
            blocked_reason="source must be a mapping",
        )

    plan_date = _string_or_none(source.get("plan_date"))
    weekly_plan = source.get("weekly_option_trade_plan", {})
    defense_review = source.get("options_strategy_defense_review", {})

    if not isinstance(weekly_plan, Mapping) and not isinstance(defense_review, Mapping):
        return _blocked_result(
            plan_date=plan_date,
            blocked_reason="weekly_option_trade_plan or options_strategy_defense_review must be provided",
        )

    if not isinstance(weekly_plan, Mapping):
        weekly_plan = {}
    if not isinstance(defense_review, Mapping):
        defense_review = {}

    max_new_trade_actions = _non_negative_int(source.get("max_new_trade_actions"), default=3)
    max_defense_review_actions = _non_negative_int(
        source.get("max_defense_review_actions"), default=5
    )
    max_total_priority_actions = _non_negative_int(
        source.get("max_total_priority_actions"), default=8
    )
    prioritize_defense = bool(source.get("prioritize_defense", True))

    blocked_items: list[dict[str, Any]] = []
    deferred_actions: list[dict[str, Any]] = []

    defense_actions, defense_blocked = _build_defense_actions(
        defense_review=defense_review,
        limit=max_defense_review_actions,
    )
    blocked_items.extend(defense_blocked)

    new_trade_actions, new_trade_deferred, new_trade_blocked = _build_new_trade_actions(
        weekly_plan=weekly_plan,
        limit=max_new_trade_actions,
    )
    deferred_actions.extend(new_trade_deferred)
    blocked_items.extend(new_trade_blocked)

    source_blocked_items = _normalize_source_items(weekly_plan.get("blocked_items", []))
    source_blocked_items.extend(_normalize_source_items(defense_review.get("blocked_items", [])))
    blocked_items.extend(_dedupe_items(source_blocked_items))

    monitor_items = _normalize_source_items(defense_review.get("monitor_items", []))
    monitor_items.extend(_normalize_source_items(weekly_plan.get("monitor_items", [])))
    monitor_items = _dedupe_items(monitor_items)

    priority_actions = _combine_priority_actions(
        defense_actions=defense_actions,
        new_trade_actions=new_trade_actions,
        prioritize_defense=prioritize_defense,
        max_total_priority_actions=max_total_priority_actions,
    )

    overflow_actions = _combine_priority_actions(
        defense_actions=defense_actions,
        new_trade_actions=new_trade_actions,
        prioritize_defense=prioritize_defense,
        max_total_priority_actions=len(defense_actions) + len(new_trade_actions),
    )[len(priority_actions) :]
    deferred_actions.extend(overflow_actions)
    deferred_actions = _dedupe_items(deferred_actions)
    blocked_items = _dedupe_items(blocked_items)

    status = _resolve_status(
        weekly_plan_status=_string_or_none(weekly_plan.get("status")),
        defense_review_status=_string_or_none(defense_review.get("status")),
        priority_actions=priority_actions,
        blocked_items=blocked_items,
    )

    return {
        "artifact_type": "weekly_options_portfolio_review",
        "schema_version": "1.0",
        "status": status,
        "plan_date": plan_date,
        "portfolio_snapshot_summary": _summarize_portfolio_snapshot(
            source.get("portfolio_snapshot", {})
        ),
        "priority_actions": priority_actions,
        "monitor_items": monitor_items,
        "deferred_actions": deferred_actions,
        "blocked_items": blocked_items,
        "action_summary": {
            "priority_action_count": len(priority_actions),
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
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_defense_actions(
    *, defense_review: Mapping[str, Any], limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for item in _normalize_source_items(defense_review.get("review_candidates", [])):
        strategy = _string_or_none(item.get("strategy"))
        if strategy and not is_defined_risk_strategy(strategy):
            blocked.append(
                _blocked_item(
                    item=item,
                    reason="undefined_risk_strategy_blocked",
                    source="defense_review",
                )
            )
            continue

        actions.append(
            _action_from_item(
                item=item,
                action_source="defense_review",
                action_type="maintenance_or_defense_review",
                priority_category="existing_position",
                default_urgency="high",
            )
        )

    return _sort_actions(actions)[:limit], blocked


def _build_new_trade_actions(
    *, weekly_plan: Mapping[str, Any], limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    source_actions = weekly_plan.get("new_trade_actions")
    if source_actions is None:
        source_actions = weekly_plan.get("ready_actions", [])

    for item in _normalize_source_items(source_actions):
        strategy = _string_or_none(item.get("strategy"))
        if strategy and not is_defined_risk_strategy(strategy):
            blocked.append(
                _blocked_item(
                    item=item,
                    reason="undefined_risk_strategy_blocked",
                    source="weekly_trade_plan",
                )
            )
            continue

        actions.append(
            _action_from_item(
                item=item,
                action_source="weekly_trade_plan",
                action_type="new_trade_review",
                priority_category="new_opportunity",
                default_urgency="normal",
            )
        )

    deferred.extend(_normalize_source_items(weekly_plan.get("deferred_actions", [])))
    sorted_actions = _sort_actions(actions)
    return sorted_actions[:limit], deferred + sorted_actions[limit:], blocked


def _action_from_item(
    *,
    item: Mapping[str, Any],
    action_source: str,
    action_type: str,
    priority_category: str,
    default_urgency: str,
) -> dict[str, Any]:
    normalized = deepcopy(dict(item))
    urgency = _string_or_none(normalized.get("urgency")) or default_urgency
    strategy = _string_or_none(normalized.get("strategy"))
    symbol = _string_or_none(normalized.get("symbol"))

    return {
        "action_source": action_source,
        "action_type": action_type,
        "priority_category": priority_category,
        "symbol": symbol,
        "strategy": strategy,
        "urgency": urgency,
        "requires_manual_review": True,
        "defined_risk_confirmed": bool(strategy and is_defined_risk_strategy(strategy)),
        "source_item": normalized,
    }


def _combine_priority_actions(
    *,
    defense_actions: list[dict[str, Any]],
    new_trade_actions: list[dict[str, Any]],
    prioritize_defense: bool,
    max_total_priority_actions: int,
) -> list[dict[str, Any]]:
    if prioritize_defense:
        ordered = _sort_actions(defense_actions) + _sort_actions(new_trade_actions)
    else:
        ordered = _sort_actions(defense_actions + new_trade_actions)
    return ordered[:max_total_priority_actions]


def _resolve_status(
    *,
    weekly_plan_status: str | None,
    defense_review_status: str | None,
    priority_actions: list[dict[str, Any]],
    blocked_items: list[dict[str, Any]],
) -> str:
    statuses = [status for status in [weekly_plan_status, defense_review_status] if status]
    if any(status == "blocked" for status in statuses) and not priority_actions:
        return "blocked"
    if blocked_items:
        return "needs_review"
    if any(action.get("action_source") == "defense_review" for action in priority_actions):
        return "needs_review"
    if any(status == "needs_review" for status in statuses):
        return "needs_review"
    if priority_actions:
        return "ready"
    return "needs_review"


def _source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not source:
        return {"status": "missing", "item_count": 0}

    keys_to_count = [
        "new_trade_actions",
        "ready_actions",
        "review_candidates",
        "monitor_items",
        "deferred_actions",
        "blocked_items",
    ]
    return {
        "status": _string_or_none(source.get("status")) or "unknown",
        "artifact_type": _string_or_none(source.get("artifact_type")),
        "item_count": sum(len(_normalize_source_items(source.get(key, []))) for key in keys_to_count),
    }


def _summarize_portfolio_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        return {"status": "missing"}

    return {
        "status": "provided",
        "account_id": _string_or_none(snapshot.get("account_id")),
        "net_liquidation_value": snapshot.get("net_liquidation_value"),
        "cash": snapshot.get("cash"),
        "open_position_count": len(_normalize_source_items(snapshot.get("positions", []))),
    }


def _blocked_result(*, plan_date: str | None, blocked_reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "weekly_options_portfolio_review",
        "schema_version": "1.0",
        "status": "blocked",
        "plan_date": plan_date,
        "portfolio_snapshot_summary": {"status": "missing"},
        "priority_actions": [],
        "monitor_items": [],
        "deferred_actions": [],
        "blocked_items": [
            {
                "status": "blocked",
                "reason": blocked_reason,
                "action_source": "weekly_options_portfolio_review",
            }
        ],
        "action_summary": {
            "priority_action_count": 0,
            "defense_review_action_count": 0,
            "new_trade_action_count": 0,
            "monitor_item_count": 0,
            "deferred_action_count": 0,
            "blocked_item_count": 1,
        },
        "source_summaries": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_item(*, item: Mapping[str, Any], reason: str, source: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "action_source": source,
        "symbol": _string_or_none(item.get("symbol")),
        "strategy": _string_or_none(item.get("strategy")),
        "source_item": deepcopy(dict(item)),
    }


def _sort_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        actions,
        key=lambda action: (
            URGGENCY_RANK.get(str(action.get("urgency", "normal")), 99),
            str(action.get("symbol") or ""),
            str(action.get("strategy") or ""),
            str(action.get("action_type") or ""),
        ),
    )


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("action_source") or ""),
            str(item.get("action_type") or item.get("reason") or ""),
            str(item.get("symbol") or ""),
            str(item.get("strategy") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _normalize_source_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _non_negative_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    return default

