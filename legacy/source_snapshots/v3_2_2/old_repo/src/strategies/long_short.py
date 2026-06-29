from __future__ import annotations

import polars as pl

from src.strategies.allocation import equal_weight, normalize_long_short
from src.strategies.base import Strategy, StrategyConfig


class LongShortStrategy(Strategy):
    """
    Cross-sectional long/short strategy.

    Assumes lower rank is better:
    - Long top-ranked assets
    - Short bottom-ranked assets
    """

    def __init__(
        self,
        rank_col: str = "rank",
        date_col: str = "date",
        symbol_col: str = "symbol",
        long_quantile: float = 0.2,
        short_quantile: float = 0.2,
        long_exposure: float = 1.0,
        short_exposure: float = -1.0,
    ):
        config = StrategyConfig(
            name="long_short",
            date_col=date_col,
            symbol_col=symbol_col,
            required_columns=(date_col, symbol_col, rank_col),
        )

        super().__init__(config=config)

        self.rank_col = rank_col
        self.long_quantile = long_quantile
        self.short_quantile = short_quantile
        self.long_exposure = long_exposure
        self.short_exposure = short_exposure

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        return (
            data.with_columns(
                pl.len().over(self.config.date_col).alias("_n_assets")
            )
            .with_columns(
                (pl.col("_n_assets") * self.long_quantile)
                .ceil()
                .alias("_long_cutoff"),
                (pl.col("_n_assets") * (1 - self.short_quantile))
                .floor()
                .alias("_short_cutoff"),
            )
            .with_columns(
                pl.when(pl.col(self.rank_col) <= pl.col("_long_cutoff"))
                .then(1)
                .when(pl.col(self.rank_col) > pl.col("_short_cutoff"))
                .then(-1)
                .otherwise(0)
                .alias(self.config.signal_col)
            )
            .drop(["_n_assets", "_long_cutoff", "_short_cutoff"])
        )

    def generate_target_weights(self, signals: pl.DataFrame) -> pl.DataFrame:
        weighted = equal_weight(
            signals,
            group_col=self.config.date_col,
            signal_col=self.config.signal_col,
            weight_col=self.config.weight_col,
        )

        return normalize_long_short(
            weighted,
            group_col=self.config.date_col,
            weight_col=self.config.weight_col,
            long_exposure=self.long_exposure,
            short_exposure=self.short_exposure,
        )
