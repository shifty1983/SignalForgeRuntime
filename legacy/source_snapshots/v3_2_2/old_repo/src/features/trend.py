import polars as pl

from src.features.moving_average import add_moving_averages


def add_trend_slope(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
    annualize: bool = True,
    trading_days: int = 252,
) -> pl.DataFrame:
    """
    Add simple log-price trend slope features.

    Example output:
    - trend_slope_21d
    - trend_slope_63d
    - trend_slope_252d
    """
    if windows is None:
        windows = [21, 63, 126, 252]

    result = df

    for window in windows:
        slope = (
            (pl.col(price_col).log() - pl.col(price_col).shift(window).log())
            / window
        )

        if annualize:
            slope = slope * trading_days

        result = result.with_columns(
            slope.alias(f"trend_slope_{window}d")
        )

    return result


def add_trend_strength(
    df: pl.DataFrame,
    price_col: str = "close",
    windows: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add price-above-moving-average trend strength features.

    Example output:
    - above_sma_20d
    - above_sma_50d
    - above_sma_200d
    - trend_strength_score
    """
    if windows is None:
        windows = [20, 50, 100, 200]

    result = add_moving_averages(
        df=df,
        price_col=price_col,
        windows=windows,
    )

    above_cols = []

    for window in windows:
        col_name = f"above_sma_{window}d"
        above_cols.append(col_name)

        result = result.with_columns(
            (pl.col(price_col) > pl.col(f"sma_{window}d"))
            .cast(pl.Int8)
            .alias(col_name)
        )

    result = result.with_columns(
        sum(pl.col(col) for col in above_cols).alias("trend_strength_score")
    )

    return result


def add_moving_average_crossovers(
    df: pl.DataFrame,
    price_col: str = "close",
) -> pl.DataFrame:
    """
    Add common moving-average crossover features.

    Example output:
    - sma_20_vs_50
    - sma_50_vs_200
    - bullish_50_200_cross
    """
    result = add_moving_averages(
        df=df,
        price_col=price_col,
        windows=[20, 50, 200],
    )

    result = result.with_columns(
        [
            ((pl.col("sma_20d") / pl.col("sma_50d")) - 1).alias("sma_20_vs_50"),
            ((pl.col("sma_50d") / pl.col("sma_200d")) - 1).alias("sma_50_vs_200"),
            (pl.col("sma_50d") > pl.col("sma_200d"))
            .cast(pl.Int8)
            .alias("bullish_50_200_cross"),
        ]
    )

    return result


def add_trend_regime(
    df: pl.DataFrame,
    price_col: str = "close",
) -> pl.DataFrame:
    """
    Add a simple trend regime label.

    Output:
    - trend_regime

    Values:
    1 = bullish trend
    0 = mixed trend
    -1 = bearish trend
    """
    result = add_moving_averages(
        df=df,
        price_col=price_col,
        windows=[50, 200],
    )

    result = result.with_columns(
        pl.when(
            (pl.col(price_col) > pl.col("sma_200d"))
            & (pl.col("sma_50d") > pl.col("sma_200d"))
        )
        .then(1)
        .when(
            (pl.col(price_col) < pl.col("sma_200d"))
            & (pl.col("sma_50d") < pl.col("sma_200d"))
        )
        .then(-1)
        .otherwise(0)
        .alias("trend_regime")
    )

    return result
