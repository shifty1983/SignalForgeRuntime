from __future__ import annotations

import polars as pl


class ExecutionModel:
    """
    Simple execution model for converting target positions into trades.
    """

    def __init__(
        self,
        commission_per_trade: float = 0.0,
        slippage_bps: float = 0.0,
    ):
        self.commission_per_trade = commission_per_trade
        self.slippage_bps = slippage_bps

    def compute_trades(
        self,
        positions: pl.DataFrame,
        date_col: str = "date",
        symbol_col: str = "symbol",
        shares_col: str = "shares",
    ) -> pl.DataFrame:
        """
        Compute trade quantities from changes in target shares.
        """

        return (
            positions.sort([symbol_col, date_col])
            .with_columns(
                pl.col(shares_col)
                .shift(1)
                .over(symbol_col)
                .fill_null(0.0)
                .alias("previous_shares")
            )
            .with_columns(
                (pl.col(shares_col) - pl.col("previous_shares")).alias("trade_shares")
            )
        )

    def apply_costs(
        self,
        trades: pl.DataFrame,
        price_col: str = "close",
    ) -> pl.DataFrame:
        """
        Apply simple commission and slippage costs.
        """

        return trades.with_columns(
            (pl.col("trade_shares").abs() * pl.col(price_col)).alias("trade_value")
        ).with_columns(
            (
                self.commission_per_trade
                + pl.col("trade_value") * (self.slippage_bps / 10_000)
            ).alias("transaction_cost")
        )

    def execute(self, positions: pl.DataFrame) -> pl.DataFrame:
        """
        Full execution pipeline.
        """

        trades = self.compute_trades(positions)
        return self.apply_costs(trades)




