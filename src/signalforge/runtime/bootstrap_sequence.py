from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from signalforge.runtime.closed_outcomes_bootstrap import build_closed_outcomes_bootstrap
from signalforge.runtime.market_regime_bootstrap import build_market_regime_bootstrap
from signalforge.runtime.prior_gate_asof_parity import build_prior_gate_asof_parity
from signalforge.runtime.prior_gate_evaluation_outcomes_bootstrap import (
    build_prior_gate_evaluation_outcomes_bootstrap,
)
from signalforge.runtime.prior_gate_skipped_row_parity import build_prior_gate_skipped_row_parity
from signalforge.runtime.prior_symbol_regime_state_builder import build_prior_symbol_regime_state


@dataclass(frozen=True)
class RuntimeBootstrapStepResult:
    step_name: str
    is_ready: bool
    blocker_count: int
    blockers: tuple[str, ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class RuntimeBootstrapSequenceSummary:
    is_ready: bool
    step_count: int
    ready_step_count: int
    failed_step_count: int
    blocker_count: int
    blockers: tuple[str, ...]
    steps: tuple[RuntimeBootstrapStepResult, ...]


def _summary_to_dict(summary: Any) -> dict[str, Any]:
    if hasattr(summary, "__dataclass_fields__"):
        return asdict(summary)

    if isinstance(summary, dict):
        return summary

    raise TypeError(f"Unsupported summary type: {type(summary)!r}")


def _blockers_from_summary(summary_dict: dict[str, Any]) -> tuple[str, ...]:
    blockers = summary_dict.get("blockers") or ()

    if isinstance(blockers, dict):
        return tuple(str(key) for key in blockers.keys())

    if isinstance(blockers, list):
        return tuple(str(item) for item in blockers)

    if isinstance(blockers, tuple):
        return tuple(str(item) for item in blockers)

    return tuple()


def _step_result(step_name: str, summary: Any) -> RuntimeBootstrapStepResult:
    summary_dict = _summary_to_dict(summary)
    is_ready = bool(summary_dict.get("is_ready"))
    blocker_count = int(summary_dict.get("blocker_count") or 0)
    blockers = _blockers_from_summary(summary_dict)

    return RuntimeBootstrapStepResult(
        step_name=step_name,
        is_ready=is_ready,
        blocker_count=blocker_count,
        blockers=blockers,
        summary=summary_dict,
    )


def build_runtime_bootstrap_sequence(
    *,
    seed_bundle: str | Path | None = None,
) -> RuntimeBootstrapSequenceSummary:
    steps: list[RuntimeBootstrapStepResult] = []

    step_builders: tuple[tuple[str, Callable[[], Any]], ...] = (
        (
            "market_regime_bootstrap",
            lambda: build_market_regime_bootstrap(seed_bundle=seed_bundle),
        ),
        (
            "closed_outcomes_bootstrap",
            lambda: build_closed_outcomes_bootstrap(seed_bundle=seed_bundle),
        ),
        (
            "prior_gate_evaluation_outcomes_bootstrap",
            lambda: build_prior_gate_evaluation_outcomes_bootstrap(seed_bundle=seed_bundle),
        ),
        (
            "prior_symbol_regime_state_builder",
            lambda: build_prior_symbol_regime_state(),
        ),
        (
            "prior_gate_skipped_row_parity",
            lambda: build_prior_gate_skipped_row_parity(seed_bundle=seed_bundle),
        ),
        (
            "prior_gate_asof_parity",
            lambda: build_prior_gate_asof_parity(seed_bundle=seed_bundle),
        ),
    )

    for step_name, builder in step_builders:
        summary = builder()
        result = _step_result(step_name, summary)
        steps.append(result)

        if not result.is_ready:
            break

    ready_step_count = sum(1 for step in steps if step.is_ready)
    failed_step_count = sum(1 for step in steps if not step.is_ready)
    blockers: list[str] = []

    for step in steps:
        for blocker in step.blockers:
            blockers.append(f"{step.step_name}:{blocker}")

    return RuntimeBootstrapSequenceSummary(
        is_ready=failed_step_count == 0 and len(steps) == len(step_builders),
        step_count=len(steps),
        ready_step_count=ready_step_count,
        failed_step_count=failed_step_count,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
        steps=tuple(steps),
    )


def summary_to_dict(summary: RuntimeBootstrapSequenceSummary) -> dict[str, Any]:
    return asdict(summary)


def write_summary(summary: RuntimeBootstrapSequenceSummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SignalForge runtime bootstrap sequence.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default="artifacts/runtime_bootstrap_sequence_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_runtime_bootstrap_sequence(seed_bundle=args.seed_bundle)
    write_summary(summary, args.output)

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"step_count: {summary.step_count}")
        print(f"ready_step_count: {summary.ready_step_count}")
        print(f"failed_step_count: {summary.failed_step_count}")
        print(f"blocker_count: {summary.blocker_count}")

        for step in summary.steps:
            print(f"{step.step_name}: ready={step.is_ready}, blockers={step.blockers}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
