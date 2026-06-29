import polars as pl

from src.validation.validators import (
    validate_not_empty,
    validate_required_columns,
)


REQUIRED_FUNDAMENTALS_COLUMNS = [
    "symbol",
    "source",
]


def validate_fundamentals(df: pl.DataFrame) -> None:
    validate_not_empty(df)
    validate_required_columns(df, REQUIRED_FUNDAMENTALS_COLUMNS)
