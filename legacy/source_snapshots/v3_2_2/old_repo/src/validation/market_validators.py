import polars as pl

from src.common.schema import MARKET_COLUMNS

from src.validation.validators import (
    validate_no_duplicate_dates,
    validate_no_nulls,
    validate_non_negative_prices,
    validate_non_negative_volume,
    validate_not_empty,
    validate_required_columns,
)

def validate_market_ohlcv(df: pl.DataFrame) -> None:
    validate_not_empty(df)
    validate_required_columns(df, MARKET_COLUMNS)
    validate_no_nulls(df, MARKET_COLUMNS)
    validate_no_duplicate_dates(df)
    validate_non_negative_prices(df)
    validate_non_negative_volume(df)
