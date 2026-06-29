from __future__ import annotations

from dataclasses import dataclass

import polars as pl


BASE_OPTION_COLUMNS = [
    "symbol",
    "expiration",
    "strike",
    "option_type",
    "bid",
    "ask",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "underlying_price",
]


OPTION_ANALYTIC_COLUMNS = [
    "mid_price",
    "bid_ask_spread",
    "spread_pct",
    "moneyness",
    "days_to_expiration",
]


VALID_OPTION_TYPES = {"call", "put"}


@dataclass(frozen=True)
class OptionSchema:
    """
    Shared schema contract for the options analytics layer.
    """

    required_columns: tuple[str, ...] = tuple(BASE_OPTION_COLUMNS)
    analytic_columns: tuple[str, ...] = tuple(OPTION_ANALYTIC_COLUMNS)


def validate_columns(
    df: pl.DataFrame,
    required: list[str] | tuple[str, ...],
    context: str = "options dataframe",
) -> None:
    """
    Validate that a dataframe contains required columns.
    """

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"{context} missing required columns: {missing}")


def normalize_option_type(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normalize option_type values to lowercase call/put.
    """

    validate_columns(df, ["option_type"], "option type normalization")

    result = df.with_columns(
        pl.col("option_type").str.to_lowercase().alias("option_type")
    )

    invalid = (
        result.filter(~pl.col("option_type").is_in(list(VALID_OPTION_TYPES)))
        .select("option_type")
        .unique()
    )

    if invalid.height > 0:
        raise ValueError(
            f"Invalid option_type values: {invalid['option_type'].to_list()}"
        )

    return result


def add_core_option_fields(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add core derived fields used throughout the options analytics layer.
    """

    validate_columns(
        df,
        [
            "bid",
            "ask",
            "strike",
            "underlying_price",
        ],
        "core option field calculation",
    )

    return df.with_columns(
        [
            ((pl.col("bid") + pl.col("ask")) / 2).alias("mid_price"),
            (pl.col("ask") - pl.col("bid")).alias("bid_ask_spread"),
            (
                (pl.col("ask") - pl.col("bid"))
                / ((pl.col("ask") + pl.col("bid")) / 2)
            ).alias("spread_pct"),
            (pl.col("strike") / pl.col("underlying_price")).alias("moneyness"),
        ]
    )


def validate_positive_values(
    df: pl.DataFrame,
    columns: list[str] | tuple[str, ...],
    context: str = "options dataframe",
) -> None:
    """
    Validate that selected numeric columns are non-negative.
    """

    validate_columns(df, columns, context)

    for column in columns:
        if df.filter(pl.col(column) < 0).height > 0:
            raise ValueError(f"{context} contains negative values in {column}")


def validate_option_chain(df: pl.DataFrame) -> pl.DataFrame:
    """
    Validate and normalize a raw option chain.
    """

    validate_columns(df, BASE_OPTION_COLUMNS, "option chain")

    validate_positive_values(
        df,
        [
            "strike",
            "bid",
            "ask",
            "volume",
            "open_interest",
            "implied_volatility",
            "underlying_price",
        ],
        "option chain",
    )

    result = normalize_option_type(df)

    crossed_markets = result.filter(pl.col("ask") < pl.col("bid"))

    if crossed_markets.height > 0:
        raise ValueError("option chain contains rows where ask < bid")

    return result
