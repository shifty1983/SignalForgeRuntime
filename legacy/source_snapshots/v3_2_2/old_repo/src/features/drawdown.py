import polars as pl


def add_drawdown(
    df: pl.DataFrame,
    price_col: str = "close",
) -> pl.DataFrame:
    """
    Add running drawdown from cumulative high.

    Example output:
    - rolling_peak
    - drawdown
    """
    return df.with_columns(
        pl.col(price_col).cum_max().alias("rolling_peak")
    ).with_columns(
        (
            (pl.col(price_col) / pl.col("rolling_peak")) - 1
        ).alias("drawdown")
    )


def add_max_drawdown(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling max drawdown columns.

    Example output:
    - max_drawdown_21d
    - max_drawdown_63d
    - max_drawdown_252d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        rolling_peak = pl.col(price_col).rolling_max(window_size=window)

        result = result.with_columns(
            (
                (pl.col(price_col) / rolling_peak) - 1
            ).rolling_min(window_size=window).alias(f"max_drawdown_{window}d")
        )

    return result
