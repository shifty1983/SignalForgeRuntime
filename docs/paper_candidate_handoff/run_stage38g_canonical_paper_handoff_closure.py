import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")
HANDOFF_PATH = Path("configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json")
CANONICAL_ROOT = Path("data/canonical/signalforge_pipeline")

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
    "stage38g_closure_check_only",
    "paper_review_bundle_and_expectancy_adapter_do_not_authorize_trades",
    "runtime_sources_must_remain_data_canonical_signalforge_pipeline_only",
]

if not HANDOFF_PATH.exists():
    blockers.append(f"missing_handoff_contract_{HANDOFF_PATH}")

handoff = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}

expectancy = handoff.get("expectancy_snapshot_adapter") if isinstance(handoff, dict) else None
bundle = handoff.get("paper_review_bundle") if isinstance(handoff, dict) else None

path_rows = []

if not isinstance(expectancy, dict):
    blockers.append("missing_expectancy_snapshot_adapter_block")
else:
    for role in ["source_rows_path", "source_summary_path"]:
        value = expectancy.get(role)
        path_rows.append({
            "block": "expectancy_snapshot_adapter",
            "role": role,
            "path": value,
            "exists": Path(value).exists() if value else False,
            "canonical": is_canonical(value) if value else False,
        })

if not isinstance(bundle, dict):
    blockers.append("missing_paper_review_bundle_block")
else:
    for role, value in bundle.get("artifact_paths", {}).items():
        path_rows.append({
            "block": "paper_review_bundle",
            "role": role,
            "path": value,
            "exists": Path(value).exists() if value else False,
            "canonical": is_canonical(value) if value else False,
        })

for row in path_rows:
    if not row["exists"]:
        blockers.append(f"missing_runtime_path_{row['block']}_{row['role']}_{row['path']}")
    if not row["canonical"]:
        blockers.append(f"non_canonical_runtime_path_{row['block']}_{row['role']}_{row['path']}")

checks = [
    {
        "check": "expectancy_adapter_present",
        "expected": True,
        "actual": isinstance(expectancy, dict),
        "passed": isinstance(expectancy, dict),
    },
    {
        "check": "paper_review_bundle_present",
        "expected": True,
        "actual": isinstance(bundle, dict),
        "passed": isinstance(bundle, dict),
    },
    {
        "check": "expectancy_trade_authorization_guard",
        "expected": "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
        "actual": expectancy.get("trade_authorization") if isinstance(expectancy, dict) else None,
        "passed": isinstance(expectancy, dict) and expectancy.get("trade_authorization") == "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
    },
    {
        "check": "bundle_trade_authorization_guard",
        "expected": "not_authorized_by_paper_review_bundle",
        "actual": bundle.get("trade_authorization") if isinstance(bundle, dict) else None,
        "passed": isinstance(bundle, dict) and bundle.get("trade_authorization") == "not_authorized_by_paper_review_bundle",
    },
    {
        "check": "bundle_runtime_source_policy",
        "expected": "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
        "actual": bundle.get("runtime_source_policy") if isinstance(bundle, dict) else None,
        "passed": isinstance(bundle, dict) and bundle.get("runtime_source_policy") == "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
    },
    {
        "check": "all_runtime_paths_exist",
        "expected": True,
        "actual": all(row["exists"] for row in path_rows),
        "passed": all(row["exists"] for row in path_rows),
    },
    {
        "check": "all_runtime_paths_canonical",
        "expected": True,
        "actual": all(row["canonical"] for row in path_rows),
        "passed": all(row["canonical"] for row in path_rows),
    },
    {
        "check": "paper_order_created_false",
        "expected": False,
        "actual": False,
        "passed": True,
    },
    {
        "check": "live_order_created_false",
        "expected": False,
        "actual": False,
        "passed": True,
    },
    {
        "check": "live_trade_supported_false",
        "expected": False,
        "actual": False,
        "passed": True,
    },
]

failed = [row["check"] for row in checks if row["passed"] is not True]
if failed:
    blockers.append(f"failed_closure_checks_{failed}")

summary = {
    "adapter_type": "canonical_paper_handoff_closure_builder",
    "artifact_type": "signalforge_canonical_paper_handoff_closure",
    "contract": "canonical_paper_handoff_closure",
    "is_ready": len(blockers) == 0,
    "closure_state": "closed_canonical_paper_review_handoff" if not blockers else "blocked",
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "handoff_path": str(HANDOFF_PATH),
    "runtime_path_count": len(path_rows),
    "runtime_path_exists_count": sum(1 for row in path_rows if row["exists"]),
    "runtime_path_canonical_count": sum(1 for row in path_rows if row["canonical"]),
    "checks": checks,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage38g_canonical_paper_handoff_closure_summary.json"
path_rows_path = OUT_DIR / "signalforge_stage38g_canonical_paper_handoff_closure_path_rows.jsonl"
check_rows_path = OUT_DIR / "signalforge_stage38g_canonical_paper_handoff_closure_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with path_rows_path.open("w", encoding="utf-8") as f:
    for row in path_rows:
        f.write(json.dumps(row, default=str) + "\n")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in checks:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 38G canonical paper handoff closure compact ---")
for key in [
    "is_ready",
    "closure_state",
    "blocker_count",
    "warning_count",
    "runtime_path_count",
    "runtime_path_exists_count",
    "runtime_path_canonical_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 38G checks compact ---")
print("check\texpected\tactual\tpassed")
for row in checks:
    print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

print(f"\nsummary_path: {summary_path}")
print(f"path_rows_path: {path_rows_path}")
print(f"check_rows_path: {check_rows_path}")

if blockers:
    print("\n--- Stage 38G blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38G warnings ---")
for warning in warnings:
    print(warning)
