from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS
from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS, RuntimeSourceMapping
from signalforge.data.seed_bundle import resolve_seed_bundle_root


@dataclass(frozen=True)
class RuntimeSourceMapStatus:
    runtime_input_name: str
    runtime_relative_path: str
    seed_source_relative_path: str | None
    generated_by: str
    required_for_paper: bool
    runtime_contract_exists: bool
    seed_source_exists: bool | None
    blocker: str | None
    warning: str | None


@dataclass(frozen=True)
class RuntimeSourceMapAudit:
    seed_bundle_root: str | None
    is_ready: bool
    mapping_count: int
    blocker_count: int
    warning_count: int
    statuses: tuple[RuntimeSourceMapStatus, ...]


def _runtime_contract_names() -> set[str]:
    return {contract.name for contract in RUNTIME_INPUT_CONTRACTS}


def build_runtime_source_map_status(
    *,
    mapping: RuntimeSourceMapping,
    seed_bundle_root: Path | None,
) -> RuntimeSourceMapStatus:
    contract_exists = mapping.runtime_input_name in _runtime_contract_names()

    seed_source_exists: bool | None
    if mapping.seed_source_relative_path is None:
        seed_source_exists = None
    elif seed_bundle_root is None:
        seed_source_exists = False
    else:
        seed_source_exists = (seed_bundle_root / mapping.seed_source_relative_path).exists()

    blocker = None
    warning = None

    if not contract_exists:
        blocker = "runtime_contract_missing"
    elif mapping.required_for_paper and mapping.seed_source_relative_path and not seed_source_exists:
        blocker = "required_seed_source_missing"

    return RuntimeSourceMapStatus(
        runtime_input_name=mapping.runtime_input_name,
        runtime_relative_path=mapping.runtime_relative_path,
        seed_source_relative_path=mapping.seed_source_relative_path,
        generated_by=mapping.generated_by,
        required_for_paper=mapping.required_for_paper,
        runtime_contract_exists=contract_exists,
        seed_source_exists=seed_source_exists,
        blocker=blocker,
        warning=warning,
    )


def build_runtime_source_map_audit(seed_bundle: str | Path | None = None) -> RuntimeSourceMapAudit:
    root = resolve_seed_bundle_root(seed_bundle)

    statuses = tuple(
        build_runtime_source_map_status(
            mapping=mapping,
            seed_bundle_root=root,
        )
        for mapping in RUNTIME_SOURCE_MAPPINGS
    )

    blocker_count = sum(1 for status in statuses if status.blocker)
    warning_count = sum(1 for status in statuses if status.warning)

    return RuntimeSourceMapAudit(
        seed_bundle_root=str(root) if root else None,
        is_ready=blocker_count == 0,
        mapping_count=len(statuses),
        blocker_count=blocker_count,
        warning_count=warning_count,
        statuses=statuses,
    )


def audit_to_dict(audit: RuntimeSourceMapAudit) -> dict:
    return asdict(audit)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit SignalForge runtime source mapping.")
    parser.add_argument("--seed-bundle", default=None, help="Optional explicit seed bundle path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    audit = build_runtime_source_map_audit(args.seed_bundle)
    payload = audit_to_dict(audit)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"seed_bundle_root: {audit.seed_bundle_root}")
        print(f"is_ready: {audit.is_ready}")
        print(f"mapping_count: {audit.mapping_count}")
        print(f"blocker_count: {audit.blocker_count}")
        print(f"warning_count: {audit.warning_count}")

    return 0 if audit.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
