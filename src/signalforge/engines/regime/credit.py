from __future__ import annotations

import polars as pl


def credit_spread_change(
    df: pl.DataFrame,
    column: str,
    periods: int = 1,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")
    if periods <= 0:
        raise ValueError("periods must be positive")
    output_column = output_column or f"{column}_credit_spread_change"
    return df.with_columns(pl.col(column).diff(periods).alias(output_column))


def classify_credit(
    df: pl.DataFrame,
    column: str,
    output_column: str = "credit_regime",
) -> pl.DataFrame:
    """Classify credit conditions from a spread-change style metric.

    Positive spread change means credit stress is increasing. Negative spread
    change means credit conditions are improving.
    """
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")
    return df.with_columns(
        pl.when(pl.col(column) > 0)
        .then(pl.lit("credit_deteriorating"))
        .when(pl.col(column) < 0)
        .then(pl.lit("credit_improving"))
        .otherwise(pl.lit("credit_stable"))
        .alias(output_column)
    )


def classify_credit_level(
    df: pl.DataFrame,
    column: str,
    output_column: str = "credit_stress_level",
    *,
    low_stress_threshold: float = 4.0,
    high_stress_threshold: float = 6.0,
) -> pl.DataFrame:
    """Classify the absolute level of a credit spread.

    Defaults are intentionally broad for high-yield OAS style inputs.
    """
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")
    if low_stress_threshold >= high_stress_threshold:
        raise ValueError("low_stress_threshold must be below high_stress_threshold")
    return df.with_columns(
        pl.when(pl.col(column).is_null())
        .then(None)
        .when(pl.col(column) >= high_stress_threshold)
        .then(pl.lit("credit_high_stress"))
        .when(pl.col(column) <= low_stress_threshold)
        .then(pl.lit("credit_low_stress"))
        .otherwise(pl.lit("credit_normal_stress"))
        .alias(output_column)
    )


