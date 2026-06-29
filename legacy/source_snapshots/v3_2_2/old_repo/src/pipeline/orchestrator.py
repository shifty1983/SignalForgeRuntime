from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.pipeline.default_gates import DEFAULT_PIPELINE_GATES
from src.pipeline.gate_registry import GateDefinition, get_gate_definition
from src.pipeline.runner import run_registered_gate
from src.pipeline.validation import GateReport


PipelineStageCallable = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class PipelineStage:
    """
    One executable end-to-end pipeline stage.

    Each stage produces the payload for one canonical pipeline layer.
    After the stage runs, its output is immediately validated by that layer's
    registered hardening gate.
    """

    layer: str
    run: PipelineStageCallable
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""


@dataclass(frozen=True)
class PipelineRunResult:
    """
    Result from a staged pipeline run.
    """

    payloads: Mapping[str, Any]
    reports: Mapping[str, GateReport]
    completed_layers: tuple[str, ...]
    failed_layer: str | None = None

    @property
    def passed(self) -> bool:
        return self.failed_layer is None and all(
            report.passed for report in self.reports.values()
        )

    @property
    def failed(self) -> bool:
        return not self.passed


class PipelineStageExecutionFailure(RuntimeError):
    """
    Raised when a pipeline stage itself fails before validation.
    """

    def __init__(self, layer: str, error: Exception) -> None:
        self.layer = layer
        self.error = error
        super().__init__(
            f"Pipeline stage '{layer}' raised an exception: {error}"
        )


def _normalize_layer(
    layer: str,
    registry: Mapping[str, GateDefinition],
) -> str:
    return get_gate_definition(layer, registry).layer


def _normalize_dependencies(
    dependencies: Sequence[str],
    registry: Mapping[str, GateDefinition],
) -> tuple[str, ...]:
    return tuple(_normalize_layer(dependency, registry) for dependency in dependencies)


def run_pipeline_stages(
    *,
    stages: Sequence[PipelineStage],
    initial_payloads: Mapping[str, Any] | None = None,
    registry: Mapping[str, GateDefinition] = DEFAULT_PIPELINE_GATES,
    raise_on_failure: bool = True,
    stop_on_failure: bool = True,
) -> PipelineRunResult:
    """
    Run pipeline stages in order and validate each stage output immediately.

    Parameters
    ----------
    stages:
        Ordered executable pipeline stages.

    initial_payloads:
        Optional pre-existing context. Useful for partial pipeline runs.

    registry:
        Gate registry used to validate stage outputs.

    raise_on_failure:
        If True, raise PipelineGateFailure when a gate blocks the pipeline.

    stop_on_failure:
        If True, stop executing downstream stages after a failed gate.

    Returns
    -------
    PipelineRunResult
        Payloads, gate reports, completed layers, and failed layer if any.
    """

    payloads: dict[str, Any] = dict(initial_payloads or {})
    reports: dict[str, GateReport] = {}
    completed_layers: list[str] = []
    failed_layer: str | None = None

    for stage in stages:
        layer = _normalize_layer(stage.layer, registry)
        dependencies = _normalize_dependencies(stage.depends_on, registry)

        missing_dependencies = tuple(
            dependency for dependency in dependencies if dependency not in payloads
        )

        if missing_dependencies:
            raise KeyError(
                f"Pipeline stage '{layer}' is missing dependencies: "
                f"{missing_dependencies}"
            )

        try:
            payload = stage.run(dict(payloads))
        except Exception as error:
            raise PipelineStageExecutionFailure(layer, error) from error

        payloads[layer] = payload

        report = run_registered_gate(
            layer=layer,
            data=payload,
            registry=registry,
            raise_on_failure=raise_on_failure,
        )

        reports[layer] = report

        if report.failed:
            if failed_layer is None:
                failed_layer = layer

            if stop_on_failure:
                break

        if report.passed:
            completed_layers.append(layer)

    return PipelineRunResult(
        payloads=payloads,
        reports=reports,
        completed_layers=tuple(completed_layers),
        failed_layer=failed_layer,
    )
