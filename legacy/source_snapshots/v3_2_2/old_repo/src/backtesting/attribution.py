from __future__ import annotations

import polars as pl


def compute_asset_contribution(
    results: pl.DataFrame,
    weight_col: str = "target_weight",
    return_col: str = "asset_return",
) -> pl.DataFrame:
    """
    Compute return contribution by asset.
    """

    return results.with_columns(
        (pl.col(weight_col) * pl.col(return_col)).alias("return_contribution")
    )


def summarize_contribution(
    contributions: pl.DataFrame,
    symbol_col: str = "symbol",
    contribution_col: str = "return_contribution",
) -> pl.DataFrame:
    """
    Summarize total contribution by symbol.
    """

    return (
        contributions.group_by(symbol_col)
        .agg(
            pl.col(contribution_col).sum().alias("total_contribution"),
            pl.col(contribution_col).mean().alias("avg_contribution"),
        )
        .sort("total_contribution", descending=True)
    )


def compute_strategy_return(
    contributions: pl.DataFrame,
    date_col: str = "date",
    contribution_col: str = "return_contribution",
) -> pl.DataFrame:
    """
    Aggregate asset contributions into daily strategy returns.
    """

    return (
        contributions.group_by(date_col)
        .agg(pl.col(contribution_col).sum().alias("strategy_return"))
        .sort(date_col)
    )
