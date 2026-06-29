from __future__ import annotations

import polars as pl

from src.options.schema import (
    add_core_option_fields,
    validate_columns,
    validate_option_chain,
)


class OptionChain:
    """
    Standardized option chain container.

    Responsibilities:
    - validate raw option chain input
    - normalize option_type values
    - add common derived fields
    - provide basic chain filtering utilities
    """

    def __init__(
        self,
        df: pl.DataFrame,
        add_core_fields: bool = True,
    ):
        validated = validate_option_chain(df)

        if add_core_fields:
            validated = add_core_option_fields(validated)

        self.df = validated

    @property
    def data(self) -> pl.DataFrame:
        return self.df

    def add_mid_price(self) -> pl.DataFrame:
        """
        Add midpoint price.
        """

        return self.df.with_columns(
            ((pl.col("bid") + pl.col("ask")) / 2).alias("mid_price")
        )

    def add_spread(self) -> pl.DataFrame:
        """
        Add absolute bid/ask spread.

        Includes both:
        - bid_ask_spread: preferred standard column
        - spread: backward-compatible alias
        """

        return self.df.with_columns(
            [
                (pl.col("ask") - pl.col("bid")).alias("bid_ask_spread"),
                (pl.col("ask") - pl.col("bid")).alias("spread"),
            ]
        )

    def add_moneyness(self) -> pl.DataFrame:
        """
        Add strike / underlying price ratio.
        """

        return self.df.with_columns(
            (pl.col("strike") / pl.col("underlying_price")).alias("moneyness")
        )

    def filter_expiration(
        self,
        min_days: int | None = None,
        max_days: int | None = None,
    ) -> pl.DataFrame:
        """
        Filter by days to expiration.
        """

        validate_columns(
            self.df,
            ["days_to_expiration"],
            "expiration filtering",
        )

        df = self.df

        if min_days is not None:
            df = df.filter(pl.col("days_to_expiration") >= min_days)

        if max_days is not None:
            df = df.filter(pl.col("days_to_expiration") <= max_days)

        return df

    def filter_option_type(
        self,
        option_type: str,
    ) -> pl.DataFrame:
        """
        Filter calls or puts.
        """

        option_type = option_type.lower()

        if option_type not in {"call", "put"}:
            raise ValueError("option_type must be 'call' or 'put'")

        return self.df.filter(pl.col("option_type") == option_type)

    def filter_strikes(
        self,
        min_strike: float | None = None,
        max_strike: float | None = None,
    ) -> pl.DataFrame:
        """
        Filter strike range.
        """

        df = self.df

        if min_strike is not None:
            df = df.filter(pl.col("strike") >= min_strike)

        if max_strike is not None:
            df = df.filter(pl.col("strike") <= max_strike)

        return df

    def filter_moneyness(
        self,
        min_moneyness: float | None = None,
        max_moneyness: float | None = None,
    ) -> pl.DataFrame:
        """
        Filter by moneyness range.
        """

        validate_columns(
            self.df,
            ["moneyness"],
            "moneyness filtering",
        )

        df = self.df

        if min_moneyness is not None:
            df = df.filter(pl.col("moneyness") >= min_moneyness)

        if max_moneyness is not None:
            df = df.filter(pl.col("moneyness") <= max_moneyness)

        return df

    def near_the_money(
        self,
        tolerance: float = 0.05,
    ) -> pl.DataFrame:
        """
        Return contracts near at-the-money.

        tolerance=0.05 keeps contracts with moneyness between 0.95 and 1.05.
        """

        validate_columns(
            self.df,
            ["moneyness"],
            "near-the-money filtering",
        )

        return self.df.filter(
            (pl.col("moneyness") >= 1.0 - tolerance)
            & (pl.col("moneyness") <= 1.0 + tolerance)
        )

    def summary(self) -> dict:
        """
        Chain summary statistics.
        """

        summary = {
            "rows": self.df.height,
            "symbols": self.df["symbol"].n_unique(),
            "expirations": self.df["expiration"].n_unique(),
            "min_strike": self.df["strike"].min(),
            "max_strike": self.df["strike"].max(),
        }

        if "days_to_expiration" in self.df.columns:
            summary["min_days_to_expiration"] = self.df[
                "days_to_expiration"
            ].min()
            summary["max_days_to_expiration"] = self.df[
                "days_to_expiration"
            ].max()

        return summary
