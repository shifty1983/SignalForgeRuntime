from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_RELATIVE_RANK_SCHEMA_VERSION = "signalforge_asset_relative_rank.v1"


def build_signalforge_asset_relative_rank(
    multi_horizon_behavior: Mapping[str, Any] | None,
    asset_directional_stance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Build relative strength / weakness ranks from multi-horizon behavior.

    This layer ranks instruments against the full universe, their asset class,
    and their directional stance group. It does not create orders, choose
    option strategies, or perform broker/execution activity.
    """

    if not isinstance(multi_horizon_behavior, Mapping):
        return _blocked_result("multi-horizon behavior source must be a mapping")

    if not isinstance(asset_directional_stance, Mapping):
        return _blocked_result("asset directional stance source must be a mapping")

    behavior_items = multi_horizon_behavior.get("instrument_multi_horizon_behaviors")
    if not isinstance(behavior_items, Sequence) or isinstance(
        behavior_items, (str, bytes, bytearray)
    ):
        return _blocked_result(
            "multi-horizon behavior source must contain instrument_multi_horizon_behaviors list"
        )

    stance_items = asset_directional_stance.get("instrument_directional_stances")
    if not isinstance(stance_items, Sequence) or isinstance(
        stance_items, (str, bytes, bytearray)
    ):
        return _blocked_result(
            "asset directional stance source must contain instrument_directional_stances list"
        )

    if not behavior_items:
        return _blocked_result("instrument_multi_horizon_behaviors list is empty")

    if not stance_items:
        return _blocked_result("instrument_directional_stances list is empty")

    stance_by_symbol = _stance_by_symbol(stance_items)
    rank_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, item in enumerate(behavior_items):
        if not isinstance(item, Mapping):
            skipped_items.append(
                {
                    "reason": "multi-horizon behavior item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "multi-horizon behavior item missing symbol",
                    "item_index": index,
                }
            )
            continue

        stance = stance_by_symbol.get(symbol)
        if stance is None:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "reason": "missing directional stance for symbol",
                    "item_index": index,
                }
            )
            continue

        rank_items.append(_base_rank_item(item, stance, symbol=symbol))

    if not rank_items:
        return _blocked_result("no relative-rank items were produced")

    _attach_ranks(rank_items)

    if skipped_items:
        warning_items.append(
            {
                "reason": "some symbols were skipped during relative-rank build",
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

    stance_status = _clean_text(asset_directional_stance.get("status"))
    if stance_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "asset directional stance source is not ready",
                "source_status": stance_status,
            }
        )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_asset_relative_rank",
        "schema_version": ASSET_RELATIVE_RANK_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_relative_rank",
        "adapter_type": "asset_relative_rank_builder",
        "source_artifacts": {
            "multi_horizon_behavior": multi_horizon_behavior.get("artifact_type"),
            "asset_directional_stance": asset_directional_stance.get("artifact_type"),
        },
        "source_statuses": {
            "multi_horizon_behavior": multi_horizon_behavior.get("status"),
            "asset_directional_stance": asset_directional_stance.get("status"),
        },
        "macro_regime_label": asset_directional_stance.get("macro_regime_label"),
        "policy_regime_label": asset_directional_stance.get("policy_regime_label"),
        "weekly_planning_label": asset_directional_stance.get("weekly_planning_label"),
        "market_confirmation": asset_directional_stance.get("market_confirmation"),
        "aggregate_market_bias": asset_directional_stance.get("aggregate_market_bias"),
        "relative_rank_items": _sort_by_relative_strength(rank_items),
        "relative_rank_summary": _summary(rank_items),
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


def _stance_by_symbol(items: Sequence[Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}

    for item in items:
        if not isinstance(item, Mapping):
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol:
            output[symbol] = item

    return output


def _base_rank_item(
    behavior: Mapping[str, Any],
    stance: Mapping[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    horizon_profiles = behavior.get("horizon_profiles")
    if not isinstance(horizon_profiles, Mapping):
        horizon_profiles = {}

    h20 = _horizon_return(horizon_profiles, "20")
    h50 = _horizon_return(horizon_profiles, "50")
    h100 = _horizon_return(horizon_profiles, "100")
    h200 = _horizon_return(horizon_profiles, "200")

    weighted_return_score = _weighted_return_score(
        {
            "20": h20,
            "50": h50,
            "100": h100,
            "200": h200,
        }
    )

    realized_volatility = _float_or_default(behavior.get("realized_volatility"), 0.0)
    volatility_adjusted_score = _volatility_adjusted_score(
        weighted_return_score,
        realized_volatility,
    )

    confirmation = _clean_text(behavior.get("multi_horizon_confirmation")) or "unknown"
    trend_consistency = _clean_text(behavior.get("trend_consistency")) or "unknown"

    confirmation_bonus = _confirmation_bonus(confirmation)
    consistency_bonus = _consistency_bonus(trend_consistency)

    relative_strength_score = _clamp(
        volatility_adjusted_score + confirmation_bonus + consistency_bonus,
        -1.0,
        1.0,
    )
    relative_weakness_score = _clamp(-relative_strength_score, -1.0, 1.0)

    directional_stance = _clean_text(stance.get("directional_stance")) or "neutral_bias"
    combined_gate = _clean_text(stance.get("combined_gate")) or "allowed"
    manual_review_required = bool(stance.get("manual_review_required"))

    direction_fit_score = _direction_fit_score(
        directional_stance=directional_stance,
        relative_strength_score=relative_strength_score,
        relative_weakness_score=relative_weakness_score,
    )

    return {
        "artifact_type": "asset_relative_rank_item",
        "symbol": symbol,
        "asset_class": _clean_text(stance.get("asset_class")) or "unknown",
        "directional_stance": directional_stance,
        "combined_gate": combined_gate,
        "manual_review_required": manual_review_required,
        "multi_horizon_confirmation": confirmation,
        "trend_consistency": trend_consistency,
        "relative_strength_score": round(relative_strength_score, 6),
        "relative_weakness_score": round(relative_weakness_score, 6),
        "direction_fit_score": round(direction_fit_score, 6),
        "weighted_return_score": round(weighted_return_score, 6),
        "volatility_adjusted_score": round(volatility_adjusted_score, 6),
        "realized_volatility": round(realized_volatility, 6),
        "max_drawdown": _float_or_default(behavior.get("max_drawdown"), 0.0),
        "total_return": _float_or_default(behavior.get("total_return"), 0.0),
        "horizon_returns": {
            "20": h20,
            "50": h50,
            "100": h100,
            "200": h200,
        },
        "positive_horizon_count": int(behavior.get("positive_horizon_count") or 0),
        "negative_horizon_count": int(behavior.get("negative_horizon_count") or 0),
        "neutral_horizon_count": int(behavior.get("neutral_horizon_count") or 0),
        "insufficient_horizon_count": int(
            behavior.get("insufficient_horizon_count") or 0
        ),
        "stance_alignment": _clean_text(stance.get("stance_alignment")) or "unknown",
        "behavior_directional_stance": _clean_text(
            stance.get("behavior_directional_stance")
        ),
        "regime_directional_stance": _clean_text(
            stance.get("regime_directional_stance")
        ),
        "selection_bucket": _clean_text(stance.get("selection_bucket")),
        "regime_policy_bucket": _clean_text(stance.get("regime_policy_bucket")),
        "conflict_reasons": list(stance.get("conflict_reasons") or []),
        "stance_reasons": list(stance.get("stance_reasons") or []),
        "relative_rank_reasons": _relative_rank_reasons(
            confirmation=confirmation,
            trend_consistency=trend_consistency,
            directional_stance=directional_stance,
            combined_gate=combined_gate,
        ),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _attach_ranks(items: list[dict[str, Any]]) -> None:
    _attach_group_ranks(
        items,
        group_key=None,
        score_key="relative_strength_score",
        rank_key="universe_strength_rank",
        percentile_key="universe_strength_percentile",
        descending=True,
    )
    _attach_group_ranks(
        items,
        group_key=None,
        score_key="relative_weakness_score",
        rank_key="universe_weakness_rank",
        percentile_key="universe_weakness_percentile",
        descending=True,
    )
    _attach_group_ranks(
        items,
        group_key="asset_class",
        score_key="relative_strength_score",
        rank_key="asset_class_strength_rank",
        percentile_key="asset_class_strength_percentile",
        descending=True,
    )
    _attach_group_ranks(
        items,
        group_key="asset_class",
        score_key="relative_weakness_score",
        rank_key="asset_class_weakness_rank",
        percentile_key="asset_class_weakness_percentile",
        descending=True,
    )
    _attach_group_ranks(
        items,
        group_key="directional_stance",
        score_key="direction_fit_score",
        rank_key="directional_fit_rank",
        percentile_key="directional_fit_percentile",
        descending=True,
    )


def _attach_group_ranks(
    items: list[dict[str, Any]],
    *,
    group_key: str | None,
    score_key: str,
    rank_key: str,
    percentile_key: str,
    descending: bool,
) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        group = "__universe__" if group_key is None else str(item.get(group_key) or "unknown")
        groups[group].append(item)

    for group_items in groups.values():
        ranked = sorted(
            group_items,
            key=lambda item: (
                _float_or_default(item.get(score_key), 0.0),
                str(item.get("symbol")),
            ),
            reverse=descending,
        )

        count = len(ranked)

        for index, item in enumerate(ranked, start=1):
            item[rank_key] = index
            item[percentile_key] = _rank_percentile(index, count)


def _rank_percentile(rank: int, count: int) -> float:
    if count <= 1:
        return 1.0

    return round(1.0 - ((rank - 1) / (count - 1)), 6)


def _weighted_return_score(horizon_returns: Mapping[str, float | None]) -> float:
    weights = {
        "20": 0.40,
        "50": 0.30,
        "100": 0.20,
        "200": 0.10,
    }

    numerator = 0.0
    denominator = 0.0

    for horizon, weight in weights.items():
        value = horizon_returns.get(horizon)
        if value is None:
            continue

        numerator += value * weight
        denominator += weight

    if denominator == 0:
        return 0.0

    return numerator / denominator


def _volatility_adjusted_score(
    weighted_return_score: float,
    realized_volatility: float,
) -> float:
    if realized_volatility <= 0:
        return _clamp(weighted_return_score, -1.0, 1.0)

    return _clamp(weighted_return_score / max(realized_volatility, 0.05), -1.0, 1.0)


def _direction_fit_score(
    *,
    directional_stance: str,
    relative_strength_score: float,
    relative_weakness_score: float,
) -> float:
    if directional_stance == "long_bias":
        return relative_strength_score

    if directional_stance == "short_bias":
        return relative_weakness_score

    return 1.0 - abs(relative_strength_score)


def _confirmation_bonus(value: str) -> float:
    return {
        "confirmed_uptrend": 0.12,
        "developing_uptrend": 0.06,
        "confirmed_downtrend": -0.12,
        "developing_downtrend": -0.06,
        "confirmed_neutral": 0.0,
        "choppy_neutral": -0.02,
        "mixed_or_transitioning": -0.04,
        "insufficient_history": -0.10,
    }.get(value, 0.0)


def _consistency_bonus(value: str) -> float:
    return {
        "consistent_positive": 0.08,
        "consistent_negative": -0.08,
        "consistent_neutral": 0.0,
        "partially_consistent": -0.02,
        "conflicting": -0.08,
        "insufficient": -0.10,
    }.get(value, 0.0)


def _relative_rank_reasons(
    *,
    confirmation: str,
    trend_consistency: str,
    directional_stance: str,
    combined_gate: str,
) -> list[str]:
    return [
        f"multi_horizon_confirmation:{confirmation}",
        f"trend_consistency:{trend_consistency}",
        f"directional_stance:{directional_stance}",
        f"combined_gate:{combined_gate}",
    ]


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stance_counts = Counter(str(item.get("directional_stance") or "unknown") for item in items)
    gate_counts = Counter(str(item.get("combined_gate") or "unknown") for item in items)
    asset_class_counts = Counter(str(item.get("asset_class") or "unknown") for item in items)
    confirmation_counts = Counter(
        str(item.get("multi_horizon_confirmation") or "unknown") for item in items
    )

    sorted_strength = _sort_by_relative_strength(items)
    sorted_weakness = _sort_by_relative_weakness(items)
    sorted_direction_fit = _sort_by_direction_fit(items)

    return {
        "instrument_count": len(items),
        "stance_counts": dict(sorted(stance_counts.items())),
        "gate_counts": dict(sorted(gate_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "confirmation_counts": dict(sorted(confirmation_counts.items())),
        "top_universe_strength_symbols": [
            item["symbol"] for item in sorted_strength[:25]
        ],
        "top_universe_weakness_symbols": [
            item["symbol"] for item in sorted_weakness[:25]
        ],
        "top_direction_fit_symbols": [
            item["symbol"] for item in sorted_direction_fit[:25]
        ],
        "top_long_relative_strength_symbols": [
            item["symbol"]
            for item in sorted_strength
            if item.get("directional_stance") == "long_bias"
        ][:25],
        "top_short_relative_weakness_symbols": [
            item["symbol"]
            for item in sorted_weakness
            if item.get("directional_stance") == "short_bias"
        ][:25],
        "top_neutral_stability_symbols": [
            item["symbol"]
            for item in sorted_direction_fit
            if item.get("directional_stance") == "neutral_bias"
        ][:25],
        "review_required_count": gate_counts.get("review_required", 0),
        "blocked_count": gate_counts.get("blocked", 0),
    }


def _sort_by_relative_strength(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("relative_strength_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _sort_by_relative_weakness(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("relative_weakness_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _sort_by_direction_fit(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("direction_fit_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _horizon_return(
    horizon_profiles: Mapping[str, Any],
    horizon: str,
) -> float | None:
    profile = horizon_profiles.get(horizon)
    if not isinstance(profile, Mapping):
        return None

    return _float_or_none(profile.get("return"))


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
        "artifact_type": "signalforge_asset_relative_rank",
        "schema_version": ASSET_RELATIVE_RANK_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_relative_rank",
        "adapter_type": "asset_relative_rank_builder",
        "source_artifacts": {},
        "source_statuses": {},
        "relative_rank_items": [],
        "relative_rank_summary": {
            "instrument_count": 0,
            "stance_counts": {},
            "gate_counts": {},
            "asset_class_counts": {},
            "confirmation_counts": {},
            "top_universe_strength_symbols": [],
            "top_universe_weakness_symbols": [],
            "top_direction_fit_symbols": [],
            "top_long_relative_strength_symbols": [],
            "top_short_relative_weakness_symbols": [],
            "top_neutral_stability_symbols": [],
            "review_required_count": 0,
            "blocked_count": 0,
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
