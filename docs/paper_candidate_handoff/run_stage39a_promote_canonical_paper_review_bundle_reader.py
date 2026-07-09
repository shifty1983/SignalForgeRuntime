import importlib
import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")
MODULE = "signalforge.engines.paper_trading.canonical_paper_review_bundle_reader"
ENTRYPOINT = "build_canonical_paper_review_bundle_reader"

blockers = []
warnings = [
    "stage39a_promotes_reader_into_src",
    "reader_does_not_create_orders",
]

try:
    module = importlib.import_module(MODULE)
    func = getattr(module, ENTRYPOINT)
except Exception as exc:
    blockers.append(f"import_failed_{MODULE}_{exc}")
    module = None
    func = None

artifact = func() if func and not blockers else {}

if artifact and artifact.get("is_ready") is not True:
    blockers.append("reader_artifact_not_ready")

summary = {
    "adapter_type": "canonical_paper_review_bundle_reader_promotion_smoke",
    "artifact_type": "signalforge_canonical_paper_review_bundle_reader_promotion_smoke",
    "contract": "canonical_paper_review_bundle_reader_promotion_smoke",
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
    "runtime_path_count": artifact.get("runtime_path_count"),
    "runtime_path_exists_count": artifact.get("runtime_path_exists_count"),
    "runtime_path_canonical_count": artifact.get("runtime_path_canonical_count"),
    "trade_authorization": artifact.get("trade_authorization"),
    "requires_manual_approval": artifact.get("requires_manual_approval"),
    "paper_order_created": artifact.get("paper_order_created"),
    "live_order_created": artifact.get("live_order_created"),
    "live_trade_supported": artifact.get("live_trade_supported"),
}

summary_path = OUT_DIR / "signalforge_stage39a_canonical_paper_review_bundle_reader_promotion_summary.json"
path_rows_path = OUT_DIR / "signalforge_stage39a_canonical_paper_review_bundle_reader_path_rows.jsonl"
check_rows_path = OUT_DIR / "signalforge_stage39a_canonical_paper_review_bundle_reader_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with path_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact.get("path_rows", []):
        f.write(json.dumps(row, default=str) + "\n")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in artifact.get("checks", []):
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 39A canonical paper review bundle reader promotion compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "reader_artifact_type",
    "reader_contract",
    "reader_is_ready",
    "reader_readiness_state",
    "runtime_path_count",
    "runtime_path_exists_count",
    "runtime_path_canonical_count",
    "trade_authorization",
    "requires_manual_approval",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary.get(key)}")

print(f"summary_path: {summary_path}")
print(f"path_rows_path: {path_rows_path}")
print(f"check_rows_path: {check_rows_path}")

if blockers:
    print("\n--- Stage 39A blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 39A warnings ---")
for warning in warnings:
    print(warning)
