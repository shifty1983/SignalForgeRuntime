import polars as pl

from src.validation.validators import (
    validate_not_empty,
    validate_required_columns,
)


REQUIRED_SENTIMENT_COLUMNS = [
    "symbol",
    "source",
    "title",
    "url",
    "time_published",
    "overall_sentiment_score",
    "overall_sentiment_label",
]


def validate_sentiment(df: pl.DataFrame) -> None:
    validate_not_empty(df)
    validate_required_columns(df, REQUIRED_SENTIMENT_COLUMNS)
