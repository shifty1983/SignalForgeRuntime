from __future__ import annotations

import polars as pl


def liquidity_change(
    df: pl.DataFrame,
    column: str,
    periods: int = 1,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if periods <= 0:
        raise ValueError("periods must be positive")

    output_column = output_column or f"{column}_liquidity_change"

    return df.with_columns(
        pl.col(column).pct_change(periods).alias(output_column)
    )


def liquidity_trend(
    df: pl.DataFrame,
    column: str,
    window: int = 3,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if window <= 0:
        raise ValueError("window must be positive")

    output_column = output_column or f"{column}_liquidity_trend"

    return df.with_columns(
        pl.col(column).rolling_mean(window).alias(output_column)
    )


def classify_liquidity(
    df: pl.DataFrame,
    column: str,
    output_column: str = "liquidity_regime",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return df.with_columns(
        pl.when(pl.col(column) > 0)
        .then(pl.lit("liquidity_expanding"))
        .when(pl.col(column) < 0)
        .then(pl.lit("liquidity_contracting"))
        .otherwise(pl.lit("liquidity_neutral"))
        .alias(output_column)
    )


