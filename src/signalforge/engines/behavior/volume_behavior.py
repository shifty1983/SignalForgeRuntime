from __future__ import annotations

from collections.abc import Sequence
from typing import Any


DEFAULT_SHORT_WINDOW = 20
DEFAULT_LONG_WINDOW = 50


def classify_volume_behavior(
    *,
    volumes: Sequence[Any],
    prices: Sequence[Any] | None = None,
    short_window: int = DEFAULT_SHORT_WINDOW,
    long_window: int = DEFAULT_LONG_WINDOW,
    expansion_threshold: float = 1.15,
    breakout_threshold: float = 1.75,
    contraction_threshold: float = 0.75,
    move_confirmation_threshold: float = 0.02,
) -> dict[str, Any]:
    """Classify volume participation behavior for one asset.

    The output is intentionally asset-behavior focused. It does not infer orders,
    submit trades, model fills, or change strategies automatically.
    """

    cleaned_volumes = [_float_or_none(value) for value in volumes]
    valid_volumes = [value for value in cleaned_volumes if value is not None and value > 0]

    if len(valid_volumes) < max(5, min(short_window, long_window)):
        return {
            "volume_behavior": "volume_unknown",
            "volume_trend": "unknown_volume_trend",
            "participation_state": "unknown_participation",
            "accumulation_distribution": "unknown_accumulation_distribution",
            "volume_confirmation": "unknown_volume_confirmation",
            "volume_observation_count": len(valid_volumes),
            "average_volume_short": None,
            "average_volume_long": None,
            "volume_relative_ratio": None,
            "volume_change": None,
            "volume_price_return": _price_return(prices, short_window),
            "volume_behavior_warnings": ["insufficient positive volume observations"],
        }

    active_short_window = min(short_window, len(valid_volumes))
    active_long_window = min(long_window, len(valid_volumes))

    short_avg = _mean(valid_volumes[-active_short_window:])
    long_avg = _mean(valid_volumes[-active_long_window:])
    ratio = short_avg / long_avg if long_avg > 0 else None
    change = (short_avg / long_avg) - 1.0 if long_avg > 0 else None

    volume_behavior = _classify_volume_behavior(
        ratio,
        expansion_threshold=expansion_threshold,
        breakout_threshold=breakout_threshold,
        contraction_threshold=contraction_threshold,
    )
    volume_trend = _classify_volume_trend(
        ratio,
        expansion_threshold=expansion_threshold,
        contraction_threshold=contraction_threshold,
    )

    price_return = _price_return(prices, short_window)
    accumulation_distribution = _classify_accumulation_distribution(
        price_return=price_return,
        volume_behavior=volume_behavior,
        move_threshold=move_confirmation_threshold,
    )
    participation_state = _classify_participation_state(
        volume_behavior=volume_behavior,
        accumulation_distribution=accumulation_distribution,
    )
    volume_confirmation = _classify_volume_confirmation(
        price_return=price_return,
        volume_behavior=volume_behavior,
        move_threshold=move_confirmation_threshold,
    )

    return {
        "volume_behavior": volume_behavior,
        "volume_trend": volume_trend,
        "participation_state": participation_state,
        "accumulation_distribution": accumulation_distribution,
        "volume_confirmation": volume_confirmation,
        "volume_observation_count": len(valid_volumes),
        "average_volume_short": round(short_avg, 4),
        "average_volume_long": round(long_avg, 4),
        "volume_relative_ratio": round(ratio, 6) if ratio is not None else None,
        "volume_change": round(change, 6) if change is not None else None,
        "volume_price_return": round(price_return, 8) if price_return is not None else None,
        "volume_behavior_warnings": [],
    }


def _classify_volume_behavior(
    ratio: float | None,
    *,
    expansion_threshold: float,
    breakout_threshold: float,
    contraction_threshold: float,
) -> str:
    if ratio is None:
        return "volume_unknown"
    if ratio >= breakout_threshold:
        return "volume_breakout"
    if ratio >= expansion_threshold:
        return "volume_expansion"
    if ratio <= contraction_threshold:
        return "volume_contraction"
    return "volume_normal"


def _classify_volume_trend(
    ratio: float | None,
    *,
    expansion_threshold: float,
    contraction_threshold: float,
) -> str:
    if ratio is None:
        return "unknown_volume_trend"
    if ratio >= expansion_threshold:
        return "rising_volume"
    if ratio <= contraction_threshold:
        return "falling_volume"
    return "stable_volume"


def _classify_accumulation_distribution(
    *,
    price_return: float | None,
    volume_behavior: str,
    move_threshold: float,
) -> str:
    expanded = volume_behavior in {"volume_expansion", "volume_breakout"}
    if price_return is None or not expanded:
        return "neutral_participation"
    if price_return >= move_threshold:
        return "accumulation"
    if price_return <= -move_threshold:
        return "distribution"
    return "neutral_participation"


def _classify_participation_state(
    *,
    volume_behavior: str,
    accumulation_distribution: str,
) -> str:
    if accumulation_distribution == "accumulation":
        return "bullish_participation"
    if accumulation_distribution == "distribution":
        return "bearish_participation"
    if volume_behavior in {"volume_expansion", "volume_breakout"}:
        return "active_participation"
    if volume_behavior == "volume_contraction":
        return "weak_participation"
    if volume_behavior == "volume_unknown":
        return "unknown_participation"
    return "neutral_participation"


def _classify_volume_confirmation(
    *,
    price_return: float | None,
    volume_behavior: str,
    move_threshold: float,
) -> str:
    if price_return is None:
        return "unknown_volume_confirmation"
    meaningful_move = abs(price_return) >= move_threshold
    if not meaningful_move:
        return "neutral_confirmation"
    if volume_behavior in {"volume_expansion", "volume_breakout"}:
        return "confirmed_move"
    if volume_behavior == "volume_contraction":
        return "unconfirmed_move"
    return "neutral_confirmation"


def _price_return(prices: Sequence[Any] | None, lookback: int) -> float | None:
    if not prices:
        return None
    cleaned = [_float_or_none(value) for value in prices]
    valid = [value for value in cleaned if value is not None and value > 0]
    if len(valid) < 2:
        return None
    start_index = max(0, len(valid) - max(lookback, 1) - 1)
    start = valid[start_index]
    end = valid[-1]
    if start <= 0:
        return None
    return (end / start) - 1.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


