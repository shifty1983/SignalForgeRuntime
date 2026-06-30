from __future__ import annotations

import polars as pl

from src.signalforge.engines.options.schema import (
    normalize_option_type,
    validate_columns,
)


def build_iv_surface(df: pl.DataFrame) -> pl.DataFrame:
    """
    Build a normalized implied volatility surface.

    Output is organized by:
    - symbol
    - expiration
    - days_to_expiration, if available
    - strike
    - moneyness
    - option_type
    - implied_volatility
    """

    required = [
        "symbol",
        "expiration",
        "strike",
        "option_type",
        "implied_volatility",
        "underlying_price",
    ]

    validate_columns(df, required, "IV surface")

    result = normalize_option_type(df)

    if "moneyness" not in result.columns:
        result = result.with_columns(
            (pl.col("strike") / pl.col("underlying_price")).alias("moneyness")
        )

    columns = [
        "symbol",
        "expiration",
        "days_to_expiration",
        "strike",
        "moneyness",
        "option_type",
        "implied_volatility",
    ]

    selected = [column for column in columns if column in result.columns]

    return result.select(selected).sort(
        ["symbol", "expiration", "option_type", "moneyness"]
    )


def get_surface_slice(
    df: pl.DataFrame,
    symbol: str,
    expiration: str,
    option_type: str | None = None,
    min_moneyness: float | None = None,
    max_moneyness: float | None = None,
) -> pl.DataFrame:
    """
    Get one expiration slice of the IV surface.
    """

    validate_columns(
        df,
        ["symbol", "expiration", "option_type"],
        "IV surface slice",
    )

    result = df.filter(
        (pl.col("symbol") == symbol)
        & (pl.col("expiration") == expiration)
    )

    if option_type is not None:
        result = result.filter(
            pl.col("option_type").str.to_lowercase() == option_type.lower()
        )

    if min_moneyness is not None:
        validate_columns(result, ["moneyness"], "IV surface moneyness filter")
        result = result.filter(pl.col("moneyness") >= min_moneyness)

    if max_moneyness is not None:
        validate_columns(result, ["moneyness"], "IV surface moneyness filter")
        result = result.filter(pl.col("moneyness") <= max_moneyness)

    return result


def add_moneyness_bucket(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add simple moneyness buckets for surface analysis.

    Buckets are intentionally option-type neutral:
    - deep_low_strike
    - low_strike
    - atm
    - high_strike
    - deep_high_strike
    """

    validate_columns(df, ["moneyness"], "moneyness bucket")

    return df.with_columns(
        pl.when(pl.col("moneyness") < 0.90)
        .then(pl.lit("deep_low_strike"))
        .when(pl.col("moneyness") < 0.97)
        .then(pl.lit("low_strike"))
        .when(pl.col("moneyness") <= 1.03)
        .then(pl.lit("atm"))
        .when(pl.col("moneyness") <= 1.10)
        .then(pl.lit("high_strike"))
        .otherwise(pl.lit("deep_high_strike"))
        .alias("moneyness_bucket")
    )


def compute_surface_summary(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Summarize the IV surface by symbol, expiration, and option type.
    """

    validate_columns(
        df,
        [
            "symbol",
            "expiration",
            "option_type",
            "moneyness",
            "implied_volatility",
        ],
        "IV surface summary",
    )

    group_cols = group_by or ["symbol", "expiration", "option_type"]

    validate_columns(df, group_cols, "IV surface summary groups")

    return (
        df.group_by(group_cols)
        .agg(
            [
                pl.col("implied_volatility").mean().alias("avg_iv"),
                pl.col("implied_volatility").median().alias("median_iv"),
                pl.col("implied_volatility").min().alias("min_iv"),
                pl.col("implied_volatility").max().alias("max_iv"),
                pl.col("implied_volatility").std().alias("iv_std"),
                pl.col("implied_volatility").count().alias("contract_count"),
                pl.col("moneyness").min().alias("min_moneyness"),
                pl.col("moneyness").max().alias("max_moneyness"),
            ]
        )
        .sort(group_cols)
    )


def get_atm_iv(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Find the closest-to-ATM contract and return its implied volatility.
    """

    validate_columns(
        df,
        [
            "symbol",
            "expiration",
            "option_type",
            "strike",
            "moneyness",
            "implied_volatility",
        ],
        "ATM IV calculation",
    )

    group_cols = group_by or ["symbol", "expiration", "option_type"]

    validate_columns(df, group_cols, "ATM IV groups")

    result = (
        df.with_columns(
            (pl.col("moneyness") - 1.0).abs().alias("_atm_distance")
        )
        .sort(group_cols + ["_atm_distance"])
        .group_by(group_cols, maintain_order=True)
        .first()
        .with_columns(
            pl.col("implied_volatility").alias("atm_iv")
        )
    )

    selected = group_cols + [
        "strike",
        "moneyness",
        "atm_iv",
    ]

    return result.select(selected)
