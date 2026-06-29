from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import polars as pl

from src.pipeline.contracts import PipelineStage
from src.pipeline.default_gates import DEFAULT_PIPELINE_GATES
from src.pipeline.gate_registry import GateDefinition
from src.pipeline.hardening_adapter import (
    PipelineHardeningResult,
    validate_pipeline_run_hardening,
)
from src.pipeline.run_pipeline import (
    PipelineRunResult,
    PipelineStep,
    PipelineStepResult,
    run_pipeline,
)
from src.pipeline.validation import GateReport


@dataclass(frozen=True)
class HardenedPipelineRunResult:
    """
    Combined result from the legacy pipeline runner and the hardening layer.
    """

    pipeline: PipelineRunResult
    hardening: PipelineHardeningResult

    @property
    def success(self) -> bool:
        return self.pipeline.success and self.hardening.passed

    @property
    def passed(self) -> bool:
        return self.success

    @property
    def failed(self) -> bool:
        return not self.success

    @property
    def outputs(self) -> dict[PipelineStage, pl.DataFrame]:
        return self.pipeline.outputs

    @property
    def steps(self) -> tuple[PipelineStepResult, ...]:
        return self.pipeline.steps

    @property
    def reports(self) -> Mapping[PipelineStage, GateReport]:
        return self.hardening.reports


def run_pipeline_with_hardening(
    *,
    steps: Sequence[PipelineStep],
    initial_outputs: Mapping[PipelineStage | str, pl.DataFrame] | None = None,
    validate_contracts: bool = True,
    validate_hardening: bool = True,
    registry: Mapping[str, GateDefinition] = DEFAULT_PIPELINE_GATES,
    raise_on_hardening_failure: bool = True,
) -> HardenedPipelineRunResult:
    """
    Run the legacy pipeline, then validate completed outputs with hardening gates.

    This keeps the old pipeline runner intact while giving production usage a
    single safe entry point.
    """

    pipeline_result = run_pipeline(
        steps=steps,
        initial_outputs=initial_outputs,
        validate_contracts=validate_contracts,
    )

    if validate_hardening:
        hardening_result = validate_pipeline_run_hardening(
            result=pipeline_result,
            registry=registry,
            raise_on_failure=raise_on_hardening_failure,
        )
    else:
        hardening_result = PipelineHardeningResult(
            success=pipeline_result.success,
            reports={},
            stage_to_layer={},
        )

    return HardenedPipelineRunResult(
        pipeline=pipeline_result,
        hardening=hardening_result,
    )
