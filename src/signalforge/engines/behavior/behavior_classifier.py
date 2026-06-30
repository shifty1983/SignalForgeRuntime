from __future__ import annotations

import polars as pl

from src.signalforge.engines.behavior.behavior_score import build_behavior_score
from src.signalforge.engines.behavior.drawdown_profile import (
    classify_drawdown,
    compute_drawdown,
    max_drawdown,
)
from src.signalforge.engines.behavior.returns_profile import classify_return_behavior
from src.signalforge.engines.behavior.schema import validate_behavior_inputs
from src.signalforge.engines.behavior.trend_profile import (
    classify_trend,
    moving_average_trend,
)
from src.signalforge.engines.behavior.trend_quality import build_trend_quality_profile
from src.signalforge.engines.behavior.volatility_behavior import build_volatility_behavior_profile
from src.signalforge.engines.behavior.volatility_profile import (
    classify_volatility_regime,
    realized_volatility,
)


def classify_asset_behavior(
    returns_df: pl.DataFrame,
    price_df: pl.DataFrame,
    equity_df: pl.DataFrame,
    return_col: str = "return",
    price_col: str = "close",
    equity_col: str = "equity",
    short_window: int = 20,
    long_window: int = 50,
    annualization_factor: int = 252,
    score_weights: dict | None = None,
) -> dict:
    """
    Build unified asset behavior classification.

    This combines:
    - return behavior
    - realized volatility level
    - volatility expansion/compression behavior
    - trend behavior
    - trend quality and momentum persistence
    - drawdown behavior
    - normalized behavior score
    - final behavior state
    """
    validate_behavior_inputs(
        returns_df=returns_df,
        price_df=price_df,
        equity_df=equity_df,
        return_col=return_col,
        price_col=price_col,
        equity_col=equity_col,
        min_price_rows=long_window,
    )

    return_behavior = classify_return_behavior(
        returns_df,
        return_col=return_col,
    )

    realized_vol = realized_volatility(
        returns_df,
        return_col=return_col,
        annualization_factor=annualization_factor,
    )

    volatility_state = classify_volatility_regime(
        realized_vol,
    )

    volatility_profile = build_volatility_behavior_profile(
        returns_df,
        return_col=return_col,
        short_window=short_window,
        long_window=long_window,
        annualization_factor=annualization_factor,
    )

    trend_df = moving_average_trend(
        price_df,
        price_col=price_col,
        short_window=short_window,
        long_window=long_window,
    )

    trend_behavior = classify_trend(
        trend_df,
        short_window=short_window,
        long_window=long_window,
    )

    trend_quality_profile = build_trend_quality_profile(
        price_df,
        price_col=price_col,
        short_window=short_window,
        long_window=long_window,
    )

    drawdown_df = compute_drawdown(
        equity_df,
        equity_col=equity_col,
    )

    max_dd = max_drawdown(drawdown_df)

    drawdown_behavior = classify_drawdown(max_dd)

    base_behavior = {
        "return_behavior": return_behavior,
        "volatility_state": volatility_state,
        "volatility_level": volatility_state,
        "trend_behavior": trend_behavior,
        "drawdown_behavior": drawdown_behavior,
        "realized_volatility": realized_vol,
        "max_drawdown": max_dd,
        **volatility_profile,
        **trend_quality_profile,
    }

    score_behavior = {
        **base_behavior,
        "volatility_behavior": volatility_state,
    }

    score_result = build_behavior_score(
        behavior=score_behavior,
        weights=score_weights,
    )

    return {
        **base_behavior,
        **score_result,
    }

