import polars as pl


def add_rolling_stats(
    df: pl.DataFrame,
    value_col: str,
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add generic rolling mean, std, min, and max columns.

    Example output:
    - close_mean_21d
    - close_std_21d
    - close_min_21d
    - close_max_21d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        result = result.with_columns(
            [
                pl.col(value_col)
                .rolling_mean(window_size=window)
                .alias(f"{value_col}_mean_{window}d"),

                pl.col(value_col)
                .rolling_std(window_size=window)
                .alias(f"{value_col}_std_{window}d"),

                pl.col(value_col)
                .rolling_min(window_size=window)
                .alias(f"{value_col}_min_{window}d"),

                pl.col(value_col)
                .rolling_max(window_size=window)
                .alias(f"{value_col}_max_{window}d"),
            ]
        )

    return result


def add_rolling_zscores(
    df: pl.DataFrame,
    value_col: str,
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling z-score columns.

    Example output:
    - close_zscore_21d
    - return_1d_zscore_63d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        rolling_mean = pl.col(value_col).rolling_mean(window_size=window)
        rolling_std = pl.col(value_col).rolling_std(window_size=window)

        result = result.with_columns(
            (
                (pl.col(value_col) - rolling_mean) / rolling_std
            ).alias(f"{value_col}_zscore_{window}d")
        )

    return result


def add_rolling_range_position(
    df: pl.DataFrame,
    value_col: str,
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling range position.

    Measures where the current value sits inside its rolling min/max range.

    0 = near rolling low
    1 = near rolling high

    Example output:
    - close_range_pos_21d
    - close_range_pos_252d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        rolling_min = pl.col(value_col).rolling_min(window_size=window)
        rolling_max = pl.col(value_col).rolling_max(window_size=window)
        rolling_range = rolling_max - rolling_min

        result = result.with_columns(
            pl.when(rolling_range != 0)
            .then((pl.col(value_col) - rolling_min) / rolling_range)
            .otherwise(None)
            .alias(f"{value_col}_range_pos_{window}d")
        )

    return result
