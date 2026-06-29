import polars as pl


def add_momentum(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add simple price momentum columns.

    Example output:
    - momentum_21d
    - momentum_63d
    - momentum_126d
    - momentum_252d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        result = result.with_columns(
            (
                (pl.col(price_col) / pl.col(price_col).shift(window)) - 1
            ).alias(f"momentum_{window}d")
        )

    return result


def add_rate_of_change(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rate of change columns.

    Same calculation as momentum, but named for technical indicator usage.
    """
    if windows is None:
        windows = [10, 21, 63]

    result = df

    for window in windows:
        result = result.with_columns(
            (
                pl.col(price_col).pct_change(window)
            ).alias(f"roc_{window}d")
        )

    return result
