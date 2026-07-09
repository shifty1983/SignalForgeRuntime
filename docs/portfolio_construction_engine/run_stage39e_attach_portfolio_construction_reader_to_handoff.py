import importlib
import json
import shutil
from pathlib import Path

OUT_DIR = Path("docs/portfolio_construction_engine")

HANDOFF_PATH = Path("configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json")
BACKUP_PATH = OUT_DIR / "stage39e_signalforge_v21_paper_live_engine_handoff_contract_before_portfolio_construction_reader_patch.json"

MODULE = "signalforge.engines.paper_trading.canonical_portfolio_construction_reader"
ENTRYPOINT = "build_canonical_portfolio_construction_reader"

PATCH = {
    "schema_version": "signalforge_portfolio_construction_reader_handoff.v1",
    "reader_state": "attached_for_paper_portfolio_review",
    "module": MODULE,
    "entrypoint": ENTRYPOINT,
    "runtime_source_policy": "consume_canonical_stage_24_25_25a_outputs_only",
    "optimizer_policy": "do_not_run_optimizer_in_paper_runtime",
    "depends_on": [
        "paper_review_bundle",
        "expectancy_snapshot_adapter"
    ],
    "canonical_stage_inputs": {
        "position_sizing": "data/canonical/signalforge_pipeline/24_position_sizing_return_bound_sensitivity/stage24_promotion_manifest.json",
        "equity_reconstruction": "data/canonical/signalforge_pipeline/25_equity_reconstruction_return_bound_sensitivity/stage25_promotion_manifest.json",
        "allocated_equity_reconstruction": "data/canonical/signalforge_pipeline/25A_equity_reconstruction_allocated_return_bound_sensitivity/stage25A_promotion_manifest.json"
    },
    "required_manual_approval": True,
    "trade_authorization": "not_authorized_by_portfolio_construction_reader",
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False
}

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

blockers = []
warnings = [
    "stage39e_patches_handoff_contract_only",
    "portfolio_construction_reader_does_not_run_optimizer",
    "portfolio_construction_reader_does_not_authorize_trades",
]

if not HANDOFF_PATH.exists():
    blockers.append(f"missing_handoff_contract_{HANDOFF_PATH}")

for role, path_text in PATCH["canonical_stage_inputs"].items():
    if not Path(path_text).exists():
        blockers.append(f"missing_canonical_stage_input_{role}_{path_text}")

try:
    module = importlib.import_module(MODULE)
    func = getattr(module, ENTRYPOINT)
except Exception as exc:
    blockers.append(f"reader_import_failed_{MODULE}_{exc}")
    func = None

reader_artifact = func() if func and not blockers else {}

if reader_artifact and reader_artifact.get("is_ready") is not True:
    blockers.append("portfolio_construction_reader_not_ready")

if not blockers:
    handoff = read_json(HANDOFF_PATH)

    if not isinstance(handoff, dict):
        blockers.append("handoff_contract_not_json_object")
    else:
        shutil.copy2(HANDOFF_PATH, BACKUP_PATH)
        handoff["portfolio_construction_reader"] = PATCH

        HANDOFF_PATH.write_text(
            json.dumps(handoff, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

patched = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}
patched_block = patched.get("portfolio_construction_reader") if isinstance(patched, dict) else None

checks = [
    {
        "check": "portfolio_construction_reader_present",
        "expected": True,
        "actual": isinstance(patched_block, dict),
        "passed": isinstance(patched_block, dict),
    },
    {
        "check": "module",
        "expected": MODULE,
        "actual": patched_block.get("module") if isinstance(patched_block, dict) else None,
        "passed": isinstance(patched_block, dict) and patched_block.get("module") == MODULE,
    },
    {
        "check": "entrypoint",
        "expected": ENTRYPOINT,
        "actual": patched_block.get("entrypoint") if isinstance(patched_block, dict) else None,
        "passed": isinstance(patched_block, dict) and patched_block.get("entrypoint") == ENTRYPOINT,
    },
    {
        "check": "optimizer_policy",
        "expected": "do_not_run_optimizer_in_paper_runtime",
        "actual": patched_block.get("optimizer_policy") if isinstance(patched_block, dict) else None,
        "passed": isinstance(patched_block, dict) and patched_block.get("optimizer_policy") == "do_not_run_optimizer_in_paper_runtime",
    },
    {
        "check": "reader_artifact_ready",
        "expected": True,
        "actual": reader_artifact.get("is_ready") if isinstance(reader_artifact, dict) else None,
        "passed": isinstance(reader_artifact, dict) and reader_artifact.get("is_ready") is True,
    },
    {
        "check": "trade_authorization_guard",
        "expected": "not_authorized_by_portfolio_construction_reader",
        "actual": patched_block.get("trade_authorization") if isinstance(patched_block, dict) else None,
        "passed": isinstance(patched_block, dict) and patched_block.get("trade_authorization") == "not_authorized_by_portfolio_construction_reader",
    },
    {
        "check": "manual_approval_required",
        "expected": True,
        "actual": patched_block.get("required_manual_approval") if isinstance(patched_block, dict) else None,
        "passed": isinstance(patched_block, dict) and patched_block.get("required_manual_approval") is True,
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
    "adapter_type": "portfolio_construction_reader_handoff_patch_builder",
    "artifact_type": "signalforge_portfolio_construction_reader_handoff_patch",
    "contract": "portfolio_construction_reader_handoff_patch",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "handoff_path": str(HANDOFF_PATH),
    "backup_path": str(BACKUP_PATH),
    "portfolio_construction_reader_present": isinstance(patched_block, dict),
    "reader_artifact_is_ready": reader_artifact.get("is_ready") if isinstance(reader_artifact, dict) else None,
    "reader_readiness_state": reader_artifact.get("readiness_state") if isinstance(reader_artifact, dict) else None,
    "manifest_count": reader_artifact.get("manifest_count") if isinstance(reader_artifact, dict) else None,
    "stage_file_count": reader_artifact.get("stage_file_count") if isinstance(reader_artifact, dict) else None,
    "optimizer_policy": PATCH["optimizer_policy"],
    "checks": checks,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage39e_attach_portfolio_construction_reader_to_handoff_summary.json"
check_rows_path = OUT_DIR / "signalforge_stage39e_attach_portfolio_construction_reader_to_handoff_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in checks:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 39E attach portfolio construction reader to handoff compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "portfolio_construction_reader_present",
    "reader_artifact_is_ready",
    "reader_readiness_state",
    "manifest_count",
    "stage_file_count",
    "optimizer_policy",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary.get(key)}")

print(f"summary_path: {summary_path}")
print(f"check_rows_path: {check_rows_path}")
print(f"backup_path: {summary.get('backup_path')}")

print("\n--- Stage 39E checks compact ---")
print("check\texpected\tactual\tpassed")
for row in checks:
    print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

if blockers:
    print("\n--- Stage 39E blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 39E warnings ---")
for warning in warnings:
    print(warning)
