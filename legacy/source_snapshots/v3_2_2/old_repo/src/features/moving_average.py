import polars as pl


def add_moving_averages(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add simple moving average columns.

    Example output:
    - sma_20d
    - sma_50d
    - sma_200d
    """
    if windows is None:
        windows = [20, 50, 100, 200]

    result = df

    for window in windows:
        result = result.with_columns(
            pl.col(price_col)
            .rolling_mean(window_size=window)
            .alias(f"sma_{window}d")
        )

    return result


def add_price_vs_moving_average(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add price relative to moving average columns.

    Example output:
    - price_vs_sma_20d
    - price_vs_sma_50d
    - price_vs_sma_200d
    """
    if windows is None:
        windows = [20, 50, 100, 200]

    result = add_moving_averages(
        df=df,
        price_col=price_col,
        windows=windows,
    )

    for window in windows:
        result = result.with_columns(
            (
                (pl.col(price_col) / pl.col(f"sma_{window}d")) - 1
            ).alias(f"price_vs_sma_{window}d")
        )

    return result
