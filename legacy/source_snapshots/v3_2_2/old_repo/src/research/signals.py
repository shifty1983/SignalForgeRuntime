from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Callable

import polars as pl

from src.research.diagnostics import require_columns


DEFAULT_DATE_COLUMN = "date"


def _max_expr(
    column: str,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.Expr:
    expr = pl.col(column).max()

    if date_column is not None:
        expr = expr.over(date_column)

    return expr


def long_short_signal(
    df: pl.DataFrame,
    bucket_column: str,
    long_bucket: int = 1,
    short_bucket: int | None = None,
    signal_column: str = "signal",
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Convert factor buckets into long/short signals.

    Convention:
    - bucket 1 = strongest
    - max bucket = weakest
    - long = 1
    - short = -1
    - neutral = 0

    If short_bucket is None, the weakest bucket is determined per date.
    """

    required_columns = [bucket_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Long/short signal input")

    short_bucket_expr = (
        pl.lit(short_bucket)
        if short_bucket is not None
        else _max_expr(bucket_column, date_column)
    )

    return df.with_columns(
        pl.when(pl.col(bucket_column).is_null())
        .then(pl.lit(0))
        .when(pl.col(bucket_column) == long_bucket)
        .then(pl.lit(1))
        .when(pl.col(bucket_column) == short_bucket_expr)
        .then(pl.lit(-1))
        .otherwise(pl.lit(0))
        .alias(signal_column)
    )


def long_only_signal(
    df: pl.DataFrame,
    bucket_column: str,
    long_bucket: int = 1,
    signal_column: str = "signal",
) -> pl.DataFrame:
    """
    Convert a bucket assignment into a long-only signal.
    """

    require_columns(df, [bucket_column], context="Long-only signal input")

    return df.with_columns(
        pl.when(pl.col(bucket_column) == long_bucket)
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias(signal_column)
    )


def threshold_signal(
    df: pl.DataFrame,
    factor_column: str,
    long_threshold: float,
    short_threshold: float | None = None,
    signal_column: str = "signal",
) -> pl.DataFrame:
    """
    Convert factor values into threshold-based signals.

    Assumption:
    - higher factor values are better
    """

    require_columns(df, [factor_column], context="Threshold signal input")

    expr = (
        pl.when(pl.col(factor_column).is_null())
        .then(pl.lit(0))
        .when(pl.col(factor_column) >= long_threshold)
        .then(pl.lit(1))
    )

    if short_threshold is not None:
        expr = expr.when(pl.col(factor_column) <= short_threshold).then(pl.lit(-1))

    return df.with_columns(
        expr.otherwise(pl.lit(0)).alias(signal_column)
    )


def percentile_signal(
    df: pl.DataFrame,
    percentile_column: str,
    long_percentile: float = 0.8,
    short_percentile: float | None = 0.2,
    signal_column: str = "signal",
) -> pl.DataFrame:
    """
    Convert percentile scores into tradeable signals.

    Convention:
    - percentile closer to 1.0 = stronger
    - percentile closer to 0.0 = weaker
    """

    if not 0 <= long_percentile <= 1:
        raise ValueError("long_percentile must be between 0 and 1.")

    if short_percentile is not None and not 0 <= short_percentile <= 1:
        raise ValueError("short_percentile must be between 0 and 1.")

    return threshold_signal(
        df=df,
        factor_column=percentile_column,
        long_threshold=long_percentile,
        short_threshold=short_percentile,
        signal_column=signal_column,
    )


def rank_signal(
    df: pl.DataFrame,
    rank_column: str,
    max_long_rank: int,
    max_short_rank: int | None = None,
    signal_column: str = "signal",
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Convert rank values into signals.

    Convention:
    - rank 1 = strongest
    - long names have rank <= max_long_rank
    - short names are the weakest max_short_rank names per date
    """

    if max_long_rank <= 0:
        raise ValueError("max_long_rank must be greater than zero.")

    if max_short_rank is not None and max_short_rank <= 0:
        raise ValueError("max_short_rank must be greater than zero.")

    required_columns = [rank_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Rank signal input")

    expr = (
        pl.when(pl.col(rank_column).is_null())
        .then(pl.lit(0))
        .when(pl.col(rank_column) <= max_long_rank)
        .then(pl.lit(1))
    )

    if max_short_rank is not None:
        max_rank = _max_expr(rank_column, date_column)
        short_cutoff = max_rank - max_short_rank + 1

        expr = expr.when(pl.col(rank_column) >= short_cutoff).then(pl.lit(-1))

    return df.with_columns(
        expr.otherwise(pl.lit(0)).alias(signal_column)
    )


def candidate_signal(
    df: pl.DataFrame,
    candidate_column: str = "candidate",
    signal_column: str = "signal",
    long_labels: Sequence[str] = ("long",),
    short_labels: Sequence[str] = ("short",),
) -> pl.DataFrame:
    """
    Convert text candidate labels into numeric signals.
    """

    require_columns(df, [candidate_column], context="Candidate signal input")

    long_labels_normalized = [label.lower() for label in long_labels]
    short_labels_normalized = [label.lower() for label in short_labels]

    label_expr = pl.col(candidate_column).cast(pl.Utf8).str.to_lowercase()

    return df.with_columns(
        pl.when(label_expr.is_in(long_labels_normalized))
        .then(pl.lit(1))
        .when(label_expr.is_in(short_labels_normalized))
        .then(pl.lit(-1))
        .otherwise(pl.lit(0))
        .alias(signal_column)
    )

SignalRule = Callable[[pl.DataFrame], pl.DataFrame]


def zscore_signal(
    df: pl.DataFrame,
    factor_column: str,
    long_zscore: float = 1.0,
    short_zscore: float | None = -1.0,
    signal_column: str = "signal",
    zscore_column: str | None = None,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Convert factor values into z-score based signals.

    If date_column is provided, z-scores are calculated cross-sectionally by date.
    """

    if short_zscore is not None and short_zscore > long_zscore:
        raise ValueError("short_zscore must be less than or equal to long_zscore.")

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Z-score signal input")

    zscore_column = zscore_column or f"{factor_column}_zscore"

    mean_expr = pl.col(factor_column).mean()
    std_expr = pl.col(factor_column).std()

    if date_column is not None:
        mean_expr = mean_expr.over(date_column)
        std_expr = std_expr.over(date_column)

    zscore_expr = (
        pl.when(
            pl.col(factor_column).is_null()
            | std_expr.is_null()
            | (std_expr <= 0)
        )
        .then(None)
        .otherwise((pl.col(factor_column) - mean_expr) / std_expr)
        .alias(zscore_column)
    )

    result = df.with_columns(zscore_expr)

    return threshold_signal(
        df=result,
        factor_column=zscore_column,
        long_threshold=long_zscore,
        short_threshold=short_zscore,
        signal_column=signal_column,
    )


def factor_percentile_signal(
    df: pl.DataFrame,
    factor_column: str,
    long_percentile: float = 0.8,
    short_percentile: float | None = 0.2,
    signal_column: str = "signal",
    percentile_column: str | None = None,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Calculate percentile ranks from a factor column and convert them into signals.

    Higher factor values are treated as stronger.
    """

    if not 0 <= long_percentile <= 1:
        raise ValueError("long_percentile must be between 0 and 1.")

    if short_percentile is not None:
        if not 0 <= short_percentile <= 1:
            raise ValueError("short_percentile must be between 0 and 1.")

        if short_percentile > long_percentile:
            raise ValueError(
                "short_percentile must be less than or equal to long_percentile."
            )

    required_columns = [factor_column]
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Factor percentile signal input")

    percentile_column = percentile_column or f"{factor_column}_percentile"

    rank_expr = pl.col(factor_column).rank(method="average")
    count_expr = pl.len()

    if date_column is not None:
        rank_expr = rank_expr.over(date_column)
        count_expr = count_expr.over(date_column)

    percentile_expr = (
        pl.when(pl.col(factor_column).is_null() | (count_expr <= 1))
        .then(None)
        .otherwise((rank_expr - 1) / (count_expr - 1))
        .alias(percentile_column)
    )

    result = df.with_columns(percentile_expr)

    return percentile_signal(
        df=result,
        percentile_column=percentile_column,
        long_percentile=long_percentile,
        short_percentile=short_percentile,
        signal_column=signal_column,
    )


def consensus_signal(
    df: pl.DataFrame,
    signal_columns: Sequence[str],
    min_agreement: int = 2,
    signal_column: str = "consensus_signal",
) -> pl.DataFrame:
    """
    Combine multiple signal columns into one consensus signal.

    Long consensus requires at least min_agreement positive votes.
    Short consensus requires at least min_agreement negative votes.
    Otherwise the signal is neutral.
    """

    if min_agreement <= 0:
        raise ValueError("min_agreement must be greater than zero.")

    if not signal_columns:
        raise ValueError("signal_columns must contain at least one column.")

    require_columns(
        df,
        list(signal_columns),
        context="Consensus signal input",
    )

    positive_votes = pl.sum_horizontal(
        [(pl.col(column) > 0).cast(pl.Int64) for column in signal_columns]
    )

    negative_votes = pl.sum_horizontal(
        [(pl.col(column) < 0).cast(pl.Int64) for column in signal_columns]
    )

    return df.with_columns(
        pl.when((positive_votes >= min_agreement) & (positive_votes > negative_votes))
        .then(pl.lit(1))
        .when((negative_votes >= min_agreement) & (negative_votes > positive_votes))
        .then(pl.lit(-1))
        .otherwise(pl.lit(0))
        .alias(signal_column)
    )


def apply_signal_rules(
    df: pl.DataFrame,
    rules: Sequence[SignalRule],
) -> pl.DataFrame:
    """
    Apply multiple signal rules to a research panel.
    """

    result = df

    for rule in rules:
        result = rule(result)

    return result


def default_signal_rules() -> list[SignalRule]:
    """
    Default reusable signal rule set for expanded research evaluation.

    These consume factor columns and create signal columns.
    """

    return [
        partial(
            zscore_signal,
            factor_column="momentum_factor",
            signal_column="momentum_signal",
        ),
        partial(
            zscore_signal,
            factor_column="reversal_factor",
            signal_column="reversal_signal",
        ),
        partial(
            zscore_signal,
            factor_column="low_volatility_factor",
            signal_column="low_volatility_signal",
        ),
        partial(
            threshold_signal,
            factor_column="trend_factor",
            long_threshold=0.0,
            short_threshold=0.0,
            signal_column="trend_signal",
        ),
        partial(
            zscore_signal,
            factor_column="risk_adjusted_momentum_factor",
            signal_column="risk_adjusted_momentum_signal",
        ),
        partial(
            threshold_signal,
            factor_column="relative_strength_factor",
            long_threshold=0.0,
            short_threshold=0.0,
            signal_column="relative_strength_signal",
        ),
        partial(
            factor_percentile_signal,
            factor_column="liquidity_factor",
            long_percentile=0.8,
            short_percentile=0.2,
            signal_column="liquidity_signal",
        ),
        partial(
            consensus_signal,
            signal_columns=[
                "momentum_signal",
                "reversal_signal",
                "low_volatility_signal",
                "trend_signal",
                "risk_adjusted_momentum_signal",
                "relative_strength_signal",
                "liquidity_signal",
            ],
            min_agreement=3,
            signal_column="research_consensus_signal",
        ),
    ]

def active_signals(
    df: pl.DataFrame,
    signal_column: str = "signal",
) -> pl.DataFrame:
    """
    Return only active long or short signals.
    """

    require_columns(df, [signal_column], context="Active signal input")

    return df.filter(pl.col(signal_column) != 0)


def signal_summary(
    df: pl.DataFrame,
    signal_column: str = "signal",
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Count long, short, and neutral signals.

    If date_column is provided, counts are calculated by date.
    """

    required_columns = [signal_column]
    group_columns = [signal_column]

    if date_column is not None:
        required_columns.append(date_column)
        group_columns = [date_column, signal_column]

    require_columns(df, required_columns, context="Signal summary input")

    return (
        df.group_by(group_columns)
        .len(name="count")
        .sort(group_columns)
    )
