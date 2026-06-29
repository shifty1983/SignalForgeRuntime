from __future__ import annotations

import polars as pl


def rolling_correlation(
    df: pl.DataFrame,
    x_col: str,
    y_col: str,
    window: int = 20,
) -> pl.DataFrame:
    """
    Compute rolling correlation between two return series.
    """
    required = [x_col, y_col]

    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    result = df.with_columns(
        pl.rolling_corr(
            pl.col(x_col),
            pl.col(y_col),
            window_size=window,
        ).alias(f"corr_{x_col}_{y_col}_{window}")
    )

    return result


def correlation_strength(
    correlation: float,
) -> str:
    """
    Classify correlation strength.
    """
    abs_corr = abs(correlation)

    if abs_corr >= 0.80:
        return "strong"

    if abs_corr >= 0.50:
        return "moderate"

    return "weak"


def correlation_direction(
    correlation: float,
) -> str:
    """
    Classify correlation direction.
    """
    if correlation > 0:
        return "positive"

    if correlation < 0:
        return "negative"

    return "neutral"
