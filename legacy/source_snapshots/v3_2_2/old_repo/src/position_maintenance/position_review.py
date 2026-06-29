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

VALID_REVIEW_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

DEFAULT_THRESHOLDS = {
    "profit_target_pct": 0.50,
    "loss_review_pct": -0.50,
    "min_dte": 21,
    "high_delta_abs": 0.65,
}


def build_position_maintenance_review(
    open_positions: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    thresholds: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a review-only maintenance artifact for existing option positions.

    This module identifies positions that need weekend or weekday review. It does
    not create orders, route orders, model fills, perform live execution, or
    choose concrete roll/defense structures.
    """

    validation_errors = _validate_inputs(
        open_positions=open_positions,
        plan_date=plan_date,
        thresholds=thresholds,
    )
    if validation_errors:
        return _blocked_review(
            plan_date=plan_date,
            blocked_reasons=validation_errors,
            market_regime=market_regime,
            metadata=metadata,
        )

    assert open_positions is not None

    resolved_thresholds = _resolve_thresholds(thresholds)
    review_actions: list[dict[str, Any]] = []
    monitor_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    for source_index, position in enumerate(_rank_positions(open_positions)):
        position_id = _position_id(position, source_index=source_index)
        symbol = _string_or_none(position.get("symbol"))
        strategy = _string_or_none(position.get("strategy"))

        position_errors = _validate_position(position, source_index=source_index)
        if position_errors:
            blocked_items.append(
                _blocked_item(
                    position_id=position_id,
                    symbol=symbol,
                    strategy=strategy,
                    source_index=source_index,
                    reasons=position_errors,
                )
            )
            blocked_reasons.extend(position_errors)
            continue

        assert symbol is not None
        assert strategy is not None

        if not is_defined_risk_strategy(strategy):
            reason = f"undefined-risk or unknown strategy requires review: {strategy}"
            blocked_items.append(
                _blocked_item(
                    position_id=position_id,
                    symbol=symbol,
                    strategy=strategy,
                    source_index=source_index,
                    reasons=[reason],
                )
            )
            blocked_reasons.append(reason)
            continue

        triggers = _maintenance_triggers(
            position,
            strategy=strategy,
            thresholds=resolved_thresholds,
        )
        action = _review_action(
            plan_date=plan_date,
            position=position,
            position_id=position_id,
            symbol=symbol,
            strategy=strategy,
            source_index=source_index,
            triggers=triggers,
            market_regime=market_regime,
        )

        if triggers:
            review_actions.append(action)
            warnings.extend(action["review_triggers"])
        else:
            monitor_items.append(action)

    status = _review_status(
        review_actions=review_actions,
        blocked_items=blocked_items,
        warnings=warnings,
    )

    return {
        "artifact_type": "position_maintenance_review",
        "status": status,
        "is_ready": status == "ready",
        "plan_date": plan_date,
        "review_mode": "existing_position_review",
        "market_regime": _string_or_none(market_regime),
        "position_count": len(open_positions),
        "review_action_count": len(review_actions),
        "monitor_item_count": len(monitor_items),
        "blocked_item_count": len(blocked_items),
        "review_actions": _rank_actions(review_actions),
        "monitor_items": _rank_actions(monitor_items),
        "blocked_items": _rank_blocked_items(blocked_items),
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "thresholds": dict(resolved_thresholds),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _validate_inputs(
    *,
    open_positions: Sequence[Mapping[str, Any]] | None,
    plan_date: str,
    thresholds: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")

    if not isinstance(open_positions, Sequence) or isinstance(
        open_positions,
        (str, bytes),
    ):
        errors.append("open_positions must be a sequence")

    if thresholds is not None and not isinstance(thresholds, Mapping):
        errors.append("thresholds must be a mapping when provided")

    return errors


def _blocked_review(
    *,
    plan_date: str,
    blocked_reasons: Sequence[str],
    market_regime: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "position_maintenance_review",
        "status": "blocked",
        "is_ready": False,
        "plan_date": plan_date,
        "review_mode": "existing_position_review",
        "market_regime": _string_or_none(market_regime),
        "position_count": 0,
        "review_action_count": 0,
        "monitor_item_count": 0,
        "blocked_item_count": 0,
        "review_actions": [],
        "monitor_items": [],
        "blocked_items": [],
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _resolve_thresholds(thresholds: Mapping[str, Any] | None) -> dict[str, float | int]:
    resolved: dict[str, float | int] = dict(DEFAULT_THRESHOLDS)
    for key, value in dict(thresholds or {}).items():
        if key not in DEFAULT_THRESHOLDS:
            continue
        number = _number_or_none(value)
        if number is not None:
            resolved[key] = number
    return resolved


def _validate_position(position: Mapping[str, Any], *, source_index: int) -> list[str]:
    errors: list[str] = []

    if not _string_or_none(position.get("symbol")):
        errors.append(f"position {source_index} symbol is required")

    if not _string_or_none(position.get("strategy")):
        errors.append(f"position {source_index} strategy is required")

    if not isinstance(position, Mapping):
        errors.append(f"position {source_index} must be a mapping")

    return errors


def _maintenance_triggers(
    position: Mapping[str, Any],
    *,
    strategy: str,
    thresholds: Mapping[str, float | int],
) -> list[str]:
    triggers: list[str] = []

    unrealized_pnl_pct = _number_or_none(position.get("unrealized_pnl_pct"))
    profit_target_pct = _number_or_none(position.get("profit_target_pct"))
    if profit_target_pct is None:
        profit_target_pct = float(thresholds["profit_target_pct"])
    if unrealized_pnl_pct is not None and unrealized_pnl_pct >= profit_target_pct:
        triggers.append("profit_target_reached")

    loss_review_pct = _number_or_none(position.get("loss_review_pct"))
    if loss_review_pct is None:
        loss_review_pct = float(thresholds["loss_review_pct"])
    if unrealized_pnl_pct is not None and unrealized_pnl_pct <= loss_review_pct:
        triggers.append("loss_review_threshold_reached")

    days_to_expiration = _number_or_none(position.get("days_to_expiration"))
    min_dte = _number_or_none(position.get("min_dte"))
    if min_dte is None:
        min_dte = float(thresholds["min_dte"])
    if days_to_expiration is not None and days_to_expiration <= min_dte:
        triggers.append("expiration_window_reached")

    if _short_strike_tested(position, strategy=strategy):
        triggers.append("short_strike_tested")

    net_delta = _number_or_none(position.get("net_delta"))
    high_delta_abs = _number_or_none(position.get("high_delta_abs"))
    if high_delta_abs is None:
        high_delta_abs = float(thresholds["high_delta_abs"])
    if net_delta is not None and abs(net_delta) >= high_delta_abs:
        triggers.append("delta_review_threshold_reached")

    if position.get("event_risk") is True:
        triggers.append("event_risk_review")

    return _dedupe_strings(triggers)


def _short_strike_tested(position: Mapping[str, Any], *, strategy: str) -> bool:
    explicit = position.get("short_strike_tested")
    if isinstance(explicit, bool):
        return explicit

    underlying_price = _number_or_none(position.get("underlying_price"))
    if underlying_price is None:
        return False

    short_strike = _number_or_none(position.get("short_strike"))
    if short_strike is not None:
        if strategy in {"put_credit_spread", "bull_put_credit_spread"}:
            return underlying_price <= short_strike
        if strategy in {"call_credit_spread", "bear_call_credit_spread"}:
            return underlying_price >= short_strike

    short_put_strike = _number_or_none(position.get("short_put_strike"))
    short_call_strike = _number_or_none(position.get("short_call_strike"))
    if strategy in {"iron_condor", "iron_butterfly"}:
        if short_put_strike is not None and underlying_price <= short_put_strike:
            return True
        if short_call_strike is not None and underlying_price >= short_call_strike:
            return True

    return False


def _review_action(
    *,
    plan_date: str,
    position: Mapping[str, Any],
    position_id: str,
    symbol: str,
    strategy: str,
    source_index: int,
    triggers: Sequence[str],
    market_regime: str | None,
) -> dict[str, Any]:
    return {
        "plan_date": plan_date,
        "position_id": position_id,
        "symbol": symbol,
        "strategy": strategy,
        "source_index": source_index,
        "status": "needs_review" if triggers else "ready",
        "urgency": _urgency(triggers),
        "review_triggers": list(triggers),
        "recommended_review_action": _recommended_review_action(triggers),
        "requires_manual_approval": True,
        "order_intent": None,
        "maintenance_action": None,
        "defense_action": None,
        "market_regime": _string_or_none(market_regime),
        "position_snapshot": _position_snapshot(position),
    }


def _blocked_item(
    *,
    position_id: str,
    symbol: str | None,
    strategy: str | None,
    source_index: int,
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "position_id": position_id,
        "symbol": symbol,
        "strategy": strategy,
        "source_index": source_index,
        "status": "blocked",
        "blocked_reasons": _dedupe_strings(reasons),
        "requires_manual_approval": True,
        "order_intent": None,
        "maintenance_action": None,
        "defense_action": None,
    }


def _urgency(triggers: Sequence[str]) -> str:
    high_urgency = {
        "loss_review_threshold_reached",
        "short_strike_tested",
        "event_risk_review",
    }
    if any(trigger in high_urgency for trigger in triggers):
        return "high"
    if triggers:
        return "medium"
    return "low"


def _recommended_review_action(triggers: Sequence[str]) -> str:
    trigger_set = set(triggers)
    if "loss_review_threshold_reached" in trigger_set or "short_strike_tested" in trigger_set:
        return "review_defense_or_exit"
    if "expiration_window_reached" in trigger_set:
        return "review_roll_or_close"
    if "profit_target_reached" in trigger_set:
        return "review_profit_take_or_close"
    if "event_risk_review" in trigger_set:
        return "review_event_risk_adjustment"
    if "delta_review_threshold_reached" in trigger_set:
        return "review_delta_exposure"
    return "continue_monitoring"


def _position_snapshot(position: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "quantity",
        "days_to_expiration",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "underlying_price",
        "short_strike",
        "short_put_strike",
        "short_call_strike",
        "net_delta",
        "event_risk",
    ]
    return {key: position[key] for key in keys if key in position}


def _review_status(
    *,
    review_actions: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
    warnings: Sequence[str],
) -> str:
    if blocked_items:
        return "needs_review"
    if review_actions or warnings:
        return "needs_review"
    return "ready"


def _rank_positions(positions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        [position for position in positions if isinstance(position, Mapping)],
        key=lambda position: (
            _string_or_none(position.get("symbol")) or "",
            _string_or_none(position.get("strategy")) or "",
            _string_or_none(position.get("position_id")) or "",
        ),
    )


def _rank_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    urgency_rank = {"high": 0, "medium": 1, "low": 2}
    return [
        dict(action)
        for action in sorted(
            actions,
            key=lambda action: (
                urgency_rank.get(_string_or_none(action.get("urgency")) or "low", 9),
                _string_or_none(action.get("symbol")) or "",
                _string_or_none(action.get("strategy")) or "",
                _string_or_none(action.get("position_id")) or "",
            ),
        )
    ]


def _rank_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in sorted(
            items,
            key=lambda item: (
                _string_or_none(item.get("symbol")) or "",
                _string_or_none(item.get("strategy")) or "",
                _string_or_none(item.get("position_id")) or "",
            ),
        )
    ]


def _position_id(position: Mapping[str, Any], *, source_index: int) -> str:
    return _string_or_none(position.get("position_id")) or f"position_{source_index}"


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})

