from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from src.research.diagnostics import require_columns


DEFAULT_DATE_COLUMN = "date"


def _resolve_optional_date_column(
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


def factor_spread(
    df: pl.DataFrame,
    factor_column: str,
    return_column: str,
    bucket_column: str,
    top_bucket: int = 1,
    bottom_bucket: int | None = None,
) -> float:
    """
    Full-sample top-minus-bottom forward return spread.

    Convention:
    - bucket 1 = strongest factor bucket
    - max bucket = weakest factor bucket
    """

    require_columns(
        df,
        [factor_column, return_column, bucket_column],
        context="Factor spread input",
    )

    resolved_bottom_bucket = bottom_bucket

    if resolved_bottom_bucket is None:
        resolved_bottom_bucket = int(
            df.select(pl.col(bucket_column).max()).item()
        )

    top_return = (
        df.filter(pl.col(bucket_column) == top_bucket)
        .select(pl.col(return_column).mean())
        .item()
    )

    bottom_return = (
        df.filter(pl.col(bucket_column) == resolved_bottom_bucket)
        .select(pl.col(return_column).mean())
        .item()
    )

    if top_return is None or bottom_return is None:
        return float("nan")

    return float(top_return - bottom_return)


def factor_spread_by_date(
    df: pl.DataFrame,
    factor_column: str,
    return_column: str,
    bucket_column: str,
    top_bucket: int = 1,
    bottom_bucket: int | None = None,
    date_column: str = DEFAULT_DATE_COLUMN,
    spread_column: str = "factor_spread",
) -> pl.DataFrame:
    """
    Date-level top-minus-bottom forward return spread.
    """

    require_columns(
        df,
        [date_column, factor_column, return_column, bucket_column],
        context="Factor spread by date input",
    )

    working = df

    if bottom_bucket is None:
        working = working.with_columns(
            pl.col(bucket_column).max().over(date_column).alias("__bottom_bucket")
        )
        bottom_condition = pl.col(bucket_column) == pl.col("__bottom_bucket")
    else:
        bottom_condition = pl.col(bucket_column) == bottom_bucket

    top_condition = pl.col(bucket_column) == top_bucket

    result = (
        working.group_by(date_column)
        .agg(
            pl.col(return_column)
            .filter(top_condition)
            .mean()
            .alias("top_return"),
            pl.col(return_column)
            .filter(bottom_condition)
            .mean()
            .alias("bottom_return"),
            pl.col(factor_column)
            .filter(top_condition)
            .mean()
            .alias("top_factor"),
            pl.col(factor_column)
            .filter(bottom_condition)
            .mean()
            .alias("bottom_factor"),
        )
        .with_columns(
            (pl.col("top_return") - pl.col("bottom_return")).alias(spread_column)
        )
        .sort(date_column)
    )

    return result


def bucket_return_table(
    df: pl.DataFrame,
    factor_column: str,
    return_column: str,
    bucket_column: str,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Return statistics by factor bucket.

    If date_column exists, statistics are calculated by date and bucket.
    Otherwise, statistics are calculated by bucket only.
    """

    resolved_date_column = _resolve_optional_date_column(df, date_column)

    required_columns = [factor_column, return_column, bucket_column]
    group_columns = [bucket_column]

    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)
        group_columns = [resolved_date_column, bucket_column]

    require_columns(
        df,
        required_columns,
        context="Bucket return table input",
    )

    return (
        df.group_by(group_columns)
        .agg(
            pl.len().alias("count"),
            pl.col(return_column).mean().alias("mean_return"),
            pl.col(return_column).median().alias("median_return"),
            pl.col(return_column).std().alias("return_std"),
            pl.col(factor_column).mean().alias("mean_factor"),
        )
        .sort(group_columns)
    )


def universe_stats(
    df: pl.DataFrame,
    columns: Sequence[str],
) -> pl.DataFrame:
    """
    Full-sample universe statistics.
    """

    require_columns(df, columns, context="Universe stats input")

    return df.select(
        [
            pl.col(col).mean().alias(f"{col}_mean")
            for col in columns
        ]
        + [
            pl.col(col).std().alias(f"{col}_std")
            for col in columns
        ]
        + [
            pl.col(col).min().alias(f"{col}_min")
            for col in columns
        ]
        + [
            pl.col(col).max().alias(f"{col}_max")
            for col in columns
        ]
    )


def universe_stats_by_date(
    df: pl.DataFrame,
    columns: Sequence[str],
    date_column: str = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Date-level cross-sectional universe statistics.
    """

    require_columns(
        df,
        [date_column, *columns],
        context="Universe stats by date input",
    )

    expressions: list[pl.Expr] = []

    for col in columns:
        expressions.extend(
            [
                pl.col(col).mean().alias(f"{col}_mean"),
                pl.col(col).std().alias(f"{col}_std"),
                pl.col(col).min().alias(f"{col}_min"),
                pl.col(col).max().alias(f"{col}_max"),
            ]
        )

    return (
        df.group_by(date_column)
        .agg(expressions)
        .sort(date_column)
    )


def dispersion(
    df: pl.DataFrame,
    column: str,
    output_column: str | None = None,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Cross-sectional dispersion.

    If date_column exists, dispersion is calculated by date.
    Otherwise, one full-sample row is returned.
    """

    resolved_date_column = _resolve_optional_date_column(df, date_column)
    output_column = output_column or f"{column}_dispersion"

    required_columns = [column]

    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)

    require_columns(df, required_columns, context="Dispersion input")

    if resolved_date_column is None:
        return df.select(
            pl.col(column).std().alias(output_column)
        )

    return (
        df.group_by(resolved_date_column)
        .agg(
            pl.col(column).std().alias(output_column)
        )
        .sort(resolved_date_column)
    )


def cross_sectional_correlation(
    df: pl.DataFrame,
    left_column: str,
    right_column: str,
    date_column: str | None = DEFAULT_DATE_COLUMN,
    output_column: str = "correlation",
) -> pl.DataFrame:
    """
    Cross-sectional correlation between two columns.

    If date_column exists, correlation is calculated by date.
    Otherwise, one full-sample row is returned.
    """

    resolved_date_column = _resolve_optional_date_column(df, date_column)

    required_columns = [left_column, right_column]

    if resolved_date_column is not None:
        required_columns.append(resolved_date_column)

    require_columns(
        df,
        required_columns,
        context="Cross-sectional correlation input",
    )

    corr_expr = pl.corr(left_column, right_column).alias(output_column)

    if resolved_date_column is None:
        return df.select(corr_expr)

    return (
        df.group_by(resolved_date_column)
        .agg(corr_expr)
        .sort(resolved_date_column)
    )


def information_coefficient_by_date(
    df: pl.DataFrame,
    factor_column: str,
    forward_return_column: str,
    date_column: str = DEFAULT_DATE_COLUMN,
    output_column: str = "information_coefficient",
) -> pl.DataFrame:
    """
    Date-level information coefficient.

    This measures the cross-sectional correlation between a factor and
    future returns.
    """

    return cross_sectional_correlation(
        df=df,
        left_column=factor_column,
        right_column=forward_return_column,
        date_column=date_column,
        output_column=output_column,
    )


def mean_information_coefficient(
    df: pl.DataFrame,
    factor_column: str,
    forward_return_column: str,
    date_column: str = DEFAULT_DATE_COLUMN,
) -> float:
    """
    Average date-level information coefficient.
    """

    ic = information_coefficient_by_date(
        df=df,
        factor_column=factor_column,
        forward_return_column=forward_return_column,
        date_column=date_column,
    )

    value = ic.select(
        pl.col("information_coefficient").mean()
    ).item()

    if value is None:
        return float("nan")

    return float(value)
