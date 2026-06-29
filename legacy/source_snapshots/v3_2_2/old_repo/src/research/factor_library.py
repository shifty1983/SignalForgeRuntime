from __future__ import annotations

import polars as pl

from src.research.factor import ColumnFactor, ExpressionFactor, Factor


def passthrough_factor(
    input_column: str,
    name: str | None = None,
    output_column: str | None = None,
) -> ColumnFactor:
    """
    Use an existing column directly as a factor.
    """

    factor_name = name or output_column or input_column

    return ColumnFactor(
        name=factor_name,
        input_column=input_column,
        output_column=output_column or factor_name,
    )


def momentum_factor(
    input_column: str = "momentum_21d",
    output_column: str = "momentum_factor",
) -> ExpressionFactor:
    """
    Momentum factor.

    Higher momentum = better.
    """

    return ExpressionFactor(
        name="momentum",
        input_columns=[input_column],
        expression=pl.col(input_column),
        output_column=output_column,
    )


def reversal_factor(
    input_column: str = "return_5d",
    output_column: str = "reversal_factor",
) -> ExpressionFactor:
    """
    Short-term reversal factor.

    Lower recent return = better, so the return is inverted.
    """

    return ExpressionFactor(
        name="reversal",
        input_columns=[input_column],
        expression=-pl.col(input_column),
        output_column=output_column,
    )


def low_volatility_factor(
    input_column: str = "volatility_21d",
    output_column: str = "low_volatility_factor",
) -> ExpressionFactor:
    """
    Low-volatility factor.

    Lower volatility = better, so volatility is inverted.
    """

    return ExpressionFactor(
        name="low_volatility",
        input_columns=[input_column],
        expression=-pl.col(input_column),
        output_column=output_column,
    )


def trend_factor(
    price_column: str = "close",
    moving_average_column: str = "sma_50",
    output_column: str = "trend_factor",
) -> ExpressionFactor:
    """
    Price trend factor.

    Higher price relative to moving average = better.
    """

    expr = (
        pl.when(
            pl.col(moving_average_column).is_null()
            | (pl.col(moving_average_column) == 0)
        )
        .then(None)
        .otherwise(
            (pl.col(price_column) / pl.col(moving_average_column)) - 1.0
        )
    )

    return ExpressionFactor(
        name="trend",
        input_columns=[price_column, moving_average_column],
        expression=expr,
        output_column=output_column,
    )


def risk_adjusted_momentum_factor(
    momentum_column: str = "momentum_21d",
    volatility_column: str = "volatility_21d",
    output_column: str = "risk_adjusted_momentum_factor",
) -> ExpressionFactor:
    """
    Momentum adjusted by volatility.

    Higher momentum per unit of volatility = better.
    """

    expr = (
        pl.when(
            pl.col(volatility_column).is_null()
            | (pl.col(volatility_column) <= 0)
        )
        .then(None)
        .otherwise(pl.col(momentum_column) / pl.col(volatility_column))
    )

    return ExpressionFactor(
        name="risk_adjusted_momentum",
        input_columns=[momentum_column, volatility_column],
        expression=expr,
        output_column=output_column,
    )


def relative_strength_factor(
    asset_return_column: str = "return_21d",
    benchmark_return_column: str = "benchmark_return_21d",
    output_column: str = "relative_strength_factor",
) -> ExpressionFactor:
    """
    Relative strength factor.

    Asset return minus benchmark return.
    """

    return ExpressionFactor(
        name="relative_strength",
        input_columns=[asset_return_column, benchmark_return_column],
        expression=pl.col(asset_return_column) - pl.col(benchmark_return_column),
        output_column=output_column,
    )


def drawdown_resilience_factor(
    drawdown_column: str = "drawdown",
    output_column: str = "drawdown_resilience_factor",
    drawdown_is_positive_magnitude: bool = False,
) -> ExpressionFactor:
    """
    Drawdown resilience factor.

    If drawdown is stored as a negative number, higher is already better.
    Example: -0.05 is better than -0.30.

    If drawdown is stored as a positive magnitude, lower is better, so it is inverted.
    Example: 0.05 is better than 0.30.
    """

    expr = (
        -pl.col(drawdown_column)
        if drawdown_is_positive_magnitude
        else pl.col(drawdown_column)
    )

    return ExpressionFactor(
        name="drawdown_resilience",
        input_columns=[drawdown_column],
        expression=expr,
        output_column=output_column,
    )

def volume_momentum_factor(
    volume_column: str = "volume",
    average_volume_column: str = "avg_volume_21d",
    output_column: str = "volume_momentum_factor",
) -> ExpressionFactor:
    """
    Volume momentum factor.

    Higher current volume relative to average volume = stronger participation.
    """

    expr = (
        pl.when(
            pl.col(average_volume_column).is_null()
            | (pl.col(average_volume_column) <= 0)
        )
        .then(None)
        .otherwise((pl.col(volume_column) / pl.col(average_volume_column)) - 1.0)
    )

    return ExpressionFactor(
        name="volume_momentum",
        input_columns=[volume_column, average_volume_column],
        expression=expr,
        output_column=output_column,
    )


def liquidity_factor(
    price_column: str = "close",
    volume_column: str = "volume",
    output_column: str = "liquidity_factor",
) -> ExpressionFactor:
    """
    Liquidity factor.

    Higher dollar volume = better liquidity.
    """

    expr = (
        pl.when(
            pl.col(price_column).is_null()
            | pl.col(volume_column).is_null()
            | (pl.col(price_column) <= 0)
            | (pl.col(volume_column) <= 0)
        )
        .then(None)
        .otherwise(pl.col(price_column) * pl.col(volume_column))
    )

    return ExpressionFactor(
        name="liquidity",
        input_columns=[price_column, volume_column],
        expression=expr,
        output_column=output_column,
    )


def intraday_range_volatility_factor(
    high_column: str = "high",
    low_column: str = "low",
    close_column: str = "close",
    output_column: str = "intraday_range_volatility_factor",
) -> ExpressionFactor:
    """
    Intraday range volatility factor.

    Lower high-low range relative to close = better, so the value is inverted.
    """

    expr = (
        pl.when(
            pl.col(high_column).is_null()
            | pl.col(low_column).is_null()
            | pl.col(close_column).is_null()
            | (pl.col(close_column) <= 0)
        )
        .then(None)
        .otherwise(-((pl.col(high_column) - pl.col(low_column)) / pl.col(close_column)))
    )

    return ExpressionFactor(
        name="intraday_range_volatility",
        input_columns=[high_column, low_column, close_column],
        expression=expr,
        output_column=output_column,
    )


def price_position_factor(
    close_column: str = "close",
    rolling_high_column: str = "rolling_high_252d",
    rolling_low_column: str = "rolling_low_252d",
    output_column: str = "price_position_factor",
) -> ExpressionFactor:
    """
    Price position factor.

    Measures where price sits inside its rolling high-low range.
    Higher position = stronger trend/relative strength.
    """

    range_width = pl.col(rolling_high_column) - pl.col(rolling_low_column)

    expr = (
        pl.when(
            pl.col(close_column).is_null()
            | pl.col(rolling_high_column).is_null()
            | pl.col(rolling_low_column).is_null()
            | (range_width <= 0)
        )
        .then(None)
        .otherwise((pl.col(close_column) - pl.col(rolling_low_column)) / range_width)
    )

    return ExpressionFactor(
        name="price_position",
        input_columns=[close_column, rolling_high_column, rolling_low_column],
        expression=expr,
        output_column=output_column,
    )


def breakout_strength_factor(
    close_column: str = "close",
    prior_high_column: str = "rolling_high_20d",
    output_column: str = "breakout_strength_factor",
) -> ExpressionFactor:
    """
    Breakout strength factor.

    Measures price relative to a prior rolling high.
    Higher value = stronger breakout.
    """

    expr = (
        pl.when(
            pl.col(close_column).is_null()
            | pl.col(prior_high_column).is_null()
            | (pl.col(prior_high_column) <= 0)
        )
        .then(None)
        .otherwise((pl.col(close_column) / pl.col(prior_high_column)) - 1.0)
    )

    return ExpressionFactor(
        name="breakout_strength",
        input_columns=[close_column, prior_high_column],
        expression=expr,
        output_column=output_column,
    )


def volatility_adjusted_relative_strength_factor(
    asset_return_column: str = "return_21d",
    benchmark_return_column: str = "benchmark_return_21d",
    volatility_column: str = "volatility_21d",
    output_column: str = "volatility_adjusted_relative_strength_factor",
) -> ExpressionFactor:
    """
    Relative strength adjusted by volatility.

    Asset excess return divided by realized volatility.
    Higher excess return per unit of volatility = better.
    """

    excess_return = pl.col(asset_return_column) - pl.col(benchmark_return_column)

    expr = (
        pl.when(
            pl.col(volatility_column).is_null()
            | (pl.col(volatility_column) <= 0)
        )
        .then(None)
        .otherwise(excess_return / pl.col(volatility_column))
    )

    return ExpressionFactor(
        name="volatility_adjusted_relative_strength",
        input_columns=[
            asset_return_column,
            benchmark_return_column,
            volatility_column,
        ],
        expression=expr,
        output_column=output_column,
    )


def default_factor_library() -> list[Factor]:
    """
    Default reusable research factor set.

    These are factor definitions only. They do not generate trade signals directly.
    """

    return [
        momentum_factor(),
        reversal_factor(),
        low_volatility_factor(),
        trend_factor(),
        risk_adjusted_momentum_factor(),
        relative_strength_factor(),
        drawdown_resilience_factor(),
        volume_momentum_factor(),
        liquidity_factor(),
        intraday_range_volatility_factor(),
        price_position_factor(),
        breakout_strength_factor(),
        volatility_adjusted_relative_strength_factor(),
    ]

def apply_factors(
    df: pl.DataFrame,
    factors: list[Factor],
) -> pl.DataFrame:
    """
    Apply multiple factor definitions to a research panel.
    """

    result = df

    for factor in factors:
        result = factor.run(result)

    return result
