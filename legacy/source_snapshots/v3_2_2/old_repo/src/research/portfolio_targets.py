from __future__ import annotations

import polars as pl

from src.research.diagnostics import require_columns


DEFAULT_DATE_COLUMN = "date"


def _resolve_date_column(
    df: pl.DataFrame,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> str | None:
    if date_column is None:
        return None

    if date_column in df.columns:
        return date_column

    if date_column == DEFAULT_DATE_COLUMN:
        return None

    raise ValueError(f"Missing date column: {date_column}")


def _grouped_sum_expr(
    expr: pl.Expr,
    date_column: str | None,
) -> pl.Expr:
    if date_column is None:
        return expr.sum()

    return expr.sum().over(date_column)


def equal_weight_targets(
    df: pl.DataFrame,
    signal_column: str = "signal",
    weight_column: str = "target_weight",
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Equal-weight portfolio construction.

    If a date column exists, weights are calculated independently per date.

    Convention:
    - signal 1 receives positive weight
    - signal -1 receives negative weight
    - signal 0 receives zero weight
    - gross exposure sums to 1.0 per date when active signals exist
    """

    resolved_date_column = _resolve_date_column(df, date_column)

    required_columns = [signal_column]
    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)

    require_columns(df, required_columns, context="Equal-weight target input")

    active_count_expr = _grouped_sum_expr(
        (pl.col(signal_column) != 0).cast(pl.Int64),
        resolved_date_column,
    )

    result = df.with_columns(
        active_count_expr.alias("__active_count")
    )

    return (
        result.with_columns(
            pl.when(
                (pl.col(signal_column) != 0)
                & (pl.col("__active_count") > 0)
            )
            .then(pl.col(signal_column).cast(pl.Float64) / pl.col("__active_count"))
            .otherwise(0.0)
            .alias(weight_column)
        )
        .drop("__active_count")
    )


def side_equal_weight_targets(
    df: pl.DataFrame,
    signal_column: str = "signal",
    weight_column: str = "target_weight",
    long_gross: float = 0.5,
    short_gross: float = 0.5,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Equal-weight long and short books separately.

    Example:
    - long_gross=0.5
    - short_gross=0.5
    - total gross exposure = 1.0
    - net exposure is approximately 0 when both sides exist
    """

    if long_gross < 0:
        raise ValueError("long_gross must be non-negative.")

    if short_gross < 0:
        raise ValueError("short_gross must be non-negative.")

    resolved_date_column = _resolve_date_column(df, date_column)

    required_columns = [signal_column]
    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)

    require_columns(df, required_columns, context="Side equal-weight target input")

    long_count_expr = _grouped_sum_expr(
        (pl.col(signal_column) > 0).cast(pl.Int64),
        resolved_date_column,
    )

    short_count_expr = _grouped_sum_expr(
        (pl.col(signal_column) < 0).cast(pl.Int64),
        resolved_date_column,
    )

    result = df.with_columns(
        long_count_expr.alias("__long_count"),
        short_count_expr.alias("__short_count"),
    )

    return (
        result.with_columns(
            pl.when(
                (pl.col(signal_column) > 0)
                & (pl.col("__long_count") > 0)
            )
            .then(long_gross / pl.col("__long_count"))
            .when(
                (pl.col(signal_column) < 0)
                & (pl.col("__short_count") > 0)
            )
            .then(-short_gross / pl.col("__short_count"))
            .otherwise(0.0)
            .alias(weight_column)
        )
        .drop(["__long_count", "__short_count"])
    )


def normalize_weights(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    target_gross: float = 1.0,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Normalize weights so total absolute exposure equals target_gross.

    If a date column exists, normalization is performed per date.
    """

    if target_gross < 0:
        raise ValueError("target_gross must be non-negative.")

    resolved_date_column = _resolve_date_column(df, date_column)

    required_columns = [weight_column]
    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)

    require_columns(df, required_columns, context="Weight normalization input")

    gross_expr = _grouped_sum_expr(
        pl.col(weight_column).abs(),
        resolved_date_column,
    )

    result = df.with_columns(
        gross_expr.alias("__gross_exposure")
    )

    return (
        result.with_columns(
            pl.when(pl.col("__gross_exposure") > 0)
            .then(pl.col(weight_column) / pl.col("__gross_exposure") * target_gross)
            .otherwise(0.0)
            .alias(weight_column)
        )
        .drop("__gross_exposure")
    )


def cap_weights(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    max_weight: float = 0.10,
) -> pl.DataFrame:
    """
    Cap individual position weights.

    The cap is symmetric:
    - positive weights capped at max_weight
    - negative weights capped at -max_weight
    """

    if max_weight <= 0:
        raise ValueError("max_weight must be greater than zero.")

    require_columns(df, [weight_column], context="Weight cap input")

    return df.with_columns(
        pl.col(weight_column)
        .clip(-max_weight, max_weight)
        .alias(weight_column)
    )


def capped_normalized_weights(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    max_weight: float = 0.10,
    target_gross: float = 1.0,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Cap weights, then renormalize gross exposure.

    Useful as a simple portfolio constraint pass.
    """

    capped = cap_weights(
        df=df,
        weight_column=weight_column,
        max_weight=max_weight,
    )

    return normalize_weights(
        df=capped,
        weight_column=weight_column,
        target_gross=target_gross,
        date_column=date_column,
    )


def gross_exposure(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
) -> float:
    """
    Total absolute exposure across the full DataFrame.
    """

    require_columns(df, [weight_column], context="Gross exposure input")

    return float(
        df.select(pl.col(weight_column).abs().sum()).item()
    )


def net_exposure(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
) -> float:
    """
    Net exposure across the full DataFrame.
    """

    require_columns(df, [weight_column], context="Net exposure input")

    return float(
        df.select(pl.col(weight_column).sum()).item()
    )


def exposure_by_date(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    date_column: str = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Gross and net exposure by date.
    """

    require_columns(
        df,
        [date_column, weight_column],
        context="Exposure by date input",
    )

    return (
        df.group_by(date_column)
        .agg(
            pl.col(weight_column).abs().sum().alias("gross_exposure"),
            pl.col(weight_column).sum().alias("net_exposure"),
            pl.when(pl.col(weight_column) > 0)
            .then(pl.col(weight_column))
            .otherwise(0.0)
            .sum()
            .alias("long_exposure"),
            pl.when(pl.col(weight_column) < 0)
            .then(pl.col(weight_column).abs())
            .otherwise(0.0)
            .sum()
            .alias("short_exposure"),
            (pl.col(weight_column) != 0).sum().alias("active_positions"),
            (pl.col(weight_column) > 0).sum().alias("long_positions"),
            (pl.col(weight_column) < 0).sum().alias("short_positions"),
        )
        .sort(date_column)
    )


def exposure_summary(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Exposure summary.

    If date_column exists, returns date-level exposure.
    Otherwise returns one full-sample exposure row.
    """

    resolved_date_column = _resolve_date_column(df, date_column)

    require_columns(df, [weight_column], context="Exposure summary input")

    if resolved_date_column is not None:
        return exposure_by_date(
            df=df,
            weight_column=weight_column,
            date_column=resolved_date_column,
        )

    return df.select(
        pl.col(weight_column).abs().sum().alias("gross_exposure"),
        pl.col(weight_column).sum().alias("net_exposure"),
        pl.when(pl.col(weight_column) > 0)
        .then(pl.col(weight_column))
        .otherwise(0.0)
        .sum()
        .alias("long_exposure"),
        pl.when(pl.col(weight_column) < 0)
        .then(pl.col(weight_column).abs())
        .otherwise(0.0)
        .sum()
        .alias("short_exposure"),
        (pl.col(weight_column) != 0).sum().alias("active_positions"),
        (pl.col(weight_column) > 0).sum().alias("long_positions"),
        (pl.col(weight_column) < 0).sum().alias("short_positions"),
    )
