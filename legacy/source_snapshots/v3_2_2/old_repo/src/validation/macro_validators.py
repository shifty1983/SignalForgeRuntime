import polars as pl

from src.common.schema import MACRO_COLUMNS

from src.validation.validators import (
    validate_no_duplicate_dates,
    validate_no_nulls,
    validate_not_empty,
    validate_required_columns,
)

def validate_macro_series(df: pl.DataFrame) -> None:
    validate_not_empty(df)
    validate_required_columns(df, MACRO_COLUMNS)
    validate_no_nulls(df, MACRO_COLUMNS)
    validate_no_duplicate_dates(df)
