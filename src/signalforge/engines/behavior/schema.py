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


BEHAVIOR_OUTPUT_KEYS = {
    "return_behavior",
    "volatility_behavior",
    "trend_behavior",
    "drawdown_behavior",
    "realized_volatility",
    "max_drawdown",
}


def validate_non_empty(
    df: pl.DataFrame,
    context: str = "DataFrame",
) -> None:
    """
    Validate that a DataFrame is not empty.
    """
    if df.is_empty():
        raise ValueError(f"{context} is empty")


def validate_required_columns(
    df: pl.DataFrame,
    required_columns: Iterable[str],
    context: str = "DataFrame",
) -> None:
    """
    Validate that all required columns are present.
    """
    missing = [
        col for col in required_columns
        if col not in df.columns
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
    """
    Validate that selected columns are numeric.
    """
    invalid = []

    for col in columns:
        dtype = df.schema.get(col)

        if dtype not in NUMERIC_DTYPES:
            invalid.append((col, dtype))

    if invalid:
        raise TypeError(
            f"{context} has non-numeric columns: {invalid}"
        )


def validate_min_rows(
    df: pl.DataFrame,
    min_rows: int,
    context: str = "DataFrame",
) -> None:
    """
    Validate that a DataFrame has at least a minimum row count.
    """
    if df.height < min_rows:
        raise ValueError(
            f"{context} requires at least {min_rows} rows, "
            f"received {df.height}"
        )


def validate_behavior_inputs(
    returns_df: pl.DataFrame,
    price_df: pl.DataFrame,
    equity_df: pl.DataFrame,
    return_col: str = "return",
    price_col: str = "close",
    equity_col: str = "equity",
    min_price_rows: int = 50,
) -> None:
    """
    Validate the core inputs required by the behavior classifier.
    """
    validate_non_empty(returns_df, "returns_df")
    validate_non_empty(price_df, "price_df")
    validate_non_empty(equity_df, "equity_df")

    validate_required_columns(
        returns_df,
        [return_col],
        "returns_df",
    )

    validate_required_columns(
        price_df,
        [price_col],
        "price_df",
    )

    validate_required_columns(
        equity_df,
        [equity_col],
        "equity_df",
    )

    validate_numeric_columns(
        returns_df,
        [return_col],
        "returns_df",
    )

    validate_numeric_columns(
        price_df,
        [price_col],
        "price_df",
    )

    validate_numeric_columns(
        equity_df,
        [equity_col],
        "equity_df",
    )

    validate_min_rows(
        price_df,
        min_price_rows,
        "price_df",
    )


def validate_behavior_output(
    result: dict,
) -> None:
    """
    Validate that a behavior classifier output has the expected keys.
    """
    missing = BEHAVIOR_OUTPUT_KEYS - set(result.keys())

    if missing:
        raise ValueError(
            f"Behavior output missing keys: {sorted(missing)}"
        )




