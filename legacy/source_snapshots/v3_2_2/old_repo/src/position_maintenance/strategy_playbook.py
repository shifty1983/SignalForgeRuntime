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

VALID_PLAYBOOK_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}

STRATEGY_FAMILIES = {
    "bull_call_debit_spread": "directional_debit_spread",
    "bear_put_debit_spread": "directional_debit_spread",
    "put_credit_spread": "directional_credit_spread",
    "bull_put_credit_spread": "directional_credit_spread",
    "call_credit_spread": "directional_credit_spread",
    "bear_call_credit_spread": "directional_credit_spread",
    "iron_condor": "neutral_income_spread",
    "iron_butterfly": "neutral_income_spread",
    "calendar_spread": "time_spread",
    "diagonal_spread": "time_spread",
    "protective_put": "portfolio_protection",
    "collar": "portfolio_protection",
    "covered_call": "covered_income",
}

DIRECTIONAL_DEBIT_SPREADS = {
    "bull_call_debit_spread",
    "bear_put_debit_spread",
}

DIRECTIONAL_CREDIT_SPREADS = {
    "put_credit_spread",
    "bull_put_credit_spread",
    "call_credit_spread",
    "bear_call_credit_spread",
}

NEUTRAL_INCOME_SPREADS = {
    "iron_condor",
    "iron_butterfly",
}

TIME_SPREADS = {
    "calendar_spread",
    "diagonal_spread",
}

PROTECTION_STRATEGIES = {
    "protective_put",
    "collar",
}

COVERED_INCOME_STRATEGIES = {
    "covered_call",
}

HIGH_URGENCY_TRIGGERS = {
    "loss_review_threshold_reached",
    "short_strike_tested",
    "event_risk_review",
    "setup_invalidation_review",
    "assignment_risk_review",
}

MEDIUM_URGENCY_TRIGGERS = {
    "expiration_window_reached",
    "delta_review_threshold_reached",
    "iv_expansion_review",
    "profit_target_reached",
}



def build_options_strategy_maintenance_playbook(
    position: Mapping[str, Any] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    regime_options_policy: Mapping[str, Any] | None = None,
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    option_behavior_options_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a strategy-specific maintenance and defense review playbook.

    The playbook recommends review paths only. It does not create orders, route
    orders, submit orders, model fills, perform live execution, or automatically
    defend positions.
    """

    errors = _validate_inputs(position=position, plan_date=plan_date)
    if errors:
        return _blocked_playbook(
            plan_date=plan_date,
            blocked_reasons=errors,
            market_regime=market_regime,
        )

    assert isinstance(position, Mapping)

    strategy = _clean(position.get("strategy"))
    symbol = _string_or_none(position.get("symbol"))
    position_id = _string_or_none(position.get("position_id")) or f"{symbol}_{strategy}"

    if not strategy or not is_defined_risk_strategy(strategy):
        return _blocked_playbook(
            plan_date=plan_date,
            symbol=symbol,
            strategy=strategy,
            position_id=position_id,
            market_regime=market_regime,
            blocked_reasons=[
                f"undefined-risk or unknown strategy has no automated maintenance playbook: {strategy}"
            ],
        )

    triggers = _resolve_triggers(position)
    policy_warnings = _policy_warnings(
        market_regime=market_regime,
        regime_options_policy=regime_options_policy,
        asset_behavior_options_policy=asset_behavior_options_policy,
        option_behavior_options_policy=option_behavior_options_policy,
        strategy=strategy,
    )
    trigger_warnings = _trigger_warnings(triggers=triggers, strategy=strategy)
    warnings = _dedupe_strings([*policy_warnings, *trigger_warnings])

    maintenance_actions = _maintenance_actions(strategy=strategy, triggers=triggers)
    defense_actions = _defense_actions(strategy=strategy, triggers=triggers)
    monitoring_rules = _monitoring_rules(strategy=strategy)

    urgency = _urgency(triggers=triggers, warnings=warnings)
    status = "needs_review" if triggers or defense_actions or policy_warnings else "ready"

    return {
        "artifact_type": "options_strategy_maintenance_playbook",
        "status": status,
        "is_ready": status == "ready",
        "plan_date": plan_date,
        "symbol": symbol,
        "position_id": position_id,
        "strategy": strategy,
        "strategy_family": STRATEGY_FAMILIES.get(strategy, "defined_risk_other"),
        "market_regime": _string_or_none(market_regime),
        "urgency": urgency,
        "review_triggers": triggers,
        "primary_management_objective": _primary_management_objective(
            strategy=strategy,
            triggers=triggers,
        ),
        "maintenance_actions": maintenance_actions,
        "defense_actions": defense_actions,
        "monitoring_rules": monitoring_rules,
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "policy_context": _policy_context(
            regime_options_policy=regime_options_policy,
            asset_behavior_options_policy=asset_behavior_options_policy,
            option_behavior_options_policy=option_behavior_options_policy,
        ),
        "position_snapshot": _position_snapshot(position),
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
    }



def build_options_strategy_maintenance_playbooks(
    positions: Sequence[Mapping[str, Any]] | None,
    *,
    plan_date: str,
    market_regime: str | None = None,
    regime_options_policy: Mapping[str, Any] | None = None,
    asset_behavior_options_policy: Mapping[str, Any] | None = None,
    option_behavior_options_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build playbooks for a portfolio of existing defined-risk options positions."""

    errors: list[str] = []
    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")
    if not isinstance(positions, Sequence) or isinstance(positions, (str, bytes)):
        errors.append("positions must be a sequence")
    if errors:
        return {
            "artifact_type": "options_strategy_maintenance_playbook_set",
            "status": "blocked",
            "is_ready": False,
            "plan_date": plan_date,
            "market_regime": _string_or_none(market_regime),
            "playbook_count": 0,
            "needs_review_count": 0,
            "blocked_count": 0,
            "playbooks": [],
            "warnings": [],
            "blocked_reasons": _dedupe_strings(errors),
            "excluded": EXCLUDED_ACTIONS,
        }

    assert positions is not None

    playbooks = [
        build_options_strategy_maintenance_playbook(
            position,
            plan_date=plan_date,
            market_regime=market_regime,
            regime_options_policy=regime_options_policy,
            asset_behavior_options_policy=asset_behavior_options_policy,
            option_behavior_options_policy=option_behavior_options_policy,
        )
        for position in _position_list(positions)
    ]
    ranked_playbooks = _rank_playbooks(playbooks)
    status = _playbook_set_status(ranked_playbooks)

    return {
        "artifact_type": "options_strategy_maintenance_playbook_set",
        "status": status,
        "is_ready": status == "ready",
        "plan_date": plan_date,
        "market_regime": _string_or_none(market_regime),
        "playbook_count": len(ranked_playbooks),
        "needs_review_count": sum(1 for playbook in ranked_playbooks if playbook["status"] == "needs_review"),
        "blocked_count": sum(1 for playbook in ranked_playbooks if playbook["status"] == "blocked"),
        "playbooks": ranked_playbooks,
        "warnings": _dedupe_strings(
            warning for playbook in ranked_playbooks for warning in playbook.get("warnings", [])
        ),
        "blocked_reasons": _dedupe_strings(
            reason for playbook in ranked_playbooks for reason in playbook.get("blocked_reasons", [])
        ),
        "excluded": EXCLUDED_ACTIONS,
    }



def _validate_inputs(*, position: Mapping[str, Any] | None, plan_date: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan_date, str) or not plan_date.strip():
        errors.append("plan_date is required")
    if not isinstance(position, Mapping):
        errors.append("position must be a mapping")
        return errors
    if not _string_or_none(position.get("symbol")):
        errors.append("position symbol is required")
    if not _string_or_none(position.get("strategy")):
        errors.append("position strategy is required")
    return errors



def _blocked_playbook(
    *,
    plan_date: str,
    blocked_reasons: Sequence[str],
    symbol: str | None = None,
    strategy: str | None = None,
    position_id: str | None = None,
    market_regime: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "options_strategy_maintenance_playbook",
        "status": "blocked",
        "is_ready": False,
        "plan_date": plan_date,
        "symbol": symbol,
        "position_id": position_id,
        "strategy": strategy,
        "strategy_family": None,
        "market_regime": _string_or_none(market_regime),
        "urgency": "high",
        "review_triggers": [],
        "primary_management_objective": "manual_risk_review",
        "maintenance_actions": [],
        "defense_actions": [],
        "monitoring_rules": [],
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "policy_context": {},
        "position_snapshot": {},
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
    }



def _resolve_triggers(position: Mapping[str, Any]) -> list[str]:
    triggers = list(_strings(position.get("review_triggers")))

    if position.get("short_strike_tested") is True:
        triggers.append("short_strike_tested")
    if position.get("event_risk") is True:
        triggers.append("event_risk_review")
    if position.get("assignment_risk") is True:
        triggers.append("assignment_risk_review")

    unrealized_pnl_pct = _number_or_none(position.get("unrealized_pnl_pct"))
    profit_target_pct = _number_or_none(position.get("profit_target_pct"))
    if profit_target_pct is None:
        profit_target_pct = 0.50
    if unrealized_pnl_pct is not None and unrealized_pnl_pct >= profit_target_pct:
        triggers.append("profit_target_reached")

    loss_review_pct = _number_or_none(position.get("loss_review_pct"))
    if loss_review_pct is None:
        loss_review_pct = -0.50
    if unrealized_pnl_pct is not None and unrealized_pnl_pct <= loss_review_pct:
        triggers.append("loss_review_threshold_reached")

    days_to_expiration = _number_or_none(position.get("days_to_expiration"))
    min_dte = _number_or_none(position.get("min_dte"))
    if min_dte is None:
        min_dte = 21.0
    if days_to_expiration is not None and days_to_expiration <= min_dte:
        triggers.append("expiration_window_reached")

    net_delta = _number_or_none(position.get("net_delta"))
    high_delta_abs = _number_or_none(position.get("high_delta_abs"))
    if high_delta_abs is None:
        high_delta_abs = 0.65
    if net_delta is not None and abs(net_delta) >= high_delta_abs:
        triggers.append("delta_review_threshold_reached")

    return _dedupe_strings(triggers)



def _maintenance_actions(*, strategy: str, triggers: Sequence[str]) -> list[dict[str, Any]]:
    trigger_set = set(triggers)
    actions: list[dict[str, Any]] = []

    if not trigger_set:
        return [
            _action(
                action="continue_monitoring",
                category="maintenance",
                priority=70,
                reason="no maintenance trigger is active",
            )
        ]

    if "profit_target_reached" in trigger_set:
        actions.append(
            _action(
                action="review_profit_take_or_close",
                category="maintenance",
                priority=10,
                reason="position reached profit target",
            )
        )

    if "expiration_window_reached" in trigger_set:
        actions.append(
            _action(
                action="review_close_or_roll_before_expiration",
                category="maintenance",
                priority=20,
                reason="position is inside the expiration review window",
            )
        )

    if "delta_review_threshold_reached" in trigger_set:
        actions.append(
            _action(
                action="review_delta_exposure",
                category="maintenance",
                priority=30,
                reason="position delta exposure moved outside review threshold",
            )
        )

    if strategy in TIME_SPREADS and "expiration_window_reached" in trigger_set:
        actions.append(
            _action(
                action="review_front_month_exit_or_roll",
                category="maintenance",
                priority=15,
                reason="time spread front expiration needs review",
            )
        )

    if strategy in PROTECTION_STRATEGIES and "profit_target_reached" in trigger_set:
        actions.append(
            _action(
                action="review_hedge_cost_and_remaining_protection",
                category="maintenance",
                priority=25,
                reason="protective structure value changed enough to review hedge efficiency",
            )
        )

    return _rank_actions(actions)



def _defense_actions(*, strategy: str, triggers: Sequence[str]) -> list[dict[str, Any]]:
    trigger_set = set(triggers)
    actions: list[dict[str, Any]] = []

    if not trigger_set.intersection(HIGH_URGENCY_TRIGGERS | {"delta_review_threshold_reached"}):
        return []

    if strategy in DIRECTIONAL_DEBIT_SPREADS:
        if trigger_set.intersection({"loss_review_threshold_reached", "setup_invalidation_review"}):
            actions.extend(
                [
                    _action(
                        action="review_close_to_preserve_remaining_debit",
                        category="defense",
                        priority=10,
                        reason="directional debit spread is moving against the setup",
                    ),
                    _action(
                        action="review_roll_out_only_if_original_direction_remains_valid",
                        category="defense",
                        priority=30,
                        reason="rolling a debit spread should require setup confirmation",
                    ),
                ]
            )

    if strategy in DIRECTIONAL_CREDIT_SPREADS:
        if trigger_set.intersection({"short_strike_tested", "loss_review_threshold_reached"}):
            actions.extend(
                [
                    _action(
                        action="review_close_or_reduce_tested_credit_spread",
                        category="defense",
                        priority=5,
                        reason="defined-risk credit spread is challenged",
                    ),
                    _action(
                        action="review_roll_out_and_away_for_credit_only_if_risk_remains_defined",
                        category="defense",
                        priority=20,
                        reason="roll should maintain defined risk and improve strike distance",
                    ),
                    _action(
                        action="review_do_not_add_undefined_risk",
                        category="defense_guardrail",
                        priority=1,
                        reason="defense cannot convert the trade into undefined risk",
                    ),
                ]
            )

    if strategy in NEUTRAL_INCOME_SPREADS:
        if trigger_set.intersection({"short_strike_tested", "delta_review_threshold_reached", "loss_review_threshold_reached"}):
            actions.extend(
                [
                    _action(
                        action="review_close_challenged_side_or_entire_structure",
                        category="defense",
                        priority=5,
                        reason="neutral income spread has a challenged side",
                    ),
                    _action(
                        action="review_roll_challenged_side_without_increasing_total_risk",
                        category="defense",
                        priority=20,
                        reason="roll should maintain defined risk and reduce concentration on the tested side",
                    ),
                    _action(
                        action="review_delta_rebalance_or_exit",
                        category="defense",
                        priority=25,
                        reason="neutral structure delta moved outside review threshold",
                    ),
                ]
            )

    if strategy in TIME_SPREADS:
        if trigger_set.intersection({"loss_review_threshold_reached", "delta_review_threshold_reached"}):
            actions.extend(
                [
                    _action(
                        action="review_close_or_reduce_time_spread",
                        category="defense",
                        priority=10,
                        reason="time spread moved outside expected risk profile",
                    ),
                    _action(
                        action="review_roll_short_leg_only_with_defined_remaining_risk",
                        category="defense",
                        priority=30,
                        reason="time-spread defense must preserve defined risk",
                    ),
                ]
            )

    if strategy in PROTECTION_STRATEGIES:
        if trigger_set.intersection({"loss_review_threshold_reached", "event_risk_review"}):
            actions.extend(
                [
                    _action(
                        action="review_keep_or_increase_defined_downside_protection",
                        category="defense",
                        priority=10,
                        reason="protective structure is being evaluated during adverse conditions",
                    ),
                    _action(
                        action="review_close_underlying_or_rebalance_portfolio_exposure",
                        category="defense",
                        priority=30,
                        reason="defense may require reducing underlying exposure rather than adding option risk",
                    ),
                ]
            )

    if strategy in COVERED_INCOME_STRATEGIES:
        if trigger_set.intersection({"assignment_risk_review", "short_strike_tested", "expiration_window_reached"}):
            actions.extend(
                [
                    _action(
                        action="review_assignment_or_call_away_risk",
                        category="defense",
                        priority=10,
                        reason="covered call short strike or expiration requires ownership-aware review",
                    ),
                    _action(
                        action="review_roll_call_only_if_upside_cap_still_desired",
                        category="defense",
                        priority=30,
                        reason="rolling covered calls should align with portfolio intent",
                    ),
                ]
            )

    if "event_risk_review" in trigger_set:
        actions.append(
            _action(
                action="review_event_risk_before_any_adjustment",
                category="defense_guardrail",
                priority=2,
                reason="event risk requires manual confirmation before adjustment",
            )
        )

    return _rank_actions(actions)



def _monitoring_rules(*, strategy: str) -> list[dict[str, str]]:
    common = [
        _rule("profit_target", "review when profit target is reached"),
        _rule("loss_threshold", "review when loss threshold is reached"),
        _rule("dte_window", "review when position enters expiration window"),
        _rule("defined_risk_integrity", "block any adjustment that creates undefined risk"),
    ]

    if strategy in DIRECTIONAL_CREDIT_SPREADS:
        return [
            *common,
            _rule("short_strike_distance", "review when the short strike is tested"),
            _rule("credit_spread_delta", "review when short-option delta expands"),
        ]
    if strategy in NEUTRAL_INCOME_SPREADS:
        return [
            *common,
            _rule("tested_side", "review when either short strike is tested"),
            _rule("net_delta", "review when neutral structure becomes directionally imbalanced"),
            _rule("iv_expansion", "review if volatility expands against the short premium structure"),
        ]
    if strategy in DIRECTIONAL_DEBIT_SPREADS:
        return [
            *common,
            _rule("setup_invalidation", "review when the underlying invalidates the directional setup"),
            _rule("time_decay", "review if DTE decay weakens remaining reward/risk"),
        ]
    if strategy in TIME_SPREADS:
        return [
            *common,
            _rule("front_expiration", "review front-leg expiration separately"),
            _rule("term_structure", "review when term structure changes materially"),
        ]
    if strategy in PROTECTION_STRATEGIES:
        return [
            *common,
            _rule("portfolio_drawdown", "review protection if underlying drawdown accelerates"),
            _rule("hedge_cost", "review hedge cost versus remaining protection"),
        ]
    if strategy in COVERED_INCOME_STRATEGIES:
        return [
            *common,
            _rule("assignment_risk", "review short call assignment or call-away risk"),
            _rule("upside_cap", "review whether capped upside is still acceptable"),
        ]
    return common



def _policy_warnings(
    *,
    market_regime: str | None,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
    strategy: str,
) -> list[str]:
    warnings: list[str] = []

    normalized_regime = _clean(market_regime)
    if normalized_regime in {"risk_off", "stagflation", "event_risk"}:
        warnings.append(f"{normalized_regime} regime raises maintenance review priority")

    for policy_name, policy in (
        ("regime", regime_options_policy),
        ("asset_behavior", asset_behavior_options_policy),
        ("option_behavior", option_behavior_options_policy),
    ):
        if not isinstance(policy, Mapping):
            continue
        if _clean(policy.get("status")) == "blocked":
            warnings.append(f"{policy_name} policy is blocked and requires manual review")
        strategy_policy = policy.get("strategy_policy")
        if isinstance(strategy_policy, Mapping):
            blocked = set(_strings(strategy_policy.get("blocked")))
            needs_review = set(_strings(strategy_policy.get("needs_review")))
            if strategy in blocked:
                warnings.append(f"{strategy} is blocked by {policy_name} policy")
            elif strategy in needs_review:
                warnings.append(f"{strategy} requires review under {policy_name} policy")

    return warnings



def _trigger_warnings(*, triggers: Sequence[str], strategy: str) -> list[str]:
    warnings: list[str] = []
    trigger_set = set(triggers)
    if strategy in DIRECTIONAL_CREDIT_SPREADS and "short_strike_tested" in trigger_set:
        warnings.append("credit spread short strike is tested")
    if strategy in NEUTRAL_INCOME_SPREADS and "short_strike_tested" in trigger_set:
        warnings.append("neutral income spread has a challenged side")
    if "loss_review_threshold_reached" in trigger_set:
        warnings.append("position loss threshold requires defense or exit review")
    if "event_risk_review" in trigger_set:
        warnings.append("event risk requires manual confirmation before adjustment")
    return warnings



def _primary_management_objective(*, strategy: str, triggers: Sequence[str]) -> str:
    trigger_set = set(triggers)
    if not trigger_set:
        return "continue_monitoring"
    if "profit_target_reached" in trigger_set:
        return "protect_realized_or_unrealized_profit"
    if strategy in DIRECTIONAL_CREDIT_SPREADS and "short_strike_tested" in trigger_set:
        return "defend_or_reduce_challenged_credit_spread"
    if strategy in NEUTRAL_INCOME_SPREADS and "short_strike_tested" in trigger_set:
        return "defend_tested_side_or_exit_neutral_structure"
    if "loss_review_threshold_reached" in trigger_set:
        return "reduce_loss_risk_or_exit"
    if "expiration_window_reached" in trigger_set:
        return "manage_expiration_risk"
    if "delta_review_threshold_reached" in trigger_set:
        return "review_directional_exposure"
    return "manual_position_review"



def _urgency(*, triggers: Sequence[str], warnings: Sequence[str]) -> str:
    trigger_set = set(triggers)
    if trigger_set.intersection(HIGH_URGENCY_TRIGGERS):
        return "high"
    if any("risk_off" in warning or "event_risk" in warning for warning in warnings):
        return "high"
    if trigger_set.intersection(MEDIUM_URGENCY_TRIGGERS):
        return "medium"
    if warnings:
        return "medium"
    return "low"



def _action(*, action: str, category: str, priority: int, reason: str) -> dict[str, Any]:
    return {
        "action": action,
        "category": category,
        "priority": priority,
        "reason": reason,
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
    }



def _rule(rule: str, description: str) -> dict[str, str]:
    return {"rule": rule, "description": description}



def _rank_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(action)
        for action in sorted(
            actions,
            key=lambda action: (
                int(action.get("priority", 999)),
                _string_or_none(action.get("action")) or "",
            ),
        )
    ]



def _rank_playbooks(playbooks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    urgency_rank = {"high": 0, "medium": 1, "low": 2}
    status_rank = {"blocked": 0, "needs_review": 1, "ready": 2}
    return [
        dict(playbook)
        for playbook in sorted(
            playbooks,
            key=lambda playbook: (
                status_rank.get(_clean(playbook.get("status")) or "ready", 9),
                urgency_rank.get(_clean(playbook.get("urgency")) or "low", 9),
                _string_or_none(playbook.get("symbol")) or "",
                _string_or_none(playbook.get("strategy")) or "",
                _string_or_none(playbook.get("position_id")) or "",
            ),
        )
    ]



def _playbook_set_status(playbooks: Sequence[Mapping[str, Any]]) -> str:
    if any(_clean(playbook.get("status")) == "blocked" for playbook in playbooks):
        return "needs_review"
    if any(_clean(playbook.get("status")) == "needs_review" for playbook in playbooks):
        return "needs_review"
    return "ready"



def _policy_context(
    *,
    regime_options_policy: Mapping[str, Any] | None,
    asset_behavior_options_policy: Mapping[str, Any] | None,
    option_behavior_options_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "regime": _compact_policy(regime_options_policy),
        "asset_behavior": _compact_policy(asset_behavior_options_policy),
        "option_behavior": _compact_policy(option_behavior_options_policy),
    }



def _compact_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {}
    return {
        "artifact_type": policy.get("artifact_type"),
        "status": policy.get("status"),
        "risk_posture": policy.get("risk_posture"),
        "directional_bias": policy.get("directional_bias"),
        "volatility_posture": policy.get("volatility_posture"),
        "warnings": list(_strings(policy.get("warnings"))),
        "blocked_reasons": list(_strings(policy.get("blocked_reasons"))),
    }



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
        "long_strike",
        "long_put_strike",
        "long_call_strike",
        "net_delta",
        "event_risk",
        "assignment_risk",
    ]
    return {key: position[key] for key in keys if key in position}



def _position_list(positions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [position for position in positions if isinstance(position, Mapping)]



def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None



def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None



def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item.strip().lower() for item in value if isinstance(item, str) and item.strip()]



def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None



def _dedupe_strings(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _clean(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result

