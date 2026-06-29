import polars as pl


def add_dollar_volume(
    df: pl.DataFrame,
    price_col: str = "close",
    volume_col: str = "volume",
) -> pl.DataFrame:
    """
    Add dollar volume.

    Example output:
    - dollar_volume
    """
    return df.with_columns(
        (pl.col(price_col) * pl.col(volume_col)).alias("dollar_volume")
    )


def add_volume_momentum(
    df: pl.DataFrame,
    volume_col: str = "volume",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add volume percentage change features.

    Example output:
    - volume_change_1d
    - volume_change_5d
    - volume_change_21d
    """
    if windows is None:
        windows = [1, 5, 21, 63]

    result = df

    for window in windows:
        result = result.with_columns(
            pl.col(volume_col)
            .pct_change(window)
            .alias(f"volume_change_{window}d")
        )

    return result


def add_average_volume(
    df: pl.DataFrame,
    volume_col: str = "volume",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling average volume features.

    Example output:
    - avg_volume_21d
    - avg_volume_63d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        result = result.with_columns(
            pl.col(volume_col)
            .rolling_mean(window_size=window)
            .alias(f"avg_volume_{window}d")
        )

    return result


def add_volume_spikes(
    df: pl.DataFrame,
    volume_col: str = "volume",
    windows: list[int] | None = None,
    spike_threshold: float = 2.0,
) -> pl.DataFrame:
    """
    Add volume spike features.

    Example output:
    - volume_ratio_21d
    - volume_spike_21d
    """
    if windows is None:
        windows = [21, 63]

    result = df

    for window in windows:
        avg_col = f"avg_volume_{window}d"
        ratio_col = f"volume_ratio_{window}d"
        spike_col = f"volume_spike_{window}d"

        result = result.with_columns(
            pl.col(volume_col)
            .rolling_mean(window_size=window)
            .alias(avg_col)
        )

        result = result.with_columns(
            pl.when(pl.col(avg_col) != 0)
            .then(pl.col(volume_col) / pl.col(avg_col))
            .otherwise(None)
            .alias(ratio_col)
        )

        result = result.with_columns(
            (pl.col(ratio_col) >= spike_threshold)
            .cast(pl.Int8)
            .alias(spike_col)
        )

    return result


def add_on_balance_volume(
    df: pl.DataFrame,
    price_col: str = "close",
    volume_col: str = "volume",
) -> pl.DataFrame:
    """
    Add on-balance volume.

    Example output:
    - obv
    """
    return df.with_columns(
        pl.when(pl.col(price_col) > pl.col(price_col).shift(1))
        .then(pl.col(volume_col))
        .when(pl.col(price_col) < pl.col(price_col).shift(1))
        .then(-pl.col(volume_col))
        .otherwise(0)
        .cum_sum()
        .alias("obv")
    )


def add_volume_features(
    df: pl.DataFrame,
    price_col: str = "close",
    volume_col: str = "volume",
) -> pl.DataFrame:
    """
    Add the standard volume feature set.
    """
    result = df

    result = add_dollar_volume(
        result,
        price_col=price_col,
        volume_col=volume_col,
    )

    result = add_volume_momentum(
        result,
        volume_col=volume_col,
    )

    result = add_average_volume(
        result,
        volume_col=volume_col,
    )

    result = add_volume_spikes(
        result,
        volume_col=volume_col,
    )

    result = add_on_balance_volume(
        result,
        price_col=price_col,
        volume_col=volume_col,
    )

    return result
