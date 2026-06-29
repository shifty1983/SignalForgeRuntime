from __future__ import annotations

import polars as pl

from src.research.diagnostics import require_columns


DEFAULT_DATE_COLUMN = "date"


def _grouped_expr(
    expr: pl.Expr,
    by: str | None,
) -> pl.Expr:
    if by is None:
        return expr

    return expr.over(by)


def rank_factor(
    df: pl.DataFrame,
    factor_column: str,
    ascending: bool = False,
    rank_column: str | None = None,
    date_column: str | None = DEFAULT_DATE_COLUMN,
    method: str = "ordinal",
) -> pl.DataFrame:
    """
    Rank a factor cross-sectionally.

    By default, ranks are calculated within each date.
    Bucket/rank convention:
    - rank 1 = strongest factor value when ascending=False
    - rank 1 = lowest factor value when ascending=True
    """

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Factor ranking input")

    rank_column = rank_column or f"{factor_column}_rank"

    rank_expr = pl.col(factor_column).rank(
        method=method,
        descending=not ascending,
    )

    return df.with_columns(
        _grouped_expr(rank_expr, date_column).alias(rank_column)
    )


def percentile_rank(
    df: pl.DataFrame,
    factor_column: str,
    ascending: bool = False,
    percentile_column: str | None = None,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Convert factor values into percentile ranks within each date.

    Strongest names receive values closest to 1.0.
    Weakest names receive values closest to 0.0.
    """

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Percentile ranking input")

    percentile_column = percentile_column or f"{factor_column}_percentile"

    ranked = rank_factor(
        df=df,
        factor_column=factor_column,
        ascending=ascending,
        rank_column="__rank",
        date_column=date_column,
    )

    count_expr = pl.col(factor_column).count()

    if date_column is not None:
        count_expr = count_expr.over(date_column)

    return (
        ranked.with_columns(
            pl.when(pl.col(factor_column).is_null())
            .then(None)
            .when(count_expr <= 1)
            .then(1.0)
            .otherwise(1.0 - ((pl.col("__rank") - 1) / (count_expr - 1)))
            .alias(percentile_column)
        )
        .drop("__rank")
    )


def quantile_buckets(
    df: pl.DataFrame,
    factor_column: str,
    n_buckets: int = 5,
    bucket_column: str | None = None,
    ascending: bool = False,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Assign securities into quantile buckets within each date.

    Convention:
    - bucket 1 = strongest
    - bucket n_buckets = weakest
    """

    if n_buckets <= 0:
        raise ValueError("n_buckets must be greater than zero.")

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Quantile bucket input")

    bucket_column = bucket_column or f"{factor_column}_bucket"

    rank_expr = pl.col(factor_column).rank(
        method="ordinal",
        descending=not ascending,
    )

    count_expr = pl.col(factor_column).count()

    if date_column is not None:
        rank_expr = rank_expr.over(date_column)
        count_expr = count_expr.over(date_column)

    ranked = df.with_columns(
        rank_expr.alias("__rank"),
        count_expr.alias("__count"),
    )

    bucket_expr = (
        (((pl.col("__rank") - 1) * n_buckets / pl.col("__count"))
        .floor()
        .cast(pl.Int64)
        + 1)
        .clip(1, n_buckets)
    )

    return (
        ranked.with_columns(
            pl.when(pl.col(factor_column).is_null())
            .then(None)
            .otherwise(bucket_expr)
            .alias(bucket_column)
        )
        .drop(["__rank", "__count"])
    )


def top_n(
    df: pl.DataFrame,
    factor_column: str,
    n: int = 10,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Select top N securities by factor value.

    If date_column is provided, selects top N per date.
    """

    if n <= 0:
        raise ValueError("n must be greater than zero.")

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Top-N selection input")

    ranked = rank_factor(
        df=df,
        factor_column=factor_column,
        ascending=False,
        rank_column="__rank",
        date_column=date_column,
    )

    result = (
        ranked.filter(
            pl.col(factor_column).is_not_null()
            & (pl.col("__rank") <= n)
        )
        .drop("__rank")
    )

    if date_column is not None:
        return result.sort([date_column, factor_column], descending=[False, True])

    return result.sort(factor_column, descending=True)


def bottom_n(
    df: pl.DataFrame,
    factor_column: str,
    n: int = 10,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Select bottom N securities by factor value.

    If date_column is provided, selects bottom N per date.
    """

    if n <= 0:
        raise ValueError("n must be greater than zero.")

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Bottom-N selection input")

    ranked = rank_factor(
        df=df,
        factor_column=factor_column,
        ascending=True,
        rank_column="__rank",
        date_column=date_column,
    )

    result = (
        ranked.filter(
            pl.col(factor_column).is_not_null()
            & (pl.col("__rank") <= n)
        )
        .drop("__rank")
    )

    if date_column is not None:
        return result.sort([date_column, factor_column], descending=[False, False])

    return result.sort(factor_column, descending=False)


def long_short_candidates(
    df: pl.DataFrame,
    bucket_column: str,
    long_bucket: int = 1,
    short_bucket: int | None = None,
    candidate_column: str = "candidate",
) -> pl.DataFrame:
    """
    Label long, short, and neutral candidates from bucket assignments.
    """

    require_columns(df, [bucket_column], context="Long/short candidate input")

    short_bucket = short_bucket or int(df[bucket_column].max())

    return df.with_columns(
        pl.when(pl.col(bucket_column) == long_bucket)
        .then(pl.lit("long"))
        .when(pl.col(bucket_column) == short_bucket)
        .then(pl.lit("short"))
        .otherwise(pl.lit("neutral"))
        .alias(candidate_column)
    )
