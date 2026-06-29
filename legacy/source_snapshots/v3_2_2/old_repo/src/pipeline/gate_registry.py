from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.pipeline.hardening_gate import ValidationCheck


CANONICAL_PIPELINE_LAYERS: tuple[str, ...] = (
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


@dataclass(frozen=True)
class GateDefinition:
    """
    Defines the hardening checks attached to one pipeline layer.

    The registry starts with empty check lists because the first goal is to
    define the pipeline gate structure. Concrete checks can then be registered
    layer by layer without changing the runner.
    """

    layer: str
    checks: tuple[ValidationCheck, ...] = field(default_factory=tuple)
    fail_fast: bool = False
    required: bool = True
    description: str = ""

    @property
    def check_count(self) -> int:
        return len(self.checks)

    @property
    def check_names(self) -> tuple[str, ...]:
        return tuple(_check_name(check) for check in self.checks)


def _normalize_layer_name(layer: str) -> str:
    normalized = layer.strip().lower().replace("-", "_").replace(" ", "_")

    if not normalized:
        raise ValueError("Layer name cannot be empty.")

    return normalized


def _check_name(check: ValidationCheck) -> str:
    return getattr(check, "__name__", check.__class__.__name__)


def build_gate_definition(
    *,
    layer: str,
    checks: tuple[ValidationCheck, ...] | list[ValidationCheck] = (),
    fail_fast: bool = False,
    required: bool = True,
    description: str = "",
) -> GateDefinition:
    normalized_layer = _normalize_layer_name(layer)
    normalized_checks = tuple(checks)

    check_names = [_check_name(check) for check in normalized_checks]
    duplicate_names = {
        name for name in check_names if check_names.count(name) > 1
    }

    if duplicate_names:
        raise ValueError(
            "Duplicate check names are not allowed in one gate: "
            f"{sorted(duplicate_names)}"
        )

    return GateDefinition(
        layer=normalized_layer,
        checks=normalized_checks,
        fail_fast=fail_fast,
        required=required,
        description=description,
    )


PIPELINE_GATES: dict[str, GateDefinition] = {
    "raw_data": build_gate_definition(
        layer="raw_data",
        description="Validates raw ingested market, macro, options, fundamental, and sentiment data.",
    ),
    "processed_data": build_gate_definition(
        layer="processed_data",
        description="Validates aligned, normalized, reusable research datasets.",
    ),
    "features": build_gate_definition(
        layer="features",
        description="Validates engineered feature outputs before research use.",
    ),
    "research": build_gate_definition(
        layer="research",
        description="Validates factors, rankings, signals, and portfolio targets.",
    ),
    "backtesting": build_gate_definition(
        layer="backtesting",
        description="Validates simulated portfolio, trades, PnL, and performance outputs.",
    ),
    "risk": build_gate_definition(
        layer="risk",
        description="Validates risk limits, exposure, volatility, and sizing outputs.",
    ),
    "regime": build_gate_definition(
        layer="regime",
        description="Validates macro regime classifications and supporting inputs.",
    ),
    "asset_behavior": build_gate_definition(
        layer="asset_behavior",
        description="Validates asset behavior profiles, correlations, trends, and diagnostics.",
    ),
    "options": build_gate_definition(
        layer="options",
        description="Validates option chains, IV surfaces, Greeks, liquidity, skew, and term structure.",
    ),
    "expected_value": build_gate_definition(
        layer="expected_value",
        description="Validates probability, payoff, scenario, and opportunity score outputs.",
    ),
    "strategy_selection": build_gate_definition(
        layer="strategy_selection",
        description="Validates selected candidates, rankings, filters, rules, and allocations.",
    ),
    "optimizer": build_gate_definition(
        layer="optimizer",
        fail_fast=True,
        description="Validates optimizer inputs, feasibility, constraints, and portfolio integrity.",
    ),
    "reporting": build_gate_definition(
        layer="reporting",
        description="Validates final reporting, dashboard, export, and attribution outputs.",
    ),
}


def registered_layers(
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> tuple[str, ...]:
    return tuple(registry.keys())


def is_registered_layer(
    layer: str,
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> bool:
    return _normalize_layer_name(layer) in registry


def get_gate_definition(
    layer: str,
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> GateDefinition:
    normalized_layer = _normalize_layer_name(layer)

    if normalized_layer not in registry:
        raise KeyError(f"No pipeline gate registered for layer: {normalized_layer}")

    return registry[normalized_layer]


def get_gate_checks(
    layer: str,
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> tuple[ValidationCheck, ...]:
    return get_gate_definition(layer, registry).checks


def register_gate(
    *,
    layer: str,
    checks: tuple[ValidationCheck, ...] | list[ValidationCheck],
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
    fail_fast: bool = False,
    required: bool = True,
    description: str = "",
) -> dict[str, GateDefinition]:
    """
    Return a new registry with one gate added or replaced.

    This does not mutate the default PIPELINE_GATES registry.
    """

    gate = build_gate_definition(
        layer=layer,
        checks=checks,
        fail_fast=fail_fast,
        required=required,
        description=description,
    )

    updated = dict(registry)
    updated[gate.layer] = gate
    return updated


def validate_gate_registry(
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
    expected_layers: tuple[str, ...] = CANONICAL_PIPELINE_LAYERS,
) -> tuple[str, ...]:
    issues: list[str] = []

    for expected_layer in expected_layers:
        if expected_layer not in registry:
            issues.append(f"Missing required pipeline gate: {expected_layer}")

    for layer, gate in registry.items():
        normalized_layer = _normalize_layer_name(layer)

        if gate.layer != normalized_layer:
            issues.append(
                f"Gate key '{layer}' does not match gate layer '{gate.layer}'."
            )

        check_names = list(gate.check_names)
        duplicate_names = {
            name for name in check_names if check_names.count(name) > 1
        }

        if duplicate_names:
            issues.append(
                f"Gate '{layer}' has duplicate checks: {sorted(duplicate_names)}"
            )

    return tuple(issues)


def assert_gate_registry_valid(
    registry: Mapping[str, GateDefinition] = PIPELINE_GATES,
) -> None:
    issues = validate_gate_registry(registry)

    if issues:
        raise ValueError(
            "Pipeline gate registry is invalid: " + "; ".join(issues)
        )
