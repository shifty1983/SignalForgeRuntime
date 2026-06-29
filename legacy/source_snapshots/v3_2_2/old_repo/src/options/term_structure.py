from __future__ import annotations

import polars as pl

from src.options.schema import validate_columns


def compute_term_structure(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Compute implied volatility term structure.

    Default grouping:
    - symbol
    - expiration
    - days_to_expiration

    Output:
    - avg_iv
    - median_iv
    - min_iv
    - max_iv
    - iv_std
    - contract_count
    """

    validate_columns(
        df,
        [
            "symbol",
            "expiration",
            "days_to_expiration",
            "implied_volatility",
        ],
        "term structure",
    )

    group_cols = group_by or [
        "symbol",
        "expiration",
        "days_to_expiration",
    ]

    validate_columns(df, group_cols, "term structure groups")

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
            ]
        )
        .sort(group_cols)
    )


def compute_term_slope(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Compute slope between adjacent expirations.

    term_slope:
    - positive = IV rises into later expirations
    - negative = IV falls into later expirations

    iv_per_day_slope normalizes the IV change by days between expirations.
    """

    validate_columns(
        df,
        ["symbol", "days_to_expiration", "avg_iv"],
        "term slope",
    )

    group_cols = group_by or ["symbol"]

    validate_columns(df, group_cols, "term slope groups")

    result = df.sort(group_cols + ["days_to_expiration"])

    return result.with_columns(
        [
            (
                pl.col("avg_iv")
                - pl.col("avg_iv").shift(1).over(group_cols)
            ).alias("term_slope"),
            (
                pl.col("days_to_expiration")
                - pl.col("days_to_expiration").shift(1).over(group_cols)
            ).alias("days_between_expirations"),
        ]
    ).with_columns(
        pl.when(pl.col("days_between_expirations") > 0)
        .then(pl.col("term_slope") / pl.col("days_between_expirations"))
        .otherwise(None)
        .alias("iv_per_day_slope")
    )


def compare_front_back_iv(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Compare front expiration IV against back expiration IV.

    back_minus_front_iv:
    - positive = upward-sloping term structure
    - negative = inverted term structure
    """

    validate_columns(
        df,
        ["symbol", "expiration", "days_to_expiration", "avg_iv"],
        "front/back IV comparison",
    )

    group_cols = group_by or ["symbol"]

    validate_columns(df, group_cols, "front/back IV groups")

    sorted_df = df.sort(group_cols + ["days_to_expiration"])

    front = (
        sorted_df.group_by(group_cols, maintain_order=True)
        .first()
        .select(
            group_cols
            + [
                pl.col("expiration").alias("front_expiration"),
                pl.col("days_to_expiration").alias("front_dte"),
                pl.col("avg_iv").alias("front_iv"),
            ]
        )
    )

    back = (
        sorted_df.group_by(group_cols, maintain_order=True)
        .last()
        .select(
            group_cols
            + [
                pl.col("expiration").alias("back_expiration"),
                pl.col("days_to_expiration").alias("back_dte"),
                pl.col("avg_iv").alias("back_iv"),
            ]
        )
    )

    joined = front.join(
        back,
        on=group_cols,
        how="inner",
    )

    return joined.with_columns(
        [
            (pl.col("back_iv") - pl.col("front_iv")).alias(
                "back_minus_front_iv"
            ),
            pl.when(pl.col("front_iv") > 0)
            .then(pl.col("back_iv") / pl.col("front_iv"))
            .otherwise(None)
            .alias("back_front_iv_ratio"),
        ]
    )


def classify_term_structure(
    df: pl.DataFrame,
    slope_column: str = "back_minus_front_iv",
    contango_threshold: float = 0.02,
    backwardation_threshold: float = -0.02,
) -> pl.DataFrame:
    """
    Classify term structure regime.

    Output:
    - contango: back IV meaningfully above front IV
    - backwardation: front IV meaningfully above back IV
    - flat: no major slope
    """

    validate_columns(
        df,
        [slope_column],
        "term structure classification",
    )

    return df.with_columns(
        pl.when(pl.col(slope_column) >= contango_threshold)
        .then(pl.lit("contango"))
        .when(pl.col(slope_column) <= backwardation_threshold)
        .then(pl.lit("backwardation"))
        .otherwise(pl.lit("flat"))
        .alias("term_structure_regime")
    )


def get_front_expiration_iv(
    df: pl.DataFrame,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Return the nearest expiration IV for each group.
    """

    validate_columns(
        df,
        ["symbol", "expiration", "days_to_expiration", "avg_iv"],
        "front expiration IV",
    )

    group_cols = group_by or ["symbol"]

    validate_columns(df, group_cols, "front expiration IV groups")

    return (
        df.sort(group_cols + ["days_to_expiration"])
        .group_by(group_cols, maintain_order=True)
        .first()
        .select(
            group_cols
            + [
                pl.col("expiration").alias("front_expiration"),
                pl.col("days_to_expiration").alias("front_dte"),
                pl.col("avg_iv").alias("front_iv"),
            ]
        )
    )
