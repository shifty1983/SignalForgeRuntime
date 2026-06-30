from __future__ import annotations

import polars as pl

from src.signalforge.engines.options.schema import validate_columns


def add_liquidity_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add option liquidity metrics.

    Metrics:
    - mid_price
    - bid_ask_spread
    - spread_pct
    - volume_oi_ratio
    - option_dollar_volume
    - total_activity
    - liquidity_score
    """

    validate_columns(
        df,
        ["bid", "ask", "volume", "open_interest"],
        "option liquidity metrics",
    )

    result = df

    if "mid_price" not in result.columns:
        result = result.with_columns(
            ((pl.col("bid") + pl.col("ask")) / 2).alias("mid_price")
        )

    if "bid_ask_spread" not in result.columns:
        result = result.with_columns(
            (pl.col("ask") - pl.col("bid")).alias("bid_ask_spread")
        )

    result = result.with_columns(
        [
            pl.when(pl.col("mid_price") > 0)
            .then(pl.col("bid_ask_spread") / pl.col("mid_price"))
            .otherwise(None)
            .alias("spread_pct"),
            pl.when(pl.col("open_interest") > 0)
            .then(pl.col("volume") / pl.col("open_interest"))
            .otherwise(None)
            .alias("volume_oi_ratio"),
            (pl.col("mid_price") * pl.col("volume")).alias(
                "option_dollar_volume"
            ),
            (pl.col("volume") + pl.col("open_interest")).alias(
                "total_activity"
            ),
        ]
    )

    return result.with_columns(
        (
            pl.col("volume").log1p()
            + pl.col("open_interest").log1p()
            + (pl.col("option_dollar_volume").log1p() / 10)
            - pl.col("spread_pct").fill_null(1.0)
        ).alias("liquidity_score")
    )


def filter_liquid_options(
    df: pl.DataFrame,
    max_spread_pct: float = 0.15,
    min_volume: int = 10,
    min_open_interest: int = 100,
    min_option_dollar_volume: float = 0.0,
) -> pl.DataFrame:
    """
    Filter option contracts by liquidity.
    """

    result = add_liquidity_metrics(df)

    return result.filter(
        (pl.col("spread_pct") <= max_spread_pct)
        & (pl.col("volume") >= min_volume)
        & (pl.col("open_interest") >= min_open_interest)
        & (pl.col("option_dollar_volume") >= min_option_dollar_volume)
    )


def rank_by_liquidity(
    df: pl.DataFrame,
    descending: bool = True,
) -> pl.DataFrame:
    """
    Rank options by liquidity score.
    """

    result = add_liquidity_metrics(df)

    return result.sort(
        "liquidity_score",
        descending=descending,
    )


def classify_liquidity(
    df: pl.DataFrame,
    high_threshold: float = 12.0,
    low_threshold: float = 7.0,
) -> pl.DataFrame:
    """
    Classify liquidity quality.
    """

    result = add_liquidity_metrics(df)

    return result.with_columns(
        pl.when(pl.col("liquidity_score") >= high_threshold)
        .then(pl.lit("high"))
        .when(pl.col("liquidity_score") <= low_threshold)
        .then(pl.lit("low"))
        .otherwise(pl.lit("medium"))
        .alias("liquidity_regime")
    )
