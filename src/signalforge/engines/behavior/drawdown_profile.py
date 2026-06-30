from __future__ import annotations

import polars as pl


def compute_drawdown(
    df: pl.DataFrame,
    equity_col: str = "equity",
) -> pl.DataFrame:
    """
    Compute drawdown series from equity curve.
    """
    if equity_col not in df.columns:
        raise ValueError(f"Missing required column: {equity_col}")

    if df.is_empty():
        raise ValueError("Input DataFrame is empty")

    result = df.with_columns(
        [
            pl.col(equity_col)
            .cum_max()
            .alias("rolling_peak"),
        ]
    ).with_columns(
        (
            (
                pl.col(equity_col)
                - pl.col("rolling_peak")
            )
            / pl.col("rolling_peak")
        ).alias("drawdown")
    )

    return result


def max_drawdown(
    df: pl.DataFrame,
    drawdown_col: str = "drawdown",
) -> float:
    """
    Compute maximum drawdown.
    """
    if drawdown_col not in df.columns:
        raise ValueError(
            f"Missing required column: {drawdown_col}"
        )

    return float(
        df.select(
            pl.col(drawdown_col).min()
        ).item()
    )


def classify_drawdown(
    max_dd: float,
) -> str:
    """
    Classify drawdown severity.
    """
    abs_dd = abs(max_dd)

    if abs_dd < 0.10:
        return "shallow_drawdown"

    if abs_dd < 0.25:
        return "moderate_drawdown"

    return "deep_drawdown"


