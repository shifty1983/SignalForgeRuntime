import polars as pl


def add_returns(
    df: pl.DataFrame,
    price_col: str = "close",
    periods: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add percentage return columns for one or more lookback periods.

    Example output columns:
    - return_1d
    - return_5d
    - return_21d
    """
    if periods is None:
        periods = [1, 5, 21, 63, 126, 252]

    result = df

    for period in periods:
        result = result.with_columns(
            (
                pl.col(price_col).pct_change(period)
            ).alias(f"return_{period}d")
        )

    return result


def add_log_returns(
    df: pl.DataFrame,
    price_col: str = "close",
    periods: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add log return columns for one or more lookback periods.
    """
    if periods is None:
        periods = [1, 5, 21, 63, 126, 252]

    result = df

    for period in periods:
        result = result.with_columns(
            (
                (pl.col(price_col) / pl.col(price_col).shift(period)).log()
            ).alias(f"log_return_{period}d")
        )

    return result

