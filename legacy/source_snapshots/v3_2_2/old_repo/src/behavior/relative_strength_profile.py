from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_relative_strength_profile(
    asset_prices: Sequence[float],
    benchmark_prices: Sequence[float],
    *,
    trend_window: int = 20,
) -> dict[str, Any]:
    """
    Classify asset relative strength versus an explicit benchmark.

    This is an asset-behavior profile only. It does not call vendors, route
    orders, select strategies, model fills, or create automatic actions.
    """

    asset = _clean_prices(asset_prices)
    benchmark = _clean_prices(benchmark_prices)
    pair_count = min(len(asset), len(benchmark))

    if pair_count < 2:
        return _empty_profile("requires at least two aligned asset and benchmark prices")

    asset = asset[-pair_count:]
    benchmark = benchmark[-pair_count:]

    if any(price <= 0 for price in asset) or any(price <= 0 for price in benchmark):
        return _empty_profile("asset and benchmark prices must be positive")

    asset_return = _period_return(asset)
    benchmark_return = _period_return(benchmark)
    benchmark_relative_return = asset_return - benchmark_return

    relative_ratio_return = _relative_ratio_return(asset, benchmark)
    relative_strength_state = classify_relative_strength_state(benchmark_relative_return)
    relative_strength_trend = classify_relative_strength_trend(
        asset,
        benchmark,
        trend_window=trend_window,
    )

    return {
        "relative_strength_status": "ready",
        "relative_strength_observation_count": pair_count,
        "asset_period_return": round(asset_return, 8),
        "benchmark_period_return": round(benchmark_return, 8),
        "benchmark_relative_return": round(benchmark_relative_return, 8),
        "relative_strength_ratio_return": round(relative_ratio_return, 8),
        "relative_strength_state": relative_strength_state,
        "relative_strength_trend": relative_strength_trend,
        "relative_strength_warning": None,
    }


def classify_relative_strength_state(relative_return: float) -> str:
    if relative_return >= 0.10:
        return "strong_outperformer"
    if relative_return >= 0.03:
        return "outperformer"
    if relative_return <= -0.10:
        return "strong_underperformer"
    if relative_return <= -0.03:
        return "underperformer"
    return "market_performer"


def classify_relative_strength_trend(
    asset_prices: Sequence[float],
    benchmark_prices: Sequence[float],
    *,
    trend_window: int = 20,
    threshold: float = 0.02,
) -> str:
    asset = _clean_prices(asset_prices)
    benchmark = _clean_prices(benchmark_prices)
    pair_count = min(len(asset), len(benchmark))

    if pair_count < 2:
        return "unknown_relative_strength_trend"

    asset = asset[-pair_count:]
    benchmark = benchmark[-pair_count:]

    window = max(2, min(trend_window, pair_count))
    recent_asset = asset[-window:]
    recent_benchmark = benchmark[-window:]
    recent_ratio_return = _relative_ratio_return(recent_asset, recent_benchmark)

    if recent_ratio_return >= threshold:
        return "improving_relative_strength"
    if recent_ratio_return <= -threshold:
        return "deteriorating_relative_strength"
    return "stable_relative_strength"


def _period_return(prices: Sequence[float]) -> float:
    first = float(prices[0])
    last = float(prices[-1])
    return (last / first) - 1.0


def _relative_ratio_return(asset_prices: Sequence[float], benchmark_prices: Sequence[float]) -> float:
    start_ratio = float(asset_prices[0]) / float(benchmark_prices[0])
    end_ratio = float(asset_prices[-1]) / float(benchmark_prices[-1])
    return (end_ratio / start_ratio) - 1.0


def _clean_prices(values: Sequence[float]) -> list[float]:
    output: list[float] = []
    for value in values:
        try:
            output.append(float(value))
        except (TypeError, ValueError):
            continue
    return output


def _empty_profile(reason: str) -> dict[str, Any]:
    return {
        "relative_strength_status": "blocked",
        "relative_strength_observation_count": 0,
        "asset_period_return": None,
        "benchmark_period_return": None,
        "benchmark_relative_return": None,
        "relative_strength_ratio_return": None,
        "relative_strength_state": None,
        "relative_strength_trend": None,
        "relative_strength_warning": reason,
    }
