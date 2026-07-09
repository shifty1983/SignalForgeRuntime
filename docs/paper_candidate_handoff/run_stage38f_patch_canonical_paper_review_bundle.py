import json
import shutil
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")

HANDOFF_PATH = Path("configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json")
BACKUP_PATH = OUT_DIR / "stage38f_signalforge_v21_paper_live_engine_handoff_contract_before_paper_review_bundle_patch.json"

CANONICAL_ROOT = Path("data/canonical/signalforge_pipeline")

PAPER_REVIEW_BUNDLE = {
    "schema_version": "signalforge_paper_review_bundle.v1",
    "bundle_state": "canonical_paper_review_bundle_attached",
    "runtime_source_policy": "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
    "review_scope": "paper_candidate_review_handoff",
    "required_manual_approval": True,
    "trade_authorization": "not_authorized_by_paper_review_bundle",
    "execution_translation_available": False,
    "execution_translation_resolution": "not_promoted_to_data_canonical_signalforge_pipeline",
    "canonical_root": str(CANONICAL_ROOT),
    "artifact_paths": {
        "expectancy_summary": str(CANONICAL_ROOT / "18_walk_forward_expectancy/signalforge_walk_forward_expectancy_summary.json"),
        "expectancy_rows": str(CANONICAL_ROOT / "18_walk_forward_expectancy/signalforge_walk_forward_expectancy_rows.jsonl"),
        "strategy_selection_summary": str(CANONICAL_ROOT / "21_strategy_selection_pruned_core_plus_credit/signalforge_historical_strategy_selection_rows_summary.json"),
        "selected_trade_sequence_summary": str(CANONICAL_ROOT / "23_selected_trade_sequence_pruned/signalforge_portfolio_selected_trade_sequence_summary.json"),
        "position_sizing_manifest": str(CANONICAL_ROOT / "24_position_sizing_return_bound_sensitivity/stage24_promotion_manifest.json"),
        "equity_reconstruction_manifest": str(CANONICAL_ROOT / "25_equity_reconstruction_return_bound_sensitivity/stage25_promotion_manifest.json"),
        "allocated_equity_reconstruction_manifest": str(CANONICAL_ROOT / "25A_equity_reconstruction_allocated_return_bound_sensitivity/stage25A_promotion_manifest.json"),
        "paper_candidate_lock": str(CANONICAL_ROOT / "33_paper_candidate_lock/signalforge_paper_candidate_lock.json"),
    },
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def is_canonical(path_text):
    try:
        Path(path_text).resolve().relative_to(CANONICAL_ROOT.resolve())
        return True
    except Exception:
        return False

blockers = []
warnings = [
    "stage38f_patches_handoff_contract_only",
    "paper_review_bundle_does_not_authorize_trades",
    "paper_review_bundle_uses_only_data_canonical_signalforge_pipeline_sources",
]

if not HANDOFF_PATH.exists():
    blockers.append(f"missing_handoff_contract_{HANDOFF_PATH}")

for role, path_text in PAPER_REVIEW_BUNDLE["artifact_paths"].items():
    path = Path(path_text)

    if not path.exists():
        blockers.append(f"missing_canonical_bundle_path_{role}_{path}")

    if not is_canonical(path_text):
        blockers.append(f"non_canonical_bundle_path_{role}_{path}")

if blockers:
    summary = {
        "adapter_type": "canonical_paper_review_bundle_handoff_patch_builder",
        "artifact_type": "signalforge_canonical_paper_review_bundle_handoff_patch",
        "contract": "canonical_paper_review_bundle_handoff_patch",
        "is_ready": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_path": str(HANDOFF_PATH),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }

else:
    handoff = read_json(HANDOFF_PATH)

    if not isinstance(handoff, dict):
        blockers.append("handoff_contract_not_json_object")
    else:
        shutil.copy2(HANDOFF_PATH, BACKUP_PATH)

        handoff["paper_review_bundle"] = PAPER_REVIEW_BUNDLE

        HANDOFF_PATH.write_text(
            json.dumps(handoff, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    patched = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}
    patched_block = patched.get("paper_review_bundle") if isinstance(patched, dict) else None

    checks = [
        {
            "check": "paper_review_bundle_present",
            "expected": True,
            "actual": isinstance(patched_block, dict),
            "passed": isinstance(patched_block, dict),
        },
        {
            "check": "runtime_source_policy",
            "expected": "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
            "actual": patched_block.get("runtime_source_policy") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("runtime_source_policy") == "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
        },
        {
            "check": "trade_authorization_guard",
            "expected": "not_authorized_by_paper_review_bundle",
            "actual": patched_block.get("trade_authorization") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("trade_authorization") == "not_authorized_by_paper_review_bundle",
        },
        {
            "check": "manual_approval_required",
            "expected": True,
            "actual": patched_block.get("required_manual_approval") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("required_manual_approval") is True,
        },
        {
            "check": "all_paths_canonical",
            "expected": True,
            "actual": all(is_canonical(p) for p in patched_block.get("artifact_paths", {}).values()) if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and all(is_canonical(p) for p in patched_block.get("artifact_paths", {}).values()),
        },
        {
            "check": "paper_order_created_false",
            "expected": False,
            "actual": patched_block.get("paper_order_created") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("paper_order_created") is False,
        },
        {
            "check": "live_order_created_false",
            "expected": False,
            "actual": patched_block.get("live_order_created") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("live_order_created") is False,
        },
        {
            "check": "live_trade_supported_false",
            "expected": False,
            "actual": patched_block.get("live_trade_supported") if isinstance(patched_block, dict) else None,
            "passed": isinstance(patched_block, dict) and patched_block.get("live_trade_supported") is False,
        },
    ]

    failed = [row["check"] for row in checks if row["passed"] is not True]
    if failed:
        blockers.append(f"failed_patch_checks_{failed}")

    summary = {
        "adapter_type": "canonical_paper_review_bundle_handoff_patch_builder",
        "artifact_type": "signalforge_canonical_paper_review_bundle_handoff_patch",
        "contract": "canonical_paper_review_bundle_handoff_patch",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_path": str(HANDOFF_PATH),
        "backup_path": str(BACKUP_PATH),
        "paper_review_bundle_present": isinstance(patched_block, dict),
        "artifact_path_count": len(PAPER_REVIEW_BUNDLE["artifact_paths"]),
        "checks": checks,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }

summary_path = OUT_DIR / "signalforge_stage38f_patch_canonical_paper_review_bundle_summary.json"
check_rows_path = OUT_DIR / "signalforge_stage38f_patch_canonical_paper_review_bundle_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in summary.get("checks", []):
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 38F patch canonical paper review bundle compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "paper_review_bundle_present",
    "artifact_path_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary.get(key)}")

print(f"summary_path: {summary_path}")
print(f"check_rows_path: {check_rows_path}")
print(f"backup_path: {summary.get('backup_path')}")

print("\n--- Stage 38F checks compact ---")
print("check\texpected\tactual\tpassed")
for row in summary.get("checks", []):
    print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

if blockers:
    print("\n--- Stage 38F blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38F warnings ---")
for warning in warnings:
    print(warning)
