from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from src.pipeline.contracts import PipelineStage
from src.pipeline.default_gates import DEFAULT_PIPELINE_GATES
from src.pipeline.gate_registry import GateDefinition
from src.pipeline.run_pipeline import PipelineRunResult
from src.pipeline.runner import run_registered_gate
from src.pipeline.validation import GateReport


LEGACY_STAGE_TO_HARDENING_LAYER: dict[PipelineStage, str] = {
    PipelineStage.MARKET_DATA: "raw_data",
    PipelineStage.FEATURES: "features",
    PipelineStage.SIGNALS: "research",
    PipelineStage.OPTIMIZER_CANDIDATES: "strategy_selection",
    PipelineStage.PORTFOLIO: "optimizer",
    PipelineStage.PERFORMANCE_REPORT: "reporting",
    PipelineStage.TRADE_REPORT: "reporting",
    PipelineStage.EXPOSURE_REPORT: "reporting",
}


@dataclass(frozen=True)
class PipelineHardeningResult:
    """
    Hardening result for a legacy pipeline run.

    Reports are keyed by the legacy PipelineStage so multiple legacy stages may
    safely map to the same canonical hardening layer, such as performance,
    trade, and exposure reports all mapping to reporting.
    """

    success: bool
    reports: Mapping[PipelineStage, GateReport]
    stage_to_layer: Mapping[PipelineStage, str]

    @property
    def passed(self) -> bool:
        return self.success and all(report.passed for report in self.reports.values())

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def blocking_failures(self) -> tuple[GateReport, ...]:
        return tuple(report for report in self.reports.values() if report.failed)


def normalize_legacy_stage(stage: PipelineStage | str) -> PipelineStage:
    if isinstance(stage, PipelineStage):
        return stage

    try:
        return PipelineStage(stage)
    except ValueError as exc:
        raise ValueError(f"Unknown legacy pipeline stage: {stage}") from exc


def hardening_layer_for_stage(stage: PipelineStage | str) -> str:
    normalized_stage = normalize_legacy_stage(stage)

    try:
        return LEGACY_STAGE_TO_HARDENING_LAYER[normalized_stage]
    except KeyError as exc:
        raise KeyError(
            f"No hardening layer mapping registered for stage: "
            f"{normalized_stage.value}"
        ) from exc


def validate_legacy_output_hardening(
    *,
    stage: PipelineStage | str,
    output: pl.DataFrame,
    registry: Mapping[str, GateDefinition] = DEFAULT_PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> GateReport:
    """
    Validate one legacy pipeline output with the new hardening gate system.
    """

    normalized_stage = normalize_legacy_stage(stage)
    layer = hardening_layer_for_stage(normalized_stage)

    return run_registered_gate(
        layer=layer,
        data=output,
        registry=registry,
        raise_on_failure=raise_on_failure,
    )


def validate_legacy_outputs_hardening(
    *,
    outputs: Mapping[PipelineStage | str, pl.DataFrame],
    registry: Mapping[str, GateDefinition] = DEFAULT_PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> PipelineHardeningResult:
    """
    Validate multiple legacy pipeline outputs with the new hardening system.
    """

    reports: dict[PipelineStage, GateReport] = {}
    stage_to_layer: dict[PipelineStage, str] = {}

    for stage, output in outputs.items():
        normalized_stage = normalize_legacy_stage(stage)
        layer = hardening_layer_for_stage(normalized_stage)

        stage_to_layer[normalized_stage] = layer
        reports[normalized_stage] = run_registered_gate(
            layer=layer,
            data=output,
            registry=registry,
            raise_on_failure=raise_on_failure,
        )

    return PipelineHardeningResult(
        success=True,
        reports=reports,
        stage_to_layer=stage_to_layer,
    )


def validate_pipeline_run_hardening(
    *,
    result: PipelineRunResult,
    registry: Mapping[str, GateDefinition] = DEFAULT_PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> PipelineHardeningResult:
    """
    Validate a completed legacy PipelineRunResult using hardening gates.
    """

    hardening_result = validate_legacy_outputs_hardening(
        outputs=result.outputs,
        registry=registry,
        raise_on_failure=raise_on_failure,
    )

    return PipelineHardeningResult(
        success=result.success,
        reports=hardening_result.reports,
        stage_to_layer=hardening_result.stage_to_layer,
    )
