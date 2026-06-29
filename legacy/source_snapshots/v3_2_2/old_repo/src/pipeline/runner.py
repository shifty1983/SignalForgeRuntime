from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.pipeline.gate_registry import (
    PIPELINE_GATES,
    GateDefinition,
    get_gate_definition,
)
from src.pipeline.hardening_gate import run_hardening_gate
from src.pipeline.validation import GateReport


class PipelineGateFailure(RuntimeError):
    """
    Raised when a pipeline gate has blocking validation failures.
    """

    def __init__(self, report: GateReport) -> None:
        self.report = report
        failures = ", ".join(
            f"{failure.check_name}: {failure.message}"
            for failure in report.blocking_failures
        )
        message = f"Pipeline gate failed for layer '{report.layer}': {failures}"
        super().__init__(message)


def assert_gate_passed(report: GateReport) -> None:
    """
    Raise PipelineGateFailure if the gate report contains blocking failures.
    """

    if report.failed:
        raise PipelineGateFailure(report)


def run_registered_gate(
    *,
    layer: str,
    data: Any,
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> GateReport:
    """
    Run the registered hardening gate for one pipeline layer.

    This is the main integration point for the end-to-end pipeline.
    """

    gate = get_gate_definition(layer, registry)

    report = run_hardening_gate(
        layer=gate.layer,
        data=data,
        checks=gate.checks,
        fail_fast=gate.fail_fast,
    )

    if raise_on_failure:
        assert_gate_passed(report)

    return report


def run_required_gates(
    *,
    payloads: Mapping[str, Any],
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> dict[str, GateReport]:
    """
    Run registered gates for every required layer that has a payload.

    This function is useful for end-to-end tests or batch validation where each
    completed layer output is collected in a dictionary.

    Missing required payloads are treated as errors because the pipeline cannot
    claim to be fully validated if a required layer was skipped.
    """

    reports: dict[str, GateReport] = {}

    for layer, gate in registry.items():
        if not gate.required:
            continue

        if layer not in payloads:
            raise KeyError(f"Missing payload for required pipeline gate: {layer}")

        reports[layer] = run_registered_gate(
            layer=layer,
            data=payloads[layer],
            registry=registry,
            raise_on_failure=raise_on_failure,
        )

    return reports


def run_available_gates(
    *,
    payloads: Mapping[str, Any],
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
    raise_on_failure: bool = True,
) -> dict[str, GateReport]:
    """
    Run registered gates only for layers present in payloads.

    This is useful during partial development when the full end-to-end pipeline
    is not being executed yet.
    """

    reports: dict[str, GateReport] = {}

    for layer in payloads:
        reports[layer] = run_registered_gate(
            layer=layer,
            data=payloads[layer],
            registry=registry,
            raise_on_failure=raise_on_failure,
        )

    return reports
