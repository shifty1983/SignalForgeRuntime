from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class MarketDataContract:
    """
    Contract for raw or processed OHLCV-style market data.

    This is intentionally lightweight. It validates the shape of data moving
    between ingestion, processing, features, research, and backtesting.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )

    optional_columns: tuple[str, ...] = (
        "adjusted_close",
        "source",
        "asset_class",
        "currency",
        "exchange",
    )

    numeric_columns: tuple[str, ...] = (
        "open",
        "high",
        "low",
        "close",
        "volume",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def validate_market_data_schema(df: pl.DataFrame) -> bool:
    """
    Validate that a DataFrame satisfies the market data contract.

    Returns True if valid.
    Raises ValueError or TypeError if invalid.
    """

    contract = MarketDataContract()

    missing = missing_columns(df, contract.required_columns)
    if missing:
        raise ValueError(f"Market data missing required columns: {missing}")

    if df.is_empty():
        raise ValueError("Market data cannot be empty.")

    null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in contract.required_columns]
    ).to_dicts()[0]

    bad_nulls = {col: count for col, count in null_counts.items() if count > 0}
    if bad_nulls:
        raise ValueError(f"Market data contains nulls in required columns: {bad_nulls}")

    for col in contract.numeric_columns:
        if col in df.columns and not df[col].dtype.is_numeric():
            raise TypeError(f"Market data column '{col}' must be numeric.")

    return True


def enforce_market_data_contract(df: pl.DataFrame) -> pl.DataFrame:
    """
    Validate and return the DataFrame unchanged.

    This function is useful inside pipelines where we want explicit contract
    enforcement without mutating the data.
    """

    validate_market_data_schema(df)
    return df
