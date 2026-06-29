import polars as pl

from src.validation.validators import (
    validate_not_empty,
    validate_required_columns,
)


REQUIRED_OPTIONS_COLUMNS = [
    "underlying_symbol",
    "contract_symbol",
    "expiration",
    "strike",
    "option_type",
    "bid",
    "ask",
    "last_price",
    "volume",
    "open_interest",
    "implied_volatility",
    "in_the_money",
    "source",
]


def validate_options_chain(df: pl.DataFrame) -> None:
    validate_not_empty(df)
    validate_required_columns(df, REQUIRED_OPTIONS_COLUMNS)
