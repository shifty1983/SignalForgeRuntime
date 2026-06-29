from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class FeatureDataContract:
    """
    Contract for feature datasets.

    Feature data should be aligned by symbol/date and contain one or more
    numeric feature columns used by research, signals, backtesting, and ranking.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
    )

    optional_metadata_columns: tuple[str, ...] = (
        "source",
        "asset_class",
        "currency",
        "exchange",
        "sector",
        "industry",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def infer_feature_columns(df: pl.DataFrame) -> list[str]:
    """
    Infer feature columns by excluding required identity columns and metadata.
    """

    contract = FeatureDataContract()

    excluded = set(contract.required_columns) | set(contract.optional_metadata_columns)

    return [col for col in df.columns if col not in excluded]


def validate_feature_data_schema(
    df: pl.DataFrame,
    feature_columns: Iterable[str] | None = None,
    require_unique_keys: bool = True,
) -> bool:
    """
    Validate that a DataFrame satisfies the feature data contract.

    Returns True if valid.
    Raises ValueError or TypeError if invalid.
    """

    contract = FeatureDataContract()

    missing = missing_columns(df, contract.required_columns)
    if missing:
        raise ValueError(f"Feature data missing required columns: {missing}")

    if df.is_empty():
        raise ValueError("Feature data cannot be empty.")

    key_null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in contract.required_columns]
    ).to_dicts()[0]

    bad_key_nulls = {col: count for col, count in key_null_counts.items() if count > 0}
    if bad_key_nulls:
        raise ValueError(
            f"Feature data contains nulls in required columns: {bad_key_nulls}"
        )

    if require_unique_keys:
        duplicate_count = (
            df.group_by(list(contract.required_columns))
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if duplicate_count > 0:
            raise ValueError("Feature data contains duplicate symbol/date keys.")

    selected_feature_columns = (
        list(feature_columns) if feature_columns is not None else infer_feature_columns(df)
    )

    missing_features = missing_columns(df, selected_feature_columns)
    if missing_features:
        raise ValueError(f"Feature data missing feature columns: {missing_features}")

    if not selected_feature_columns:
        raise ValueError("Feature data must contain at least one feature column.")

    for col in selected_feature_columns:
        if not df[col].dtype.is_numeric():
            raise TypeError(f"Feature data column '{col}' must be numeric.")

    return True


def enforce_feature_data_contract(
    df: pl.DataFrame,
    feature_columns: Iterable[str] | None = None,
    require_unique_keys: bool = True,
) -> pl.DataFrame:
    """
    Validate and return the DataFrame unchanged.
    """

    validate_feature_data_schema(
        df=df,
        feature_columns=feature_columns,
        require_unique_keys=require_unique_keys,
    )
    return df
