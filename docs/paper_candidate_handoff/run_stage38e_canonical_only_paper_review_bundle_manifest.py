import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")
CANONICAL_ROOT = Path("data/canonical/signalforge_pipeline")

CANONICAL_STAGES = {
    "expectancy": CANONICAL_ROOT / "18_walk_forward_expectancy",
    "strategy_selection": CANONICAL_ROOT / "21_strategy_selection_pruned_core_plus_credit",
    "selected_trade_sequence": CANONICAL_ROOT / "23_selected_trade_sequence_pruned",
    "position_sizing": CANONICAL_ROOT / "24_position_sizing_return_bound_sensitivity",
    "equity_reconstruction": CANONICAL_ROOT / "25_equity_reconstruction_return_bound_sensitivity",
    "allocated_equity_reconstruction": CANONICAL_ROOT / "25A_equity_reconstruction_allocated_return_bound_sensitivity",
    "paper_candidate_lock": CANONICAL_ROOT / "33_paper_candidate_lock",
}

REQUIRED_FILES = {
    "expectancy_summary": CANONICAL_STAGES["expectancy"] / "signalforge_walk_forward_expectancy_summary.json",
    "expectancy_rows": CANONICAL_STAGES["expectancy"] / "signalforge_walk_forward_expectancy_rows.jsonl",
    "strategy_selection_summary": CANONICAL_STAGES["strategy_selection"] / "signalforge_historical_strategy_selection_rows_summary.json",
    "selected_trade_sequence_summary": CANONICAL_STAGES["selected_trade_sequence"] / "signalforge_portfolio_selected_trade_sequence_summary.json",
    "position_sizing_manifest": CANONICAL_STAGES["position_sizing"] / "stage24_promotion_manifest.json",
    "equity_reconstruction_manifest": CANONICAL_STAGES["equity_reconstruction"] / "stage25_promotion_manifest.json",
    "allocated_equity_reconstruction_manifest": CANONICAL_STAGES["allocated_equity_reconstruction"] / "stage25A_promotion_manifest.json",
    "paper_candidate_lock": CANONICAL_STAGES["paper_candidate_lock"] / "signalforge_paper_candidate_lock.json",
}

def read_json_safe(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"__read_error__": str(exc)}

def count_jsonl_safe(path):
    if not path.exists() or path.suffix.lower() != ".jsonl":
        return None
    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1
    return count

def is_canonical(path):
    try:
        path.resolve().relative_to(CANONICAL_ROOT.resolve())
        return True
    except Exception:
        return False

blockers = []
warnings = [
    "stage38e_canonical_only_manifest_no_handoff_patch",
    "paper_review_bundle_does_not_create_orders",
    "docs_outputs_are_audit_records_not_runtime_sources",
]

stage_rows = []
artifact_rows = []

for role, stage_path in CANONICAL_STAGES.items():
    stage_rows.append({
        "role": role,
        "stage_path": str(stage_path),
        "exists": stage_path.exists(),
        "is_dir": stage_path.is_dir(),
        "canonical": is_canonical(stage_path),
        "json_count": len(list(stage_path.glob("*.json"))) if stage_path.exists() else 0,
        "jsonl_count": len(list(stage_path.glob("*.jsonl"))) if stage_path.exists() else 0,
    })

    if not stage_path.exists():
        blockers.append(f"missing_canonical_stage_{role}_{stage_path}")

for role, path in REQUIRED_FILES.items():
    data = read_json_safe(path) if path.exists() and path.suffix.lower() == ".json" else {}

    row = {
        "role": role,
        "path": str(path),
        "exists": path.exists(),
        "canonical": is_canonical(path),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "jsonl_row_count": count_jsonl_safe(path),
        "is_ready": data.get("is_ready") if isinstance(data, dict) else None,
        "artifact_type": data.get("artifact_type") if isinstance(data, dict) else None,
        "contract": data.get("contract") if isinstance(data, dict) else None,
        "paper_candidate_id": data.get("paper_candidate_id") if isinstance(data, dict) else None,
        "paper_candidate_state": data.get("paper_candidate_state") if isinstance(data, dict) else None,
        "live_candidate_state": data.get("live_candidate_state") if isinstance(data, dict) else None,
        "paper_trade_supported": data.get("paper_trade_supported") if isinstance(data, dict) else None,
        "live_trade_supported": data.get("live_trade_supported") if isinstance(data, dict) else None,
        "read_error": data.get("__read_error__") if isinstance(data, dict) else None,
    }

    artifact_rows.append(row)

    if not path.exists():
        blockers.append(f"missing_required_canonical_file_{role}_{path}")

    if not is_canonical(path):
        blockers.append(f"non_canonical_runtime_source_{role}_{path}")

    if row["read_error"]:
        blockers.append(f"json_read_error_{role}_{row['read_error']}")

non_canonical_rows = [row for row in artifact_rows if row["canonical"] is not True]

bundle = {
    "schema_version": "signalforge_paper_review_bundle.v1",
    "bundle_state": "canonical_candidate_manifest_ready" if not blockers else "blocked",
    "runtime_source_policy": "paper_trading_inputs_must_come_from_data_canonical_signalforge_pipeline",
    "review_scope": "paper_candidate_review_handoff",
    "trade_authorization": "not_authorized_by_paper_review_bundle",
    "required_manual_approval": True,
    "execution_translation_available": False,
    "execution_translation_resolution": "not_promoted_to_data_canonical_signalforge_pipeline",
    "artifact_paths": {role: str(path) for role, path in REQUIRED_FILES.items()},
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary = {
    "adapter_type": "canonical_only_paper_review_bundle_manifest_builder",
    "artifact_type": "signalforge_canonical_only_paper_review_bundle_manifest",
    "contract": "canonical_only_paper_review_bundle_manifest",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "canonical_root": str(CANONICAL_ROOT),
    "stage_count": len(stage_rows),
    "stage_exists_count": sum(1 for row in stage_rows if row["exists"]),
    "required_artifact_count": len(artifact_rows),
    "required_artifact_exists_count": sum(1 for row in artifact_rows if row["exists"]),
    "non_canonical_runtime_source_count": len(non_canonical_rows),
    "bundle": bundle,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage38e_canonical_only_paper_review_bundle_manifest_summary.json"
stage_rows_path = OUT_DIR / "signalforge_stage38e_canonical_only_paper_review_bundle_stage_rows.jsonl"
artifact_rows_path = OUT_DIR / "signalforge_stage38e_canonical_only_paper_review_bundle_artifact_rows.jsonl"
bundle_path = OUT_DIR / "signalforge_canonical_only_paper_review_bundle_manifest.json"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
bundle_path.write_text(json.dumps(bundle, indent=2, default=str) + "\n", encoding="utf-8")

with stage_rows_path.open("w", encoding="utf-8") as f:
    for row in stage_rows:
        f.write(json.dumps(row, default=str) + "\n")

with artifact_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact_rows:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 38E canonical-only paper review bundle manifest compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "stage_count",
    "stage_exists_count",
    "required_artifact_count",
    "required_artifact_exists_count",
    "non_canonical_runtime_source_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 38E canonical artifact rows compact ---")
print("role\texists\tcanonical\tis_ready\tartifact_type\tcontract\tjsonl_row_count\tpath")
for row in artifact_rows:
    print(
        f"{row['role']}\t{row['exists']}\t{row['canonical']}\t{row['is_ready']}\t"
        f"{row['artifact_type']}\t{row['contract']}\t{row['jsonl_row_count']}\t{row['path']}"
    )

print(f"\nsummary_path: {summary_path}")
print(f"stage_rows_path: {stage_rows_path}")
print(f"artifact_rows_path: {artifact_rows_path}")
print(f"bundle_path: {bundle_path}")

if blockers:
    print("\n--- Stage 38E blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38E warnings ---")
for warning in warnings:
    print(warning)
