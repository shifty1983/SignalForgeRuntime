from __future__ import annotations

from statistics import pstdev
from typing import Any

import polars as pl


def build_trend_quality_profile(
    df: pl.DataFrame,
    price_col: str = "close",
    short_window: int = 20,
    long_window: int = 50,
) -> dict[str, Any]:
    """
    Build a Koyfin-style trend quality and momentum persistence profile.

    This is an asset-behavior layer only. It uses local price history and does
    not call brokers, vendors, route orders, model fills, or perform execution.
    """
    _validate_price_frame(df, price_col=price_col, min_rows=long_window)

    prices = [float(value) for value in df[price_col].to_list()]
    returns = _returns(prices)

    short_return = _period_return(prices, short_window)
    long_return = _period_return(prices, long_window)
    prior_short_return = _prior_period_return(prices, short_window)
    trend_acceleration = short_return - prior_short_return

    realized_short_volatility = _volatility(returns[-short_window:])
    prior_short_volatility = _volatility(
        returns[-(short_window * 2): -short_window]
        if len(returns) >= short_window * 2
        else []
    )
    volatility_change = realized_short_volatility - prior_short_volatility

    trend_strength_score = _trend_strength_score(
        short_return=short_return,
        long_return=long_return,
        realized_short_volatility=realized_short_volatility,
    )

    trend_quality = classify_trend_quality(
        short_return=short_return,
        long_return=long_return,
        trend_acceleration=trend_acceleration,
        volatility_change=volatility_change,
        trend_strength_score=trend_strength_score,
    )

    momentum_state = classify_momentum_state(
        short_return=short_return,
        long_return=long_return,
        trend_acceleration=trend_acceleration,
    )

    reversal_risk = classify_reversal_risk(
        short_return=short_return,
        long_return=long_return,
        trend_acceleration=trend_acceleration,
        volatility_change=volatility_change,
    )

    return {
        "trend_quality": trend_quality,
        "trend_strength_score": trend_strength_score,
        "trend_slope": round(long_return / max(long_window, 1), 8),
        "trend_acceleration": round(trend_acceleration, 8),
        "short_window_return": round(short_return, 8),
        "long_window_return": round(long_return, 8),
        "prior_short_window_return": round(prior_short_return, 8),
        "momentum_persistence": _momentum_persistence(momentum_state),
        "momentum_state": momentum_state,
        "reversal_risk": reversal_risk,
        "trend_quality_volatility_change": round(volatility_change, 8),
    }


def classify_trend_quality(
    *,
    short_return: float,
    long_return: float,
    trend_acceleration: float,
    volatility_change: float = 0.0,
    trend_strength_score: float = 0.0,
) -> str:
    if long_return > 0.03 and short_return < -0.02:
        return "trend_breakdown"

    if short_return > 0.0 and long_return < 0.0:
        return "trend_accelerating"

    if short_return < 0.0 and long_return > 0.0:
        return "trend_breakdown"

    if (short_return > 0.0 and long_return > 0.0) or (short_return < 0.0 and long_return < 0.0):
        if trend_strength_score >= 0.70 and volatility_change <= 0.05:
            return "strong_trend"
        return "weak_trend"

    if abs(short_return) < 0.01 and abs(long_return) < 0.02:
        return "weak_trend"

    return "choppy_trend"


def classify_momentum_state(
    *,
    short_return: float,
    long_return: float,
    trend_acceleration: float,
) -> str:
    if long_return > 0.03 and short_return < -0.02:
        return "reversal_risk"

    if short_return > 0.0 and trend_acceleration > 0.01:
        return "accelerating_momentum"

    if short_return > 0.0 and long_return > 0.0:
        if trend_acceleration < -0.01:
            return "decelerating_momentum"
        return "persistent_momentum"

    if short_return < 0.0 and long_return < 0.0:
        return "negative_momentum"

    return "neutral_momentum"


def classify_reversal_risk(
    *,
    short_return: float,
    long_return: float,
    trend_acceleration: float,
    volatility_change: float = 0.0,
) -> str:
    if long_return > 0.03 and short_return < -0.02:
        return "high_reversal_risk"

    if trend_acceleration < -0.03 or (short_return < 0.0 and volatility_change > 0.03):
        return "moderate_reversal_risk"

    return "low_reversal_risk"


def _momentum_persistence(momentum_state: str) -> str:
    if momentum_state in {"persistent_momentum", "accelerating_momentum"}:
        return "persistent_momentum"

    if momentum_state in {"decelerating_momentum", "reversal_risk"}:
        return "weakening_momentum"

    if momentum_state == "negative_momentum":
        return "negative_momentum"

    return "neutral_momentum"


def _validate_price_frame(df: pl.DataFrame, *, price_col: str, min_rows: int) -> None:
    if price_col not in df.columns:
        raise ValueError(f"Missing required column: {price_col}")

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    if df.height < min_rows:
        raise ValueError(f"Input DataFrame requires at least {min_rows} rows")


def _period_return(prices: list[float], periods: int) -> float:
    if periods <= 0 or len(prices) <= periods:
        return 0.0

    start = prices[-periods - 1]
    end = prices[-1]
    if start <= 0:
        return 0.0
    return (end / start) - 1.0


def _prior_period_return(prices: list[float], periods: int) -> float:
    if periods <= 0 or len(prices) <= periods * 2:
        return 0.0

    start = prices[-(periods * 2) - 1]
    end = prices[-periods - 1]
    if start <= 0:
        return 0.0
    return (end / start) - 1.0


def _returns(prices: list[float]) -> list[float]:
    output: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous > 0:
            output.append((current / previous) - 1.0)
    return output


def _volatility(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return pstdev(values)


def _trend_strength_score(
    *,
    short_return: float,
    long_return: float,
    realized_short_volatility: float,
) -> float:
    same_direction_bonus = 0.35 if short_return * long_return > 0 else 0.0
    direction_strength = min((abs(short_return) * 3.0) + (abs(long_return) * 1.5), 0.55)
    volatility_penalty = min(realized_short_volatility * 10.0, 0.25)
    score = same_direction_bonus + direction_strength - volatility_penalty
    return round(max(0.0, min(1.0, score)), 4)
