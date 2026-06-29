from __future__ import annotations

import polars as pl


def yield_curve_direction(
    df: pl.DataFrame,
    column: str,
    periods: int = 1,
    output_column: str = "yield_curve_direction",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")
    if periods <= 0:
        raise ValueError("periods must be positive")
    return df.with_columns(
        pl.when(pl.col(column).diff(periods) > 0)
        .then(pl.lit("curve_steepening"))
        .when(pl.col(column).diff(periods) < 0)
        .then(pl.lit("curve_flattening"))
        .otherwise(pl.lit("curve_stable"))
        .alias(output_column)
    )


def classify_yield_curve(
    df: pl.DataFrame,
    spread_column: str = "yield_curve_spread",
    direction_column: str = "yield_curve_direction",
    output_column: str = "yield_curve_regime",
    *,
    inverted_threshold: float = 0.0,
    normal_threshold: float = 1.0,
) -> pl.DataFrame:
    if spread_column not in df.columns:
        raise ValueError(f"Missing column: {spread_column}")
    if direction_column not in df.columns:
        raise ValueError(f"Missing column: {direction_column}")
    if inverted_threshold >= normal_threshold:
        raise ValueError("inverted_threshold must be below normal_threshold")

    return df.with_columns(
        pl.when(pl.col(spread_column).is_null())
        .then(None)
        .when((pl.col(spread_column) < inverted_threshold) & (pl.col(direction_column) == "curve_steepening"))
        .then(pl.lit("curve_bearish_resteepening"))
        .when(pl.col(spread_column) < inverted_threshold)
        .then(pl.lit("curve_inverted"))
        .when((pl.col(spread_column) < normal_threshold) & (pl.col(direction_column) == "curve_flattening"))
        .then(pl.lit("curve_flattening"))
        .when((pl.col(spread_column) < normal_threshold) & (pl.col(direction_column) == "curve_steepening"))
        .then(pl.lit("curve_resteepening"))
        .otherwise(pl.lit("curve_normal"))
        .alias(output_column)
    )
