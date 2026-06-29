from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import polars as pl


@dataclass(frozen=True)
class PerformanceReportContract:
    """
    Contract for report-ready performance data.

    This validates the handoff from backtesting / portfolio evaluation into
    the reporting layer.
    """

    required_columns: tuple[str, ...] = (
        "date",
        "portfolio_value",
        "period_return",
    )

    identity_columns: tuple[str, ...] = (
        "date",
    )

    numeric_columns: tuple[str, ...] = (
        "portfolio_value",
        "period_return",
    )

    optional_numeric_columns: tuple[str, ...] = (
        "cumulative_return",
        "drawdown",
        "benchmark_return",
        "alpha",
        "beta",
        "sharpe",
        "volatility",
        "gross_exposure",
        "net_exposure",
        "turnover",
        "cash",
    )

    optional_metadata_columns: tuple[str, ...] = (
        "strategy",
        "benchmark",
        "regime",
    )


@dataclass(frozen=True)
class TradeReportContract:
    """
    Contract for report-ready trade data.
    """

    required_columns: tuple[str, ...] = (
        "symbol",
        "date",
        "side",
        "quantity",
        "price",
    )

    numeric_columns: tuple[str, ...] = (
        "quantity",
        "price",
    )

    optional_numeric_columns: tuple[str, ...] = (
        "commission",
        "fees",
        "slippage",
        "notional",
        "realized_pnl",
        "unrealized_pnl",
        "weight",
        "delta",
        "gamma",
        "theta",
        "vega",
    )

    valid_sides: tuple[str, ...] = (
        "buy",
        "sell",
        "long",
        "short",
        "cover",
        "close",
        "open",
        "exit",
        "rebalance",
    )


@dataclass(frozen=True)
class ExposureReportContract:
    """
    Contract for report-ready exposure data.
    """

    required_columns: tuple[str, ...] = (
        "date",
        "gross_exposure",
        "net_exposure",
    )

    numeric_columns: tuple[str, ...] = (
        "gross_exposure",
        "net_exposure",
    )

    optional_numeric_columns: tuple[str, ...] = (
        "long_exposure",
        "short_exposure",
        "cash",
        "beta",
        "delta",
        "gamma",
        "theta",
        "vega",
        "sector_exposure",
        "asset_class_exposure",
    )


def missing_columns(df: pl.DataFrame, required_columns: Iterable[str]) -> list[str]:
    """Return required columns that are missing from the DataFrame."""
    return [col for col in required_columns if col not in df.columns]


def _validate_required_columns(
    df: pl.DataFrame,
    required_columns: Iterable[str],
    label: str,
) -> None:
    missing = missing_columns(df, required_columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")

    if df.is_empty():
        raise ValueError(f"{label} cannot be empty.")

    null_counts = df.select(
        [pl.col(col).null_count().alias(col) for col in required_columns]
    ).to_dicts()[0]

    bad_nulls = {col: count for col, count in null_counts.items() if count > 0}
    if bad_nulls:
        raise ValueError(f"{label} contains nulls in required columns: {bad_nulls}")


def _validate_numeric_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
    label: str,
) -> None:
    for col in columns:
        if not df[col].dtype.is_numeric():
            raise TypeError(f"{label} column '{col}' must be numeric.")

    invalid_filter = None

    for col in columns:
        expr = (
            pl.col(col).cast(pl.Float64).is_nan().fill_null(False)
            | pl.col(col).cast(pl.Float64).is_infinite().fill_null(False)
        )
        invalid_filter = expr if invalid_filter is None else invalid_filter | expr

    if invalid_filter is not None and df.filter(invalid_filter).height > 0:
        raise ValueError(f"{label} numeric values must be finite.")


def validate_performance_report_schema(
    df: pl.DataFrame,
    require_unique_dates: bool = True,
) -> bool:
    """
    Validate that a DataFrame satisfies the performance reporting contract.
    """

    contract = PerformanceReportContract()
    label = "Performance report data"

    _validate_required_columns(df, contract.required_columns, label)

    if require_unique_dates:
        duplicate_count = (
            df.group_by(list(contract.identity_columns))
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if duplicate_count > 0:
            raise ValueError("Performance report data contains duplicate dates.")

    all_numeric_columns = list(contract.numeric_columns) + [
        col for col in contract.optional_numeric_columns if col in df.columns
    ]

    _validate_numeric_columns(df, all_numeric_columns, label)

    negative_value_count = df.filter(pl.col("portfolio_value") < 0.0).height
    if negative_value_count > 0:
        raise ValueError("Performance report portfolio_value cannot be negative.")

    return True


def validate_trade_report_schema(df: pl.DataFrame) -> bool:
    """
    Validate that a DataFrame satisfies the trade reporting contract.
    """

    contract = TradeReportContract()
    label = "Trade report data"

    _validate_required_columns(df, contract.required_columns, label)

    all_numeric_columns = list(contract.numeric_columns) + [
        col for col in contract.optional_numeric_columns if col in df.columns
    ]

    _validate_numeric_columns(df, all_numeric_columns, label)

    invalid_side_count = (
        df.with_columns(
            pl.col("side").cast(pl.Utf8).str.to_lowercase().alias("_side_normalized")
        )
        .filter(~pl.col("_side_normalized").is_in(contract.valid_sides))
        .height
    )

    if invalid_side_count > 0:
        raise ValueError(f"Trade report side must be one of {contract.valid_sides}.")

    invalid_quantity_count = df.filter(pl.col("quantity") <= 0.0).height
    if invalid_quantity_count > 0:
        raise ValueError("Trade report quantity must be positive.")

    invalid_price_count = df.filter(pl.col("price") < 0.0).height
    if invalid_price_count > 0:
        raise ValueError("Trade report price cannot be negative.")

    return True


def validate_exposure_report_schema(df: pl.DataFrame) -> bool:
    """
    Validate that a DataFrame satisfies the exposure reporting contract.
    """

    contract = ExposureReportContract()
    label = "Exposure report data"

    _validate_required_columns(df, contract.required_columns, label)

    all_numeric_columns = list(contract.numeric_columns) + [
        col for col in contract.optional_numeric_columns if col in df.columns
    ]

    _validate_numeric_columns(df, all_numeric_columns, label)

    negative_gross_count = df.filter(pl.col("gross_exposure") < 0.0).height
    if negative_gross_count > 0:
        raise ValueError("Exposure report gross_exposure cannot be negative.")

    impossible_net_count = df.filter(
        pl.col("net_exposure").abs() > pl.col("gross_exposure")
    ).height

    if impossible_net_count > 0:
        raise ValueError(
            "Exposure report absolute net_exposure cannot exceed gross_exposure."
        )

    return True


def enforce_performance_report_contract(
    df: pl.DataFrame,
    require_unique_dates: bool = True,
) -> pl.DataFrame:
    """
    Validate and return performance report data unchanged.
    """

    validate_performance_report_schema(
        df=df,
        require_unique_dates=require_unique_dates,
    )
    return df


def enforce_trade_report_contract(df: pl.DataFrame) -> pl.DataFrame:
    """
    Validate and return trade report data unchanged.
    """

    validate_trade_report_schema(df)
    return df


def enforce_exposure_report_contract(df: pl.DataFrame) -> pl.DataFrame:
    """
    Validate and return exposure report data unchanged.
    """

    validate_exposure_report_schema(df)
    return df
