from __future__ import annotations

import polars as pl

from src.strategies.allocation import (
    equal_weight,
    inverse_volatility_weight,
    normalize_long_short,
)
from src.strategies.base import Strategy, StrategyConfig


class MomentumStrategy(Strategy):
    """
    Momentum strategy.

    Supports:
    - Long-only momentum
    - Optional long/short momentum
    - Top-N selection
    - Optional inverse-volatility weighting
    """

    def __init__(
        self,
        momentum_col: str = "momentum",
        date_col: str = "date",
        symbol_col: str = "symbol",
        top_n: int | None = None,
        bottom_n: int | None = None,
        min_momentum: float = 0.0,
        long_short: bool = False,
        allocation_method: str = "equal",
        volatility_col: str = "volatility",
        long_exposure: float = 1.0,
        short_exposure: float = -1.0,
    ):
        required_columns = [date_col, symbol_col, momentum_col]

        if allocation_method == "inverse_vol":
            required_columns.append(volatility_col)

        config = StrategyConfig(
            name="momentum",
            date_col=date_col,
            symbol_col=symbol_col,
            required_columns=tuple(required_columns),
        )

        super().__init__(config=config)

        self.momentum_col = momentum_col
        self.top_n = top_n
        self.bottom_n = bottom_n
        self.min_momentum = min_momentum
        self.long_short = long_short
        self.allocation_method = allocation_method
        self.volatility_col = volatility_col
        self.long_exposure = long_exposure
        self.short_exposure = short_exposure

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        df = data.with_columns(
            pl.col(self.momentum_col)
            .rank(method="ordinal", descending=True)
            .over(self.config.date_col)
            .alias("_strong_rank"),
            pl.col(self.momentum_col)
            .rank(method="ordinal", descending=False)
            .over(self.config.date_col)
            .alias("_weak_rank"),
        )

        if self.top_n is not None:
            long_condition = pl.col("_strong_rank") <= self.top_n
        else:
            long_condition = pl.col(self.momentum_col) > self.min_momentum

        if self.long_short:
            if self.bottom_n is not None:
                short_condition = pl.col("_weak_rank") <= self.bottom_n
            else:
                short_condition = pl.col(self.momentum_col) < -self.min_momentum

            return (
                df.with_columns(
                    pl.when(long_condition)
                    .then(1)
                    .when(short_condition)
                    .then(-1)
                    .otherwise(0)
                    .alias(self.config.signal_col)
                )
                .drop(["_strong_rank", "_weak_rank"])
            )

        return (
            df.with_columns(
                pl.when(long_condition)
                .then(1)
                .otherwise(0)
                .alias(self.config.signal_col)
            )
            .drop(["_strong_rank", "_weak_rank"])
        )

    def generate_target_weights(self, signals: pl.DataFrame) -> pl.DataFrame:
        if self.allocation_method == "inverse_vol":
            weighted = inverse_volatility_weight(
                signals,
                group_col=self.config.date_col,
                signal_col=self.config.signal_col,
                volatility_col=self.volatility_col,
                weight_col=self.config.weight_col,
            )
        elif self.allocation_method == "equal":
            weighted = equal_weight(
                signals,
                group_col=self.config.date_col,
                signal_col=self.config.signal_col,
                weight_col=self.config.weight_col,
            )
        else:
            raise ValueError(
                f"Unsupported allocation_method: {self.allocation_method}"
            )

        if self.long_short:
            return normalize_long_short(
                weighted,
                group_col=self.config.date_col,
                weight_col=self.config.weight_col,
                long_exposure=self.long_exposure,
                short_exposure=self.short_exposure,
            )

        return weighted
