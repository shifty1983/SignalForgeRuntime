from __future__ import annotations

import polars as pl


def inflation_rate(
    df: pl.DataFrame,
    column: str,
    periods: int = 1,
    output_column: str |None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if periods <= 0:
        raise ValueError("periods must be positive")

    output_column = output_column or f"{column}_inflation_rate"

    return df.with_columns(
        pl.col(column).pct_change(periods).alias(output_column)
    )


def inflation_trend(
    df: pl.DataFrame,
    column: str,
    window: int = 3,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if window <= 0:
        raise ValueError("window must be positive")

    output_column = output_column or f"{column}_inflation_trend"

    return df.with_columns(
        pl.col(column).rolling_mean(window).alias(output_column)
    )


def classify_inflation(
    df: pl.DataFrame,
    column: str,
    output_column: str = "inflation_regime",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return df.with_columns(
        pl.when(pl.col(column) > 0)
        .then(pl.lit("inflation_rising"))
        .when(pl.col(column) < 0)
        .then(pl.lit("inflation_falling"))
        .otherwise(pl.lit("inflation_stable"))
        .alias(output_column)
    )
