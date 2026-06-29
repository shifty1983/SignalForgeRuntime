from __future__ import annotations

from collections.abc import Mapping

from src.pipeline.checks import (
    PipelineCheck,
    make_non_empty_check,
    make_not_none_check,
)
from src.pipeline.gate_registry import (
    PIPELINE_GATES,
    GateDefinition,
)


DEFAULT_NON_EMPTY_LAYERS: tuple[str, ...] = (
    "raw_data",
    "processed_data",
    "features",
    "research",
    "backtesting",
    "risk",
    "regime",
    "asset_behavior",
    "options",
    "expected_value",
    "strategy_selection",
    "optimizer",
    "reporting",
)


def build_default_gate_checks(layer: str) -> tuple[PipelineCheck, ...]:
    """
    Build the baseline checks every production pipeline gate should enforce.

    These checks are intentionally generic:
    - payload must exist
    - payload must be non-empty

    More specific schema, NaN, freshness, feasibility, and contract checks can
    be attached later without changing the gate runner.
    """

    checks: list[PipelineCheck] = [
        make_not_none_check(
            layer=layer,
            check_name=f"{layer}_not_none_check",
        )
    ]

    if layer in DEFAULT_NON_EMPTY_LAYERS:
        checks.append(
            make_non_empty_check(
                layer=layer,
                check_name=f"{layer}_non_empty_check",
            )
        )

    return tuple(checks)


def build_default_hardening_registry(
    base_registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> dict[str, GateDefinition]:
    """
    Return a production-oriented registry with default checks attached.

    This does not mutate PIPELINE_GATES. The structural registry remains useful
    for architecture tests, while DEFAULT_PIPELINE_GATES becomes the registry
    the end-to-end pipeline should use.
    """

    registry: dict[str, GateDefinition] = {}

    for layer, gate in base_registry.items():
        registry[layer] = GateDefinition(
            layer=gate.layer,
            checks=build_default_gate_checks(gate.layer),
            fail_fast=gate.fail_fast,
            required=gate.required,
            description=gate.description,
        )

    return registry


DEFAULT_PIPELINE_GATES: dict[str, GateDefinition] = build_default_hardening_registry()
