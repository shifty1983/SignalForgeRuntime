from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from src.pipeline.gate_registry import CANONICAL_PIPELINE_LAYERS, assert_gate_registry_valid
from src.pipeline.run_pipeline import PipelineRunResult, PipelineStep, run_pipeline
from src.pipeline.runner import PipelineGateFailure, run_required_gates


@dataclass(frozen=True)
class OperationalPipelineConfig:
    """
    Configuration for an operational pipeline run.

    This layer turns the hardening system from a standalone validation tool
    into an execution gate for real pipeline runs.
    """

    required_layers: Sequence[str] = field(
        default_factory=lambda: tuple(CANONICAL_PIPELINE_LAYERS)
    )
    fail_fast: bool = True
    run_preflight_gates: bool = True
    run_postrun_gates: bool = True
    raise_on_gate_failure: bool = True


@dataclass(frozen=True)
class OperationalPipelineResult:
    """
    Result object for a hardened operational pipeline run.
    """

    preflight_gate_results: Mapping[str, Any]
    pipeline_result: PipelineRunResult | None
    postrun_gate_results: Mapping[str, Any]
    passed: bool

    @property
    def failed(self) -> bool:
        return not self.passed
    
@dataclass(frozen=True)
class OperationalBlockingFailure:
    """
    Compatibility failure object for PipelineGateFailure.

    runner.py expects each blocking failure to expose check_name.
    """

    check_name: str
    message: str
    layer: str | None = None
    severity: str = "blocking"
    passed: bool = False
    blocking: bool = True


@dataclass(frozen=True)
class OperationalGateFailureReport:
    """
    Compatibility wrapper for PipelineGateFailure.

    PipelineGateFailure expects a report object with:
    - layer
    - blocking_failures

    Each blocking failure also needs check_name.
    """

    message: str
    gate_results: Mapping[str, Any]
    blocking_failures: tuple[OperationalBlockingFailure, ...]
    layer: str = "Operational Pipeline"


def _gate_report_passed(report: Any) -> bool:
    """
    Supports both strict GateReport-style objects and simple test doubles.
    """

    if isinstance(report, bool):
        return report

    for attr in ("passed", "success", "ok", "valid"):
        if hasattr(report, attr):
            return bool(getattr(report, attr))

    if isinstance(report, Mapping):
        for key in ("passed", "success", "ok", "valid"):
            if key in report:
                return bool(report[key])

    return False


def _all_gates_passed(results: Mapping[str, Any]) -> bool:
    return all(_gate_report_passed(report) for report in results.values())


def _pipeline_result_passed(result: PipelineRunResult | None) -> bool:
    if result is None:
        return False

    for attr in ("passed", "success", "ok", "completed"):
        if hasattr(result, attr):
            return bool(getattr(result, attr))

    if hasattr(result, "failed"):
        return not bool(getattr(result, "failed"))

    return True


def _run_required_layer_gates(
    required_layers: Sequence[str],
    *,
    fail_fast: bool,
) -> Mapping[str, Any]:
    """
    Runs hardening gates for the required operational layers.

    This wrapper keeps operational.py insulated from small signature changes
    in the lower-level runner.
    """

    try:
        return run_required_gates(
            required_layers=required_layers,
            fail_fast=fail_fast,
        )
    except TypeError:
        try:
            return run_required_gates(
                layers=required_layers,
                fail_fast=fail_fast,
            )
        except TypeError:
            try:
                return run_required_gates(required_layers)
            except TypeError:
                return run_required_gates()
            
def _collect_blocking_failures(
    results: Mapping[str, Any],
    *,
    fallback_message: str,
) -> tuple[OperationalBlockingFailure, ...]:
    failures: list[OperationalBlockingFailure] = []

    for layer, report in results.items():
        if _gate_report_passed(report):
            continue

        if hasattr(report, "blocking_failures"):
            blocking_failures = getattr(report, "blocking_failures")

            for index, failure in enumerate(blocking_failures):
                if hasattr(failure, "check_name"):
                    failures.append(
                        OperationalBlockingFailure(
                            check_name=str(getattr(failure, "check_name")),
                            message=str(
                                getattr(
                                    failure,
                                    "message",
                                    f"{layer} gate failed.",
                                )
                            ),
                            layer=str(layer),
                        )
                    )
                else:
                    failures.append(
                        OperationalBlockingFailure(
                            check_name=f"{layer}.blocking_failure_{index}",
                            message=str(failure),
                            layer=str(layer),
                        )
                    )

            continue

        if isinstance(report, Mapping) and "blocking_failures" in report:
            for index, failure in enumerate(report["blocking_failures"]):
                if isinstance(failure, Mapping):
                    failures.append(
                        OperationalBlockingFailure(
                            check_name=str(
                                failure.get(
                                    "check_name",
                                    f"{layer}.blocking_failure_{index}",
                                )
                            ),
                            message=str(
                                failure.get(
                                    "message",
                                    f"{layer} gate failed.",
                                )
                            ),
                            layer=str(layer),
                        )
                    )
                else:
                    failures.append(
                        OperationalBlockingFailure(
                            check_name=f"{layer}.blocking_failure_{index}",
                            message=str(failure),
                            layer=str(layer),
                        )
                    )

            continue

        failures.append(
            OperationalBlockingFailure(
                check_name=f"{layer}.gate_failed",
                message=f"{layer} gate failed.",
                layer=str(layer),
            )
        )

    if not failures:
        failures.append(
            OperationalBlockingFailure(
                check_name="operational_pipeline.gate_failed",
                message=fallback_message,
                layer="Operational Pipeline",
            )
        )

    return tuple(failures)


def _raise_pipeline_gate_failure(
    message: str,
    results: Mapping[str, Any],
    *,
    layer: str = "Operational Pipeline",
) -> None:
    failure_report = OperationalGateFailureReport(
        message=message,
        gate_results=results,
        blocking_failures=_collect_blocking_failures(
            results,
            fallback_message=message,
        ),
        layer=layer,
    )

    raise PipelineGateFailure(failure_report)


def run_operational_pipeline(
    steps: Iterable[PipelineStep],
    *,
    config: OperationalPipelineConfig | None = None,
) -> OperationalPipelineResult:
    """
    Run the pipeline through the operational hardening layer.

    This should become the preferred entry point for real operational use.
    """

    cfg = config or OperationalPipelineConfig()

    assert_gate_registry_valid()

    preflight_results: Mapping[str, Any] = {}
    postrun_results: Mapping[str, Any] = {}
    pipeline_result: PipelineRunResult | None = None

    if cfg.run_preflight_gates:
        preflight_results = _run_required_layer_gates(
            cfg.required_layers,
            fail_fast=cfg.fail_fast,
        )

        if not _all_gates_passed(preflight_results):
            if cfg.raise_on_gate_failure:
                _raise_pipeline_gate_failure(
                    "Operational pipeline blocked by failed preflight hardening gate.",
                    preflight_results,
                    layer="Operational Pipeline Preflight",     
                )

            return OperationalPipelineResult(
                preflight_gate_results=preflight_results,
                pipeline_result=None,
                postrun_gate_results={},
                passed=False,
            )

    pipeline_result = run_pipeline(steps)

    if cfg.run_postrun_gates:
        postrun_results = _run_required_layer_gates(
            cfg.required_layers,
            fail_fast=cfg.fail_fast,
        )

        if not _all_gates_passed(postrun_results):
            _raise_pipeline_gate_failure(
                "Operational pipeline completed, but failed post-run hardening gate.",
                postrun_results,
                layer="Operational Pipeline Postrun",
            )

    passed = (
        _all_gates_passed(preflight_results)
        and _pipeline_result_passed(pipeline_result)
        and _all_gates_passed(postrun_results)
    )

    return OperationalPipelineResult(
        preflight_gate_results=preflight_results,
        pipeline_result=pipeline_result,
        postrun_gate_results=postrun_results,
        passed=passed,
    )
