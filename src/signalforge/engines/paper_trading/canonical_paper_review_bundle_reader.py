import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


CANONICAL_ROOT = Path("data/canonical/signalforge_pipeline")
DEFAULT_HANDOFF_CONTRACT_PATH = Path(
    "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json"
)

CONTRACT = "canonical_paper_review_bundle_reader"
ARTIFACT_TYPE = "signalforge_canonical_paper_review_bundle_reader"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _count_jsonl(path: Path) -> Optional[int]:
    if not path.exists() or path.suffix.lower() != ".jsonl":
        return None

    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _is_canonical(path_text: str) -> bool:
    try:
        Path(path_text).resolve().relative_to(CANONICAL_ROOT.resolve())
        return True
    except Exception:
        return False


def build_canonical_paper_review_bundle_reader(
    handoff_contract_path: str | Path = DEFAULT_HANDOFF_CONTRACT_PATH,
) -> Dict[str, Any]:
    handoff_path = Path(handoff_contract_path)

    blockers: List[str] = []
    warnings: List[str] = [
        "paper_review_bundle_reader_does_not_authorize_trades",
        "paper_review_bundle_runtime_sources_must_be_canonical",
    ]

    if not handoff_path.exists():
        blockers.append(f"missing_handoff_contract_{handoff_path}")
        return {
            "adapter_type": "canonical_paper_review_bundle_reader_builder",
            "artifact_type": ARTIFACT_TYPE,
            "contract": CONTRACT,
            "is_ready": False,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "warning_count": len(warnings),
            "warnings": warnings,
            "handoff_contract_path": str(handoff_path),
            "paper_order_created": False,
            "live_order_created": False,
            "live_trade_supported": False,
        }

    handoff = _read_json(handoff_path)

    if not isinstance(handoff, Mapping):
        blockers.append("handoff_contract_not_json_object")
        handoff = {}

    expectancy = handoff.get("expectancy_snapshot_adapter")
    bundle = handoff.get("paper_review_bundle")

    if not isinstance(expectancy, Mapping):
        blockers.append("missing_expectancy_snapshot_adapter_block")
        expectancy = {}

    if not isinstance(bundle, Mapping):
        blockers.append("missing_paper_review_bundle_block")
        bundle = {}

    path_rows: List[Dict[str, Any]] = []

    for role in ["source_rows_path", "source_summary_path"]:
        path_text = expectancy.get(role)
        if isinstance(path_text, str):
            path = Path(path_text)
            path_rows.append({
                "block": "expectancy_snapshot_adapter",
                "role": role,
                "path": path_text,
                "exists": path.exists(),
                "canonical": _is_canonical(path_text),
                "jsonl_row_count": _count_jsonl(path),
            })

    artifact_paths = bundle.get("artifact_paths", {})
    if isinstance(artifact_paths, Mapping):
        for role, path_text in artifact_paths.items():
            if isinstance(path_text, str):
                path = Path(path_text)
                path_rows.append({
                    "block": "paper_review_bundle",
                    "role": str(role),
                    "path": path_text,
                    "exists": path.exists(),
                    "canonical": _is_canonical(path_text),
                    "jsonl_row_count": _count_jsonl(path),
                })

    for row in path_rows:
        if row["exists"] is not True:
            blockers.append(f"missing_runtime_path_{row['block']}_{row['role']}_{row['path']}")
        if row["canonical"] is not True:
            blockers.append(f"non_canonical_runtime_path_{row['block']}_{row['role']}_{row['path']}")

    expectancy_trade_auth = expectancy.get("trade_authorization")
    bundle_trade_auth = bundle.get("trade_authorization")

    if expectancy_trade_auth != "not_authorized_by_expectancy_adapter_or_expected_value_scoring":
        blockers.append("expectancy_trade_authorization_guard_missing_or_changed")

    if bundle_trade_auth != "not_authorized_by_paper_review_bundle":
        blockers.append("paper_review_bundle_trade_authorization_guard_missing_or_changed")

    if bundle.get("runtime_source_policy") != "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline":
        blockers.append("paper_review_bundle_runtime_source_policy_missing_or_changed")

    checks = [
        {
            "check": "expectancy_snapshot_adapter_present",
            "passed": isinstance(expectancy, Mapping) and bool(expectancy),
        },
        {
            "check": "paper_review_bundle_present",
            "passed": isinstance(bundle, Mapping) and bool(bundle),
        },
        {
            "check": "all_runtime_paths_exist",
            "passed": all(row["exists"] for row in path_rows),
        },
        {
            "check": "all_runtime_paths_canonical",
            "passed": all(row["canonical"] for row in path_rows),
        },
        {
            "check": "paper_review_bundle_requires_manual_approval",
            "passed": bundle.get("required_manual_approval") is True,
        },
        {
            "check": "paper_review_bundle_does_not_authorize_trades",
            "passed": bundle_trade_auth == "not_authorized_by_paper_review_bundle",
        },
    ]

    failed_checks = [row["check"] for row in checks if row["passed"] is not True]
    if failed_checks:
        blockers.append(f"failed_reader_checks_{failed_checks}")

    return {
        "adapter_type": "canonical_paper_review_bundle_reader_builder",
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": len(blockers) == 0,
        "readiness_state": "ready_for_paper_review" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_contract_path": str(handoff_path),
        "canonical_root": str(CANONICAL_ROOT),
        "runtime_path_count": len(path_rows),
        "runtime_path_exists_count": sum(1 for row in path_rows if row["exists"]),
        "runtime_path_canonical_count": sum(1 for row in path_rows if row["canonical"]),
        "path_rows": path_rows,
        "checks": checks,
        "paper_review_bundle": dict(bundle),
        "expectancy_snapshot_adapter": dict(expectancy),
        "trade_authorization": "not_authorized_by_paper_review_bundle",
        "requires_manual_approval": True,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }
