import polars as pl


def _ensure_benchmark_close(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    date_col: str = "date",
    benchmark_price_col: str = "close",
) -> pl.DataFrame:
    """
    Join benchmark close only if it is not already present.
    """
    if "benchmark_close" in df.columns:
        return df.sort(date_col)

    benchmark = benchmark_df.select(
        [
            pl.col(date_col),
            pl.col(benchmark_price_col).alias("benchmark_close"),
        ]
    ).sort(date_col)

    return df.join(
        benchmark,
        on=date_col,
        how="left",
    ).sort(date_col)


def add_benchmark_returns(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    date_col: str = "date",
    benchmark_price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Join benchmark prices and add benchmark return columns.
    """
    if windows is None:
        windows = [1, 5, 21, 63, 126, 252]

    result = _ensure_benchmark_close(
        df=df,
        benchmark_df=benchmark_df,
        date_col=date_col,
        benchmark_price_col=benchmark_price_col,
    )

    for window in windows:
        col_name = f"benchmark_return_{window}d"

        if col_name not in result.columns:
            result = result.with_columns(
                (
                    (pl.col("benchmark_close") / pl.col("benchmark_close").shift(window)) - 1
                ).alias(col_name)
            )

    return result


def add_excess_returns(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add asset returns minus benchmark returns.
    """
    if windows is None:
        windows = [1, 5, 21, 63, 126, 252]

    result = add_benchmark_returns(
        df=df,
        benchmark_df=benchmark_df,
        date_col=date_col,
        benchmark_price_col=benchmark_price_col,
        windows=windows,
    )

    for window in windows:
        asset_return = (pl.col(price_col) / pl.col(price_col).shift(window)) - 1

        result = result.with_columns(
            (
                asset_return - pl.col(f"benchmark_return_{window}d")
            ).alias(f"excess_return_{window}d")
        )

    return result


def add_relative_strength_ratio(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add relative strength ratio features.
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = _ensure_benchmark_close(
        df=df,
        benchmark_df=benchmark_df,
        date_col=date_col,
        benchmark_price_col=benchmark_price_col,
    )

    result = result.with_columns(
        pl.when(pl.col("benchmark_close") != 0)
        .then(pl.col(price_col) / pl.col("benchmark_close"))
        .otherwise(None)
        .alias("relative_strength_ratio")
    )

    for window in windows:
        result = result.with_columns(
            (
                (pl.col("relative_strength_ratio") / pl.col("relative_strength_ratio").shift(window)) - 1
            ).alias(f"relative_strength_ratio_change_{window}d")
        )

    return result


def add_rolling_beta(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling beta versus benchmark.
    """
    if windows is None:
        windows = [63, 126, 252]

    result = _ensure_benchmark_close(
        df=df,
        benchmark_df=benchmark_df,
        date_col=date_col,
        benchmark_price_col=benchmark_price_col,
    )

    result = result.with_columns(
        [
            pl.col(price_col).pct_change(1).alias("asset_return_1d"),
            pl.col("benchmark_close").pct_change(1).alias("benchmark_return_1d"),
        ]
    )

    for window in windows:
        asset_return = pl.col("asset_return_1d")
        benchmark_return = pl.col("benchmark_return_1d")

        rolling_cov = (
            (asset_return * benchmark_return).rolling_mean(window_size=window)
            - asset_return.rolling_mean(window_size=window)
            * benchmark_return.rolling_mean(window_size=window)
        )

        rolling_var = (
            (benchmark_return * benchmark_return).rolling_mean(window_size=window)
            - benchmark_return.rolling_mean(window_size=window)
            * benchmark_return.rolling_mean(window_size=window)
        )

        result = result.with_columns(
            pl.when(rolling_var != 0)
            .then(rolling_cov / rolling_var)
            .otherwise(None)
            .alias(f"beta_{window}d")
        )

    return result


def add_rolling_correlation(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add rolling correlation versus benchmark.
    """
    if windows is None:
        windows = [63, 126, 252]

    result = _ensure_benchmark_close(
        df=df,
        benchmark_df=benchmark_df,
        date_col=date_col,
        benchmark_price_col=benchmark_price_col,
    )

    result = result.with_columns(
        [
            pl.col(price_col).pct_change(1).alias("asset_return_1d"),
            pl.col("benchmark_close").pct_change(1).alias("benchmark_return_1d"),
        ]
    )

    for window in windows:
        asset_return = pl.col("asset_return_1d")
        benchmark_return = pl.col("benchmark_return_1d")

        rolling_cov = (
            (asset_return * benchmark_return).rolling_mean(window_size=window)
            - asset_return.rolling_mean(window_size=window)
            * benchmark_return.rolling_mean(window_size=window)
        )

        asset_std = asset_return.rolling_std(window_size=window)
        benchmark_std = benchmark_return.rolling_std(window_size=window)

        result = result.with_columns(
            pl.when((asset_std != 0) & (benchmark_std != 0))
            .then(rolling_cov / (asset_std * benchmark_std))
            .otherwise(None)
            .alias(f"correlation_{window}d")
        )

    return result


def add_relative_strength_features(
    df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    price_col: str = "close",
    benchmark_price_col: str = "close",
    date_col: str = "date",
) -> pl.DataFrame:
    """
    Add the standard relative strength feature set versus a benchmark.
    """
    result = df

    result = add_excess_returns(
        result,
        benchmark_df=benchmark_df,
        price_col=price_col,
        benchmark_price_col=benchmark_price_col,
        date_col=date_col,
    )

    result = add_relative_strength_ratio(
        result,
        benchmark_df=benchmark_df,
        price_col=price_col,
        benchmark_price_col=benchmark_price_col,
        date_col=date_col,
    )

    result = add_rolling_beta(
        result,
        benchmark_df=benchmark_df,
        price_col=price_col,
        benchmark_price_col=benchmark_price_col,
        date_col=date_col,
    )

    result = add_rolling_correlation(
        result,
        benchmark_df=benchmark_df,
        price_col=price_col,
        benchmark_price_col=benchmark_price_col,
        date_col=date_col,
    )

    return result
