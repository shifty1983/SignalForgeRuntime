from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import polars as pl

from src.research.composites import (
    percentile_composite,
    rank_composite,
    zscore_composite,
)
from src.research.diagnostics import require_columns, validate_research_panel
from src.research.factor import Factor
from src.research.factor_library import apply_factors
from src.research.portfolio_targets import (
    equal_weight_targets,
    exposure_summary,
    normalize_weights,
    side_equal_weight_targets,
)
from src.research.signals import (
    long_only_signal,
    long_short_signal,
    percentile_signal,
    rank_signal,
)


CompositeMethod = Literal["percentile", "zscore", "single"]
SignalMethod = Literal["long_short_bucket", "long_only_bucket", "percentile", "rank"]
TargetMethod = Literal["equal_weight", "side_equal_weight", "none"]


@dataclass(frozen=True)
class ResearchPipelineConfig:
    date_column: str = "date"
    symbol_column: str = "symbol"

    factors: Sequence[Factor] = ()
    factor_columns: Sequence[str] = ()

    composite_method: CompositeMethod = "percentile"
    composite_weights: Mapping[str, float] | None = None
    composite_column: str = "composite_score"

    rank_column: str = "composite_rank"
    bucket_column: str = "composite_bucket"
    n_buckets: int = 5

    signal_method: SignalMethod = "long_short_bucket"
    signal_column: str = "signal"
    long_bucket: int = 1
    short_bucket: int | None = None
    long_percentile: float = 0.8
    short_percentile: float | None = 0.2
    max_long_rank: int = 10
    max_short_rank: int | None = 10

    target_method: TargetMethod = "side_equal_weight"
    weight_column: str = "target_weight"
    target_gross: float = 1.0
    long_gross: float = 0.5
    short_gross: float = 0.5

    validate_input: bool = True


def _resolve_factor_columns(config: ResearchPipelineConfig) -> list[str]:
    if config.factor_columns:
        return list(config.factor_columns)

    if config.factors:
        return [factor.output_column for factor in config.factors]

    raise ValueError(
        "ResearchPipelineConfig requires either factor_columns or factors."
    )


def _build_composite(
    df: pl.DataFrame,
    factor_columns: Sequence[str],
    config: ResearchPipelineConfig,
) -> pl.DataFrame:
    if config.composite_method == "percentile":
        return percentile_composite(
            df=df,
            factor_columns=factor_columns,
            weights=config.composite_weights,
            output_column=config.composite_column,
            date_column=config.date_column,
        )

    if config.composite_method == "zscore":
        return zscore_composite(
            df=df,
            factor_columns=factor_columns,
            weights=config.composite_weights,
            output_column=config.composite_column,
            date_column=config.date_column,
        )

    if config.composite_method == "single":
        if len(factor_columns) != 1:
            raise ValueError(
                "composite_method='single' requires exactly one factor column."
            )

        return df.with_columns(
            pl.col(factor_columns[0]).alias(config.composite_column)
        )

    raise ValueError(f"Unknown composite method: {config.composite_method}")


def _build_signal(
    df: pl.DataFrame,
    config: ResearchPipelineConfig,
) -> pl.DataFrame:
    if config.signal_method == "long_short_bucket":
        return long_short_signal(
            df=df,
            bucket_column=config.bucket_column,
            long_bucket=config.long_bucket,
            short_bucket=config.short_bucket,
            signal_column=config.signal_column,
            date_column=config.date_column,
        )

    if config.signal_method == "long_only_bucket":
        return long_only_signal(
            df=df,
            bucket_column=config.bucket_column,
            long_bucket=config.long_bucket,
            signal_column=config.signal_column,
        )

    if config.signal_method == "percentile":
        if config.composite_method != "percentile":
            raise ValueError(
                "signal_method='percentile' should be used with "
                "composite_method='percentile'."
            )

        return percentile_signal(
            df=df,
            percentile_column=config.composite_column,
            long_percentile=config.long_percentile,
            short_percentile=config.short_percentile,
            signal_column=config.signal_column,
        )

    if config.signal_method == "rank":
        return rank_signal(
            df=df,
            rank_column=config.rank_column,
            max_long_rank=config.max_long_rank,
            max_short_rank=config.max_short_rank,
            signal_column=config.signal_column,
            date_column=config.date_column,
        )

    raise ValueError(f"Unknown signal method: {config.signal_method}")


def _build_targets(
    df: pl.DataFrame,
    config: ResearchPipelineConfig,
) -> pl.DataFrame:
    if config.target_method == "none":
        return df

    if config.target_method == "equal_weight":
        result = equal_weight_targets(
            df=df,
            signal_column=config.signal_column,
            weight_column=config.weight_column,
            date_column=config.date_column,
        )

        if config.target_gross != 1.0:
            result = normalize_weights(
                df=result,
                weight_column=config.weight_column,
                target_gross=config.target_gross,
                date_column=config.date_column,
            )

        return result

    if config.target_method == "side_equal_weight":
        return side_equal_weight_targets(
            df=df,
            signal_column=config.signal_column,
            weight_column=config.weight_column,
            long_gross=config.long_gross,
            short_gross=config.short_gross,
            date_column=config.date_column,
        )

    raise ValueError(f"Unknown target method: {config.target_method}")


def run_research_pipeline(
    df: pl.DataFrame,
    config: ResearchPipelineConfig,
) -> pl.DataFrame:
    """
    Run a complete research pipeline:

    1. validate panel
    2. apply factor definitions
    3. build composite score
    4. rank and bucket composite
    5. convert buckets/ranks/scores into signals
    6. convert signals into target weights
    """

    if config.validate_input:
        validate_research_panel(
            df=df,
            date_column=config.date_column,
            symbol_column=config.symbol_column,
            allow_duplicate_keys=False,
        )

    result = df

    if config.factors:
        result = apply_factors(
            df=result,
            factors=list(config.factors),
        )

    factor_columns = _resolve_factor_columns(config)

    required_columns = [
        config.date_column,
        config.symbol_column,
        *factor_columns,
    ]

    require_columns(
        result,
        required_columns,
        context="Research pipeline factor input",
    )

    result = _build_composite(
        df=result,
        factor_columns=factor_columns,
        config=config,
    )

    result = rank_composite(
        df=result,
        composite_column=config.composite_column,
        rank_column=config.rank_column,
        bucket_column=config.bucket_column,
        n_buckets=config.n_buckets,
        date_column=config.date_column,
    )

    result = _build_signal(
        df=result,
        config=config,
    )

    return _build_targets(
        df=result,
        config=config,
    )


def run_research_pipeline_with_summary(
    df: pl.DataFrame,
    config: ResearchPipelineConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Run the research pipeline and return target-level exposure summary.
    """

    result = run_research_pipeline(
        df=df,
        config=config,
    )

    if config.target_method == "none":
        summary = pl.DataFrame()

    else:
        summary = exposure_summary(
            df=result,
            weight_column=config.weight_column,
            date_column=config.date_column,
        )

    return result, summary
