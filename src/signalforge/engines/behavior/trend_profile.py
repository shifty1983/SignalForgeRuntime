from __future__ import annotations

import polars as pl


def moving_average_trend(
    df: pl.DataFrame,
    price_col: str = "close",
    short_window: int = 20,
    long_window: int = 50,
) -> pl.DataFrame:
    """
    Compute short and long moving averages for trend analysis.
    """
    if price_col not in df.columns:
        raise ValueError(f"Missing required column: {price_col}")

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    result = df.with_columns(
        [
            pl.col(price_col)
            .rolling_mean(window_size=short_window)
            .alias(f"sma_{short_window}"),

            pl.col(price_col)
            .rolling_mean(window_size=long_window)
            .alias(f"sma_{long_window}"),
        ]
    )

    return result


def classify_trend(
    df: pl.DataFrame,
    short_window: int = 20,
    long_window: int = 50,
) -> str:
    """
    Classify trend direction using moving averages.
    """
    short_col = f"sma_{short_window}"
    long_col = f"sma_{long_window}"

    if short_col not in df.columns or long_col not in df.columns:
        raise ValueError(
            "Trend moving average columns are missing"
        )

    latest_short = df[short_col][-1]
    latest_long = df[long_col][-1]

    if latest_short is None or latest_long is None:
        return "insufficient_data"

    if latest_short > latest_long:
        return "uptrend"

    if latest_short < latest_long:
        return "downtrend"

    return "sideways"




