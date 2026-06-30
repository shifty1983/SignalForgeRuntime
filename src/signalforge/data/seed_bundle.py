from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SEED_BUNDLE_ENV_VAR = "SIGNALFORGE_SEED_BUNDLE"


REQUIRED_DIRECTORIES = (
    "data/manual",
    "data/samples",

    "artifacts/qc_replay_5y_behavior_inputs",
    "artifacts/qc_5y_data_inventory_20210601_20260531",
    "artifacts/quantconnect_historical_replay_5y_window_plan_20210601_20260531",

    "artifacts/historical_decision_rows_20210601_20260531",
    "artifacts/historical_strategy_selection_rows_20210601_20260531",
    "artifacts/layer_field_carry_forward_enrichment_v2_20210601_20260531",
    "artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531",

    "artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531",
    "artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531",
    "artifacts/v3_2_reconciled_canonical_from_v2_locked_actions_20230101_20260531",

    "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531",
    "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531",
    "artifacts/v3_2_1_native_quote_attribution_v1_20230101_20260531",
    "artifacts/v3_2_1_paper_candidate_ruleset_lock_20230101_20260531",

    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
    "artifacts/v3_2_2_native_quote_attribution_v1_20230101_20260531",
    "artifacts/v3_2_2_iron_butterfly_dependence_v1_20230101_20260531",
    "artifacts/v3_2_2_paper_candidate_ruleset_lock_20230101_20260531",
    "artifacts/v3_2_2_pre_broker_audit_pack_v1_20230101_20260531",
    "artifacts/project_current_candidate_snapshot_20260628_171901",
)


REQUIRED_FILES = (
    "seed_bundle_manifest.json",

    "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531/"
    "signalforge_v3_2_1_native_quote_join_summary.json",

    "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/"
    "signalforge_v3_2_1_native_quote_pnl_stress_summary.json",

    "artifacts/v3_2_1_native_quote_attribution_v1_20230101_20260531/"
    "signalforge_v3_2_1_native_quote_attribution_summary.json",

    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/"
    "signalforge_v3_2_2_symbol_regime_walkforward_prune_stress_summary.json",

    "artifacts/v3_2_2_native_quote_attribution_v1_20230101_20260531/"
    "signalforge_v3_2_2_native_quote_attribution_summary.json",

    "artifacts/v3_2_2_iron_butterfly_dependence_v1_20230101_20260531/"
    "signalforge_v3_2_2_iron_butterfly_dependence_summary.json",

    "artifacts/v3_2_2_paper_candidate_ruleset_lock_20230101_20260531/"
    "signalforge_v3_2_2_paper_candidate_ruleset_lock.json",

    "artifacts/v3_2_2_pre_broker_audit_pack_v1_20230101_20260531/"
    "signalforge_v3_2_2_pre_broker_audit_pack_summary.json",

    "artifacts/project_current_candidate_snapshot_20260628_171901/"
    "signalforge_project_current_candidate_snapshot.json",
)


@dataclass(frozen=True)
class SeedBundleInventory:
    bundle_root: str | None
    is_ready: bool
    missing_directory_count: int
    missing_file_count: int
    file_count: int
    total_size_bytes: int
    missing_directories: tuple[str, ...]
    missing_files: tuple[str, ...]


def _candidate_roots_from_documents() -> list[Path]:
    user_profile = os.environ.get("USERPROFILE")
    if not user_profile:
        return []

    documents = Path(user_profile) / "Documents"
    if not documents.exists():
        return []

    return sorted(
        [
            path
            for path in documents.glob("SignalForge_v3_2_2_seed_bundle_*")
            if path.is_dir()
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def resolve_seed_bundle_root(path: str | Path | None = None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None

    env_path = os.environ.get(SEED_BUNDLE_ENV_VAR)
    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.exists() else None

    candidates = _candidate_roots_from_documents()
    return candidates[0] if candidates else None


def _count_files_and_bytes(root: Path) -> tuple[int, int]:
    file_count = 0
    total_size = 0

    for file_path in root.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size

    return file_count, total_size


def build_seed_bundle_inventory(path: str | Path | None = None) -> SeedBundleInventory:
    root = resolve_seed_bundle_root(path)

    if root is None:
        return SeedBundleInventory(
            bundle_root=None,
            is_ready=False,
            missing_directory_count=len(REQUIRED_DIRECTORIES),
            missing_file_count=len(REQUIRED_FILES),
            file_count=0,
            total_size_bytes=0,
            missing_directories=tuple(REQUIRED_DIRECTORIES),
            missing_files=tuple(REQUIRED_FILES),
        )

    missing_dirs = tuple(
        rel_path for rel_path in REQUIRED_DIRECTORIES
        if not (root / rel_path).is_dir()
    )

    missing_files = tuple(
        rel_path for rel_path in REQUIRED_FILES
        if not (root / rel_path).is_file()
    )

    file_count, total_size = _count_files_and_bytes(root)

    return SeedBundleInventory(
        bundle_root=str(root),
        is_ready=not missing_dirs and not missing_files,
        missing_directory_count=len(missing_dirs),
        missing_file_count=len(missing_files),
        file_count=file_count,
        total_size_bytes=total_size,
        missing_directories=missing_dirs,
        missing_files=missing_files,
    )


def inventory_to_dict(inventory: SeedBundleInventory) -> dict:
    return asdict(inventory)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit SignalForge V3.2.2 seed bundle readiness.")
    parser.add_argument("--seed-bundle", default=None, help="Optional explicit seed bundle path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    inventory = build_seed_bundle_inventory(args.seed_bundle)
    payload = inventory_to_dict(inventory)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"bundle_root: {inventory.bundle_root}")
        print(f"is_ready: {inventory.is_ready}")
        print(f"missing_directory_count: {inventory.missing_directory_count}")
        print(f"missing_file_count: {inventory.missing_file_count}")
        print(f"file_count: {inventory.file_count}")
        print(f"total_size_bytes: {inventory.total_size_bytes}")

    return 0 if inventory.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

