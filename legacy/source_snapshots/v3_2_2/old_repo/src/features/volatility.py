import polars as pl


def add_rolling_volatility(
    df: pl.DataFrame,
    return_col: str = "return_1d",
    windows: list[int] | None = None,
    annualize: bool = True,
    trading_days: int = 252,
) -> pl.DataFrame:
    """
    Add rolling volatility columns.

    Example output:
    - vol_21d
    - vol_63d
    - vol_252d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        vol = pl.col(return_col).rolling_std(window_size=window)

        if annualize:
            vol = vol * (trading_days ** 0.5)

        result = result.with_columns(
            vol.alias(f"vol_{window}d")
        )

    return result
