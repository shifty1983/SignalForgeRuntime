from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl

from src.research.diagnostics import require_columns
from src.research.ranking import percentile_rank, quantile_buckets, rank_factor


DEFAULT_DATE_COLUMN = "date"


def _resolve_weights(
    columns: Sequence[str],
    weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    if not columns:
        raise ValueError("At least one factor column is required.")

    if weights is None:
        equal_weight = 1.0 / len(columns)
        return {col: equal_weight for col in columns}

    missing_weights = [col for col in columns if col not in weights]
    extra_weights = [col for col in weights if col not in columns]

    if missing_weights:
        raise ValueError(f"Missing weights for columns: {missing_weights}")

    if extra_weights:
        raise ValueError(f"Weights provided for unknown columns: {extra_weights}")

    total_abs_weight = sum(abs(weight) for weight in weights.values())

    if total_abs_weight == 0:
        raise ValueError("Total absolute weight cannot be zero.")

    return {
        col: float(weight) / total_abs_weight
        for col, weight in weights.items()
    }

def _derived_weights(
    source_columns: Sequence[str],
    derived_columns: Sequence[str],
    weights: Mapping[str, float] | None,
) -> dict[str, float] | None:
    if weights is None:
        return None

    if set(weights).issubset(set(derived_columns)):
        return dict(weights)

    missing_weights = [col for col in source_columns if col not in weights]
    extra_weights = [col for col in weights if col not in source_columns]

    if missing_weights:
        raise ValueError(f"Missing weights for columns: {missing_weights}")

    if extra_weights:
        raise ValueError(f"Weights provided for unknown columns: {extra_weights}")

    return {
        derived_col: float(weights[source_col])
        for source_col, derived_col in zip(source_columns, derived_columns)
    }

def zscore_factors(
    df: pl.DataFrame,
    factor_columns: Sequence[str],
    date_column: str | None = DEFAULT_DATE_COLUMN,
    suffix: str = "_zscore",
) -> pl.DataFrame:
    """
    Cross-sectionally z-score factor columns.

    By default, z-scores are calculated within each date.
    """

    required_columns = list(factor_columns)
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Z-score factor input")

    expressions: list[pl.Expr] = []

    for col in factor_columns:
        mean_expr = pl.col(col).mean()
        std_expr = pl.col(col).std()

        if date_column is not None:
            mean_expr = mean_expr.over(date_column)
            std_expr = std_expr.over(date_column)

        expressions.append(
            pl.when(
                pl.col(col).is_null()
                | std_expr.is_null()
                | (std_expr == 0)
            )
            .then(None)
            .otherwise((pl.col(col) - mean_expr) / std_expr)
            .alias(f"{col}{suffix}")
        )

    return df.with_columns(expressions)


def composite_score(
    df: pl.DataFrame,
    score_columns: Sequence[str],
    weights: Mapping[str, float] | None = None,
    output_column: str = "composite_score",
    fill_null_score: float | None = None,
) -> pl.DataFrame:
    """
    Build a weighted composite score from existing score columns.

    Best practice:
    - use percentile columns or z-score columns as inputs
    - keep all input scores aligned so higher = better
    """

    require_columns(df, score_columns, context="Composite score input")

    resolved_weights = _resolve_weights(score_columns, weights)

    expr: pl.Expr | None = None

    for col, weight in resolved_weights.items():
        col_expr = pl.col(col)

        if fill_null_score is not None:
            col_expr = col_expr.fill_null(fill_null_score)

        weighted_expr = col_expr * weight
        expr = weighted_expr if expr is None else expr + weighted_expr

    if expr is None:
        raise ValueError("Unable to build composite expression.")

    return df.with_columns(expr.alias(output_column))


def percentile_composite(
    df: pl.DataFrame,
    factor_columns: Sequence[str],
    weights: Mapping[str, float] | None = None,
    output_column: str = "composite_score",
    date_column: str | None = DEFAULT_DATE_COLUMN,
    percentile_suffix: str = "_percentile",
) -> pl.DataFrame:
    """
    Convert raw factor columns into percentile ranks, then combine them.

    Convention:
    - factor inputs must already be oriented so higher = better
    - percentile values closer to 1.0 are stronger
    """

    required_columns = list(factor_columns)
    if date_column is not None:
        required_columns.append(date_column)

    require_columns(df, required_columns, context="Percentile composite input")

    result = df
    percentile_columns: list[str] = []

    for col in factor_columns:
        percentile_col = f"{col}{percentile_suffix}"
        percentile_columns.append(percentile_col)

        result = percentile_rank(
            df=result,
            factor_column=col,
            ascending=False,
            percentile_column=percentile_col,
            date_column=date_column,
        )

    return composite_score(
        df=result,
        score_columns=percentile_columns,
        weights=_derived_weights(factor_columns, percentile_columns, weights),
        output_column=output_column,
        fill_null_score=None,
    )


def zscore_composite(
    df: pl.DataFrame,
    factor_columns: Sequence[str],
    weights: Mapping[str, float] | None = None,
    output_column: str = "composite_score",
    date_column: str | None = DEFAULT_DATE_COLUMN,
    zscore_suffix: str = "_zscore",
) -> pl.DataFrame:
    """
    Z-score raw factor columns, then combine them into a composite score.

    Convention:
    - factor inputs must already be oriented so higher = better
    """

    result = zscore_factors(
        df=df,
        factor_columns=factor_columns,
        date_column=date_column,
        suffix=zscore_suffix,
    )

    zscore_columns = [f"{col}{zscore_suffix}" for col in factor_columns]

    return composite_score(
        df=result,
        score_columns=zscore_columns,
        weights=_derived_weights(factor_columns, zscore_columns, weights),
        output_column=output_column,
        fill_null_score=None,
    )


def rank_composite(
    df: pl.DataFrame,
    composite_column: str = "composite_score",
    rank_column: str = "composite_rank",
    bucket_column: str = "composite_bucket",
    n_buckets: int = 5,
    date_column: str | None = DEFAULT_DATE_COLUMN,
) -> pl.DataFrame:
    """
    Rank and bucket a composite score.

    Convention:
    - rank 1 = strongest composite score
    - bucket 1 = strongest composite bucket
    """

    result = rank_factor(
        df=df,
        factor_column=composite_column,
        ascending=False,
        rank_column=rank_column,
        date_column=date_column,
    )

    return quantile_buckets(
        df=result,
        factor_column=composite_column,
        n_buckets=n_buckets,
        bucket_column=bucket_column,
        ascending=False,
        date_column=date_column,
    )
