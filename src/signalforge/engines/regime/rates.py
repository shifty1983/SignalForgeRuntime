from __future__ import annotations

import polars as pl


def rate_change(
    df: pl.DataFrame,
    column: str,
    periods: int = 1,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if periods <= 0:
        raise ValueError("periods must be positive")

    output_column = output_column or f"{column}_rate_change"

    return df.with_columns(
        pl.col(column).diff(periods).alias(output_column)
    )


def yield_curve_spread(
    df: pl.DataFrame,
    long_rate: str,
    short_rate: str,
    output_column: str = "yield_curve_spread",
) -> pl.DataFrame:
    missing = [c for c in [long_rate, short_rate] if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.with_columns(
        (pl.col(long_rate) - pl.col(short_rate)).alias(output_column)
    )


def classify_rates(
    df: pl.DataFrame,
    column: str,
    output_column: str = "rates_regime",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return df.with_columns(
        pl.when(pl.col(column) > 0)
        .then(pl.lit("rates_rising"))
        .when(pl.col(column) < 0)
        .then(pl.lit("rates_falling"))
        .otherwise(pl.lit("rates_stable"))
        .alias(output_column)
    )




