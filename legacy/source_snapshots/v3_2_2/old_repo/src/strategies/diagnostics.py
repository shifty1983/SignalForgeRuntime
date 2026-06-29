from __future__ import annotations

import polars as pl


def validate_strategy_output(
    df: pl.DataFrame,
    date_col: str = "date",
    symbol_col: str = "symbol",
    weight_col: str = "target_weight",
) -> None:
    """
    Validate that a strategy output has the minimum required columns.
    """

    required = [date_col, symbol_col, weight_col]

    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(f"Strategy output missing required columns: {missing}")

    if df.height == 0:
        raise ValueError("Strategy output is empty.")


def summarize_signals(
    df: pl.DataFrame,
    date_col: str = "date",
    signal_col: str = "signal",
) -> pl.DataFrame:
    """
    Summarize signal counts by date.
    """

    return (
        df.group_by(date_col)
        .agg(
            (pl.col(signal_col) > 0).sum().alias("long_count"),
            (pl.col(signal_col) < 0).sum().alias("short_count"),
            (pl.col(signal_col) == 0).sum().alias("flat_count"),
            pl.col(signal_col).count().alias("total_count"),
        )
        .sort(date_col)
    )


def summarize_weights(
    df: pl.DataFrame,
    date_col: str = "date",
    weight_col: str = "target_weight",
) -> pl.DataFrame:
    """
    Summarize target weights by date.
    """

    return (
        df.group_by(date_col)
        .agg(
            pl.col(weight_col).sum().alias("net_exposure"),
            pl.col(weight_col).abs().sum().alias("gross_exposure"),
            pl.col(weight_col).max().alias("max_weight"),
            pl.col(weight_col).min().alias("min_weight"),
            pl.col(weight_col).abs().max().alias("max_abs_weight"),
            (pl.col(weight_col) != 0).sum().alias("active_positions"),
        )
        .sort(date_col)
    )


def summarize_strategy_output(
    df: pl.DataFrame,
    date_col: str = "date",
    symbol_col: str = "symbol",
    signal_col: str = "signal",
    weight_col: str = "target_weight",
) -> dict[str, pl.DataFrame]:
    """
    Return common diagnostics for one strategy output.
    """

    validate_strategy_output(
        df=df,
        date_col=date_col,
        symbol_col=symbol_col,
        weight_col=weight_col,
    )

    output = {
        "weights": summarize_weights(
            df=df,
            date_col=date_col,
            weight_col=weight_col,
        )
    }

    if signal_col in df.columns:
        output["signals"] = summarize_signals(
            df=df,
            date_col=date_col,
            signal_col=signal_col,
        )

    return output


def compare_strategy_weights(
    df: pl.DataFrame,
    date_col: str = "date",
    strategy_col: str = "strategy_name",
    weight_col: str = "target_weight",
) -> pl.DataFrame:
    """
    Compare gross and net exposure by strategy and date.
    """

    return (
        df.group_by([date_col, strategy_col])
        .agg(
            pl.col(weight_col).sum().alias("net_exposure"),
            pl.col(weight_col).abs().sum().alias("gross_exposure"),
            (pl.col(weight_col) != 0).sum().alias("active_positions"),
        )
        .sort([date_col, strategy_col])
    )
