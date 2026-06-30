from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS
from signalforge.data.seed_bundle import resolve_seed_bundle_root


@dataclass(frozen=True)
class RuntimeBootstrapPlanRow:
    runtime_input_name: str
    runtime_relative_path: str
    seed_source_relative_path: str | None
    generated_by: str
    required_for_paper: bool
    seed_source_exists: bool | None
    seed_file_count: int
    seed_total_size_bytes: int
    blocker: str | None
    warning: str | None


@dataclass(frozen=True)
class RuntimeBootstrapPlan:
    seed_bundle_root: str | None
    is_ready: bool
    row_count: int
    blocker_count: int
    warning_count: int
    rows: tuple[RuntimeBootstrapPlanRow, ...]


def _count_files_and_bytes(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    if path.is_file():
        return 1, path.stat().st_size

    file_count = 0
    total_size = 0

    for file_path in path.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size

    return file_count, total_size


def build_runtime_bootstrap_plan(seed_bundle: str | Path | None = None) -> RuntimeBootstrapPlan:
    root = resolve_seed_bundle_root(seed_bundle)

    rows: list[RuntimeBootstrapPlanRow] = []

    for mapping in RUNTIME_SOURCE_MAPPINGS:
        seed_source_exists: bool | None = None
        seed_file_count = 0
        seed_total_size_bytes = 0
        blocker = None
        warning = None

        if mapping.seed_source_relative_path is None:
            warning = "no_seed_source_mapped"
        elif root is None:
            seed_source_exists = False
            blocker = "seed_bundle_missing"
        else:
            seed_path = root / mapping.seed_source_relative_path
            seed_source_exists = seed_path.exists()

            if not seed_source_exists:
                blocker = "seed_source_missing" if mapping.required_for_paper else None
                warning = None if mapping.required_for_paper else "optional_seed_source_missing"
            else:
                seed_file_count, seed_total_size_bytes = _count_files_and_bytes(seed_path)

                if seed_file_count == 0:
                    blocker = "seed_source_empty" if mapping.required_for_paper else None
                    warning = None if mapping.required_for_paper else "optional_seed_source_empty"

        rows.append(
            RuntimeBootstrapPlanRow(
                runtime_input_name=mapping.runtime_input_name,
                runtime_relative_path=mapping.runtime_relative_path,
                seed_source_relative_path=mapping.seed_source_relative_path,
                generated_by=mapping.generated_by,
                required_for_paper=mapping.required_for_paper,
                seed_source_exists=seed_source_exists,
                seed_file_count=seed_file_count,
                seed_total_size_bytes=seed_total_size_bytes,
                blocker=blocker,
                warning=warning,
            )
        )

    blocker_count = sum(1 for row in rows if row.blocker)
    warning_count = sum(1 for row in rows if row.warning)

    return RuntimeBootstrapPlan(
        seed_bundle_root=str(root) if root else None,
        is_ready=blocker_count == 0,
        row_count=len(rows),
        blocker_count=blocker_count,
        warning_count=warning_count,
        rows=tuple(rows),
    )


def plan_to_dict(plan: RuntimeBootstrapPlan) -> dict:
    return asdict(plan)


def write_bootstrap_plan(plan: RuntimeBootstrapPlan, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SignalForge runtime bootstrap plan.")
    parser.add_argument("--seed-bundle", default=None, help="Optional explicit seed bundle path.")
    parser.add_argument(
        "--output",
        default="artifacts/runtime_bootstrap_plan.json",
        help="Output JSON path.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    plan = build_runtime_bootstrap_plan(args.seed_bundle)
    write_bootstrap_plan(plan, args.output)

    if args.json:
        print(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True))
    else:
        print(f"seed_bundle_root: {plan.seed_bundle_root}")
        print(f"is_ready: {plan.is_ready}")
        print(f"row_count: {plan.row_count}")
        print(f"blocker_count: {plan.blocker_count}")
        print(f"warning_count: {plan.warning_count}")
        print(f"output: {args.output}")

    return 0 if plan.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




