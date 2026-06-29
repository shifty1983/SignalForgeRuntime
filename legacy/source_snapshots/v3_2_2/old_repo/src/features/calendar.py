import polars as pl


def add_calendar_features(
    df: pl.DataFrame,
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Add basic calendar features.

    Example output:
    - day_of_week
    - day_of_month
    - month
    - quarter
    - year
    """
    result = df.with_columns(
        pl.col(date_col).cast(pl.Date).alias(date_col)
    )

    result = result.with_columns(
        [
            pl.col(date_col).dt.weekday().alias("day_of_week"),
            pl.col(date_col).dt.day().alias("day_of_month"),
            pl.col(date_col).dt.month().alias("month"),
            pl.col(date_col).dt.quarter().alias("quarter"),
            pl.col(date_col).dt.year().alias("year"),
        ]
    )

    return result


def add_month_end_features(
    df: pl.DataFrame,
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Add month boundary features.

    Example output:
    - is_month_start
    - is_month_end
    """
    result = df.with_columns(
        pl.col(date_col).cast(pl.Date).alias(date_col)
    )

    result = result.with_columns(
        [
            (
                pl.col(date_col).dt.day() == 1
            ).cast(pl.Int8).alias("is_month_start"),

            (
                pl.col(date_col).dt.month()
                != pl.col(date_col).shift(-1).dt.month()
            ).cast(pl.Int8).alias("is_month_end"),
        ]
    )

    return result


def add_quarter_end_features(
    df: pl.DataFrame,
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Add quarter boundary features.

    Example output:
    - is_quarter_start
    - is_quarter_end
    """
    result = df.with_columns(
        pl.col(date_col).cast(pl.Date).alias(date_col)
    )

    result = result.with_columns(
        [
            (
                pl.col(date_col).dt.quarter()
                != pl.col(date_col).shift(1).dt.quarter()
            ).cast(pl.Int8).alias("is_quarter_start"),

            (
                pl.col(date_col).dt.quarter()
                != pl.col(date_col).shift(-1).dt.quarter()
            ).cast(pl.Int8).alias("is_quarter_end"),
        ]
    )

    return result


def add_calendar_feature_set(
    df: pl.DataFrame,
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Add the standard calendar feature set.
    """
    result = df.sort(date_col)

    result = add_calendar_features(
        result,
        date_col=date_col,
    )

    result = add_month_end_features(
        result,
        date_col=date_col,
    )

    result = add_quarter_end_features(
        result,
        date_col=date_col,
    )

    return result
