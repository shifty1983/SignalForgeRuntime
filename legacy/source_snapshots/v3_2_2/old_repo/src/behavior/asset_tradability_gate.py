from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_TRADABILITY_GATE_SCHEMA_VERSION = "signalforge_asset_tradability_gate.v1"


def build_signalforge_asset_tradability_gate(
    multi_horizon_behavior: Mapping[str, Any] | None,
    relative_rank: Mapping[str, Any] | None,
    *,
    min_observations: int = 50,
    min_price: float = 5.0,
    min_average_volume: float = 250_000.0,
    min_average_dollar_volume: float = 5_000_000.0,
    review_realized_volatility: float = 0.80,
    block_realized_volatility: float = 1.50,
    review_max_drawdown: float = -0.40,
    block_max_drawdown: float = -0.65,
) -> dict[str, Any]:
    """
    Build underlying tradability gates for ranked assets.

    This layer checks whether the underlying instrument is liquid/tradable
    enough to continue toward option behavior. It does not inspect option
    chains yet and performs no broker/execution activity.
    """

    if not isinstance(multi_horizon_behavior, Mapping):
        return _blocked_result("multi-horizon behavior source must be a mapping")

    if not isinstance(relative_rank, Mapping):
        return _blocked_result("relative rank source must be a mapping")

    behavior_items = multi_horizon_behavior.get("instrument_multi_horizon_behaviors")
    if not isinstance(behavior_items, Sequence) or isinstance(
        behavior_items, (str, bytes, bytearray)
    ):
        return _blocked_result(
            "multi-horizon behavior source must contain instrument_multi_horizon_behaviors list"
        )

    relative_items = relative_rank.get("relative_rank_items")
    if not isinstance(relative_items, Sequence) or isinstance(
        relative_items, (str, bytes, bytearray)
    ):
        return _blocked_result(
            "relative rank source must contain relative_rank_items list"
        )

    if not behavior_items:
        return _blocked_result("instrument_multi_horizon_behaviors list is empty")

    if not relative_items:
        return _blocked_result("relative_rank_items list is empty")

    behavior_by_symbol = _behavior_by_symbol(behavior_items)

    tradability_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, item in enumerate(relative_items):
        if not isinstance(item, Mapping):
            skipped_items.append(
                {
                    "reason": "relative rank item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "relative rank item missing symbol",
                    "item_index": index,
                }
            )
            continue

        behavior = behavior_by_symbol.get(symbol)
        if behavior is None:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "reason": "missing multi-horizon behavior for symbol",
                    "item_index": index,
                }
            )
            continue

        tradability_items.append(
            _tradability_item(
                relative=item,
                behavior=behavior,
                symbol=symbol,
                min_observations=min_observations,
                min_price=min_price,
                min_average_volume=min_average_volume,
                min_average_dollar_volume=min_average_dollar_volume,
                review_realized_volatility=review_realized_volatility,
                block_realized_volatility=block_realized_volatility,
                review_max_drawdown=review_max_drawdown,
                block_max_drawdown=block_max_drawdown,
            )
        )

    if not tradability_items:
        return _blocked_result("no tradability gate items were produced")

    if skipped_items:
        warning_items.append(
            {
                "reason": "some symbols were skipped during tradability gate build",
                "skipped_count": len(skipped_items),
            }
        )

    behavior_status = _clean_text(multi_horizon_behavior.get("status"))
    if behavior_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "multi-horizon behavior source is not ready",
                "source_status": behavior_status,
            }
        )

    rank_status = _clean_text(relative_rank.get("status"))
    if rank_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "relative rank source is not ready",
                "source_status": rank_status,
            }
        )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_asset_tradability_gate",
        "schema_version": ASSET_TRADABILITY_GATE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_tradability_gate",
        "adapter_type": "asset_tradability_gate_builder",
        "source_artifacts": {
            "multi_horizon_behavior": multi_horizon_behavior.get("artifact_type"),
            "relative_rank": relative_rank.get("artifact_type"),
        },
        "source_statuses": {
            "multi_horizon_behavior": multi_horizon_behavior.get("status"),
            "relative_rank": relative_rank.get("status"),
        },
        "macro_regime_label": relative_rank.get("macro_regime_label"),
        "policy_regime_label": relative_rank.get("policy_regime_label"),
        "weekly_planning_label": relative_rank.get("weekly_planning_label"),
        "market_confirmation": relative_rank.get("market_confirmation"),
        "aggregate_market_bias": relative_rank.get("aggregate_market_bias"),
        "thresholds": {
            "min_observations": min_observations,
            "min_price": min_price,
            "min_average_volume": min_average_volume,
            "min_average_dollar_volume": min_average_dollar_volume,
            "review_realized_volatility": review_realized_volatility,
            "block_realized_volatility": block_realized_volatility,
            "review_max_drawdown": review_max_drawdown,
            "block_max_drawdown": block_max_drawdown,
        },
        "tradability_gate_items": _sort_tradability_items(tradability_items),
        "tradability_gate_summary": _summary(tradability_items),
        "skipped_items": skipped_items,
        "blocker_items": [],
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _behavior_by_symbol(items: Sequence[Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}

    for item in items:
        if not isinstance(item, Mapping):
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol:
            output[symbol] = item

    return output


def _tradability_item(
    *,
    relative: Mapping[str, Any],
    behavior: Mapping[str, Any],
    symbol: str,
    min_observations: int,
    min_price: float,
    min_average_volume: float,
    min_average_dollar_volume: float,
    review_realized_volatility: float,
    block_realized_volatility: float,
    review_max_drawdown: float,
    block_max_drawdown: float,
) -> dict[str, Any]:
    current_price = _float_or_none(behavior.get("current_price"))
    average_volume = _float_or_none(behavior.get("average_volume"))
    observation_count = int(behavior.get("observation_count") or 0)
    realized_volatility = _float_or_default(behavior.get("realized_volatility"), 0.0)
    max_drawdown = _float_or_default(behavior.get("max_drawdown"), 0.0)

    average_dollar_volume = None
    if current_price is not None and average_volume is not None:
        average_dollar_volume = current_price * average_volume

    reasons: list[str] = []
    review_reasons: list[str] = []
    blocked_reasons: list[str] = []

    if observation_count < min_observations:
        blocked_reasons.append("insufficient_price_history")

    if current_price is None:
        blocked_reasons.append("missing_current_price")
    elif current_price <= 0:
        blocked_reasons.append("invalid_current_price")
    elif current_price < min_price:
        review_reasons.append("low_price")

    if average_volume is None:
        review_reasons.append("missing_average_volume")
    elif average_volume < min_average_volume:
        review_reasons.append("thin_average_volume")

    if average_dollar_volume is None:
        review_reasons.append("missing_average_dollar_volume")
    elif average_dollar_volume < min_average_dollar_volume:
        review_reasons.append("thin_average_dollar_volume")

    if realized_volatility >= block_realized_volatility:
        blocked_reasons.append("extreme_realized_volatility")
    elif realized_volatility >= review_realized_volatility:
        review_reasons.append("high_realized_volatility")

    if max_drawdown <= block_max_drawdown:
        blocked_reasons.append("extreme_drawdown")
    elif max_drawdown <= review_max_drawdown:
        review_reasons.append("large_drawdown")

    if blocked_reasons:
        gate = "blocked"
        state = "blocked_not_tradable"
    elif review_reasons:
        gate = "review_required"
        state = "review_tradability"
    else:
        gate = "allowed"
        state = "tradable"

    if not blocked_reasons and not review_reasons:
        reasons.append("underlying_tradability_thresholds_passed")

    tradability_score = _tradability_score(
        gate=gate,
        current_price=current_price,
        average_volume=average_volume,
        average_dollar_volume=average_dollar_volume,
        realized_volatility=realized_volatility,
        max_drawdown=max_drawdown,
    )

    return {
        "artifact_type": "asset_tradability_gate_item",
        "symbol": symbol,
        "asset_class": _clean_text(relative.get("asset_class")) or "unknown",
        "directional_stance": _clean_text(relative.get("directional_stance")) or "neutral_bias",
        "combined_gate": _clean_text(relative.get("combined_gate")) or "allowed",
        "tradability_gate": gate,
        "tradability_state": state,
        "tradability_score": tradability_score,
        "observation_count": observation_count,
        "current_price": current_price,
        "average_volume": average_volume,
        "average_dollar_volume": round(average_dollar_volume, 2) if average_dollar_volume is not None else None,
        "realized_volatility": round(realized_volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "relative_strength_score": _float_or_default(relative.get("relative_strength_score"), 0.0),
        "relative_weakness_score": _float_or_default(relative.get("relative_weakness_score"), 0.0),
        "direction_fit_score": _float_or_default(relative.get("direction_fit_score"), 0.0),
        "universe_strength_rank": relative.get("universe_strength_rank"),
        "universe_weakness_rank": relative.get("universe_weakness_rank"),
        "asset_class_strength_rank": relative.get("asset_class_strength_rank"),
        "asset_class_weakness_rank": relative.get("asset_class_weakness_rank"),
        "directional_fit_rank": relative.get("directional_fit_rank"),
        "multi_horizon_confirmation": _clean_text(relative.get("multi_horizon_confirmation")),
        "trend_consistency": _clean_text(relative.get("trend_consistency")),
        "review_reasons": review_reasons,
        "blocked_reasons": blocked_reasons,
        "tradability_reasons": reasons,
        "manual_review_required": bool(relative.get("manual_review_required")) or gate != "allowed",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _tradability_score(
    *,
    gate: str,
    current_price: float | None,
    average_volume: float | None,
    average_dollar_volume: float | None,
    realized_volatility: float,
    max_drawdown: float,
) -> float:
    if gate == "blocked":
        base = 0.20
    elif gate == "review_required":
        base = 0.55
    else:
        base = 0.85

    if current_price is not None and current_price >= 20:
        base += 0.03

    if average_volume is not None and average_volume >= 1_000_000:
        base += 0.04

    if average_dollar_volume is not None and average_dollar_volume >= 25_000_000:
        base += 0.04

    if realized_volatility <= 0.35:
        base += 0.03
    elif realized_volatility >= 0.80:
        base -= 0.05

    if max_drawdown >= -0.20:
        base += 0.02
    elif max_drawdown <= -0.40:
        base -= 0.05

    return round(_clamp(base, 0.0, 1.0), 4)


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gate_counts = Counter(str(item.get("tradability_gate") or "unknown") for item in items)
    state_counts = Counter(str(item.get("tradability_state") or "unknown") for item in items)
    asset_class_counts = Counter(str(item.get("asset_class") or "unknown") for item in items)
    stance_counts = Counter(str(item.get("directional_stance") or "unknown") for item in items)

    allowed = [item for item in items if item.get("tradability_gate") == "allowed"]
    review = [item for item in items if item.get("tradability_gate") == "review_required"]
    blocked = [item for item in items if item.get("tradability_gate") == "blocked"]

    return {
        "instrument_count": len(items),
        "tradability_gate_counts": dict(sorted(gate_counts.items())),
        "tradability_state_counts": dict(sorted(state_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "stance_counts": dict(sorted(stance_counts.items())),
        "allowed_count": len(allowed),
        "review_required_count": len(review),
        "blocked_count": len(blocked),
        "top_tradable_symbols": [
            item["symbol"] for item in _sort_tradability_items(allowed)[:25]
        ],
        "review_required_symbols": [
            item["symbol"] for item in _sort_tradability_items(review)[:25]
        ],
        "blocked_symbols": [
            item["symbol"] for item in _sort_tradability_items(blocked)[:25]
        ],
        "top_tradable_long_symbols": [
            item["symbol"]
            for item in _sort_tradability_items(allowed)
            if item.get("directional_stance") == "long_bias"
        ][:25],
        "top_tradable_short_symbols": [
            item["symbol"]
            for item in _sort_tradability_items(allowed)
            if item.get("directional_stance") == "short_bias"
        ][:25],
        "top_tradable_neutral_symbols": [
            item["symbol"]
            for item in _sort_tradability_items(allowed)
            if item.get("directional_stance") == "neutral_bias"
        ][:25],
    }


def _sort_tradability_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("tradability_score"), 0.0),
            -_float_or_default(item.get("direction_fit_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_default(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_tradability_gate",
        "schema_version": ASSET_TRADABILITY_GATE_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_tradability_gate",
        "adapter_type": "asset_tradability_gate_builder",
        "source_artifacts": {},
        "source_statuses": {},
        "thresholds": {},
        "tradability_gate_items": [],
        "tradability_gate_summary": {
            "instrument_count": 0,
            "tradability_gate_counts": {},
            "tradability_state_counts": {},
            "asset_class_counts": {},
            "stance_counts": {},
            "allowed_count": 0,
            "review_required_count": 0,
            "blocked_count": 0,
            "top_tradable_symbols": [],
            "review_required_symbols": [],
            "blocked_symbols": [],
            "top_tradable_long_symbols": [],
            "top_tradable_short_symbols": [],
            "top_tradable_neutral_symbols": [],
        },
        "skipped_items": [],
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
