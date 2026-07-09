import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")
HANDOFF_PATH = Path("configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json")

CATEGORY_TERMS = {
    "expectancy": ["expectancy", "expected_value", "walk_forward"],
    "strategy_selection": ["strategy_selection", "selected_strategy", "candidate_selection", "selection_rows"],
    "selected_trade_sequence": ["selected_trade_sequence", "trade_sequence"],
    "position_sizing": ["position_sizing", "sizing", "capital"],
    "execution_translation": ["execution_translation", "translation_rulebook", "deployment_readiness", "execution_gap"],
    "portfolio_construction": ["portfolio_construction", "allocator", "allocation"],
    "portfolio_reconstruction": ["equity_reconstruction", "metrics_report", "portfolio_metrics"],
    "paper_candidate_lock": ["paper_candidate", "candidate_lock", "ruleset_lock"],
}

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def flatten(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.append({"field": path, "value": item})
            rows.extend(flatten(item, path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            rows.extend(flatten(item, f"{prefix}[{idx}]"))
    return rows

def is_path_like(value):
    if not isinstance(value, str):
        return False
    text = value.replace("\\", "/")
    return (
        "/" in text
        or text.startswith("artifacts")
        or text.startswith("data")
        or text.startswith("docs")
        or text.startswith("configs")
        or text.endswith((".json", ".jsonl", ".md", ".csv", ".parquet"))
    )

def classify(row):
    haystack = f"{row['field']} {row['value']}".lower()
    hits = []
    for category, terms in CATEGORY_TERMS.items():
        if any(term in haystack for term in terms):
            hits.append(category)
    return hits or ["uncategorized"]

blockers = []
warnings = [
    "stage38c_fast_inventory_only",
    "paper_review_bundle_inventory_does_not_create_orders",
]

if not HANDOFF_PATH.exists():
    blockers.append(f"missing_handoff_contract_{HANDOFF_PATH}")

handoff = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}
flat_rows = flatten(handoff)

path_rows = []
for row in flat_rows:
    if is_path_like(row["value"]):
        p = Path(row["value"])
        cats = classify(row)
        path_rows.append({
            "field": row["field"],
            "value": row["value"],
            "categories": cats,
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else None,
        })

category_counts = {}
category_existing_counts = {}
category_missing_counts = {}

for row in path_rows:
    for cat in row["categories"]:
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if row["exists"]:
            category_existing_counts[cat] = category_existing_counts.get(cat, 0) + 1
        else:
            category_missing_counts[cat] = category_missing_counts.get(cat, 0) + 1

expectancy_block = handoff.get("expectancy_snapshot_adapter") if isinstance(handoff, dict) else None

checks = [
    {
        "check": "handoff_contract_exists",
        "expected": True,
        "actual": HANDOFF_PATH.exists(),
        "passed": HANDOFF_PATH.exists(),
    },
    {
        "check": "expectancy_snapshot_adapter_present",
        "expected": True,
        "actual": isinstance(expectancy_block, dict),
        "passed": isinstance(expectancy_block, dict),
    },
    {
        "check": "expectancy_source_rows_exists",
        "expected": True,
        "actual": Path(expectancy_block.get("source_rows_path", "")).exists() if isinstance(expectancy_block, dict) else None,
        "passed": isinstance(expectancy_block, dict) and Path(expectancy_block.get("source_rows_path", "")).exists(),
    },
    {
        "check": "expectancy_source_summary_exists",
        "expected": True,
        "actual": Path(expectancy_block.get("source_summary_path", "")).exists() if isinstance(expectancy_block, dict) else None,
        "passed": isinstance(expectancy_block, dict) and Path(expectancy_block.get("source_summary_path", "")).exists(),
    },
    {
        "check": "trade_authorization_guard",
        "expected": "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
        "actual": expectancy_block.get("trade_authorization") if isinstance(expectancy_block, dict) else None,
        "passed": isinstance(expectancy_block, dict) and expectancy_block.get("trade_authorization") == "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
    },
]

failed = [row["check"] for row in checks if row["passed"] is not True]
if failed:
    blockers.append(f"failed_checks_{failed}")

summary = {
    "adapter_type": "paper_review_bundle_inventory_builder",
    "artifact_type": "signalforge_paper_review_bundle_inventory",
    "contract": "paper_review_bundle_inventory",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "handoff_path": str(HANDOFF_PATH),
    "path_row_count": len(path_rows),
    "category_counts": category_counts,
    "category_existing_counts": category_existing_counts,
    "category_missing_counts": category_missing_counts,
    "checks": checks,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage38c_paper_review_bundle_inventory_summary.json"
rows_path = OUT_DIR / "signalforge_stage38c_paper_review_bundle_inventory_path_rows.jsonl"
check_rows_path = OUT_DIR / "signalforge_stage38c_paper_review_bundle_inventory_check_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with rows_path.open("w", encoding="utf-8") as f:
    for row in path_rows:
        f.write(json.dumps(row, default=str) + "\n")

with check_rows_path.open("w", encoding="utf-8") as f:
    for row in checks:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 38C paper review bundle inventory compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "path_row_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 38C category counts ---")
print(json.dumps(category_counts, indent=2, default=str))

print("\n--- Stage 38C existing counts ---")
print(json.dumps(category_existing_counts, indent=2, default=str))

print("\n--- Stage 38C missing counts ---")
print(json.dumps(category_missing_counts, indent=2, default=str))

print("\n--- Stage 38C checks compact ---")
print("check\texpected\tactual\tpassed")
for row in checks:
    print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

print(f"\nsummary_path: {summary_path}")
print(f"rows_path: {rows_path}")
print(f"check_rows_path: {check_rows_path}")

if blockers:
    print("\n--- Stage 38C blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38C warnings ---")
for warning in warnings:
    print(warning)
