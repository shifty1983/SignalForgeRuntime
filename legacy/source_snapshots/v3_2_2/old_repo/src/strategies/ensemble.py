from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from src.strategies.base import Strategy


@dataclass(frozen=True)
class StrategyWeight:
    """
    Weight assigned to an individual strategy inside an ensemble.
    """

    strategy: Strategy
    weight: float


class EnsembleStrategy:
    """
    Blend multiple strategy outputs into one combined target-weight table.

    Each underlying strategy must return:
    - date
    - symbol
    - target_weight
    - strategy_name
    """

    def __init__(
        self,
        strategies: list[StrategyWeight],
        name: str = "ensemble",
        date_col: str = "date",
        symbol_col: str = "symbol",
        weight_col: str = "target_weight",
    ):
        if not strategies:
            raise ValueError("EnsembleStrategy requires at least one strategy.")

        total_weight = sum(item.weight for item in strategies)

        if total_weight == 0:
            raise ValueError("Total ensemble strategy weight cannot be zero.")

        self.strategies = strategies
        self.name = name
        self.date_col = date_col
        self.symbol_col = symbol_col
        self.weight_col = weight_col
        self.total_weight = total_weight

    def run(self, data: pl.DataFrame) -> pl.DataFrame:
        """
        Run each strategy and blend target weights.
        """

        outputs: list[pl.DataFrame] = []

        for item in self.strategies:
            strategy_output = item.strategy.run(data)

            weighted_output = strategy_output.with_columns(
                (
                    pl.col(self.weight_col)
                    * (item.weight / self.total_weight)
                ).alias("_weighted_target")
            )

            outputs.append(weighted_output)

        combined = pl.concat(outputs, how="diagonal")

        return (
            combined.group_by([self.date_col, self.symbol_col])
            .agg(
                pl.col("_weighted_target").sum().alias(self.weight_col)
            )
            .with_columns(
                pl.lit(self.name).alias("strategy_name")
            )
            .sort([self.date_col, self.symbol_col])
        )
