from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import polars as pl

from src.strategy_selection.candidates import validate_candidate_data


@dataclass(frozen=True)
class CandidateRankingConfig:
    sort_columns: Sequence[str] = field(default_factory=lambda: ("opportunity_score",))
    descending: bool | Sequence[bool] = True
    weights: Mapping[str, float] | None = None
    top_n: int | None = None
    rank_column: str = "rank"
    weighted_score_column: str = "weighted_score"
    percentile_column: str = "score_percentile"
    add_percentile: bool = False


def _require_columns(df: pl.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in df.columns]

    if missing:
        raise ValueError(f"Missing {label} columns: {missing}")


def _validate_positive_int(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("Weights cannot be empty.")

    total_weight = sum(abs(weight) for weight in weights.values())

    if total_weight <= 0:
        raise ValueError("Total absolute weight must be greater than 0.")

    return {
        column: weight / total_weight
        for column, weight in weights.items()
    }


def rank_candidates(
    df: pl.DataFrame,
    sort_columns: list[str] | None = None,
    descending: bool | list[bool] = True,
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Rank candidates using one or more sort columns.

    Default ranking is by opportunity_score, highest first.
    """
    validate_candidate_data(df)

    columns = sort_columns or ["opportunity_score"]
    _require_columns(df, columns, "ranking")

    return (
        df.sort(columns, descending=descending)
        .with_row_index(rank_column, offset=1)
    )


def rank_by_weighted_score(
    df: pl.DataFrame,
    weights: Mapping[str, float],
    output_column: str = "weighted_score",
    rank_column: str = "rank",
    normalize_weights: bool = False,
) -> pl.DataFrame:
    """
    Create a weighted score from multiple numeric columns, then rank candidates.

    By default, raw weights are used exactly as supplied.

    Example:
    weights = {
        "opportunity_score": 0.50,
        "expected_return": 0.30,
        "confidence": 0.20,
    }
    """
    validate_candidate_data(df)

    active_weights = _normalize_weights(weights) if normalize_weights else dict(weights)

    if not active_weights:
        raise ValueError("Weights cannot be empty.")

    _require_columns(df, list(active_weights), "weighted ranking")

    weighted_expr: pl.Expr | None = None

    for column, weight in active_weights.items():
        expr = pl.col(column).cast(pl.Float64, strict=False).fill_null(0.0) * weight
        weighted_expr = expr if weighted_expr is None else weighted_expr + expr

    if weighted_expr is None:
        raise ValueError("Weights cannot be empty.")

    return (
        df.with_columns(weighted_expr.alias(output_column))
        .sort(output_column, descending=True)
        .with_row_index(rank_column, offset=1)
    )


def rank_by_normalized_weighted_score(
    df: pl.DataFrame,
    weights: Mapping[str, float],
    output_column: str = "weighted_score",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Rank candidates using min-max normalized columns before applying weights.

    This is useful when inputs are on different scales, such as:
    - opportunity_score: 0 to 1
    - expected_value: dollars
    - volume: contracts/shares
    """
    validate_candidate_data(df)

    normalized_weights = _normalize_weights(weights)
    _require_columns(df, list(normalized_weights), "normalized weighted ranking")

    result = df

    normalized_columns: list[str] = []

    for column in normalized_weights:
        normalized_column = f"_{column}_normalized"
        normalized_columns.append(normalized_column)

        values = result.select(
            pl.col(column).cast(pl.Float64, strict=False)
        ).to_series()

        min_value = values.min()
        max_value = values.max()

        if min_value is None or max_value is None:
            result = result.with_columns(pl.lit(0.0).alias(normalized_column))
        elif max_value == min_value:
            result = result.with_columns(pl.lit(1.0).alias(normalized_column))
        else:
            result = result.with_columns(
                (
                    (
                        pl.col(column).cast(pl.Float64, strict=False).fill_null(min_value)
                        - min_value
                    )
                    / (max_value - min_value)
                ).alias(normalized_column)
            )

    weighted_expr: pl.Expr | None = None

    for column, weight in normalized_weights.items():
        normalized_column = f"_{column}_normalized"
        expr = pl.col(normalized_column) * weight
        weighted_expr = expr if weighted_expr is None else weighted_expr + expr

    if weighted_expr is None:
        raise ValueError("Weights cannot be empty.")

    return (
        result.with_columns(weighted_expr.alias(output_column))
        .drop(normalized_columns)
        .sort(output_column, descending=True)
        .with_row_index(rank_column, offset=1)
    )


def top_n_candidates(
    df: pl.DataFrame,
    n: int,
    sort_column: str = "opportunity_score",
    descending: bool = True,
) -> pl.DataFrame:
    """
    Return the top N candidates after sorting by a selected column.
    """
    validate_candidate_data(df)
    _validate_positive_int(n, "n")
    _require_columns(df, [sort_column], "sort")

    return df.sort(sort_column, descending=descending).head(n)


def bottom_n_candidates(
    df: pl.DataFrame,
    n: int,
    sort_column: str = "opportunity_score",
) -> pl.DataFrame:
    """
    Return the bottom N candidates after sorting by a selected column.
    """
    validate_candidate_data(df)
    _validate_positive_int(n, "n")
    _require_columns(df, [sort_column], "sort")

    return df.sort(sort_column, descending=False).head(n)


def add_percentile_rank(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    percentile_column: str = "score_percentile",
) -> pl.DataFrame:
    """
    Add percentile ranking based on a score column.

    Higher scores receive higher percentiles.
    """
    validate_candidate_data(df)
    _require_columns(df, [score_column], "score")

    if df.height == 1:
        return df.with_columns(pl.lit(1.0).alias(percentile_column))

    return df.with_columns(
        (
            pl.col(score_column)
            .cast(pl.Float64, strict=False)
            .rank(method="average")
            / pl.len()
        ).alias(percentile_column)
    )


def add_group_rank(
    df: pl.DataFrame,
    group_column: str,
    score_column: str = "opportunity_score",
    group_rank_column: str = "group_rank",
    descending: bool = True,
) -> pl.DataFrame:
    """
    Add rank within a group, such as strategy, regime, asset_class, or symbol.
    """
    validate_candidate_data(df)
    _require_columns(df, [group_column, score_column], "group ranking")

    return df.with_columns(
        pl.col(score_column)
        .cast(pl.Float64, strict=False)
        .rank(method="dense", descending=descending)
        .over(group_column)
        .cast(pl.Int64)
        .alias(group_rank_column)
    )


def add_score_bucket(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    bucket_column: str = "score_bucket",
) -> pl.DataFrame:
    """
    Label candidates into simple score quality buckets.

    Buckets:
    - elite: >= 90th percentile
    - strong: >= 70th percentile
    - average: >= 40th percentile
    - weak: below 40th percentile
    """
    validate_candidate_data(df)
    _require_columns(df, [score_column], "score")

    with_percentile = add_percentile_rank(
        df,
        score_column=score_column,
        percentile_column="_bucket_percentile",
    )

    return (
        with_percentile.with_columns(
            pl.when(pl.col("_bucket_percentile") >= 0.90)
            .then(pl.lit("elite"))
            .when(pl.col("_bucket_percentile") >= 0.70)
            .then(pl.lit("strong"))
            .when(pl.col("_bucket_percentile") >= 0.40)
            .then(pl.lit("average"))
            .otherwise(pl.lit("weak"))
            .alias(bucket_column)
        )
        .drop("_bucket_percentile")
    )


def rank_selection_pipeline(
    df: pl.DataFrame,
    weights: Mapping[str, float] | None = None,
    top_n: int | None = None,
    *,
    config: CandidateRankingConfig | None = None,
    normalized_weights: bool = False,
) -> pl.DataFrame:
    """
    Full ranking pipeline.

    If weights are supplied, candidates are ranked by weighted_score.
    Otherwise, candidates are ranked by opportunity_score or configured sort columns.
    """
    validate_candidate_data(df)

    cfg = config or CandidateRankingConfig()

    active_weights = weights if weights is not None else cfg.weights
    active_top_n = top_n if top_n is not None else cfg.top_n

    if active_weights is not None:
        if normalized_weights:
            ranked = rank_by_normalized_weighted_score(
                df,
                weights=active_weights,
                output_column=cfg.weighted_score_column,
                rank_column=cfg.rank_column,
            )
        else:
            ranked = rank_by_weighted_score(
                df,
                weights=active_weights,
                output_column=cfg.weighted_score_column,
                rank_column=cfg.rank_column,
            )
    else:
        ranked = rank_candidates(
            df,
            sort_columns=list(cfg.sort_columns),
            descending=cfg.descending,
            rank_column=cfg.rank_column,
        )

    if cfg.add_percentile:
        score_column = (
            cfg.weighted_score_column
            if active_weights is not None
            else list(cfg.sort_columns)[0]
        )

        ranked = add_percentile_rank(
            ranked,
            score_column=score_column,
            percentile_column=cfg.percentile_column,
        )

    if active_top_n is not None:
        _validate_positive_int(active_top_n, "top_n")
        ranked = ranked.head(active_top_n)

    return ranked
