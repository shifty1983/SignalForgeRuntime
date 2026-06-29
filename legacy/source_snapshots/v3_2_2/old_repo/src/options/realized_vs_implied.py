from __future__ import annotations

import polars as pl

from src.options.schema import validate_columns


def compare_realized_vs_implied(
    df: pl.DataFrame,
    implied_col: str = "implied_volatility",
    realized_col: str = "realized_volatility",
) -> pl.DataFrame:
    """
    Compare implied volatility to realized volatility.

    Output:
    - iv_rv_spread
    - iv_rv_ratio
    - iv_rv_premium_pct
    """

    validate_columns(
        df,
        ["symbol", implied_col, realized_col],
        "realized vs implied volatility",
    )

    return df.with_columns(
        [
            (pl.col(implied_col) - pl.col(realized_col)).alias(
                "iv_rv_spread"
            ),
            pl.when(pl.col(realized_col) > 0)
            .then(pl.col(implied_col) / pl.col(realized_col))
            .otherwise(None)
            .alias("iv_rv_ratio"),
            pl.when(pl.col(realized_col) > 0)
            .then(
                (pl.col(implied_col) - pl.col(realized_col))
                / pl.col(realized_col)
            )
            .otherwise(None)
            .alias("iv_rv_premium_pct"),
        ]
    )


def compute_variance_risk_premium(
    df: pl.DataFrame,
    implied_col: str = "implied_volatility",
    realized_col: str = "realized_volatility",
) -> pl.DataFrame:
    """
    Compute variance risk premium.

    Uses variance rather than volatility:

        implied_variance - realized_variance

    Positive values mean implied variance is above realized variance.
    """

    validate_columns(
        df,
        [implied_col, realized_col],
        "variance risk premium",
    )

    return df.with_columns(
        [
            (pl.col(implied_col) * pl.col(implied_col)).alias(
                "implied_variance"
            ),
            (pl.col(realized_col) * pl.col(realized_col)).alias(
                "realized_variance"
            ),
        ]
    ).with_columns(
        (
            pl.col("implied_variance") - pl.col("realized_variance")
        ).alias("variance_risk_premium")
    )


def estimate_expected_move(
    df: pl.DataFrame,
    implied_col: str = "implied_volatility",
    price_col: str = "underlying_price",
    dte_col: str = "days_to_expiration",
    trading_days: int = 252,
) -> pl.DataFrame:
    """
    Estimate one-standard-deviation expected move from implied volatility.

    expected_move = underlying_price * implied_volatility * sqrt(DTE / trading_days)
    """

    validate_columns(
        df,
        [implied_col, price_col, dte_col],
        "expected move estimate",
    )

    return df.with_columns(
        (
            pl.col(price_col)
            * pl.col(implied_col)
            * (pl.col(dte_col) / trading_days).sqrt()
        ).alias("expected_move")
    ).with_columns(
        pl.when(pl.col(price_col) > 0)
        .then(pl.col("expected_move") / pl.col(price_col))
        .otherwise(None)
        .alias("expected_move_pct")
    )


def classify_vol_premium(
    df: pl.DataFrame,
    ratio_col: str = "iv_rv_ratio",
    high_threshold: float = 1.25,
    low_threshold: float = 0.90,
) -> pl.DataFrame:
    """
    Classify implied volatility richness/cheapness.

    Output:
    - rich
    - cheap
    - neutral
    """

    validate_columns(
        df,
        [ratio_col],
        "vol premium classification",
    )

    return df.with_columns(
        pl.when(pl.col(ratio_col) >= high_threshold)
        .then(pl.lit("rich"))
        .when(pl.col(ratio_col) <= low_threshold)
        .then(pl.lit("cheap"))
        .otherwise(pl.lit("neutral"))
        .alias("vol_premium_regime")
    )


def rank_vol_premium(
    df: pl.DataFrame,
    spread_col: str = "iv_rv_spread",
    ratio_col: str = "iv_rv_ratio",
    descending: bool = True,
) -> pl.DataFrame:
    """
    Rank contracts or symbols by implied-over-realized premium.
    """

    validate_columns(
        df,
        [spread_col, ratio_col],
        "vol premium ranking",
    )

    return (
        df.with_columns(
            (
                pl.col(spread_col).fill_null(0.0)
                + pl.col(ratio_col).fill_null(1.0)
            ).alias("vol_premium_score")
        )
        .sort("vol_premium_score", descending=descending)
    )


def attach_realized_volatility(
    option_df: pl.DataFrame,
    realized_df: pl.DataFrame,
    on: list[str] | None = None,
    realized_col: str = "realized_volatility",
) -> pl.DataFrame:
    """
    Attach realized volatility data to an options dataframe.

    Default join key:
    - symbol
    """

    join_cols = on or ["symbol"]

    validate_columns(option_df, join_cols, "option dataframe realized vol join")
    validate_columns(
        realized_df,
        join_cols + [realized_col],
        "realized volatility dataframe",
    )

    realized_subset = realized_df.select(join_cols + [realized_col]).unique(
        subset=join_cols,
        keep="last",
    )

    return option_df.join(
        realized_subset,
        on=join_cols,
        how="left",
    )
