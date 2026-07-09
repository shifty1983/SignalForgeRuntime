import importlib
import json
from pathlib import Path

OUT_DIR = Path("docs/portfolio_construction_engine")
MODULE = "signalforge.engines.paper_trading.canonical_portfolio_construction_reader"
ENTRYPOINT = "build_canonical_portfolio_construction_reader"

blockers = []
warnings = [
    "stage39d_promotes_reader_into_src",
    "reader_does_not_run_optimizer",
    "reader_does_not_create_orders",
]

try:
    module = importlib.import_module(MODULE)
    func = getattr(module, ENTRYPOINT)
except Exception as exc:
    blockers.append(f"import_failed_{MODULE}_{exc}")
    func = None

artifact = func() if func and not blockers else {}

if artifact and artifact.get("is_ready") is not True:
    blockers.append("canonical_portfolio_construction_reader_not_ready")

summary = {
    "adapter_type": "canonical_portfolio_construction_reader_promotion_smoke",
    "artifact_type": "signalforge_canonical_portfolio_construction_reader_promotion_smoke",
    "contract": "canonical_portfolio_construction_reader_promotion_smoke",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "module": MODULE,
    "entrypoint": ENTRYPOINT,
    "reader_artifact_type": artifact.get("artifact_type"),
    "reader_contract": artifact.get("contract"),
    "reader_is_ready": artifact.get("is_ready"),
    "reader_readiness_state": artifact.get("readiness_state"),
    "manifest_count": artifact.get("manifest_count"),
    "stage_file_count": artifact.get("stage_file_count"),
    "portfolio_construction_policy": artifact.get("portfolio_construction_policy"),
    "optimizer_policy": artifact.get("optimizer_policy"),
    "trade_authorization": artifact.get("trade_authorization"),
    "requires_manual_approval": artifact.get("requires_manual_approval"),
    "paper_order_created": artifact.get("paper_order_created"),
    "live_order_created": artifact.get("live_order_created"),
    "live_trade_supported": artifact.get("live_trade_supported"),
}

summary_path = OUT_DIR / "signalforge_stage39d_canonical_portfolio_construction_reader_promotion_summary.json"
manifest_rows_path = OUT_DIR / "signalforge_stage39d_canonical_portfolio_construction_reader_manifest_rows.jsonl"
stage_file_rows_path = OUT_DIR / "signalforge_stage39d_canonical_portfolio_construction_reader_stage_file_rows.jsonl"
check_rows_path = OUT_DIR / "signalforge_stage39d_canonical_portfolio_construction_reader_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with manifest_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact.get("manifest_rows", []):
        f.write(json.dumps(row, default=str) + "\n")

with stage_file_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact.get("stage_file_rows", []):
        f.write(json.dumps(row, default=str) + "\n")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact.get("checks", []):
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 39D canonical portfolio construction reader promotion compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "reader_artifact_type",
    "reader_contract",
    "reader_is_ready",
    "reader_readiness_state",
    "manifest_count",
    "stage_file_count",
    "portfolio_construction_policy",
    "optimizer_policy",
    "trade_authorization",
    "requires_manual_approval",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary.get(key)}")

print(f"summary_path: {summary_path}")
print(f"manifest_rows_path: {manifest_rows_path}")
print(f"stage_file_rows_path: {stage_file_rows_path}")
print(f"check_rows_path: {check_rows_path}")

if blockers:
    print("\n--- Stage 39D blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 39D warnings ---")
for warning in warnings:
    print(warning)
