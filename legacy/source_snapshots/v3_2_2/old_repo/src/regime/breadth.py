from __future__ import annotations

from collections.abc import Sequence

import polars as pl


def moving_average_breadth(
    df: pl.DataFrame,
    price_columns: Sequence[str],
    *,
    window: int = 200,
    output_column: str = "breadth_score",
) -> pl.DataFrame:
    """Calculate the share of price columns trading above their moving average.

    The output is a 0.0 to 1.0 score. A value of 0.80 means 80% of the
    supplied assets are above their rolling moving average.
    """
    columns = _validate_price_columns(df, price_columns)
    if window <= 0:
        raise ValueError("window must be positive")

    above_columns = [f"{column}_above_{window}ma" for column in columns]
    result = df.with_columns(
        [
            (pl.col(column) > pl.col(column).rolling_mean(window)).cast(pl.Float64).alias(alias)
            for column, alias in zip(columns, above_columns, strict=True)
        ]
    )

    return result.with_columns(
        pl.mean_horizontal([pl.col(column) for column in above_columns]).alias(output_column)
    )


def equal_weight_relative_breadth(
    df: pl.DataFrame,
    price_columns: Sequence[str],
    benchmark_column: str,
    *,
    periods: int = 20,
    output_column: str = "relative_breadth_score",
) -> pl.DataFrame:
    """Calculate the share of assets outperforming a benchmark over a lookback."""
    columns = _validate_price_columns(df, price_columns)
    if benchmark_column not in df.columns:
        raise ValueError(f"Missing column: {benchmark_column}")
    if periods <= 0:
        raise ValueError("periods must be positive")

    outperform_columns = [f"{column}_outperforming_{benchmark_column}_{periods}" for column in columns]
    benchmark_return = pl.col(benchmark_column).pct_change(periods)
    result = df.with_columns(
        [
            (pl.col(column).pct_change(periods) > benchmark_return).cast(pl.Float64).alias(alias)
            for column, alias in zip(columns, outperform_columns, strict=True)
        ]
    )

    return result.with_columns(
        pl.mean_horizontal([pl.col(column) for column in outperform_columns]).alias(output_column)
    )


def breadth_trend(
    df: pl.DataFrame,
    column: str = "breadth_score",
    *,
    periods: int = 1,
    output_column: str = "breadth_trend",
) -> pl.DataFrame:
    """Measure whether breadth is improving or deteriorating."""
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")
    if periods <= 0:
        raise ValueError("periods must be positive")

    return df.with_columns(pl.col(column).diff(periods).alias(output_column))


def classify_breadth(
    df: pl.DataFrame,
    score_column: str = "breadth_score",
    trend_column: str = "breadth_trend",
    output_column: str = "breadth_regime",
    *,
    broad_strength_threshold: float = 0.70,
    broad_weakness_threshold: float = 0.30,
    improving_threshold: float = 0.10,
    deteriorating_threshold: float = -0.10,
) -> pl.DataFrame:
    """Classify breadth into broad strength, weakness, or transition states."""
    missing = [column for column in [score_column, trend_column] if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    if not 0 <= broad_weakness_threshold < broad_strength_threshold <= 1:
        raise ValueError("breadth thresholds must satisfy 0 <= weakness < strength <= 1")
    if deteriorating_threshold >= improving_threshold:
        raise ValueError("deteriorating_threshold must be below improving_threshold")

    score = pl.col(score_column)
    trend = pl.col(trend_column)

    return df.with_columns(
        pl.when(score.is_null() | trend.is_null())
        .then(None)
        .when(score >= broad_strength_threshold)
        .then(pl.lit("broad_strength"))
        .when(score <= broad_weakness_threshold)
        .then(pl.lit("broad_weakness"))
        .when(trend >= improving_threshold)
        .then(pl.lit("breadth_improving"))
        .when(trend <= deteriorating_threshold)
        .then(pl.lit("breadth_deteriorating"))
        .otherwise(pl.lit("mixed_breadth"))
        .alias(output_column)
    )


def _validate_price_columns(df: pl.DataFrame, price_columns: Sequence[str]) -> list[str]:
    columns = list(price_columns)
    if not columns:
        raise ValueError("price_columns must not be empty")

    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return columns
