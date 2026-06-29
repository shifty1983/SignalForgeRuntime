"""Scheduled risk monitor for open defined-risk options positions.

The weekly portfolio review is a planning artifact. This module is the weekday
counterpart: it combines the latest market/option snapshot with existing option
positions, detects maintenance/defense triggers, and then routes those triggered
positions into the options strategy defense review pipeline.

It is intentionally alert/review only. It does not create broker orders, route
orders, submit orders, model fills, perform live execution, or automatically
close/roll/defend positions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from src.position_maintenance.defense_review import build_options_strategy_defense_review

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

VALID_MONITOR_STATUSES = {"ready", "needs_review", "blocked"}

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

BULLISH_STRATEGIES = {
    "bull_call_debit_spread",
    "put_credit_spread",
    "bull_put_credit_spread",
    "covered_call",
    "collar",
}

BEARISH_STRATEGIES = {
    "bear_put_debit_spread",
    "call_credit_spread",
    "bear_call_credit_spread",
}

PUT_SHORT_STRIKE_STRATEGIES = {
    "put_credit_spread",
    "bull_put_credit_spread",
}

CALL_SHORT_STRIKE_STRATEGIES = {
    "call_credit_spread",
    "bear_call_credit_spread",
    "covered_call",
}

RANGE_SHORT_STRIKE_STRATEGIES = {
    "iron_condor",
    "iron_butterfly",
}

DEFAULT_THRESHOLDS = {
    "profit_target_pct": 0.50,
    "loss_review_pct": -0.50,
    "expiration_window_dte": 21,
    "delta_abs_threshold": 0.35,
    "iv_expansion_pct": 0.25,
    "short_strike_buffer_pct": 0.0,
}


def build_options_position_risk_monitor(source: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a scheduled/intraday risk monitor artifact for open options positions.

    Parameters
    ----------
    source:
        Mapping with keys such as:
        - evaluation_timestamp
        - plan_date
        - market_regime
        - positions
        - latest_market_data or market_data
        - thresholds
        - max_candidates_per_position

    Returns
    -------
    dict
        Review-only monitor artifact containing triggered positions, monitor-only
        positions, risk alerts, and a nested options strategy defense review.
    """

    if not isinstance(source, Mapping):
        return _blocked_monitor(
            evaluation_timestamp=None,
            plan_date=None,
            blocked_reasons=["source must be a mapping"],
        )

    evaluation_timestamp = _string_or_none(source.get("evaluation_timestamp"))
    plan_date = _string_or_none(source.get("plan_date")) or _date_from_timestamp(evaluation_timestamp)
    positions = source.get("positions")
    max_candidates_per_position = _optional_non_negative_int(
        source.get("max_candidates_per_position")
    )

    errors = _validate_source(
        evaluation_timestamp=evaluation_timestamp,
        plan_date=plan_date,
        positions=positions,
        max_candidates_per_position=max_candidates_per_position,
    )
    if errors:
        return _blocked_monitor(
            evaluation_timestamp=evaluation_timestamp,
            plan_date=plan_date,
            blocked_reasons=errors,
        )

    assert isinstance(positions, Sequence) and not isinstance(positions, (str, bytes))

    thresholds = _thresholds(source.get("thresholds"))
    market_data = _market_data_index(
        source.get("latest_market_data")
        or source.get("market_data")
        or source.get("latest_quotes")
        or {},
    )

    enriched_positions: list[dict[str, Any]] = []
    triggered_positions: list[dict[str, Any]] = []
    monitor_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for raw_position in positions:
        assert isinstance(raw_position, Mapping)
        enriched = _enriched_position(
            position=raw_position,
            market_data=market_data,
            thresholds=thresholds,
            evaluation_timestamp=evaluation_timestamp,
        )
        enriched_positions.append(enriched)
        warnings.extend(_strings(enriched.get("warnings")))

        if _strings(enriched.get("blocked_reasons")):
            blocked_items.append(_blocked_item_from_position(enriched))
        elif _strings(enriched.get("review_triggers")):
            triggered_positions.append(enriched)
        else:
            monitor_items.append(_monitor_item_from_position(enriched))

    defense_review = build_options_strategy_defense_review(
        enriched_positions,
        plan_date=plan_date or "",
        market_regime=_string_or_none(source.get("market_regime")),
        regime_options_policy=_mapping_or_none(source.get("regime_options_policy")),
        asset_behavior_options_policy=_mapping_or_none(source.get("asset_behavior_options_policy")),
        option_behavior_options_policy=_mapping_or_none(source.get("option_behavior_options_policy")),
        max_candidates_per_position=max_candidates_per_position,
    )

    risk_alerts = _risk_alerts_from_defense_review(defense_review)
    defense_blocked_items = _list_of_mappings(defense_review.get("blocked_items"))
    blocked_items.extend(defense_blocked_items)

    status = _monitor_status(
        risk_alerts=risk_alerts,
        blocked_items=blocked_items,
        defense_review=defense_review,
    )

    return {
        "artifact_type": "options_position_risk_monitor",
        "status": status,
        "is_ready": status == "ready",
        "monitor_mode": "scheduled_position_risk_monitor",
        "evaluation_timestamp": evaluation_timestamp,
        "plan_date": plan_date,
        "market_regime": _string_or_none(source.get("market_regime")),
        "position_count": len(enriched_positions),
        "triggered_position_count": len(triggered_positions),
        "risk_alert_count": len(risk_alerts),
        "manual_review_count": len(risk_alerts),
        "monitor_item_count": len(monitor_items),
        "blocked_count": len(blocked_items),
        "risk_alerts": _rank_risk_alerts(risk_alerts),
        "triggered_positions": _rank_positions(triggered_positions),
        "monitor_items": _rank_monitor_items(monitor_items),
        "blocked_items": _rank_blocked_items(blocked_items),
        "position_snapshots": _rank_positions(enriched_positions),
        "trigger_summary": _trigger_summary(enriched_positions),
        "urgency_summary": _urgency_summary(risk_alerts=risk_alerts, monitor_items=monitor_items),
        "defense_review": defense_review,
        "thresholds": thresholds,
        "warnings": _dedupe_strings([*warnings, *_strings(defense_review.get("warnings"))]),
        "blocked_reasons": _dedupe_strings(
            [
                *_blocked_reasons_from_items(blocked_items),
                *_strings(defense_review.get("blocked_reasons")),
            ]
        ),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": list(EXPLICIT_EXCLUSIONS),
    }


def _validate_source(
    *,
    evaluation_timestamp: str | None,
    plan_date: str | None,
    positions: Any,
    max_candidates_per_position: int | None,
) -> list[str]:
    errors: list[str] = []
    if not evaluation_timestamp:
        errors.append("evaluation_timestamp is required")
    if not plan_date:
        errors.append("plan_date is required or must be derivable from evaluation_timestamp")
    if positions is None:
        errors.append("positions are required")
    elif isinstance(positions, (str, bytes)) or not isinstance(positions, Sequence):
        errors.append("positions must be a sequence")
    elif not all(isinstance(position, Mapping) for position in positions):
        errors.append("positions must contain only mappings")
    if max_candidates_per_position is not None and max_candidates_per_position < 0:
        errors.append("max_candidates_per_position must be greater than or equal to zero")
    return errors


def _blocked_monitor(
    *,
    evaluation_timestamp: str | None,
    plan_date: str | None,
    blocked_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "options_position_risk_monitor",
        "status": "blocked",
        "is_ready": False,
        "monitor_mode": "scheduled_position_risk_monitor",
        "evaluation_timestamp": _string_or_none(evaluation_timestamp),
        "plan_date": _string_or_none(plan_date),
        "market_regime": None,
        "position_count": 0,
        "triggered_position_count": 0,
        "risk_alert_count": 0,
        "manual_review_count": 0,
        "monitor_item_count": 0,
        "blocked_count": 0,
        "risk_alerts": [],
        "triggered_positions": [],
        "monitor_items": [],
        "blocked_items": [],
        "position_snapshots": [],
        "trigger_summary": {},
        "urgency_summary": {"high": 0, "medium": 0, "low": 0},
        "defense_review": None,
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "requires_manual_approval": True,
        "order_intent": None,
        "automatic_action": None,
        "excluded": list(EXPLICIT_EXCLUSIONS),
    }


def _enriched_position(
    *,
    position: Mapping[str, Any],
    market_data: Mapping[str, Mapping[str, Any]],
    thresholds: Mapping[str, float],
    evaluation_timestamp: str | None,
) -> dict[str, Any]:
    symbol = _string_or_none(position.get("symbol"))
    strategy = _clean(position.get("strategy"))
    position_id = _string_or_none(position.get("position_id")) or _fallback_position_id(
        symbol=symbol,
        strategy=strategy,
    )
    quote = _quote_for_position(
        market_data=market_data,
        position_id=position_id,
        symbol=symbol,
    )
    merged = {**dict(position), **quote}

    triggers = _dedupe_strings(
        [
            *_strings(position.get("review_triggers")),
            *_strings(position.get("triggered_conditions")),
            *_derived_triggers(position=merged, thresholds=thresholds),
        ]
    )
    warnings = _position_warnings(position=merged, quote=quote)
    blocked_reasons = _position_blocked_reasons(position=merged)

    return {
        **merged,
        "position_id": position_id,
        "symbol": symbol,
        "strategy": strategy,
        "evaluation_timestamp": evaluation_timestamp,
        "review_triggers": triggers,
        "risk_urgency": _urgency(triggers),
        "latest_market_snapshot": _latest_market_snapshot(merged),
        "warnings": _dedupe_strings([*_strings(position.get("warnings")), *warnings]),
        "blocked_reasons": _dedupe_strings(
            [*_strings(position.get("blocked_reasons")), *blocked_reasons]
        ),
    }


def _derived_triggers(*, position: Mapping[str, Any], thresholds: Mapping[str, float]) -> list[str]:
    triggers: list[str] = []
    strategy = _clean(position.get("strategy"))
    underlying_price = _float_or_none(position.get("underlying_price") or position.get("price"))
    short_strike = _float_or_none(position.get("short_strike"))
    lower_short_strike = _float_or_none(
        position.get("lower_short_strike") or position.get("put_short_strike")
    )
    upper_short_strike = _float_or_none(
        position.get("upper_short_strike") or position.get("call_short_strike")
    )
    dte = _float_or_none(position.get("days_to_expiration") or position.get("dte"))
    pnl_pct = _pnl_pct(position)
    net_delta = _float_or_none(
        position.get("net_delta")
        or position.get("position_delta")
        or position.get("delta")
    )
    iv_change_pct = _float_or_none(
        position.get("iv_change_pct")
        or position.get("implied_volatility_change_pct")
    )
    invalidation_price = _float_or_none(position.get("invalidation_price"))

    if dte is not None and dte <= thresholds["expiration_window_dte"]:
        triggers.append("expiration_window_reached")
    if pnl_pct is not None and pnl_pct >= thresholds["profit_target_pct"]:
        triggers.append("profit_target_reached")
    if pnl_pct is not None and pnl_pct <= thresholds["loss_review_pct"]:
        triggers.append("loss_review_threshold_reached")
    if net_delta is not None and abs(net_delta) >= thresholds["delta_abs_threshold"]:
        triggers.append("delta_review_threshold_reached")
    if iv_change_pct is not None and iv_change_pct >= thresholds["iv_expansion_pct"]:
        triggers.append("iv_expansion_review")
    if _truthy(position.get("event_risk") or position.get("event_risk_review")):
        triggers.append("event_risk_review")
    if _truthy(position.get("assignment_risk") or position.get("assignment_risk_review")):
        triggers.append("assignment_risk_review")
    if _short_strike_tested(
        strategy=strategy,
        underlying_price=underlying_price,
        short_strike=short_strike,
        lower_short_strike=lower_short_strike,
        upper_short_strike=upper_short_strike,
        buffer_pct=thresholds["short_strike_buffer_pct"],
    ):
        triggers.append("short_strike_tested")
    if _setup_invalidated(
        strategy=strategy,
        underlying_price=underlying_price,
        invalidation_price=invalidation_price,
    ):
        triggers.append("setup_invalidation_review")
    return _dedupe_strings(triggers)


def _short_strike_tested(
    *,
    strategy: str | None,
    underlying_price: float | None,
    short_strike: float | None,
    lower_short_strike: float | None,
    upper_short_strike: float | None,
    buffer_pct: float,
) -> bool:
    if underlying_price is None or not strategy:
        return False
    if strategy in PUT_SHORT_STRIKE_STRATEGIES and short_strike is not None:
        return underlying_price <= short_strike * (1.0 + buffer_pct)
    if strategy in CALL_SHORT_STRIKE_STRATEGIES and short_strike is not None:
        return underlying_price >= short_strike * (1.0 - buffer_pct)
    if strategy in RANGE_SHORT_STRIKE_STRATEGIES:
        if lower_short_strike is not None and underlying_price <= lower_short_strike * (1.0 + buffer_pct):
            return True
        if upper_short_strike is not None and underlying_price >= upper_short_strike * (1.0 - buffer_pct):
            return True
    return False


def _setup_invalidated(
    *,
    strategy: str | None,
    underlying_price: float | None,
    invalidation_price: float | None,
) -> bool:
    if not strategy or underlying_price is None or invalidation_price is None:
        return False
    if strategy in BULLISH_STRATEGIES:
        return underlying_price <= invalidation_price
    if strategy in BEARISH_STRATEGIES:
        return underlying_price >= invalidation_price
    return False


def _pnl_pct(position: Mapping[str, Any]) -> float | None:
    direct = _float_or_none(
        position.get("unrealized_pnl_pct")
        or position.get("pnl_pct")
        or position.get("profit_loss_pct")
    )
    if direct is not None:
        return direct

    entry = _float_or_none(
        position.get("entry_mark")
        or position.get("entry_debit")
        or position.get("entry_credit")
    )
    current = _float_or_none(
        position.get("current_mark")
        or position.get("mark")
        or position.get("option_mark")
    )
    side = _clean(position.get("mark_side") or position.get("position_side"))
    if entry is None or current is None or entry == 0:
        return None

    if side == "credit" or _clean(position.get("strategy")) in {
        "put_credit_spread",
        "bull_put_credit_spread",
        "call_credit_spread",
        "bear_call_credit_spread",
        "iron_condor",
        "iron_butterfly",
        "covered_call",
    }:
        return (entry - current) / abs(entry)
    return (current - entry) / abs(entry)


def _risk_alerts_from_defense_review(defense_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = _list_of_mappings(defense_review.get("review_candidates"))
    alerts: list[dict[str, Any]] = []
    for candidate in candidates:
        alerts.append(
            {
                "alert_type": "manual_defense_review",
                "urgency": _clean(candidate.get("urgency")) or "medium",
                "symbol": _string_or_none(candidate.get("symbol")),
                "position_id": _string_or_none(candidate.get("position_id")),
                "strategy": _clean(candidate.get("strategy")),
                "candidate_action": _string_or_none(candidate.get("candidate_action") or candidate.get("action")),
                "reason": _string_or_none(candidate.get("reason")) or _string_or_none(candidate.get("candidate_reason")),
                "review_triggers": _strings(candidate.get("review_triggers")),
                "requires_manual_approval": True,
                "order_intent": None,
                "automatic_action": None,
            }
        )
    return alerts


def _monitor_item_from_position(position: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _string_or_none(position.get("symbol")),
        "position_id": _string_or_none(position.get("position_id")),
        "strategy": _clean(position.get("strategy")),
        "urgency": "low",
        "monitor_reason": "no maintenance or defense trigger detected",
        "latest_market_snapshot": dict(position.get("latest_market_snapshot", {}))
        if isinstance(position.get("latest_market_snapshot"), Mapping)
        else {},
    }


def _blocked_item_from_position(position: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _string_or_none(position.get("symbol")),
        "position_id": _string_or_none(position.get("position_id")),
        "strategy": _clean(position.get("strategy")),
        "blocked_reasons": _strings(position.get("blocked_reasons")),
    }


def _monitor_status(
    *,
    risk_alerts: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
    defense_review: Mapping[str, Any],
) -> str:
    defense_status = _clean(defense_review.get("status"))
    if blocked_items and not risk_alerts:
        return "blocked"
    if risk_alerts or blocked_items or defense_status == "needs_review":
        return "needs_review"
    if defense_status == "blocked":
        return "blocked"
    return "ready"


def _thresholds(value: Any) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    if isinstance(value, Mapping):
        for key in DEFAULT_THRESHOLDS:
            override = _float_or_none(value.get(key))
            if override is not None:
                thresholds[key] = override
    return thresholds


def _market_data_index(value: Any) -> dict[str, Mapping[str, Any]]:
    if not value:
        return {}
    if isinstance(value, Mapping):
        indexed: dict[str, Mapping[str, Any]] = {}
        for key, quote in value.items():
            if isinstance(quote, Mapping):
                indexed[str(key)] = quote
        return indexed
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        indexed = {}
        for quote in value:
            if not isinstance(quote, Mapping):
                continue
            for key in (
                quote.get("position_id"),
                quote.get("symbol"),
                quote.get("underlying"),
            ):
                key_string = _string_or_none(key)
                if key_string:
                    indexed[key_string] = quote
        return indexed
    return {}


def _quote_for_position(
    *,
    market_data: Mapping[str, Mapping[str, Any]],
    position_id: str | None,
    symbol: str | None,
) -> Mapping[str, Any]:
    if position_id and position_id in market_data:
        return market_data[position_id]
    if symbol and symbol in market_data:
        return market_data[symbol]
    return {}


def _position_warnings(*, position: Mapping[str, Any], quote: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not quote:
        warnings.append("latest market data missing for position; using position snapshot values")
    if _float_or_none(position.get("bid_ask_spread_pct")) is not None:
        spread = _float_or_none(position.get("bid_ask_spread_pct"))
        if spread is not None and spread >= 0.20:
            warnings.append("wide option spread review")
    return warnings


def _position_blocked_reasons(position: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _string_or_none(position.get("symbol")):
        reasons.append("position symbol is required")
    if not _clean(position.get("strategy")):
        reasons.append("position strategy is required")
    return reasons


def _latest_market_snapshot(position: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "underlying_price",
        "price",
        "bid",
        "ask",
        "mark",
        "current_mark",
        "option_mark",
        "days_to_expiration",
        "dte",
        "delta",
        "net_delta",
        "bid_ask_spread_pct",
        "implied_volatility",
        "iv_change_pct",
        "event_risk",
    ]
    return {key: position[key] for key in keys if key in position}


def _trigger_summary(positions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for position in positions:
        for trigger in _strings(position.get("review_triggers")):
            summary[trigger] = summary.get(trigger, 0) + 1
    return dict(sorted(summary.items()))


def _urgency_summary(
    *,
    risk_alerts: Sequence[Mapping[str, Any]],
    monitor_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    summary = {"high": 0, "medium": 0, "low": 0}
    for alert in risk_alerts:
        urgency = _clean(alert.get("urgency")) or "medium"
        if urgency in summary:
            summary[urgency] += 1
    summary["low"] += len(monitor_items)
    return summary


def _urgency(triggers: Sequence[str]) -> str:
    trigger_set = set(triggers)
    if trigger_set & HIGH_URGENCY_TRIGGERS:
        return "high"
    if trigger_set & MEDIUM_URGENCY_TRIGGERS:
        return "medium"
    return "low"


def _rank_risk_alerts(alerts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    urgency_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        [dict(alert) for alert in alerts],
        key=lambda item: (
            urgency_rank.get(_clean(item.get("urgency")) or "medium", 1),
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
            _string_or_none(item.get("candidate_action")) or "",
        ),
    )


def _rank_positions(positions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    urgency_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        [dict(position) for position in positions],
        key=lambda item: (
            urgency_rank.get(_clean(item.get("risk_urgency")) or "low", 2),
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
        ),
    )


def _rank_monitor_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
        ),
    )


def _rank_blocked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            _string_or_none(item.get("symbol")) or "",
            _string_or_none(item.get("position_id")) or "",
            _clean(item.get("strategy")) or "",
        ),
    )


def _blocked_reasons_from_items(items: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in items:
        reasons.extend(_strings(item.get("blocked_reasons")))
    return reasons


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return -1
    return number


def _date_from_timestamp(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    if "T" in timestamp:
        return timestamp.split("T", 1)[0]
    try:
        return datetime.fromisoformat(timestamp).date().isoformat()
    except ValueError:
        return None


def _fallback_position_id(*, symbol: str | None, strategy: str | None) -> str:
    return "_".join(part for part in [symbol, strategy] if part) or "unknown_position"


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean(value: Any) -> str | None:
    text = _string_or_none(value)
    return text.lower() if text else None


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "review"}
    return bool(value)


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

