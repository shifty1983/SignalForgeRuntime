from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

import polars as pl

from src.contracts import (
    validate_exposure_report_schema,
    validate_feature_data_schema,
    validate_market_data_schema,
    validate_optimizer_candidate_schema,
    validate_performance_report_schema,
    validate_portfolio_data_schema,
    validate_signal_data_schema,
    validate_trade_report_schema,
)


class PipelineStage(str, Enum):
    """
    Named stages that can be contract-validated inside the pipeline.
    """

    MARKET_DATA = "market_data"
    FEATURES = "features"
    SIGNALS = "signals"
    OPTIMIZER_CANDIDATES = "optimizer_candidates"
    PORTFOLIO = "portfolio"
    PERFORMANCE_REPORT = "performance_report"
    TRADE_REPORT = "trade_report"
    EXPOSURE_REPORT = "exposure_report"


@dataclass(frozen=True)
class PipelineContractResult:
    """
    Result object returned by non-raising pipeline contract validation.
    """

    stage: PipelineStage
    valid: bool
    rows: int
    columns: tuple[str, ...]
    error: str | None = None


def _normalize_stage(stage: PipelineStage | str) -> PipelineStage:
    """
    Convert a string or PipelineStage into a PipelineStage enum.
    """

    if isinstance(stage, PipelineStage):
        return stage

    try:
        return PipelineStage(stage)
    except ValueError as exc:
        raise ValueError(f"Unknown pipeline stage: {stage}") from exc


def _validator_for_stage(stage: PipelineStage) -> Callable[[pl.DataFrame], bool]:
    """
    Return the contract validator for a pipeline stage.
    """

    validators: dict[PipelineStage, Callable[[pl.DataFrame], bool]] = {
        PipelineStage.MARKET_DATA: validate_market_data_schema,
        PipelineStage.FEATURES: validate_feature_data_schema,
        PipelineStage.SIGNALS: validate_signal_data_schema,
        PipelineStage.OPTIMIZER_CANDIDATES: validate_optimizer_candidate_schema,
        PipelineStage.PORTFOLIO: lambda df: validate_portfolio_data_schema(
            df,
            max_abs_weight=1.0,
            max_gross_exposure=1.0,
        ),
        PipelineStage.PERFORMANCE_REPORT: validate_performance_report_schema,
        PipelineStage.TRADE_REPORT: validate_trade_report_schema,
        PipelineStage.EXPOSURE_REPORT: validate_exposure_report_schema,
    }

    return validators[stage]


def validate_stage_contract(
    stage: PipelineStage | str,
    df: pl.DataFrame,
) -> PipelineContractResult:
    """
    Validate one pipeline stage without raising for schema failures.

    Returns a PipelineContractResult with valid=False when the contract fails.
    Unknown stage names still raise ValueError because that is a programming error.
    """

    normalized_stage = _normalize_stage(stage)
    validator = _validator_for_stage(normalized_stage)

    try:
        validator(df)
    except (ValueError, TypeError) as exc:
        return PipelineContractResult(
            stage=normalized_stage,
            valid=False,
            rows=df.height,
            columns=tuple(df.columns),
            error=str(exc),
        )

    return PipelineContractResult(
        stage=normalized_stage,
        valid=True,
        rows=df.height,
        columns=tuple(df.columns),
        error=None,
    )


def enforce_stage_contract(
    stage: PipelineStage | str,
    df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Validate one pipeline stage and raise if invalid.

    Returns the DataFrame unchanged when valid.
    """

    normalized_stage = _normalize_stage(stage)
    validator = _validator_for_stage(normalized_stage)

    validator(df)

    return df


def validate_pipeline_contracts(
    outputs: Mapping[PipelineStage | str, pl.DataFrame],
) -> list[PipelineContractResult]:
    """
    Validate multiple named pipeline outputs without raising for schema failures.
    """

    return [
        validate_stage_contract(stage=stage, df=df)
        for stage, df in outputs.items()
    ]


def enforce_pipeline_contracts(
    outputs: Mapping[PipelineStage | str, pl.DataFrame],
) -> bool:
    """
    Validate multiple named pipeline outputs and raise if any fail.
    """

    results = validate_pipeline_contracts(outputs)

    failures = [result for result in results if not result.valid]

    if failures:
        failure_text = "; ".join(
            f"{failure.stage.value}: {failure.error}" for failure in failures
        )
        raise ValueError(f"Pipeline contract validation failed: {failure_text}")

    return True
