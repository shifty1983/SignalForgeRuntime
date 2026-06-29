from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class PortfolioDataContract:
    """
    Contract for portfolio weight outputs.

    This validates portfolio-ready outputs produced by strategy selection,
    allocation, optimizer, or rebalance logic.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
        "weight",
    )

    identity_columns: tuple[str, ...] = (
        "symbol",
        "date",
    )

    numeric_columns: tuple[str, ...] = (
        "weight",
    )

    optional_columns: tuple[str, ...] = (
        "strategy",
        "asset_class",
        "side",
        "price",
        "quantity",
        "market_value",
        "target_weight",
        "current_weight",
        "notional_exposure",
        "delta",
        "gamma",
        "theta",
        "vega",
        "beta",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def validate_portfolio_data_schema(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
    max_abs_weight: float | None = 1.0,
    max_gross_exposure: float | None = None,
) -> bool:
    """
    Validate that a DataFrame satisfies the portfolio data contract.

    Returns True if valid.
    Raises ValueError or TypeError if invalid.
    """

    contract = PortfolioDataContract()

    missing = missing_columns(df, contract.required_columns)
    if missing:
        raise ValueError(f"Portfolio data missing required columns: {missing}")

    if df.is_empty():
        raise ValueError("Portfolio data cannot be empty.")

    null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in contract.required_columns]
    ).to_dicts()[0]

    bad_nulls = {col: count for col, count in null_counts.items() if count > 0}
    if bad_nulls:
        raise ValueError(
            f"Portfolio data contains nulls in required columns: {bad_nulls}"
        )

    if require_unique_keys:
        duplicate_count = (
            df.group_by(list(contract.identity_columns))
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if duplicate_count > 0:
            raise ValueError("Portfolio data contains duplicate symbol/date keys.")

    for col in contract.numeric_columns:
        if not df[col].dtype.is_numeric():
            raise TypeError(f"Portfolio data column '{col}' must be numeric.")

    invalid_weight_count = df.filter(
        pl.col("weight").cast(pl.Float64).is_nan()
        | pl.col("weight").cast(pl.Float64).is_infinite()
    ).height

    if invalid_weight_count > 0:
        raise ValueError("Portfolio weights must be finite numeric values.")

    if max_abs_weight is not None:
        oversized_weight_count = df.filter(pl.col("weight").abs() > max_abs_weight).height

        if oversized_weight_count > 0:
            raise ValueError(
                f"Portfolio weight absolute value cannot exceed {max_abs_weight}."
            )

    if max_gross_exposure is not None:
        gross_by_date = df.group_by("date").agg(
            pl.col("weight").abs().sum().alias("gross_exposure")
        )

        excessive_gross_count = gross_by_date.filter(
            pl.col("gross_exposure") > max_gross_exposure
        ).height

        if excessive_gross_count > 0:
            raise ValueError(
                f"Portfolio gross exposure cannot exceed {max_gross_exposure}."
            )

    return True


def enforce_portfolio_data_contract(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
    max_abs_weight: float | None = 1.0,
    max_gross_exposure: float | None = None,
) -> pl.DataFrame:
    """
    Validate and return the DataFrame unchanged.
    """

    validate_portfolio_data_schema(
        df=df,
        require_unique_keys=require_unique_keys,
        max_abs_weight=max_abs_weight,
        max_gross_exposure=max_gross_exposure,
    )
    return df
