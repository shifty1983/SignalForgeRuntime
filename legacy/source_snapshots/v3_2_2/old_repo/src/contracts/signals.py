from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class SignalDataContract:
    """
    Contract for tradeable signal outputs.

    Signal data is the bridge between research/features and strategy selection.
    A valid signal should identify the asset/date, directional intent, strength,
    and confidence.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
        "signal",
        "direction",
        "strength",
        "confidence",
    )

    identity_columns: tuple[str, ...] = (
        "symbol",
        "date",
    )

    numeric_columns: tuple[str, ...] = (
        "signal",
        "direction",
        "strength",
        "confidence",
    )

    bounded_columns: tuple[str, ...] = (
        "strength",
        "confidence",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def validate_signal_data_schema(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
) -> bool:
    """
    Validate that a DataFrame satisfies the signal data contract.

    Returns True if valid.
    Raises ValueError or TypeError if invalid.
    """

    contract = SignalDataContract()

    missing = missing_columns(df, contract.required_columns)
    if missing:
        raise ValueError(f"Signal data missing required columns: {missing}")

    if df.is_empty():
        raise ValueError("Signal data cannot be empty.")

    null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in contract.required_columns]
    ).to_dicts()[0]

    bad_nulls = {col: count for col, count in null_counts.items() if count > 0}
    if bad_nulls:
        raise ValueError(f"Signal data contains nulls in required columns: {bad_nulls}")

    if require_unique_keys:
        duplicate_count = (
            df.group_by(list(contract.identity_columns))
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if duplicate_count > 0:
            raise ValueError("Signal data contains duplicate symbol/date keys.")

    for col in contract.numeric_columns:
        if not df[col].dtype.is_numeric():
            raise TypeError(f"Signal data column '{col}' must be numeric.")

    invalid_direction_count = df.filter(~pl.col("direction").is_in([-1, 0, 1])).height
    if invalid_direction_count > 0:
        raise ValueError("Signal direction must be one of -1, 0, or 1.")

    for col in contract.bounded_columns:
        invalid_count = df.filter((pl.col(col) < 0.0) | (pl.col(col) > 1.0)).height
        if invalid_count > 0:
            raise ValueError(f"Signal data column '{col}' must be between 0 and 1.")

    inconsistent_direction_count = df.filter(
        ((pl.col("signal") > 0) & (pl.col("direction") != 1))
        | ((pl.col("signal") < 0) & (pl.col("direction") != -1))
        | ((pl.col("signal") == 0) & (pl.col("direction") != 0))
    ).height

    if inconsistent_direction_count > 0:
        raise ValueError("Signal direction must match the sign of the signal value.")

    return True


def enforce_signal_data_contract(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
) -> pl.DataFrame:
    """
    Validate and return the DataFrame unchanged.
    """

    validate_signal_data_schema(df=df, require_unique_keys=require_unique_keys)
    return df
