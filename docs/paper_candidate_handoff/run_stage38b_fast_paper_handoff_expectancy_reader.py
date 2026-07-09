import importlib
import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")

HANDOFF_PATH = Path("configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json")

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

blockers = []
warnings = [
    "stage38b_fast_smoke_only",
    "expectancy_adapter_does_not_authorize_trades",
    "expected_value_scoring_remains_review_handoff",
]

if not HANDOFF_PATH.exists():
    blockers.append(f"missing_handoff_contract_{HANDOFF_PATH}")

handoff = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}
patch = handoff.get("expectancy_snapshot_adapter")

if not isinstance(patch, dict):
    blockers.append("missing_expectancy_snapshot_adapter_block")

runtime = {}

if not blockers:
    rows_path = Path(patch["source_rows_path"])
    summary_path = Path(patch["source_summary_path"])

    if not rows_path.exists():
        blockers.append(f"missing_source_rows_{rows_path}")

    if not summary_path.exists():
        blockers.append(f"missing_source_summary_{summary_path}")

    if not blockers:
        source_summary = read_json(summary_path)
        source_rows = read_jsonl(rows_path)

        adapter_module = importlib.import_module(patch["adapter_module"])
        adapter_func = getattr(adapter_module, patch["adapter_entrypoint"])

        consumer_module = importlib.import_module(patch["consumer_module"])
        consumer_func = getattr(consumer_module, patch["consumer_entrypoint"])

        adapter_artifact = adapter_func(
            source_rows,
            source_rows_path=str(rows_path),
            source_summary_path=str(summary_path),
        )

        ev_artifact = consumer_func(adapter_artifact)

        runtime = {
            "source_summary_ready": source_summary.get("is_ready"),
            "source_row_count": len(source_rows),
            "adapter_contract": adapter_artifact.get("contract"),
            "adapter_ready": adapter_artifact.get("is_ready"),
            "adapter_output_item_count": adapter_artifact.get("output_item_count"),
            "ev_contract": ev_artifact.get("contract"),
            "ev_status": ev_artifact.get("status"),
            "ev_is_ready": ev_artifact.get("is_ready"),
            "ev_requires_manual_approval": ev_artifact.get("requires_manual_approval"),
            "ev_order_intent": ev_artifact.get("order_intent"),
            "paper_rule": patch.get("paper_rule"),
            "trade_authorization": patch.get("trade_authorization"),
        }

        checks = {
            "source_summary_ready": runtime["source_summary_ready"] is True,
            "adapter_ready": runtime["adapter_ready"] is True,
            "adapter_count_matches_source": runtime["adapter_output_item_count"] == runtime["source_row_count"],
            "ev_status_review": runtime["ev_status"] == "needs_review",
            "ev_requires_manual_approval": runtime["ev_requires_manual_approval"] is True,
            "ev_no_order_intent": runtime["ev_order_intent"] is None,
            "trade_not_authorized": runtime["trade_authorization"] == "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
        }

        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            blockers.append(f"failed_checks_{failed}")

summary = {
    "adapter_type": "fast_paper_handoff_expectancy_reader_smoke",
    "artifact_type": "signalforge_fast_paper_handoff_expectancy_reader_smoke",
    "contract": "fast_paper_handoff_expectancy_reader_smoke",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "handoff_path": str(HANDOFF_PATH),
    "patch_present": isinstance(patch, dict),
    "runtime": runtime,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage38b_fast_paper_handoff_expectancy_reader_summary.json"
summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

print("\n--- Stage 38B fast paper handoff expectancy reader compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "patch_present",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 38B runtime compact ---")
for key, value in runtime.items():
    print(f"{key}: {value}")

print(f"\nsummary_path: {summary_path}")

if blockers:
    print("\n--- Stage 38B blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38B warnings ---")
for warning in warnings:
    print(warning)
