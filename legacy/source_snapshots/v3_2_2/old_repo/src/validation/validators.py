import polars as pl


def validate_required_columns(df: pl.DataFrame, required_columns: list[str]) -> None:
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")


def validate_not_empty(df: pl.DataFrame) -> None:
    if df.is_empty():
        raise ValueError("DataFrame is empty")


def validate_no_nulls(df: pl.DataFrame, columns: list[str]) -> None:
    null_counts = df.select([pl.col(col).null_count().alias(col) for col in columns])

    bad_columns = [
        col
        for col, value in zip(null_counts.columns, null_counts.row(0))
        if value > 0
    ]

    if bad_columns:
        raise ValueError(f"Null values found in required columns: {bad_columns}")


def validate_no_duplicate_dates(df: pl.DataFrame) -> None:
    if "date" not in df.columns:
        return

    duplicate_count = df.group_by("date").len().filter(pl.col("len") > 1).height

    if duplicate_count > 0:
        raise ValueError(f"Duplicate dates found: {duplicate_count}")


def validate_non_negative_prices(df: pl.DataFrame) -> None:
    price_columns = [
        col for col in ["open", "high", "low", "close", "adj_close"]
        if col in df.columns
    ]

    for col in price_columns:
        bad_count = df.filter(pl.col(col) < 0).height

        if bad_count > 0:
            raise ValueError(f"Negative values found in price column '{col}': {bad_count}")


def validate_non_negative_volume(df: pl.DataFrame) -> None:
    if "volume" not in df.columns:
        return

    bad_count = df.filter(pl.col("volume") < 0).height

    if bad_count > 0:
        raise ValueError(f"Negative volume values found: {bad_count}")
