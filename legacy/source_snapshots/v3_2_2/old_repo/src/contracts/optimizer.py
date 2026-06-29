from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class OptimizerCandidateContract:
    """
    Contract for optimizer-ready candidate data.

    This validates the handoff from strategy selection / expected value into
    the optimizer layer. These rows represent assets or trades that are eligible
    for portfolio construction.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
        "expected_return",
        "risk_score",
        "score",
    )

    identity_columns: tuple[str, ...] = (
        "symbol",
        "date",
    )

    numeric_columns: tuple[str, ...] = (
        "expected_return",
        "risk_score",
        "score",
    )

    optional_numeric_columns: tuple[str, ...] = (
        "confidence",
        "strength",
        "direction",
        "min_weight",
        "max_weight",
        "current_weight",
        "target_weight",
        "expected_volatility",
        "expected_drawdown",
        "liquidity_score",
        "opportunity_score",
        "delta",
        "gamma",
        "theta",
        "vega",
        "beta",
    )

    optional_metadata_columns: tuple[str, ...] = (
        "strategy",
        "asset_class",
        "sector",
        "industry",
        "regime",
        "side",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def _finite_invalid_count(df: pl.DataFrame, columns: Iterable[str]) -> int:
    """Count rows with NaN or infinite values in selected numeric columns."""
    invalid_filter = None

    for col in columns:
        expr = (
            pl.col(col).cast(pl.Float64).is_nan()
            | pl.col(col).cast(pl.Float64).is_infinite()
        )
        invalid_filter = expr if invalid_filter is None else invalid_filter | expr

    if invalid_filter is None:
        return 0

    return df.filter(invalid_filter).height


def validate_optimizer_candidate_schema(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
) -> bool:
    """
    Validate that a DataFrame satisfies the optimizer candidate contract.

    Returns True if valid.
    Raises ValueError or TypeError if invalid.
    """

    contract = OptimizerCandidateContract()

    missing = missing_columns(df, contract.required_columns)
    if missing:
        raise ValueError(f"Optimizer candidates missing required columns: {missing}")

    if df.is_empty():
        raise ValueError("Optimizer candidates cannot be empty.")

    null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in contract.required_columns]
    ).to_dicts()[0]

    bad_nulls = {col: count for col, count in null_counts.items() if count > 0}
    if bad_nulls:
        raise ValueError(
            f"Optimizer candidates contain nulls in required columns: {bad_nulls}"
        )

    if require_unique_keys:
        duplicate_count = (
            df.group_by(list(contract.identity_columns))
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if duplicate_count > 0:
            raise ValueError(
                "Optimizer candidates contain duplicate symbol/date keys."
            )

    all_numeric_columns = list(contract.numeric_columns) + [
        col for col in contract.optional_numeric_columns if col in df.columns
    ]

    for col in all_numeric_columns:
        if not df[col].dtype.is_numeric():
            raise TypeError(f"Optimizer candidate column '{col}' must be numeric.")

    invalid_numeric_count = _finite_invalid_count(df, all_numeric_columns)
    if invalid_numeric_count > 0:
        raise ValueError("Optimizer candidate numeric values must be finite.")

    negative_risk_count = df.filter(pl.col("risk_score") < 0.0).height
    if negative_risk_count > 0:
        raise ValueError("Optimizer candidate risk_score cannot be negative.")

    if "confidence" in df.columns:
        invalid_confidence_count = df.filter(
            (pl.col("confidence") < 0.0) | (pl.col("confidence") > 1.0)
        ).height

        if invalid_confidence_count > 0:
            raise ValueError("Optimizer candidate confidence must be between 0 and 1.")

    if "strength" in df.columns:
        invalid_strength_count = df.filter(
            (pl.col("strength") < 0.0) | (pl.col("strength") > 1.0)
        ).height

        if invalid_strength_count > 0:
            raise ValueError("Optimizer candidate strength must be between 0 and 1.")

    if "direction" in df.columns:
        invalid_direction_count = df.filter(~pl.col("direction").is_in([-1, 0, 1])).height

        if invalid_direction_count > 0:
            raise ValueError("Optimizer candidate direction must be one of -1, 0, or 1.")

    if "min_weight" in df.columns and "max_weight" in df.columns:
        invalid_weight_bounds_count = df.filter(
            pl.col("min_weight") > pl.col("max_weight")
        ).height

        if invalid_weight_bounds_count > 0:
            raise ValueError(
                "Optimizer candidate min_weight cannot exceed max_weight."
            )

    return True


def enforce_optimizer_candidate_contract(
    df: pl.DataFrame,
    require_unique_keys: bool = True,
) -> pl.DataFrame:
    """
    Validate and return the DataFrame unchanged.
    """

    validate_optimizer_candidate_schema(
        df=df,
        require_unique_keys=require_unique_keys,
    )
    return df
