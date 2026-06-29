from __future__ import annotations

import polars as pl

from src.strategies.allocation import (
    equal_weight,
    inverse_volatility_weight,
    normalize_long_short,
)
from src.strategies.base import Strategy, StrategyConfig


class MeanReversionStrategy(Strategy):
    """
    Mean reversion strategy.

    Assumes:
    - Negative score = oversold = long
    - Positive score = overbought = short

    Supports:
    - Long-only mean reversion
    - Long/short mean reversion
    - Equal weighting
    - Inverse-volatility weighting
    """

    def __init__(
        self,
        score_col: str = "z_score",
        date_col: str = "date",
        symbol_col: str = "symbol",
        entry_threshold: float = 1.0,
        long_short: bool = True,
        allocation_method: str = "equal",
        volatility_col: str = "volatility",
        long_exposure: float = 1.0,
        short_exposure: float = -1.0,
    ):
        required_columns = [date_col, symbol_col, score_col]

        if allocation_method == "inverse_vol":
            required_columns.append(volatility_col)

        config = StrategyConfig(
            name="mean_reversion",
            date_col=date_col,
            symbol_col=symbol_col,
            required_columns=tuple(required_columns),
        )

        super().__init__(config=config)

        self.score_col = score_col
        self.entry_threshold = entry_threshold
        self.long_short = long_short
        self.allocation_method = allocation_method
        self.volatility_col = volatility_col
        self.long_exposure = long_exposure
        self.short_exposure = short_exposure

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        long_condition = pl.col(self.score_col) <= -self.entry_threshold
        short_condition = pl.col(self.score_col) >= self.entry_threshold

        if self.long_short:
            return data.with_columns(
                pl.when(long_condition)
                .then(1)
                .when(short_condition)
                .then(-1)
                .otherwise(0)
                .alias(self.config.signal_col)
            )

        return data.with_columns(
            pl.when(long_condition)
            .then(1)
            .otherwise(0)
            .alias(self.config.signal_col)
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
