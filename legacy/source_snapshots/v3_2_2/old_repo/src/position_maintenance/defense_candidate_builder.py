from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.options_strategy.catalog import is_defined_risk_strategy


EXCLUDED_ACTIONS = [
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

NON_CANDIDATE_ACTIONS = {
    "continue_monitoring",
}

URGENCY_RANK = {"high": 0, "medium": 1, "low": 2}
CATEGORY_RANK = {"defense_guardrail": 0, "defense": 1, "maintenance": 2}
STATUS_RANK = {"blocked": 0, "needs_review": 1, "ready": 2}


def build_options_strategy_defense_candidates(
    playbook_source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str | None = None,
    max_candidates_per_position: int | None = None,
) -> dict[str, Any]:
    """
    Convert strategy-specific maintenance playbooks into manual defense/review candidates.

    This builder is intentionally review-only. It does not create order intents, route
    orders, submit orders, model fills, perform live execution, or automatically defend
    positions.
    """

    errors = _validate_inputs(playbook_source=playbook_source, plan_date=plan_date)
    if errors:
        return _blocked_result(plan_date=plan_date, blocked_reasons=errors)

    playbooks = _extract_playbooks(playbook_source)
    assert playbooks is not None

    resolved_plan_date = _string_or_none(plan_date) or _infer_plan_date(playbook_source) or ""
    candidates: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    for playbook in playbooks:
        normalized = _normalize_playbook(playbook=playbook, plan_date=resolved_plan_date)
        warnings.extend(normalized["warnings"])

        if normalized["status"] == "blocked":
            blocked_items.append(_blocked_item_from_playbook(normalized))
            blocked_reasons.extend(normalized["blocked_reasons"])
            continue

        strategy = normalized["strategy"]
        if not strategy or not is_defined_risk_strategy(strategy):
            reason = f"undefined-risk or unknown strategy cannot produce defense candidates: {strategy}"
            blocked_items.append(
                {
                    "symbol": normalized["symbol"],
                    "position_id": normalized["position_id"],
                    "strategy": strategy,
                    "blocked_reasons": [reason],
                }
            )
            blocked_reasons.append(reason)
            continue

        actions = _candidate_actions(normalized)
        if max_candidates_per_position is not None and max_candidates_per_position >= 0:
            actions = actions[:max_candidates_per_position]

        for action in actions:
            candidates.append(_candidate_from_action(playbook=normalized, action=action))

    ranked_candidates = _rank_candidates(candidates)
    ranked_blocked_items = _rank_blocked_items(blocked_items)
    status = _result_status(candidates=ranked_candidates, blocked_items=ranked_blocked_items)

    return {
        "artifact_type": "options_strategy_defense_candidate_set",
        "status": status,
        "is_ready": status == "ready",
        "plan_date": resolved_plan_date,
        "candidate_count": len(ranked_candidates),
        "manual_review_count": len(ranked_candidates),
        "blocked_count": len(ranked_blocked_items),
        "candidates": ranked_candidates,
        "blocked_items": ranked_blocked_items,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": EXCLUDED_ACTIONS,
    }


def _validate_inputs(
    *,
    playbook_source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    plan_date: str | None,
) -> list[str]:
    errors: list[str] = []
    if plan_date is not None and not _string_or_none(plan_date):
        errors.append("plan_date must be a non-empty string when provided")
    if playbook_source is None:
        errors.append("playbook_source is required")
    elif isinstance(playbook_source, (str, bytes)):
        errors.append("playbook_source must be a mapping or sequence of mappings")
    elif isinstance(playbook_source, Sequence) and not all(isinstance(item, Mapping) for item in playbook_source):
        errors.append("playbook_source sequence must contain only mappings")
    elif not isinstance(playbook_source, Mapping | Sequence):
        errors.append("playbook_source must be a mapping or sequence of mappings")
    return errors


def _blocked_result(*, plan_date: str | None, blocked_reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_defense_candidate_set",
        "status": "blocked",
        "is_ready": False,
        "plan_date": _string_or_none(plan_date),
        "candidate_count": 0,
        "manual_review_count": 0,
        "blocked_count": 0,
        "candidates": [],
        "blocked_items": [],
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": EXCLUDED_ACTIONS,
    }


def _extract_playbooks(
    playbook_source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]] | None:
    if playbook_source is None:
        return None
    if isinstance(playbook_source, Mapping):
        playbooks = playbook_source.get("playbooks")
        if isinstance(playbooks, Sequence) and not isinstance(playbooks, (str, bytes)):
            return [playbook for playbook in playbooks if isinstance(playbook, Mapping)]
        if _clean(playbook_source.get("artifact_type")) == "options_strategy_maintenance_playbook":
            return [playbook_source]
        return []
    if isinstance(playbook_source, Sequence) and not isinstance(playbook_source, (str, bytes)):
        return [playbook for playbook in playbook_source if isinstance(playbook, Mapping)]
    return None


def _infer_plan_date(playbook_source: Any) -> str | None:
    if isinstance(playbook_source, Mapping):
        return _string_or_none(playbook_source.get("plan_date"))
    if isinstance(playbook_source, Sequence) and not isinstance(playbook_source, (str, bytes)):
        for playbook in playbook_source:
            if isinstance(playbook, Mapping):
                plan_date = _string_or_none(playbook.get("plan_date"))
                if plan_date:
                    return plan_date
    return None


def _normalize_playbook(*, playbook: Mapping[str, Any], plan_date: str) -> dict[str, Any]:
    status = _clean(playbook.get("status")) or "needs_review"
    strategy = _clean(playbook.get("strategy"))
    symbol = _string_or_none(playbook.get("symbol"))
    position_id = _string_or_none(playbook.get("position_id")) or _fallback_position_id(symbol=symbol, strategy=strategy)
    return {
        "artifact_type": _string_or_none(playbook.get("artifact_type")),
        "status": status,
        "plan_date": _string_or_none(playbook.get("plan_date")) or plan_date,
        "symbol": symbol,
        "position_id": position_id,
        "strategy": strategy,
        "strategy_family": _string_or_none(playbook.get("strategy_family")),
        "market_regime": _string_or_none(playbook.get("market_regime")),
        "urgency": _clean(playbook.get("urgency")) or "medium",
        "review_triggers": _strings(playbook.get("review_triggers")),
        "primary_management_objective": _string_or_none(playbook.get("primary_management_objective")),
        "maintenance_actions": _action_list(playbook.get("maintenance_actions")),
        "defense_actions": _action_list(playbook.get("defense_actions")),
        "monitoring_rules": _mapping_list(playbook.get("monitoring_rules")),
        "position_snapshot": dict(playbook.get("position_snapshot", {})) if isinstance(playbook.get("position_snapshot"), Mapping) else {},
        "warnings": _strings(playbook.get("warnings")),
        "blocked_reasons": _strings(playbook.get("blocked_reasons")),
    }


def _candidate_actions(playbook: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions = [
        *playbook.get("defense_actions", []),
        *playbook.get("maintenance_actions", []),
    ]
    filtered = [
        action
        for action in actions
        if _clean(action.get("action")) not in NON_CANDIDATE_ACTIONS
    ]
    return _rank_actions(filtered)


def _candidate_from_action(*, playbook: Mapping[str, Any], action: Mapping[str, Any]) -> dict[str, Any]:
    action_name = _clean(action.get("action")) or "manual_review"
    category = _clean(action.get("category")) or "maintenance"
    strategy = _clean(playbook.get("strategy"))
    symbol = _string_or_none(playbook.get("symbol"))
    position_id = _string_or_none(playbook.get("position_id"))
    return {
        "artifact_type": "options_strategy_defense_candidate",
        "status": "needs_review",
        "candidate_id": _candidate_id(
            position_id=position_id,
            symbol=symbol,
            strategy=strategy,
            action=action_name,
        ),
        "plan_date": _string_or_none(playbook.get("plan_date")),
        "symbol": symbol,
        "position_id": position_id,
        "strategy": strategy,
        "strategy_family": _string_or_none(playbook.get("strategy_family")),
        "candidate_type": category,
        "action": action_name,
        "review_action_type": _review_action_type(action_name),
        "priority": _int_or_default(action.get("priority"), 999),
        "urgency": _clean(playbook.get("urgency")) or "medium",
        "reason": _string_or_none(action.get("reason")),
        "primary_management_objective": _string_or_none(playbook.get("primary_management_objective")),
        "review_triggers": list(_strings(playbook.get("review_triggers"))),
        "defined_risk_required": True,
        "risk_guardrails": _risk_guardrails(action_name=action_name, strategy=strategy),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "source_playbook_summary": {
            "status": _clean(playbook.get("status")),
            "market_regime": _string_or_none(playbook.get("market_regime")),
            "warnings": list(_strings(playbook.get("warnings"))),
        },
    }


def _risk_guardrails(*, action_name: str, strategy: str | None) -> list[str]:
    guardrails = [
        "maintain_defined_risk",
        "manual_approval_required",
        "no_order_submission_from_candidate",
    ]
    if "roll" in action_name:
        guardrails.append("roll_must_not_increase_total_risk_without_review")
    if "credit" in action_name or strategy in {"put_credit_spread", "call_credit_spread", "bear_call_credit_spread", "bull_put_credit_spread"}:
        guardrails.append("credit_adjustment_must_preserve_spread_width_or_reduce_risk")
    if "event_risk" in action_name:
        guardrails.append("event_risk_requires_fresh_manual_review")
    if "undefined_risk" in action_name:
        guardrails.append("block_any_adjustment_that_creates_undefined_risk")
    return _dedupe_strings(guardrails)


def _review_action_type(action_name: str) -> str:
    if "undefined_risk" in action_name:
        return "risk_guardrail_review"
    if "profit" in action_name:
        return "profit_management_review"
    if "close" in action_name or "exit" in action_name:
        return "close_or_exit_review"
    if "roll" in action_name:
        return "roll_review"
    if "reduce" in action_name:
        return "risk_reduction_review"
    if "delta" in action_name:
        return "exposure_rebalance_review"
    if "event_risk" in action_name:
        return "event_risk_review"
    if "assignment" in action_name:
        return "assignment_review"
    if "hedge" in action_name or "protection" in action_name:
        return "protection_review"
    return "manual_review"


def _blocked_item_from_playbook(playbook: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _string_or_none(playbook.get("symbol")),
        "position_id": _string_or_none(playbook.get("position_id")),
        "strategy": _clean(playbook.get("strategy")),
        "blocked_reasons": list(_strings(playbook.get("blocked_reasons"))),
    }


def _fallback_position_id(*, symbol: str | None, strategy: str | None) -> str | None:
    if symbol and strategy:
        return f"{symbol}_{strategy}"
    return symbol or strategy


def _candidate_id(*, position_id: str | None, symbol: str | None, strategy: str | None, action: str) -> str:
    base = position_id or _fallback_position_id(symbol=symbol, strategy=strategy) or "unknown_position"
    return f"{base}_{action}"


def _rank_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(action)
        for action in sorted(
            actions,
            key=lambda action: (
                CATEGORY_RANK.get(_clean(action.get("category")) or "maintenance", 9),
                _int_or_default(action.get("priority"), 999),
                _clean(action.get("action")) or "",
            ),
        )
    ]


def _rank_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(candidate)
        for candidate in sorted(
            candidates,
            key=lambda candidate: (
                URGENCY_RANK.get(_clean(candidate.get("urgency")) or "medium", 9),
                CATEGORY_RANK.get(_clean(candidate.get("candidate_type")) or "maintenance", 9),
                _int_or_default(candidate.get("priority"), 999),
                _string_or_none(candidate.get("symbol")) or "",
                _string_or_none(candidate.get("candidate_id")) or "",
            ),
        )
    ]


def _rank_blocked_items(blocked_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in sorted(
            blocked_items,
            key=lambda item: (
                _string_or_none(item.get("symbol")) or "",
                _string_or_none(item.get("position_id")) or "",
                _clean(item.get("strategy")) or "",
            ),
        )
    ]


def _result_status(*, candidates: Sequence[Mapping[str, Any]], blocked_items: Sequence[Mapping[str, Any]]) -> str:
    if blocked_items:
        return "needs_review"
    if candidates:
        return "needs_review"
    return "ready"


def _action_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in _mapping_list(value)]


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item.strip().lower() for item in value if isinstance(item, str) and item.strip()]


def _int_or_default(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _dedupe_strings(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _clean(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result

