from __future__ import annotations

import polars as pl


def summarize_returns(
    df: pl.DataFrame,
    return_col: str = "return",
) -> pl.DataFrame:
    """
    Summarize basic return behavior for an asset or strategy.
    """
    if return_col not in df.columns:
        raise ValueError(f"Missing required column: {return_col}")

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    return df.select(
        pl.col(return_col).mean().alias("mean_return"),
        pl.col(return_col).std().alias("return_volatility"),
        pl.col(return_col).min().alias("min_return"),
        pl.col(return_col).max().alias("max_return"),
        pl.col(return_col).median().alias("median_return"),
        pl.col(return_col).skew().alias("skew"),
        pl.col(return_col).kurtosis().alias("kurtosis"),
    )


def classify_return_behavior(
    df: pl.DataFrame,
    return_col: str = "return",
    positive_threshold: float = 0.0,
) -> str:
    """
    Classify return behavior based on average returns.
    """
    summary = summarize_returns(df, return_col)
    mean_return = summary["mean_return"][0]

    if mean_return > positive_threshold:
        return "positive"
    if mean_return < -positive_threshold:
        return "negative"
    return "neutral"
