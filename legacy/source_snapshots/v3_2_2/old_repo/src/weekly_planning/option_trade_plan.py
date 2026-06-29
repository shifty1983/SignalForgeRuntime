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
    "maintenance_actions",
    "defense_actions",
]


VALID_PLAN_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


VALID_SOURCE_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


def build_weekly_option_trade_plan(
    option_strategy_candidate_results: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    portfolio_snapshot: Mapping[str, Any] | None = None,
    max_new_trades: int | None = None,
    max_candidates_per_symbol: int | None = 3,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the weekend review artifact for defined-risk option trade ideas.

    This planner consumes already-generated option strategy family candidates and
    turns them into weekly review actions. It does not build orders, submit
    orders, model fills, perform live execution, or produce maintenance/defense
    recommendations for existing positions.
    """

    validation_errors = _validate_plan_inputs(
        option_strategy_candidate_results=option_strategy_candidate_results,
        plan_date=plan_date,
        portfolio_snapshot=portfolio_snapshot,
        max_new_trades=max_new_trades,
        max_candidates_per_symbol=max_candidates_per_symbol,
    )
    if validation_errors:
        return _blocked_plan(
            plan_date=plan_date,
            blocked_reasons=validation_errors,
            metadata=metadata,
        )

    assert option_strategy_candidate_results is not None

    warnings: list[str] = []
    blocked_reasons: list[str] = []
    review_actions: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []

    for source_index, candidate_result in enumerate(option_strategy_candidate_results):
        source_summary = _source_candidate_summary(candidate_result)
        source_summaries.append(source_summary)

        source_status = _string_or_none(candidate_result.get("status"))
        symbol = _string_or_none(candidate_result.get("symbol"))

        if source_status not in VALID_SOURCE_STATUSES:
            blocked_items.append(
                _blocked_item(
                    symbol=symbol,
                    source_index=source_index,
                    reasons=["invalid option strategy candidate result status"],
                    source_status=source_status,
                )
            )
            continue

        source_warnings = list(_strings(candidate_result.get("warnings")))
        source_blocked_reasons = list(_strings(candidate_result.get("blocked_reasons")))
        warnings.extend(source_warnings)

        if source_status == "blocked":
            blocked_items.append(
                _blocked_item(
                    symbol=symbol,
                    source_index=source_index,
                    reasons=source_blocked_reasons
                    or ["option strategy candidate result is blocked"],
                    source_status=source_status,
                )
            )
            continue

        candidates = candidate_result.get("candidates")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            blocked_items.append(
                _blocked_item(
                    symbol=symbol,
                    source_index=source_index,
                    reasons=["invalid candidates shape"],
                    source_status=source_status,
                )
            )
            continue

        symbol_actions: list[dict[str, Any]] = []
        for candidate_index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                blocked_items.append(
                    _blocked_item(
                        symbol=symbol,
                        source_index=source_index,
                        reasons=["invalid candidate shape"],
                        source_status=source_status,
                    )
                )
                continue

            strategy = _string_or_none(candidate.get("strategy"))
            if strategy is None:
                blocked_items.append(
                    _blocked_item(
                        symbol=symbol,
                        source_index=source_index,
                        reasons=["candidate strategy is required"],
                        source_status=source_status,
                    )
                )
                continue

            if not is_defined_risk_strategy(strategy):
                blocked_items.append(
                    _blocked_item(
                        symbol=symbol,
                        source_index=source_index,
                        reasons=[f"undefined-risk strategy blocked: {strategy}"],
                        source_status=source_status,
                    )
                )
                continue

            action_status = _action_status(
                source_status=source_status,
                source_warnings=source_warnings,
                candidate_warnings=list(_strings(candidate.get("warnings"))),
            )
            symbol_actions.append(
                _review_action(
                    plan_date=plan_date,
                    symbol=symbol,
                    candidate=candidate,
                    candidate_result=candidate_result,
                    source_index=source_index,
                    candidate_index=candidate_index,
                    status=action_status,
                )
            )

        review_actions.extend(
            _limit_symbol_actions(
                symbol_actions,
                max_candidates_per_symbol=max_candidates_per_symbol,
            )
        )

    ranked_actions = _rank_actions(review_actions)
    selected_actions, deferred_actions = _split_selected_actions(
        ranked_actions,
        max_new_trades=max_new_trades,
    )

    plan_status = _plan_status(
        actions=selected_actions,
        deferred_actions=deferred_actions,
        blocked_items=blocked_items,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )

    if not selected_actions and not deferred_actions and not blocked_items:
        blocked_reasons.append("no option strategy candidate results produced plan actions")
        plan_status = "blocked"

    return {
        "artifact_type": "weekly_option_trade_plan",
        "status": plan_status,
        "is_ready": plan_status == "ready",
        "plan_date": plan_date,
        "plan_mode": "weekend_review",
        "new_trade_action_count": len(selected_actions),
        "deferred_action_count": len(deferred_actions),
        "blocked_item_count": len(blocked_items),
        "source_candidate_result_count": len(option_strategy_candidate_results),
        "new_trade_actions": selected_actions,
        "deferred_actions": deferred_actions,
        "blocked_items": _rank_blocked_items(blocked_items),
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "portfolio_snapshot_summary": _portfolio_snapshot_summary(portfolio_snapshot),
        "source_candidate_summaries": source_summaries,
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _validate_plan_inputs(
    *,
    option_strategy_candidate_results: Sequence[Mapping[str, Any]] | None,
    plan_date: str,
    portfolio_snapshot: Mapping[str, Any] | None,
    max_new_trades: int | None,
    max_candidates_per_symbol: int | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")

    if not isinstance(option_strategy_candidate_results, Sequence) or isinstance(
        option_strategy_candidate_results,
        (str, bytes),
    ):
        errors.append("option_strategy_candidate_results must be a sequence")
    elif len(option_strategy_candidate_results) == 0:
        errors.append("option_strategy_candidate_results is empty")

    if portfolio_snapshot is not None and not isinstance(portfolio_snapshot, Mapping):
        errors.append("portfolio_snapshot must be a mapping when provided")

    if max_new_trades is not None and max_new_trades < 1:
        errors.append("max_new_trades must be at least 1 when provided")

    if max_candidates_per_symbol is not None and max_candidates_per_symbol < 1:
        errors.append("max_candidates_per_symbol must be at least 1 when provided")

    return errors


def _blocked_plan(
    *,
    plan_date: str,
    blocked_reasons: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "weekly_option_trade_plan",
        "status": "blocked",
        "is_ready": False,
        "plan_date": plan_date,
        "plan_mode": "weekend_review",
        "new_trade_action_count": 0,
        "deferred_action_count": 0,
        "blocked_item_count": 0,
        "source_candidate_result_count": 0,
        "new_trade_actions": [],
        "deferred_actions": [],
        "blocked_items": [],
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "portfolio_snapshot_summary": {},
        "source_candidate_summaries": [],
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _review_action(
    *,
    plan_date: str,
    symbol: str | None,
    candidate: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    source_index: int,
    candidate_index: int,
    status: str,
) -> dict[str, Any]:
    strategy = _string_or_none(candidate.get("strategy")) or ""
    action_id = f"{plan_date}:{symbol or 'UNKNOWN'}:{strategy}:{source_index}:{candidate_index}"

    return {
        "action_id": action_id,
        "action_type": "consider_new_defined_risk_option_strategy",
        "status": status,
        "requires_manual_approval": True,
        "symbol": symbol,
        "strategy": strategy,
        "display_name": _string_or_none(candidate.get("display_name")),
        "direction": _string_or_none(candidate.get("direction")),
        "risk_profile": _string_or_none(candidate.get("risk_profile")),
        "priority_score": _float_or_zero(candidate.get("score")),
        "market_regime": _string_or_none(candidate_result.get("market_regime")),
        "asset_behavior": _string_or_none(candidate_result.get("asset_behavior")),
        "setup_family": _string_or_none(candidate_result.get("setup_family")),
        "best_setups": list(_strings(candidate.get("best_setups"))),
        "matched_reasons": list(_strings(candidate.get("matched_reasons"))),
        "warnings": list(_strings(candidate.get("warnings"))),
        "source_candidate_status": _string_or_none(candidate_result.get("status")),
        "order_intent": None,
        "execution_status": "not_submitted",
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_item(
    *,
    symbol: str | None,
    source_index: int,
    reasons: Sequence[str],
    source_status: str | None,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "source_index": source_index,
        "source_status": source_status,
        "reasons": _dedupe_strings(reasons),
    }


def _action_status(
    *,
    source_status: str,
    source_warnings: Sequence[str],
    candidate_warnings: Sequence[str],
) -> str:
    if source_status == "needs_review" or source_warnings or candidate_warnings:
        return "needs_review"

    return "ready"


def _limit_symbol_actions(
    actions: Sequence[dict[str, Any]],
    *,
    max_candidates_per_symbol: int | None,
) -> list[dict[str, Any]]:
    ranked = _rank_actions(actions)
    if max_candidates_per_symbol is None:
        return ranked

    return ranked[:max_candidates_per_symbol]


def _rank_actions(actions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        actions,
        key=lambda action: (
            _status_rank(_string_or_none(action.get("status"))),
            -_float_or_zero(action.get("priority_score")),
            _string_or_none(action.get("symbol")) or "",
            _string_or_none(action.get("strategy")) or "",
            _string_or_none(action.get("action_id")) or "",
        ),
    )


def _rank_blocked_items(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            _string_or_none(item.get("symbol")) or "",
            int(item.get("source_index", 0)),
            ",".join(_strings(item.get("reasons"))),
        ),
    )


def _split_selected_actions(
    actions: Sequence[dict[str, Any]],
    *,
    max_new_trades: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranked = list(actions)
    if max_new_trades is None:
        return ranked, []

    return ranked[:max_new_trades], ranked[max_new_trades:]


def _plan_status(
    *,
    actions: Sequence[Mapping[str, Any]],
    deferred_actions: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
    warnings: Sequence[str],
    blocked_reasons: Sequence[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if not actions and not deferred_actions:
        return "blocked" if blocked_items else "needs_review"

    if any(action.get("status") == "needs_review" for action in actions):
        return "needs_review"

    if warnings or blocked_items or deferred_actions:
        return "needs_review"

    return "ready"


def _source_candidate_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": _string_or_none(source.get("artifact_type")),
        "status": _string_or_none(source.get("status")),
        "symbol": _string_or_none(source.get("symbol")),
        "market_regime": _string_or_none(source.get("market_regime")),
        "asset_behavior": _string_or_none(source.get("asset_behavior")),
        "setup_family": _string_or_none(source.get("setup_family")),
        "candidate_count": _int_or_zero(source.get("candidate_count")),
        "rejected_count": _int_or_zero(source.get("rejected_count")),
    }


def _portfolio_snapshot_summary(
    portfolio_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(portfolio_snapshot, Mapping):
        return {}

    return {
        "portfolio_id": _string_or_none(portfolio_snapshot.get("portfolio_id")),
        "as_of": _string_or_none(portfolio_snapshot.get("as_of")),
        "cash": portfolio_snapshot.get("cash"),
        "net_liquidation_value": portfolio_snapshot.get("net_liquidation_value"),
        "open_position_count": _int_or_zero(portfolio_snapshot.get("open_position_count")),
        "source": _string_or_none(portfolio_snapshot.get("source")),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return None


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _status_rank(status: str | None) -> int:
    if status == "ready":
        return 0
    if status == "needs_review":
        return 1
    return 2


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output

