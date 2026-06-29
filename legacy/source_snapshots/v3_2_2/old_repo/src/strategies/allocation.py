from __future__ import annotations

import polars as pl


def equal_weight(
    df: pl.DataFrame,
    group_col: str = "date",
    signal_col: str = "signal",
    weight_col: str = "target_weight",
) -> pl.DataFrame:
    """
    Assign equal weights to active non-zero signals.
    """

    return (
        df.with_columns(
            pl.when(pl.col(signal_col) != 0)
            .then(1)
            .otherwise(0)
            .alias("_active")
        )
        .with_columns(
            pl.col("_active").sum().over(group_col).alias("_active_count")
        )
        .with_columns(
            pl.when(pl.col("_active_count") > 0)
            .then(pl.col(signal_col) / pl.col("_active_count"))
            .otherwise(0.0)
            .alias(weight_col)
        )
        .drop(["_active", "_active_count"])
    )


def normalize_long_short(
    df: pl.DataFrame,
    group_col: str = "date",
    weight_col: str = "target_weight",
    long_exposure: float = 1.0,
    short_exposure: float = -1.0,
) -> pl.DataFrame:
    """
    Normalize long and short books separately.
    """

    return (
        df.with_columns(
            pl.when(pl.col(weight_col) > 0)
            .then(pl.col(weight_col))
            .otherwise(0.0)
            .sum()
            .over(group_col)
            .alias("_long_sum"),
            pl.when(pl.col(weight_col) < 0)
            .then(pl.col(weight_col).abs())
            .otherwise(0.0)
            .sum()
            .over(group_col)
            .alias("_short_sum"),
        )
        .with_columns(
            pl.when((pl.col(weight_col) > 0) & (pl.col("_long_sum") > 0))
            .then(pl.col(weight_col) / pl.col("_long_sum") * long_exposure)
            .when((pl.col(weight_col) < 0) & (pl.col("_short_sum") > 0))
            .then(pl.col(weight_col).abs() / pl.col("_short_sum") * short_exposure)
            .otherwise(0.0)
            .alias(weight_col)
        )
        .drop(["_long_sum", "_short_sum"])
    )


def cap_weights(
    df: pl.DataFrame,
    weight_col: str = "target_weight",
    max_abs_weight: float = 0.10,
) -> pl.DataFrame:
    """
    Cap absolute position weights.
    """

    return df.with_columns(
        pl.col(weight_col)
        .clip(lower_bound=-max_abs_weight, upper_bound=max_abs_weight)
        .alias(weight_col)
    )


def scale_to_gross_exposure(
    df: pl.DataFrame,
    group_col: str = "date",
    weight_col: str = "target_weight",
    gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Scale weights so each group reaches a target gross exposure.
    """

    return (
        df.with_columns(
            pl.col(weight_col).abs().sum().over(group_col).alias("_gross")
        )
        .with_columns(
            pl.when(pl.col("_gross") > 0)
            .then(pl.col(weight_col) / pl.col("_gross") * gross_exposure)
            .otherwise(0.0)
            .alias(weight_col)
        )
        .drop("_gross")
    )


def inverse_volatility_weight(
    df: pl.DataFrame,
    group_col: str = "date",
    signal_col: str = "signal",
    volatility_col: str = "volatility",
    weight_col: str = "target_weight",
) -> pl.DataFrame:
    """
    Allocate active positions using inverse volatility weights.
    """

    return (
        df.with_columns(
            pl.when((pl.col(signal_col) != 0) & (pl.col(volatility_col) > 0))
            .then(1 / pl.col(volatility_col))
            .otherwise(0.0)
            .alias("_inv_vol")
        )
        .with_columns(
            pl.col("_inv_vol").sum().over(group_col).alias("_inv_vol_sum")
        )
        .with_columns(
            pl.when(pl.col("_inv_vol_sum") > 0)
            .then(
                pl.col(signal_col)
                * pl.col("_inv_vol")
                / pl.col("_inv_vol_sum")
            )
            .otherwise(0.0)
            .alias(weight_col)
        )
        .drop(["_inv_vol", "_inv_vol_sum"])
    )
