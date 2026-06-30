from __future__ import annotations

import polars as pl

from src.signalforge.engines.options.schema import (
    normalize_option_type,
    validate_columns,
)


GREEK_COLUMNS = [
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
]


def validate_greeks(df: pl.DataFrame) -> pl.DataFrame:
    """
    Validate and normalize option Greeks.

    Required columns:
    - symbol
    - expiration
    - strike
    - option_type
    - delta
    - gamma
    - theta
    - vega

    rho is optional because some data vendors omit it.
    """

    required = [
        "symbol",
        "expiration",
        "strike",
        "option_type",
        "delta",
        "gamma",
        "theta",
        "vega",
    ]

    validate_columns(df, required, "option Greeks")

    return normalize_option_type(df)


def add_greek_exposures(
    df: pl.DataFrame,
    contract_multiplier: int = 100,
) -> pl.DataFrame:
    """
    Add contract-level Greek exposures.

    Exposure columns are scaled by contract multiplier.
    """

    validate_columns(
        df,
        [
            "delta",
            "gamma",
            "theta",
            "vega",
        ],
        "Greek exposure calculation",
    )

    return df.with_columns(
        [
            (pl.col("delta") * contract_multiplier).alias("delta_exposure"),
            (pl.col("gamma") * contract_multiplier).alias("gamma_exposure"),
            (pl.col("theta") * contract_multiplier).alias("theta_exposure"),
            (pl.col("vega") * contract_multiplier).alias("vega_exposure"),
        ]
    )


def add_position_greek_exposures(
    df: pl.DataFrame,
    quantity_col: str = "quantity",
    contract_multiplier: int = 100,
) -> pl.DataFrame:
    """
    Add position-level Greek exposures.

    Positive quantity means long contracts.
    Negative quantity means short contracts.
    """

    validate_columns(
        df,
        [
            quantity_col,
            "delta",
            "gamma",
            "theta",
            "vega",
        ],
        "position Greek exposure calculation",
    )

    return df.with_columns(
        [
            (
                pl.col(quantity_col)
                * pl.col("delta")
                * contract_multiplier
            ).alias("position_delta"),
            (
                pl.col(quantity_col)
                * pl.col("gamma")
                * contract_multiplier
            ).alias("position_gamma"),
            (
                pl.col(quantity_col)
                * pl.col("theta")
                * contract_multiplier
            ).alias("position_theta"),
            (
                pl.col(quantity_col)
                * pl.col("vega")
                * contract_multiplier
            ).alias("position_vega"),
        ]
    )


def summarize_greek_exposures(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Summarize position Greek exposures by symbol by default.
    """

    required = [
        "position_delta",
        "position_gamma",
        "position_theta",
        "position_vega",
    ]

    validate_columns(df, required, "Greek exposure summary")

    group_cols = group_by or ["symbol"]

    validate_columns(df, group_cols, "Greek exposure summary groups")

    return (
        df.group_by(group_cols)
        .agg(
            [
                pl.col("position_delta").sum().alias("net_delta"),
                pl.col("position_gamma").sum().alias("net_gamma"),
                pl.col("position_theta").sum().alias("net_theta"),
                pl.col("position_vega").sum().alias("net_vega"),
                pl.col("position_delta").abs().sum().alias("gross_delta"),
                pl.col("position_gamma").abs().sum().alias("gross_gamma"),
                pl.col("position_theta").abs().sum().alias("gross_theta"),
                pl.col("position_vega").abs().sum().alias("gross_vega"),
            ]
        )
        .sort(group_cols)
    )


def classify_delta_bucket(df: pl.DataFrame) -> pl.DataFrame:
    """
    Classify contracts by absolute delta bucket.

    Buckets:
    - deep_otm
    - otm
    - near_atm
    - itm
    - deep_itm
    """

    validate_columns(df, ["delta"], "delta bucket classification")

    abs_delta = pl.col("delta").abs()

    return df.with_columns(
        pl.when(abs_delta < 0.15)
        .then(pl.lit("deep_otm"))
        .when(abs_delta < 0.35)
        .then(pl.lit("otm"))
        .when(abs_delta <= 0.65)
        .then(pl.lit("near_atm"))
        .when(abs_delta <= 0.85)
        .then(pl.lit("itm"))
        .otherwise(pl.lit("deep_itm"))
        .alias("delta_bucket")
    )


def filter_by_delta(
    df: pl.DataFrame,
    min_abs_delta: float | None = None,
    max_abs_delta: float | None = None,
) -> pl.DataFrame:
    """
    Filter contracts by absolute delta range.
    """

    validate_columns(df, ["delta"], "delta filter")

    result = df.with_columns(pl.col("delta").abs().alias("_abs_delta"))

    if min_abs_delta is not None:
        result = result.filter(pl.col("_abs_delta") >= min_abs_delta)

    if max_abs_delta is not None:
        result = result.filter(pl.col("_abs_delta") <= max_abs_delta)

    return result.drop("_abs_delta")


def rank_gamma_exposure(
    df: pl.DataFrame,
    descending: bool = True,
) -> pl.DataFrame:
    """
    Rank options by absolute gamma exposure.
    """

    validate_columns(df, ["gamma"], "gamma exposure ranking")

    return (
        df.with_columns(pl.col("gamma").abs().alias("abs_gamma"))
        .sort("abs_gamma", descending=descending)
    )


def rank_vega_exposure(
    df: pl.DataFrame,
    descending: bool = True,
) -> pl.DataFrame:
    """
    Rank options by absolute vega exposure.
    """

    validate_columns(df, ["vega"], "vega exposure ranking")

    return (
        df.with_columns(pl.col("vega").abs().alias("abs_vega"))
        .sort("abs_vega", descending=descending)
    )
