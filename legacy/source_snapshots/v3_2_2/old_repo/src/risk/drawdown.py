from __future__ import annotations

import polars as pl


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def calculate_equity_curve_from_returns(
    returns: pl.DataFrame,
    return_col: str = "returns",
    equity_col: str = "equity",
    starting_value: float = 1.0,
) -> pl.DataFrame:
    """
    Convert a return series into an equity curve.
    """

    _require_columns(returns, {return_col})

    if starting_value <= 0:
        raise ValueError("starting_value must be positive")

    return returns.with_columns(
        (
            (1.0 + pl.col(return_col).fill_null(0.0)).cum_prod()
            * starting_value
        ).alias(equity_col)
    )


def calculate_drawdown(
    equity: pl.DataFrame,
    equity_col: str = "equity",
    drawdown_col: str = "drawdown",
) -> pl.DataFrame:
    """
    Calculate drawdown from an equity curve.

    Drawdown is expressed as a negative percentage from the running peak.
    """

    _require_columns(equity, {equity_col})

    invalid = equity.filter(pl.col(equity_col) <= 0)

    if invalid.height > 0:
        raise ValueError("Equity values must be positive")

    return (
        equity.with_columns(
            pl.col(equity_col).cum_max().alias("running_peak")
        )
        .with_columns(
            (
                pl.col(equity_col) / pl.col("running_peak") - 1.0
            ).alias(drawdown_col)
        )
    )


def calculate_max_drawdown(
    equity: pl.DataFrame,
    equity_col: str = "equity",
) -> float:
    """
    Calculate maximum drawdown from an equity curve.
    """

    drawdowns = calculate_drawdown(equity, equity_col=equity_col)

    max_drawdown = drawdowns.select(pl.col("drawdown").min()).item()

    return float(max_drawdown or 0.0)


def calculate_underwater_curve(
    equity: pl.DataFrame,
    equity_col: str = "equity",
    underwater_col: str = "underwater",
) -> pl.DataFrame:
    """
    Calculate underwater curve.

    This is the same drawdown concept, renamed for charting/reporting.
    """

    result = calculate_drawdown(
        equity,
        equity_col=equity_col,
        drawdown_col=underwater_col,
    )

    return result


def calculate_drawdown_durations(
    equity: pl.DataFrame,
    equity_col: str = "equity",
) -> dict[str, int]:
    """
    Calculate drawdown duration statistics.

    Duration counts consecutive periods below the running peak.
    """

    drawdowns = calculate_drawdown(equity, equity_col=equity_col)

    values = drawdowns["drawdown"].to_list()

    current_duration = 0
    max_duration = 0

    for value in values:
        if value < 0:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0

    return {
        "max_drawdown_duration": max_duration,
        "current_drawdown_duration": current_duration,
    }


def drawdown_summary(
    equity: pl.DataFrame,
    equity_col: str = "equity",
) -> dict[str, float | int]:
    """
    Create compact drawdown summary.
    """

    drawdowns = calculate_drawdown(equity, equity_col=equity_col)
    durations = calculate_drawdown_durations(equity, equity_col=equity_col)

    max_drawdown = drawdowns.select(pl.col("drawdown").min()).item()
    ending_drawdown = drawdowns.select(pl.col("drawdown").last()).item()
    ending_equity = drawdowns.select(pl.col(equity_col).last()).item()
    running_peak = drawdowns.select(pl.col("running_peak").last()).item()

    return {
        "max_drawdown": float(max_drawdown or 0.0),
        "ending_drawdown": float(ending_drawdown or 0.0),
        "ending_equity": float(ending_equity or 0.0),
        "running_peak": float(running_peak or 0.0),
        "max_drawdown_duration": durations["max_drawdown_duration"],
        "current_drawdown_duration": durations["current_drawdown_duration"],
    }
