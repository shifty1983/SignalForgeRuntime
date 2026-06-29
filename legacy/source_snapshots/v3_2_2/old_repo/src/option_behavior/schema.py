from __future__ import annotations

from typing import Iterable

import polars as pl


NUMERIC_DTYPES = {
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
}

OPTION_BEHAVIOR_REQUIRED_COLUMNS = {
    "symbol",
    "implied_volatility",
    "volume",
    "open_interest",
    "spread_pct",
}

OPTION_BEHAVIOR_OUTPUT_KEYS = {
    "iv_behavior",
    "vol_premium_behavior",
    "liquidity_behavior",
    "skew_behavior",
    "term_structure_behavior",
    "greek_behavior",
    "contract_count",
    "avg_implied_volatility",
    "avg_spread_pct",
    "total_volume",
    "total_open_interest",
    "avg_abs_delta",
    "avg_abs_gamma",
    "avg_abs_vega",
}


def validate_non_empty(
    df: pl.DataFrame,
    context: str = "DataFrame",
) -> None:
    if df.is_empty():
        raise ValueError(f"{context} is empty")


def validate_required_columns(
    df: pl.DataFrame,
    required_columns: Iterable[str],
    context: str = "DataFrame",
) -> None:
    missing = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{context} missing required columns: {missing}"
        )


def validate_numeric_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
    context: str = "DataFrame",
) -> None:
    invalid = []

    for column in columns:
        dtype = df.schema.get(column)

        if dtype not in NUMERIC_DTYPES:
            invalid.append((column, dtype))

    if invalid:
        raise TypeError(
            f"{context} has non-numeric columns: {invalid}"
        )


def validate_option_behavior_inputs(
    option_df: pl.DataFrame,
    required_columns: Iterable[str] | None = None,
) -> None:
    active_required = required_columns or OPTION_BEHAVIOR_REQUIRED_COLUMNS

    validate_non_empty(option_df, "option_df")

    validate_required_columns(
        option_df,
        active_required,
        "option_df",
    )

    numeric_columns = [
        column for column in [
            "implied_volatility",
            "volume",
            "open_interest",
            "spread_pct",
            "liquidity_score",
            "iv_rv_ratio",
            "iv_rv_spread",
            "variance_risk_premium",
            "expected_move_pct",
            "delta",
            "gamma",
            "theta",
            "vega",
        ]
        if column in option_df.columns
    ]

    validate_numeric_columns(
        option_df,
        numeric_columns,
        "option_df",
    )


def validate_option_behavior_output(
    result: dict,
) -> None:
    missing = OPTION_BEHAVIOR_OUTPUT_KEYS - set(result.keys())

    if missing:
        raise ValueError(
            f"Option behavior output missing keys: {sorted(missing)}"
        )
