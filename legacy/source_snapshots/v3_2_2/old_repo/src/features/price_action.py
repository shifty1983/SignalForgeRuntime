import polars as pl


def add_daily_range_features(
    df: pl.DataFrame,
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pl.DataFrame:
    """
    Add daily price action range features.

    Example output:
    - daily_range
    - daily_range_pct
    - close_location
    - intraday_return
    - overnight_gap
    """
    daily_range = pl.col(high_col) - pl.col(low_col)

    return df.with_columns(
        [
            daily_range.alias("daily_range"),

            pl.when(pl.col(low_col) != 0)
            .then((pl.col(high_col) / pl.col(low_col)) - 1)
            .otherwise(None)
            .alias("daily_range_pct"),

            pl.when(daily_range != 0)
            .then((pl.col(close_col) - pl.col(low_col)) / daily_range)
            .otherwise(None)
            .alias("close_location"),

            pl.when(pl.col(open_col) != 0)
            .then((pl.col(close_col) / pl.col(open_col)) - 1)
            .otherwise(None)
            .alias("intraday_return"),

            pl.when(pl.col(close_col).shift(1) != 0)
            .then((pl.col(open_col) / pl.col(close_col).shift(1)) - 1)
            .otherwise(None)
            .alias("overnight_gap"),
        ]
    )


def add_candlestick_features(
    df: pl.DataFrame,
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pl.DataFrame:
    """
    Add basic candlestick/body features.

    Example output:
    - candle_body
    - candle_body_pct
    - upper_wick_pct
    - lower_wick_pct
    - candle_direction
    """
    candle_body = pl.col(close_col) - pl.col(open_col)
    high_body = pl.max_horizontal(pl.col(open_col), pl.col(close_col))
    low_body = pl.min_horizontal(pl.col(open_col), pl.col(close_col))

    return df.with_columns(
        [
            candle_body.alias("candle_body"),

            pl.when(pl.col(open_col) != 0)
            .then(candle_body.abs() / pl.col(open_col))
            .otherwise(None)
            .alias("candle_body_pct"),

            pl.when(pl.col(open_col) != 0)
            .then((pl.col(high_col) - high_body) / pl.col(open_col))
            .otherwise(None)
            .alias("upper_wick_pct"),

            pl.when(pl.col(open_col) != 0)
            .then((low_body - pl.col(low_col)) / pl.col(open_col))
            .otherwise(None)
            .alias("lower_wick_pct"),

            pl.when(pl.col(close_col) > pl.col(open_col))
            .then(1)
            .when(pl.col(close_col) < pl.col(open_col))
            .then(-1)
            .otherwise(0)
            .alias("candle_direction"),
        ]
    )


def add_gap_features(
    df: pl.DataFrame,
    open_col: str = "open",
    close_col: str = "close",
    gap_threshold: float = 0.01,
) -> pl.DataFrame:
    """
    Add gap-up and gap-down features.

    Example output:
    - gap_return
    - gap_up
    - gap_down
    """
    gap_return = (pl.col(open_col) / pl.col(close_col).shift(1)) - 1

    return df.with_columns(
        [
            pl.when(pl.col(close_col).shift(1) != 0)
            .then(gap_return)
            .otherwise(None)
            .alias("gap_return"),

            (gap_return >= gap_threshold)
            .cast(pl.Int8)
            .alias("gap_up"),

            (gap_return <= -gap_threshold)
            .cast(pl.Int8)
            .alias("gap_down"),
        ]
    )


def add_breakout_features(
    df: pl.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling breakout features.

    Example output:
    - breakout_high_21d
    - breakdown_low_21d
    - close_vs_high_21d
    - close_vs_low_21d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        rolling_high = pl.col(high_col).rolling_max(window_size=window).shift(1)
        rolling_low = pl.col(low_col).rolling_min(window_size=window).shift(1)

        result = result.with_columns(
            [
                (pl.col(close_col) > rolling_high)
                .cast(pl.Int8)
                .alias(f"breakout_high_{window}d"),

                (pl.col(close_col) < rolling_low)
                .cast(pl.Int8)
                .alias(f"breakdown_low_{window}d"),

                pl.when(rolling_high != 0)
                .then((pl.col(close_col) / rolling_high) - 1)
                .otherwise(None)
                .alias(f"close_vs_high_{window}d"),

                pl.when(rolling_low != 0)
                .then((pl.col(close_col) / rolling_low) - 1)
                .otherwise(None)
                .alias(f"close_vs_low_{window}d"),
            ]
        )

    return result


def add_price_action_features(
    df: pl.DataFrame,
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pl.DataFrame:
    """
    Add the standard price action feature set.
    """
    result = df

    result = add_daily_range_features(
        result,
        open_col=open_col,
        high_col=high_col,
        low_col=low_col,
        close_col=close_col,
    )

    result = add_candlestick_features(
        result,
        open_col=open_col,
        high_col=high_col,
        low_col=low_col,
        close_col=close_col,
    )

    result = add_gap_features(
        result,
        open_col=open_col,
        close_col=close_col,
    )

    result = add_breakout_features(
        result,
        high_col=high_col,
        low_col=low_col,
        close_col=close_col,
    )

    return result
