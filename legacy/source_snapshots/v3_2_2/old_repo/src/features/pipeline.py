import polars as pl

from src.features.returns import add_returns, add_log_returns
from src.features.volatility import add_rolling_volatility
from src.features.momentum import add_momentum, add_rate_of_change
from src.features.drawdown import add_drawdown, add_max_drawdown
from src.features.moving_average import (
    add_moving_averages,
    add_price_vs_moving_average,
)
from src.features.rolling_stats import (
    add_rolling_stats,
    add_rolling_zscores,
    add_rolling_range_position,
)
from src.features.trend import (
    add_trend_slope,
    add_trend_strength,
    add_moving_average_crossovers,
    add_trend_regime,
)
from src.features.volume import add_volume_features
from src.features.price_action import add_price_action_features
from src.features.calendar import add_calendar_feature_set
from src.features.relative_strength import add_relative_strength_features


def build_market_features(
    df: pl.DataFrame,
    price_col: str = "close",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Build the standard single-symbol market feature set for OHLCV-style data.

    This pipeline does not require a benchmark.
    """
    result = df.sort(date_col)

    # Return features
    result = add_returns(result, price_col=price_col)
    result = add_log_returns(result, price_col=price_col)

    # Volatility features
    result = add_rolling_volatility(result, return_col="return_1d")

    # Momentum features
    result = add_momentum(result, price_col=price_col)
    result = add_rate_of_change(result, price_col=price_col)

    # Drawdown features
    result = add_drawdown(result, price_col=price_col)
    result = add_max_drawdown(result, price_col=price_col)

    # Moving average features
    result = add_moving_averages(result, price_col=price_col)
    result = add_price_vs_moving_average(result, price_col=price_col)

    # Rolling statistical features
    result = add_rolling_stats(result, value_col=price_col)
    result = add_rolling_zscores(result, value_col=price_col)
    result = add_rolling_range_position(result, value_col=price_col)
    result = add_rolling_zscores(result, value_col="return_1d")

    # Trend features
    result = add_trend_slope(result, price_col=price_col)
    result = add_trend_strength(result, price_col=price_col)
    result = add_moving_average_crossovers(result, price_col=price_col)
    result = add_trend_regime(result, price_col=price_col)

    # Volume features
    result = add_volume_features(
        result,
        price_col=price_col,
        volume_col=volume_col,
    )

    # Price action features
    result = add_price_action_features(
        result,
        open_col=open_col,
        high_col=high_col,
        low_col=low_col,
        close_col=close_col,
    )

    # Calendar features
    result = add_calendar_feature_set(result, date_col=date_col)

    return result


def build_market_features_with_benchmark(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Build market features plus benchmark-relative features.

    Use this for features like:
    - excess returns
    - relative strength ratio
    - beta
    - correlation
    """
    result = build_market_features(
        df=df,
        price_col=price_col,
        date_col=date_col,
    )

    result = add_relative_strength_features(
        result,
        benchmark_df=benchmark_df,
        price_col=price_col,
        benchmark_price_col=benchmark_price_col,
        date_col=date_col,
    )

    return result
