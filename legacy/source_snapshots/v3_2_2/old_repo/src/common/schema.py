from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


DEFAULT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class MetadataColumn:
    """
    Defines a reusable column contract.

    dtype is stored as a string to keep this module lightweight and independent
    from pandas or polars.
    """

    name: str
    dtype: str
    required: bool = True
    description: str = ""


# ---------------------------------------------------------------------------
# Row-level metadata columns
# ---------------------------------------------------------------------------

METADATA_COLUMNS: tuple[MetadataColumn, ...] = (
    MetadataColumn("source", "string", True, "Data provider or source name"),
    MetadataColumn("symbol", "string", True, "Ticker, symbol, or identifier"),
    MetadataColumn("asset_class", "string", False, "Asset class such as equity, ETF, option, macro"),
    MetadataColumn("interval", "string", False, "Data interval such as 1d, 1h, 5m"),
    MetadataColumn("ingested_at", "datetime", True, "UTC timestamp when data was ingested"),
    MetadataColumn("source_file", "string", False, "Original source file path if applicable"),
    MetadataColumn("source_url", "string", False, "Original source URL if applicable"),
    MetadataColumn("row_hash", "string", False, "Hash for row-level deduplication"),
    MetadataColumn("schema_version", "string", True, "Schema version used for this dataset"),
)

METADATA_COLUMN_NAMES: tuple[str, ...] = tuple(column.name for column in METADATA_COLUMNS)

REQUIRED_METADATA_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in METADATA_COLUMNS if column.required
)

OPTIONAL_METADATA_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in METADATA_COLUMNS if not column.required
)


# ---------------------------------------------------------------------------
# Catalog-level metadata columns
# ---------------------------------------------------------------------------

CATALOG_COLUMNS: tuple[MetadataColumn, ...] = (
    MetadataColumn("dataset", "string", True, "Dataset name such as market, options, macro"),
    MetadataColumn("source", "string", True, "Data provider or source name"),
    MetadataColumn("symbol", "string", False, "Ticker, symbol, or identifier"),
    MetadataColumn("asset_class", "string", False, "Asset class such as equity, ETF, option, macro"),
    MetadataColumn("series_type", "string", False, "Series category such as OHLCV, chain, rate, factor"),
    MetadataColumn("interval", "string", False, "Data interval such as 1d, 1h, 5m"),
    MetadataColumn("start_date", "date", False, "Earliest timestamp or date in the dataset"),
    MetadataColumn("end_date", "date", False, "Latest timestamp or date in the dataset"),
    MetadataColumn("row_count", "integer", False, "Number of rows in the dataset partition"),
    MetadataColumn("partition_path", "string", True, "Path to the stored dataset partition"),
    MetadataColumn("created_at", "datetime", True, "UTC timestamp when catalog record was created"),
    MetadataColumn("updated_at", "datetime", True, "UTC timestamp when catalog record was last updated"),
    MetadataColumn("schema_version", "string", True, "Schema version used for this dataset"),
)

CATALOG_COLUMN_NAMES: tuple[str, ...] = tuple(column.name for column in CATALOG_COLUMNS)

REQUIRED_CATALOG_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in CATALOG_COLUMNS if column.required
)


# ---------------------------------------------------------------------------
# Dataset-specific column contracts
# ---------------------------------------------------------------------------

MARKET_COLUMNS: tuple[str, ...] = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "symbol",
    "source",
    "interval",
)

OPTIONS_CHAIN_COLUMNS: tuple[str, ...] = (
    "date",
    "underlying",
    "expiration",
    "strike",
    "option_type",
    "bid",
    "ask",
    "mid",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
)

MACRO_COLUMNS: tuple[str, ...] = (
    "date",
    "series_id",
    "value",
)

FUNDAMENTAL_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "metric",
    "value",
    "period",
)

SENTIMENT_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "source",
    "sentiment_score",
    "sentiment_label",
)

FEATURE_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "feature_name",
    "feature_value",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def metadata_defaults(
    *,
    source: str,
    symbol: str,
    asset_class: str | None = None,
    interval: str | None = None,
    ingested_at: str | None = None,
    source_file: str | None = None,
    source_url: str | None = None,
    row_hash: str | None = None,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> dict[str, str | None]:
    """
    Build standard row-level metadata defaults.
    """
    return {
        "source": source,
        "symbol": symbol,
        "asset_class": asset_class,
        "interval": interval,
        "ingested_at": ingested_at,
        "source_file": source_file,
        "source_url": source_url,
        "row_hash": row_hash,
        "schema_version": schema_version,
    }


def catalog_defaults(
    *,
    dataset: str,
    source: str,
    partition_path: str,
    symbol: str | None = None,
    asset_class: str | None = None,
    series_type: str | None = None,
    interval: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    row_count: int | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> dict[str, str | int | None]:
    """
    Build standard catalog-level metadata defaults.
    """
    return {
        "dataset": dataset,
        "source": source,
        "symbol": symbol,
        "asset_class": asset_class,
        "series_type": series_type,
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "row_count": row_count,
        "partition_path": partition_path,
        "created_at": created_at,
        "updated_at": updated_at,
        "schema_version": schema_version,
    }


def missing_columns(columns: Iterable[str], required_columns: Iterable[str]) -> list[str]:
    """
    Return required columns that are missing from a collection of columns.
    """
    available = set(columns)
    return [column for column in required_columns if column not in available]


def has_columns(columns: Iterable[str], required_columns: Iterable[str]) -> bool:
    """
    Return True if all required columns are present.
    """
    return not missing_columns(columns, required_columns)


def require_columns(columns: Iterable[str], required_columns: Iterable[str]) -> None:
    """
    Raise ValueError if required columns are missing.
    """
    missing = missing_columns(columns, required_columns)

    if missing:
        formatted = ", ".join(missing)
        raise ValueError(f"Missing required columns: {formatted}")
