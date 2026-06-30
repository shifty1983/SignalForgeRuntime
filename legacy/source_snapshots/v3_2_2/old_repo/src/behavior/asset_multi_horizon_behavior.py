from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_MULTI_HORIZON_BEHAVIOR_SCHEMA_VERSION = (
    "signalforge_asset_multi_horizon_behavior.v1"
)

DEFAULT_HORIZONS = (20, 50, 100, 200)
DIRECTION_STATES = {
    "positive_trend",
    "negative_trend",
    "neutral_trend",
    "insufficient_history",
}


def build_signalforge_asset_multi_horizon_behavior(
    source: Mapping[str, Any] | None,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    annualization_factor: int = 252,
    positive_return_threshold: float = 0.02,
    negative_return_threshold: float = -0.02,
) -> dict[str, Any]:
    """
    Build multi-horizon behavior confirmation from market price history.

    This layer does not choose trades or strategies. It confirms whether
    each instrument behavior is consistent across short, medium, and long
    horizons.

    It performs no broker API calls, order routing, order submission, fills,
    live execution, slippage modeling, or automatic strategy/parameter/pause
    changes.
    """

    if not isinstance(source, Mapping):
        return _blocked_result("market price history source must be a mapping")

    rows = _extract_price_rows(source)
    if not rows:
        return _blocked_result("market price history source contains no price rows")

    clean_horizons = _clean_horizons(horizons)
    if not clean_horizons:
        return _blocked_result("at least one positive horizon is required")

    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        normalized = _normalize_price_row(row)
        if normalized is None:
            skipped_rows.append(
                {
                    "reason": "price row missing symbol, timestamp, or price",
                    "row_index": index,
                }
            )
            continue

        rows_by_symbol[normalized["symbol"]].append(normalized)

    if not rows_by_symbol:
        return _blocked_result("no usable symbol price histories were produced")

    instrument_behaviors: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for symbol in sorted(rows_by_symbol):
        history = sorted(
            rows_by_symbol[symbol],
            key=lambda item: item["timestamp_sort_key"],
        )

        if len(history) < 2:
            warning_items.append(
                {
                    "symbol": symbol,
                    "reason": "symbol has fewer than two usable price rows",
                }
            )
            continue

        instrument_behaviors.append(
            _build_symbol_behavior(
                symbol=symbol,
                history=history,
                horizons=clean_horizons,
                annualization_factor=annualization_factor,
                positive_return_threshold=positive_return_threshold,
                negative_return_threshold=negative_return_threshold,
            )
        )

    if not instrument_behaviors:
        return _blocked_result("no multi-horizon behavior records were produced")

    if skipped_rows:
        warning_items.append(
            {
                "reason": "some price rows were skipped",
                "skipped_row_count": len(skipped_rows),
            }
        )

    source_status = _clean_text(source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "market price history source is not ready",
                "source_status": source_status,
            }
        )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_asset_multi_horizon_behavior",
        "schema_version": ASSET_MULTI_HORIZON_BEHAVIOR_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_multi_horizon_behavior",
        "adapter_type": "asset_multi_horizon_behavior_builder",
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "horizons": list(clean_horizons),
        "annualization_factor": annualization_factor,
        "positive_return_threshold": positive_return_threshold,
        "negative_return_threshold": negative_return_threshold,
        "instrument_multi_horizon_behaviors": instrument_behaviors,
        "multi_horizon_summary": _summary(instrument_behaviors),
        "skipped_rows": skipped_rows,
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


def _build_symbol_behavior(
    *,
    symbol: str,
    history: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
    annualization_factor: int,
    positive_return_threshold: float,
    negative_return_threshold: float,
) -> dict[str, Any]:
    prices = [float(item["price"]) for item in history]
    volumes = [
        item.get("volume")
        for item in history
        if isinstance(item.get("volume"), (int, float))
    ]

    current_price = prices[-1]
    first_price = prices[0]
    total_return = _safe_return(first_price, current_price)

    horizon_profiles: dict[str, Any] = {}

    for horizon in horizons:
        horizon_profiles[str(horizon)] = _horizon_profile(
            prices=prices,
            history=history,
            horizon=horizon,
            annualization_factor=annualization_factor,
            positive_return_threshold=positive_return_threshold,
            negative_return_threshold=negative_return_threshold,
        )

    confirmation = _confirmation_state(horizon_profiles, horizons)
    trend_consistency = _trend_consistency(horizon_profiles)

    return {
        "symbol": symbol,
        "observation_count": len(history),
        "start": history[0]["timestamp"],
        "end": history[-1]["timestamp"],
        "current_price": round(current_price, 6),
        "first_price": round(first_price, 6),
        "total_return": round(total_return, 6),
        "average_volume": round(sum(volumes) / len(volumes), 2) if volumes else None,
        "horizon_profiles": horizon_profiles,
        "multi_horizon_confirmation": confirmation,
        "trend_consistency": trend_consistency,
        "positive_horizon_count": _count_horizon_states(
            horizon_profiles,
            "positive_trend",
        ),
        "negative_horizon_count": _count_horizon_states(
            horizon_profiles,
            "negative_trend",
        ),
        "neutral_horizon_count": _count_horizon_states(
            horizon_profiles,
            "neutral_trend",
        ),
        "insufficient_horizon_count": _count_horizon_states(
            horizon_profiles,
            "insufficient_history",
        ),
        "max_drawdown": round(_max_drawdown(prices), 6),
        "realized_volatility": round(
            _realized_volatility(prices, annualization_factor),
            6,
        ),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _horizon_profile(
    *,
    prices: Sequence[float],
    history: Sequence[Mapping[str, Any]],
    horizon: int,
    annualization_factor: int,
    positive_return_threshold: float,
    negative_return_threshold: float,
) -> dict[str, Any]:
    if len(prices) < 2:
        return _insufficient_horizon_profile(horizon)

    lookback_count = min(horizon + 1, len(prices))
    window_prices = list(prices[-lookback_count:])
    window_history = list(history[-lookback_count:])

    if len(window_prices) < 2:
        return _insufficient_horizon_profile(horizon)

    start_price = window_prices[0]
    end_price = window_prices[-1]
    horizon_return = _safe_return(start_price, end_price)
    simple_moving_average = sum(window_prices) / len(window_prices)
    price_vs_sma = _safe_return(simple_moving_average, end_price)

    if horizon_return >= positive_return_threshold and end_price >= simple_moving_average:
        state = "positive_trend"
    elif horizon_return <= negative_return_threshold and end_price <= simple_moving_average:
        state = "negative_trend"
    else:
        state = "neutral_trend"

    return {
        "horizon": horizon,
        "available_observations": len(window_prices),
        "start": window_history[0]["timestamp"],
        "end": window_history[-1]["timestamp"],
        "start_price": round(start_price, 6),
        "end_price": round(end_price, 6),
        "return": round(horizon_return, 6),
        "simple_moving_average": round(simple_moving_average, 6),
        "price_vs_sma": round(price_vs_sma, 6),
        "realized_volatility": round(
            _realized_volatility(window_prices, annualization_factor),
            6,
        ),
        "max_drawdown": round(_max_drawdown(window_prices), 6),
        "horizon_state": state,
    }


def _confirmation_state(
    horizon_profiles: Mapping[str, Mapping[str, Any]],
    horizons: Sequence[int],
) -> str:
    ordered_states = [
        str(horizon_profiles[str(horizon)].get("horizon_state"))
        for horizon in horizons
        if str(horizon) in horizon_profiles
    ]

    positive_count = ordered_states.count("positive_trend")
    negative_count = ordered_states.count("negative_trend")
    neutral_count = ordered_states.count("neutral_trend")
    insufficient_count = ordered_states.count("insufficient_history")

    short_state = ordered_states[0] if ordered_states else "insufficient_history"

    if positive_count >= 3 and negative_count == 0:
        return "confirmed_uptrend"

    if negative_count >= 3 and positive_count == 0:
        return "confirmed_downtrend"

    if short_state == "positive_trend" and positive_count >= 2 and negative_count == 0:
        return "developing_uptrend"

    if short_state == "negative_trend" and negative_count >= 2 and positive_count == 0:
        return "developing_downtrend"

    if positive_count > 0 and negative_count > 0:
        return "mixed_or_transitioning"

    if insufficient_count >= max(1, len(ordered_states) // 2):
        return "insufficient_history"

    if neutral_count == len(ordered_states):
        return "confirmed_neutral"

    return "choppy_neutral"


def _trend_consistency(
    horizon_profiles: Mapping[str, Mapping[str, Any]],
) -> str:
    states = [
        str(profile.get("horizon_state"))
        for profile in horizon_profiles.values()
        if profile.get("horizon_state") != "insufficient_history"
    ]

    if not states:
        return "insufficient"

    unique_states = set(states)

    if unique_states == {"positive_trend"}:
        return "consistent_positive"

    if unique_states == {"negative_trend"}:
        return "consistent_negative"

    if unique_states == {"neutral_trend"}:
        return "consistent_neutral"

    if "positive_trend" in unique_states and "negative_trend" in unique_states:
        return "conflicting"

    return "partially_consistent"


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    confirmation_counts = Counter(
        str(item.get("multi_horizon_confirmation") or "unknown")
        for item in items
    )
    trend_consistency_counts = Counter(
        str(item.get("trend_consistency") or "unknown")
        for item in items
    )

    return {
        "instrument_count": len(items),
        "confirmation_counts": dict(sorted(confirmation_counts.items())),
        "trend_consistency_counts": dict(sorted(trend_consistency_counts.items())),
        "confirmed_uptrend_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "confirmed_uptrend"
        ],
        "confirmed_downtrend_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "confirmed_downtrend"
        ],
        "developing_uptrend_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "developing_uptrend"
        ],
        "developing_downtrend_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "developing_downtrend"
        ],
        "mixed_or_transitioning_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "mixed_or_transitioning"
        ],
        "confirmed_neutral_symbols": [
            item["symbol"]
            for item in items
            if item.get("multi_horizon_confirmation") == "confirmed_neutral"
        ],
    }


def _extract_price_rows(source: Mapping[str, Any]) -> list[Any]:
    direct_keys = (
        "price_rows",
        "market_price_rows",
        "quantconnect_history",
        "market_price_history",
        "price_history",
        "history",
        "rows",
        "data",
    )

    for key in direct_keys:
        value = source.get(key)
        if _looks_like_price_rows(value):
            return list(value)

    nested_paths = (
        ("import_result", "price_rows"),
        ("import_result", "market_price_rows"),
        ("import_result", "quantconnect_history"),
        ("import_result", "market_price_history"),
        ("import_result", "price_history"),
        ("import_result", "history"),
        ("import_result", "rows"),
        ("result", "price_rows"),
        ("result", "market_price_rows"),
        ("result", "quantconnect_history"),
        ("result", "market_price_history"),
        ("result", "price_history"),
        ("payload", "price_rows"),
        ("payload", "market_price_rows"),
        ("payload", "quantconnect_history"),
        ("payload", "market_price_history"),
        ("payload", "price_history"),
        ("data", "price_rows"),
        ("data", "market_price_rows"),
        ("data", "quantconnect_history"),
        ("data", "market_price_history"),
        ("data", "price_history"),
    )

    for path in nested_paths:
        value = _get_nested(source, path)
        if _looks_like_price_rows(value):
            return list(value)

    recursive_match = _find_price_rows_recursively(source)
    return recursive_match or []


def _get_nested(value: Any, path: Sequence[str]) -> Any:
    current = value

    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)

    return current


def _find_price_rows_recursively(value: Any) -> list[Any] | None:
    if _looks_like_price_rows(value):
        return list(value)

    if isinstance(value, Mapping):
        for child in value.values():
            found = _find_price_rows_recursively(child)
            if found:
                return found

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found = _find_price_rows_recursively(child)
            if found:
                return found

    return None


def _looks_like_price_rows(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False

    sample = [item for item in list(value)[:10] if isinstance(item, Mapping)]
    if not sample:
        return False

    for item in sample:
        has_symbol = item.get("symbol") is not None
        has_time = (
            item.get("timestamp") is not None
            or item.get("date") is not None
            or item.get("time") is not None
        )
        has_price = item.get("adjusted_close") is not None or item.get("close") is not None

        if has_symbol and has_time and has_price:
            return True

    return False


def _normalize_price_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None

    symbol = _clean_symbol(row.get("symbol"))
    timestamp = _clean_timestamp(row.get("timestamp") or row.get("date") or row.get("time"))
    price = _float_or_none(
        row.get("adjusted_close")
        if row.get("adjusted_close") is not None
        else row.get("close")
    )

    if symbol is None or timestamp is None or price is None or price <= 0:
        return None

    volume = _float_or_none(row.get("volume"))

    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "timestamp_sort_key": _timestamp_sort_key(timestamp),
        "price": price,
        "volume": volume,
    }


def _count_horizon_states(
    horizon_profiles: Mapping[str, Mapping[str, Any]],
    state: str,
) -> int:
    return sum(
        1
        for profile in horizon_profiles.values()
        if profile.get("horizon_state") == state
    )


def _realized_volatility(
    prices: Sequence[float],
    annualization_factor: int,
) -> float:
    returns = [
        _safe_return(prices[index - 1], prices[index])
        for index in range(1, len(prices))
        if prices[index - 1] > 0
    ]

    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)

    return math.sqrt(variance) * math.sqrt(annualization_factor)


def _max_drawdown(prices: Sequence[float]) -> float:
    peak = prices[0]
    max_drawdown = 0.0

    for price in prices:
        peak = max(peak, price)
        drawdown = _safe_return(peak, price)
        max_drawdown = min(max_drawdown, drawdown)

    return max_drawdown


def _safe_return(start: float, end: float) -> float:
    if start == 0:
        return 0.0

    return (end / start) - 1.0


def _insufficient_horizon_profile(horizon: int) -> dict[str, Any]:
    return {
        "horizon": horizon,
        "available_observations": 0,
        "start": None,
        "end": None,
        "start_price": None,
        "end_price": None,
        "return": None,
        "simple_moving_average": None,
        "price_vs_sma": None,
        "realized_volatility": None,
        "max_drawdown": None,
        "horizon_state": "insufficient_history",
    }


def _clean_horizons(horizons: Sequence[int]) -> tuple[int, ...]:
    clean = []

    for horizon in horizons:
        try:
            value = int(horizon)
        except (TypeError, ValueError):
            continue

        if value > 0:
            clean.append(value)

    return tuple(sorted(set(clean)))


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clean_timestamp(value: Any) -> str | None:
    text = _clean_text(value)
    return text


def _timestamp_sort_key(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_multi_horizon_behavior",
        "schema_version": ASSET_MULTI_HORIZON_BEHAVIOR_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_multi_horizon_behavior",
        "adapter_type": "asset_multi_horizon_behavior_builder",
        "horizons": [],
        "instrument_multi_horizon_behaviors": [],
        "multi_horizon_summary": {
            "instrument_count": 0,
            "confirmation_counts": {},
            "trend_consistency_counts": {},
            "confirmed_uptrend_symbols": [],
            "confirmed_downtrend_symbols": [],
            "developing_uptrend_symbols": [],
            "developing_downtrend_symbols": [],
            "mixed_or_transitioning_symbols": [],
            "confirmed_neutral_symbols": [],
        },
        "skipped_rows": [],
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
