import json
from pathlib import Path

OUT_DIR = Path("docs/paper_candidate_handoff")
ARTIFACTS = Path("artifacts")
CANONICAL = Path("data/canonical/signalforge_pipeline")

CATEGORIES = {
    "strategy_selection": ["historical_strategy_selection", "strategy_selection", "candidate_selection"],
    "selected_trade_sequence": ["selected_trade_sequence"],
    "position_sizing": ["position_sizing"],
    "execution_translation": ["execution_translation", "translation_rulebook", "deployment_readiness"],
    "portfolio_reconstruction": ["equity_reconstruction", "metrics_report", "portfolio_metrics"],
    "capital_sufficiency": ["capital_sufficiency"],
    "paper_candidate_lock": ["paper_candidate", "candidate_lock", "ruleset_lock"],
}

def read_json_safe(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"__read_error__": str(exc)}

def classify(name):
    text = name.lower()
    hits = []
    for category, terms in CATEGORIES.items():
        if any(term in text for term in terms):
            hits.append(category)
    return hits

rows = []
blockers = []
warnings = [
    "stage38d_fast_top_level_locator_only",
    "does_not_read_large_row_files",
    "paper_review_artifact_locator_does_not_create_orders",
]

if not ARTIFACTS.exists():
    blockers.append(f"missing_artifacts_root_{ARTIFACTS}")

roots = []
if ARTIFACTS.exists():
    roots.extend([p for p in ARTIFACTS.iterdir() if p.is_dir()])

if CANONICAL.exists():
    roots.extend([p for p in CANONICAL.iterdir() if p.is_dir()])

for root in sorted(roots, key=lambda p: str(p).lower()):
    categories = classify(root.name)
    if not categories:
        continue

    json_summaries = sorted([
        p for p in root.glob("*.json")
        if "summary" in p.name.lower()
        or "manifest" in p.name.lower()
        or "lock" in p.name.lower()
        or "rulebook" in p.name.lower()
    ])

    for summary_path in json_summaries[:10]:
        data = read_json_safe(summary_path)
        rows.append({
            "category": categories,
            "root": str(root),
            "summary_path": str(summary_path),
            "exists": summary_path.exists(),
            "size_bytes": summary_path.stat().st_size if summary_path.exists() else None,
            "is_ready": data.get("is_ready") if isinstance(data, dict) else None,
            "artifact_type": data.get("artifact_type") if isinstance(data, dict) else None,
            "contract": data.get("contract") if isinstance(data, dict) else None,
            "paper_candidate_id": data.get("paper_candidate_id") if isinstance(data, dict) else None,
            "live_trade_supported": data.get("live_trade_supported") if isinstance(data, dict) else None,
            "paper_trade_supported": data.get("paper_trade_supported") if isinstance(data, dict) else None,
        })

category_counts = {}
ready_counts = {}

for row in rows:
    for category in row["category"]:
        category_counts[category] = category_counts.get(category, 0) + 1
        if row["is_ready"] is True:
            ready_counts[category] = ready_counts.get(category, 0) + 1

missing_categories = [
    category for category in CATEGORIES
    if category_counts.get(category, 0) == 0
]

if "selected_trade_sequence" in missing_categories:
    warnings.append("selected_trade_sequence_summary_not_found_in_fast_locator")
if "position_sizing" in missing_categories:
    warnings.append("position_sizing_summary_not_found_in_fast_locator")
if "execution_translation" in missing_categories:
    warnings.append("execution_translation_summary_not_found_in_fast_locator")

summary = {
    "adapter_type": "fast_paper_review_artifact_locator",
    "artifact_type": "signalforge_fast_paper_review_artifact_locator",
    "contract": "fast_paper_review_artifact_locator",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "artifact_root": str(ARTIFACTS),
    "canonical_root": str(CANONICAL),
    "located_summary_count": len(rows),
    "category_counts": category_counts,
    "ready_counts": ready_counts,
    "missing_categories": missing_categories,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage38d_fast_paper_review_artifact_locator_summary.json"
rows_path = OUT_DIR / "signalforge_stage38d_fast_paper_review_artifact_locator_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with rows_path.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 38D fast paper review artifact locator compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "located_summary_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 38D category counts ---")
print(json.dumps(category_counts, indent=2, default=str))

print("\n--- Stage 38D ready counts ---")
print(json.dumps(ready_counts, indent=2, default=str))

print("\n--- Stage 38D missing categories ---")
print(json.dumps(missing_categories, indent=2, default=str))

print("\n--- Stage 38D located rows compact ---")
print("category\tis_ready\tartifact_type\tcontract\tsummary_path")
for row in rows:
    print(
        f"{','.join(row['category'])}\t{row['is_ready']}\t"
        f"{row['artifact_type']}\t{row['contract']}\t{row['summary_path']}"
    )

print(f"\nsummary_path: {summary_path}")
print(f"rows_path: {rows_path}")

if blockers:
    print("\n--- Stage 38D blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 38D warnings ---")
for warning in warnings:
    print(warning)
