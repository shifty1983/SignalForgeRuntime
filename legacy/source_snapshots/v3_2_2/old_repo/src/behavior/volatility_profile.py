from __future__ import annotations

import polars as pl


def realized_volatility(
    df: pl.DataFrame,
    return_col: str = "return",
    annualization_factor: int = 252,
) -> float:
    """
    Compute annualized realized volatility.
    """
    if return_col not in df.columns:
        raise ValueError(f"Missing required column: {return_col}")

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    daily_vol = df.select(
        pl.col(return_col).std().alias("daily_vol")
    )["daily_vol"][0]

    return float(daily_vol * (annualization_factor ** 0.5))


def rolling_volatility(
    df: pl.DataFrame,
    window: int = 20,
    return_col: str = "return",
    annualization_factor: int = 252,
) -> pl.DataFrame:
    """
    Compute rolling annualized volatility.
    """
    if return_col not in df.columns:
        raise ValueError(f"Missing required column: {return_col}")

    result = df.with_columns(
        (
            pl.col(return_col)
            .rolling_std(window_size=window)
            * (annualization_factor ** 0.5)
        ).alias(f"rolling_vol_{window}")
    )

    return result


def classify_volatility_regime(
    volatility: float,
    low_threshold: float = 0.10,
    high_threshold: float = 0.25,
) -> str:
    """
    Classify volatility environment.
    """
    if volatility < low_threshold:
        return "low_vol"

    if volatility > high_threshold:
        return "high_vol"

    return "normal_vol"
