from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_drawdown_behavior_profile(
    prices: Sequence[float],
    *,
    shallow_threshold: float = 0.03,
    correction_threshold: float = 0.10,
    deep_threshold: float = 0.20,
    severe_threshold: float = 0.35,
) -> dict[str, Any]:
    """Classify current drawdown behavior from a price/equity series.

    This is an asset-behavior layer only. It does not size positions, submit
    orders, or make automatic strategy changes.
    """

    clean_prices = [float(value) for value in prices if value is not None]
    if len(clean_prices) < 2:
        raise ValueError("requires at least two price observations")
    if any(value <= 0 for value in clean_prices):
        raise ValueError("prices must be positive")

    peak = clean_prices[0]
    peak_index = 0
    trough_after_peak = clean_prices[0]
    max_drawdown = 0.0
    max_drawdown_index = 0
    current_peak_index = 0

    drawdowns: list[float] = []
    for index, price in enumerate(clean_prices):
        if price >= peak:
            peak = price
            current_peak_index = index
            trough_after_peak = price

        trough_after_peak = min(trough_after_peak, price)
        drawdown = (price - peak) / peak
        drawdowns.append(drawdown)

        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_drawdown_index = index
            peak_index = current_peak_index

    current_price = clean_prices[-1]
    current_peak = max(clean_prices)
    current_drawdown = (current_price - current_peak) / current_peak
    current_drawdown_depth = abs(current_drawdown)
    max_drawdown_depth = abs(max_drawdown)
    days_from_high = len(clean_prices) - 1 - max(
        index for index, price in enumerate(clean_prices) if price == current_peak
    )

    post_peak_prices = clean_prices[peak_index:]
    trough_price = min(post_peak_prices) if post_peak_prices else current_price
    peak_to_trough = max(current_peak - trough_price, 0.0)
    recovered = max(current_price - trough_price, 0.0)
    recovery_pct = recovered / peak_to_trough if peak_to_trough > 0 else 1.0
    recovery_pct = max(0.0, min(recovery_pct, 1.0))

    recent_window = clean_prices[-min(10, len(clean_prices)):]
    recent_return = (recent_window[-1] / recent_window[0]) - 1.0 if len(recent_window) > 1 else 0.0

    drawdown_state = _classify_drawdown_state(
        current_drawdown_depth=current_drawdown_depth,
        max_drawdown_depth=max_drawdown_depth,
        shallow_threshold=shallow_threshold,
        correction_threshold=correction_threshold,
        deep_threshold=deep_threshold,
        severe_threshold=severe_threshold,
    )
    recovery_strength = _classify_recovery_strength(
        current_drawdown_depth=current_drawdown_depth,
        recovery_pct=recovery_pct,
        recent_return=recent_return,
    )
    drawdown_risk = _classify_drawdown_risk(
        current_drawdown_depth=current_drawdown_depth,
        max_drawdown_depth=max_drawdown_depth,
        recent_return=recent_return,
    )

    return {
        "drawdown_state": drawdown_state,
        "drawdown_depth": round(current_drawdown, 6),
        "drawdown_magnitude": round(current_drawdown_depth, 6),
        "max_drawdown_depth": round(max_drawdown, 6),
        "max_drawdown_magnitude": round(max_drawdown_depth, 6),
        "days_from_high": int(days_from_high),
        "drawdown_recovery_pct": round(recovery_pct, 6),
        "recovery_strength": recovery_strength,
        "drawdown_risk": drawdown_risk,
    }


def _classify_drawdown_state(
    *,
    current_drawdown_depth: float,
    max_drawdown_depth: float,
    shallow_threshold: float,
    correction_threshold: float,
    deep_threshold: float,
    severe_threshold: float,
) -> str:
    depth = max(current_drawdown_depth, max_drawdown_depth)

    if current_drawdown_depth <= 0.005:
        return "near_high"
    if depth < shallow_threshold:
        return "shallow_pullback"
    if depth < correction_threshold:
        return "normal_pullback"
    if depth < deep_threshold:
        return "normal_correction"
    if depth < severe_threshold:
        return "deep_correction"
    return "severe_drawdown"


def _classify_recovery_strength(
    *,
    current_drawdown_depth: float,
    recovery_pct: float,
    recent_return: float,
) -> str:
    if current_drawdown_depth <= 0.005:
        return "at_high"
    if recovery_pct >= 0.75 and recent_return >= 0:
        return "strong_recovery"
    if recovery_pct >= 0.40:
        return "partial_recovery"
    if recent_return < -0.03:
        return "deteriorating"
    return "weak_recovery"


def _classify_drawdown_risk(
    *,
    current_drawdown_depth: float,
    max_drawdown_depth: float,
    recent_return: float,
) -> str:
    depth = max(current_drawdown_depth, max_drawdown_depth)

    if depth >= 0.30 or (current_drawdown_depth >= 0.15 and recent_return < 0):
        return "extreme_drawdown_risk"
    if depth >= 0.18 or current_drawdown_depth >= 0.10:
        return "high_drawdown_risk"
    if depth >= 0.08 or current_drawdown_depth >= 0.05:
        return "moderate_drawdown_risk"
    return "low_drawdown_risk"
