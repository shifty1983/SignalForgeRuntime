from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import polars as pl

from src.pipeline.contracts import (
    PipelineContractResult,
    PipelineStage,
    validate_stage_contract,
)


PipelineOutputs = Mapping[PipelineStage, pl.DataFrame]
PipelineStepCallable = Callable[[PipelineOutputs], pl.DataFrame]


@dataclass(frozen=True)
class PipelineStep:
    """
    One executable pipeline step.

    The step receives prior pipeline outputs and returns a new DataFrame for
    its declared stage.
    """

    name: str
    stage: PipelineStage | str
    run: PipelineStepCallable


@dataclass(frozen=True)
class PipelineStepResult:
    """
    Result for one executed pipeline step.
    """

    name: str
    stage: PipelineStage
    rows: int
    columns: tuple[str, ...]
    contract: PipelineContractResult | None = None


@dataclass(frozen=True)
class PipelineRunResult:
    """
    Result returned by run_pipeline.
    """

    success: bool
    outputs: dict[PipelineStage, pl.DataFrame]
    steps: tuple[PipelineStepResult, ...]


def _normalize_stage(stage: PipelineStage | str) -> PipelineStage:
    if isinstance(stage, PipelineStage):
        return stage

    try:
        return PipelineStage(stage)
    except ValueError as exc:
        raise ValueError(f"Unknown pipeline stage: {stage}") from exc


def run_pipeline(
    steps: list[PipelineStep] | tuple[PipelineStep, ...],
    initial_outputs: Mapping[PipelineStage | str, pl.DataFrame] | None = None,
    validate_contracts: bool = True,
) -> PipelineRunResult:
    """
    Execute pipeline steps in order.

    This is intentionally a thin orchestration layer. It does not contain alpha,
    optimization, execution, or reporting logic. It only runs supplied step
    functions, stores their outputs, and optionally validates stage contracts.
    """

    outputs: dict[PipelineStage, pl.DataFrame] = {}

    if initial_outputs is not None:
        outputs.update(
            {
                _normalize_stage(stage): df
                for stage, df in initial_outputs.items()
            }
        )

    step_results: list[PipelineStepResult] = []

    for step in steps:
        stage = _normalize_stage(step.stage)
        output = step.run(outputs)

        if not isinstance(output, pl.DataFrame):
            raise TypeError(
                f"Pipeline step '{step.name}' must return a polars DataFrame."
            )

        contract_result: PipelineContractResult | None = None

        if validate_contracts:
            contract_result = validate_stage_contract(stage, output)

            if not contract_result.valid:
                raise ValueError(
                    "Pipeline step "
                    f"'{step.name}' failed {stage.value} contract validation: "
                    f"{contract_result.error}"
                )

        outputs[stage] = output

        step_results.append(
            PipelineStepResult(
                name=step.name,
                stage=stage,
                rows=output.height,
                columns=tuple(output.columns),
                contract=contract_result,
            )
        )

    return PipelineRunResult(
        success=True,
        outputs=outputs,
        steps=tuple(step_results),
    )
