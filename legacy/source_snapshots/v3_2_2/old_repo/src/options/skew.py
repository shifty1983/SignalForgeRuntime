from __future__ import annotations

import polars as pl

from src.options.schema import (
    normalize_option_type,
    validate_columns,
)


def compute_skew(df: pl.DataFrame) -> pl.DataFrame:
    """
    Compute IV skew relative to the closest ATM contract.

    If option_type exists, ATM IV is calculated separately for calls and puts.
    If option_type does not exist, ATM IV is calculated by symbol/expiration.
    """

    required = [
        "symbol",
        "expiration",
        "strike",
        "moneyness",
        "implied_volatility",
    ]

    validate_columns(df, required, "IV skew")

    result = df

    group_cols = ["symbol", "expiration"]

    if "option_type" in result.columns:
        result = normalize_option_type(result)
        group_cols.append("option_type")

    atm = (
        result.with_columns(
            (pl.col("moneyness") - 1.0).abs().alias("_atm_distance")
        )
        .sort(group_cols + ["_atm_distance"])
        .group_by(group_cols, maintain_order=True)
        .first()
        .select(
            group_cols
            + [
                pl.col("strike").alias("atm_strike"),
                pl.col("moneyness").alias("atm_moneyness"),
                pl.col("implied_volatility").alias("atm_iv"),
            ]
        )
    )

    result = result.join(
        atm,
        on=group_cols,
        how="left",
    )

    return result.with_columns(
        [
            (pl.col("implied_volatility") - pl.col("atm_iv")).alias("iv_skew"),
            pl.when(pl.col("atm_iv") > 0)
            .then((pl.col("implied_volatility") - pl.col("atm_iv")) / pl.col("atm_iv"))
            .otherwise(None)
            .alias("relative_iv_skew"),
            (pl.col("moneyness") - 1.0).abs().alias("abs_moneyness_distance"),
        ]
    )


def compute_smile_slope(
    df: pl.DataFrame,
    epsilon: float = 1e-9,
) -> pl.DataFrame:
    """
    Approximate volatility smile slope using moneyness.

    ATM rows receive null slope to avoid division by zero.
    """

    validate_columns(
        df,
        ["moneyness", "implied_volatility", "atm_iv"],
        "smile slope",
    )

    denominator = pl.col("moneyness") - 1.0

    return df.with_columns(
        pl.when(denominator.abs() > epsilon)
        .then((pl.col("implied_volatility") - pl.col("atm_iv")) / denominator)
        .otherwise(None)
        .alias("smile_slope")
    )


def compute_put_call_skew(
    df: pl.DataFrame,
    target_moneyness: float = 1.0,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Compare put IV versus call IV near a target moneyness.

    Positive put_call_iv_spread means puts are richer than calls.
    """

    required = [
        "symbol",
        "expiration",
        "strike",
        "option_type",
        "moneyness",
        "implied_volatility",
    ]

    validate_columns(df, required, "put/call skew")

    result = normalize_option_type(df)

    group_cols = group_by or ["symbol", "expiration"]

    validate_columns(result, group_cols, "put/call skew groups")

    nearest = (
        result.with_columns(
            (pl.col("moneyness") - target_moneyness)
            .abs()
            .alias("_target_distance")
        )
        .sort(group_cols + ["option_type", "_target_distance"])
        .group_by(group_cols + ["option_type"], maintain_order=True)
        .first()
    )

    calls = nearest.filter(pl.col("option_type") == "call").select(
        group_cols
        + [
            pl.col("strike").alias("call_strike"),
            pl.col("moneyness").alias("call_moneyness"),
            pl.col("implied_volatility").alias("call_iv"),
        ]
    )

    puts = nearest.filter(pl.col("option_type") == "put").select(
        group_cols
        + [
            pl.col("strike").alias("put_strike"),
            pl.col("moneyness").alias("put_moneyness"),
            pl.col("implied_volatility").alias("put_iv"),
        ]
    )

    joined = puts.join(
        calls,
        on=group_cols,
        how="inner",
    )

    return joined.with_columns(
        [
            (pl.col("put_iv") - pl.col("call_iv")).alias("put_call_iv_spread"),
            pl.when(pl.col("call_iv") > 0)
            .then(pl.col("put_iv") / pl.col("call_iv"))
            .otherwise(None)
            .alias("put_call_iv_ratio"),
        ]
    )


def compute_wing_skew(
    df: pl.DataFrame,
    downside_moneyness: float = 0.95,
    upside_moneyness: float = 1.05,
    group_by: list[str] | None = None,
) -> pl.DataFrame:
    """
    Compare downside put IV versus upside call IV.

    Positive wing_skew generally means downside protection is expensive.
    """

    required = [
        "symbol",
        "expiration",
        "strike",
        "option_type",
        "moneyness",
        "implied_volatility",
    ]

    validate_columns(df, required, "wing skew")

    result = normalize_option_type(df)

    group_cols = group_by or ["symbol", "expiration"]

    validate_columns(result, group_cols, "wing skew groups")

    downside = (
        result.filter(pl.col("option_type") == "put")
        .with_columns(
            (pl.col("moneyness") - downside_moneyness)
            .abs()
            .alias("_downside_distance")
        )
        .sort(group_cols + ["_downside_distance"])
        .group_by(group_cols, maintain_order=True)
        .first()
        .select(
            group_cols
            + [
                pl.col("strike").alias("downside_strike"),
                pl.col("moneyness").alias("downside_moneyness"),
                pl.col("implied_volatility").alias("downside_iv"),
            ]
        )
    )

    upside = (
        result.filter(pl.col("option_type") == "call")
        .with_columns(
            (pl.col("moneyness") - upside_moneyness)
            .abs()
            .alias("_upside_distance")
        )
        .sort(group_cols + ["_upside_distance"])
        .group_by(group_cols, maintain_order=True)
        .first()
        .select(
            group_cols
            + [
                pl.col("strike").alias("upside_strike"),
                pl.col("moneyness").alias("upside_moneyness"),
                pl.col("implied_volatility").alias("upside_iv"),
            ]
        )
    )

    joined = downside.join(
        upside,
        on=group_cols,
        how="inner",
    )

    return joined.with_columns(
        [
            (pl.col("downside_iv") - pl.col("upside_iv")).alias("wing_skew"),
            pl.when(pl.col("upside_iv") > 0)
            .then(pl.col("downside_iv") / pl.col("upside_iv"))
            .otherwise(None)
            .alias("wing_skew_ratio"),
        ]
    )


def classify_skew_regime(
    df: pl.DataFrame,
    skew_column: str = "wing_skew",
    downside_threshold: float = 0.03,
    upside_threshold: float = 0.03,
) -> pl.DataFrame:
    """
    Classify skew regime.

    Output:
    - downside_rich: downside options are meaningfully richer
    - upside_rich: upside options are meaningfully richer
    - balanced: skew is not extreme
    """

    validate_columns(df, [skew_column], "skew regime classification")

    return df.with_columns(
        pl.when(pl.col(skew_column) >= downside_threshold)
        .then(pl.lit("downside_rich"))
        .when(pl.col(skew_column) <= -upside_threshold)
        .then(pl.lit("upside_rich"))
        .otherwise(pl.lit("balanced"))
        .alias("skew_regime")
    )
