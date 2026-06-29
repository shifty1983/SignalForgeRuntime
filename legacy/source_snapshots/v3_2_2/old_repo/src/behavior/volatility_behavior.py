from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl


DEFAULT_SHORT_WINDOW = 20
DEFAULT_LONG_WINDOW = 50


def build_volatility_behavior_profile(
    returns_df: pl.DataFrame,
    *,
    return_col: str = "return",
    short_window: int = DEFAULT_SHORT_WINDOW,
    long_window: int = DEFAULT_LONG_WINDOW,
    annualization_factor: int = 252,
) -> dict[str, Any]:
    """
    Build an asset-level volatility behavior profile.

    Existing volatility_profile.py classifies absolute realized volatility as
    low/normal/high. This module adds Koyfin-style behavior around whether
    volatility is expanding, compressing, breaking out, or stable.
    """
    if return_col not in returns_df.columns:
        raise ValueError(f"Missing required column: {return_col}")

    if returns_df.is_empty():
        raise ValueError("Input DataFrame is empty")

    returns = [float(value) for value in returns_df[return_col].drop_nulls().to_list()]
    return build_volatility_behavior_profile_from_returns(
        returns,
        short_window=short_window,
        long_window=long_window,
        annualization_factor=annualization_factor,
    )


def build_volatility_behavior_profile_from_returns(
    returns: Sequence[float],
    *,
    short_window: int = DEFAULT_SHORT_WINDOW,
    long_window: int = DEFAULT_LONG_WINDOW,
    annualization_factor: int = 252,
) -> dict[str, Any]:
    if long_window <= 1 or short_window <= 1:
        raise ValueError("volatility windows must be greater than one")

    clean_returns = [float(value) for value in returns]
    if len(clean_returns) < long_window:
        raise ValueError(f"requires at least {long_window} return observations")

    short_vol = _annualized_std(clean_returns[-short_window:], annualization_factor)
    long_vol = _annualized_std(clean_returns[-long_window:], annualization_factor)
    prior_short_vol = _prior_short_volatility(
        clean_returns,
        short_window=short_window,
        annualization_factor=annualization_factor,
    )

    volatility_change = _safe_ratio_change(short_vol, long_vol)
    volatility_trend = classify_volatility_trend(volatility_change)
    volatility_behavior = classify_volatility_behavior(
        short_volatility=short_vol,
        long_volatility=long_vol,
        prior_short_volatility=prior_short_vol,
        volatility_change=volatility_change,
    )

    return {
        "volatility_behavior": volatility_behavior,
        "volatility_trend": volatility_trend,
        "volatility_change": round(volatility_change, 8),
        "short_realized_volatility": round(short_vol, 8),
        "long_realized_volatility": round(long_vol, 8),
        "prior_short_realized_volatility": (
            round(prior_short_vol, 8) if prior_short_vol is not None else None
        ),
    }


def classify_volatility_behavior(
    *,
    short_volatility: float,
    long_volatility: float,
    prior_short_volatility: float | None = None,
    volatility_change: float | None = None,
    expansion_threshold: float = 0.20,
    compression_threshold: float = -0.20,
    breakout_threshold: float = 0.50,
) -> str:
    change = (
        volatility_change
        if volatility_change is not None
        else _safe_ratio_change(short_volatility, long_volatility)
    )

    if prior_short_volatility is not None and prior_short_volatility > 0:
        prior_change = _safe_ratio_change(short_volatility, prior_short_volatility)
        if change >= expansion_threshold and prior_change >= breakout_threshold:
            return "volatility_breakout"

    if change >= breakout_threshold:
        return "volatility_breakout"

    if change >= expansion_threshold:
        return "volatility_expansion"

    if change <= compression_threshold:
        return "volatility_compression"

    return "volatility_stable"


def classify_volatility_trend(
    volatility_change: float,
    *,
    rising_threshold: float = 0.10,
    falling_threshold: float = -0.10,
) -> str:
    if volatility_change >= rising_threshold:
        return "rising_volatility"

    if volatility_change <= falling_threshold:
        return "falling_volatility"

    return "stable_volatility"


def _prior_short_volatility(
    returns: Sequence[float],
    *,
    short_window: int,
    annualization_factor: int,
) -> float | None:
    if len(returns) < short_window * 2:
        return None

    prior_slice = returns[-short_window * 2 : -short_window]
    if len(prior_slice) < short_window:
        return None

    return _annualized_std(prior_slice, annualization_factor)


def _annualized_std(values: Sequence[float], annualization_factor: int) -> float:
    if len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return (variance ** 0.5) * (annualization_factor ** 0.5)


def _safe_ratio_change(numerator: float, denominator: float) -> float:
    if denominator == 0:
        if numerator == 0:
            return 0.0
        return 1.0
    return (numerator / denominator) - 1.0
