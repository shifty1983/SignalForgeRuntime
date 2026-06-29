import json
from pathlib import Path
from collections import defaultdict, Counter

OUT_DIR = Path("artifacts/layer_score_confidence_inventory_20210601_20260531")
OUT_DIR.mkdir(parents=True, exist_ok=True)

INPUTS = {
    "historical_decision_rows": Path("artifacts/historical_decision_rows_20210601_20260531/signalforge_historical_decision_rows.jsonl"),
    "historical_strategy_selection_rows": Path("artifacts/historical_strategy_selection_rows_20210601_20260531/signalforge_historical_strategy_selection_rows.jsonl"),
    "strategy_gate_v1_position_sizing_rows": Path("artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531/signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl"),
    "allocator_v2_30k_canonical_rows": Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/allocator_v2_30k_pf_42100_heat50/allocator_v2_30k_pf_42100_heat50_canonical_position_sizing_replay.jsonl"),
    "allocator_v2_40k_canonical_rows": Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/allocator_v2_40k_pf_42100_heat50/allocator_v2_40k_pf_42100_heat50_canonical_position_sizing_replay.jsonl"),
}

KEYWORDS = [
    "score",
    "confidence",
    "quality",
    "strength",
    "conviction",
    "rank",
    "probability",
    "state",
    "classification",
    "signal",
    "edge",
    "expectancy",
    "regime",
    "behavior",
    "option",
    "construction",
]

def read_jsonl(path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, key))
            else:
                out[key] = v
    return out

def is_candidate_field(name):
    n = name.lower()
    return any(k in n for k in KEYWORDS)

def fnum(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(x)
    except Exception:
        return None

def percentile(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    return vals[int(p * (len(vals) - 1))]

inventory_rows = []
field_examples = {}

for label, path in INPUTS.items():
    rows = list(read_jsonl(path) or [])
    flat_rows = [flatten(r) for r in rows]

    field_counts = Counter()
    non_null_counts = Counter()
    numeric_values = defaultdict(list)
    category_values = defaultdict(Counter)

    for r in flat_rows:
        for field, value in r.items():
            if not is_candidate_field(field):
                continue

            field_counts[field] += 1

            if value is not None and str(value).strip() != "":
                non_null_counts[field] += 1

                n = fnum(value)
                if n is not None:
                    numeric_values[field].append(n)
                else:
                    category_values[field][str(value)[:100]] += 1

                field_examples.setdefault((label, field), value)

    for field in sorted(field_counts):
        nums = numeric_values.get(field, [])
        cats = category_values.get(field, Counter())

        inventory_rows.append({
            "artifact_label": label,
            "path": str(path),
            "file_exists": path.exists(),
            "row_count": len(rows),
            "field": field,
            "field_present_count": field_counts[field],
            "field_non_null_count": non_null_counts[field],
            "non_null_coverage": non_null_counts[field] / len(rows) if rows else 0.0,
            "is_numeric": bool(nums),
            "numeric_min": min(nums) if nums else None,
            "numeric_p25": percentile(nums, 0.25) if nums else None,
            "numeric_median": percentile(nums, 0.50) if nums else None,
            "numeric_p75": percentile(nums, 0.75) if nums else None,
            "numeric_max": max(nums) if nums else None,
            "top_categories": dict(cats.most_common(10)) if cats else None,
            "example_value": field_examples.get((label, field)),
        })

summary = {
    "adapter_type": "layer_score_confidence_inventory_builder",
    "artifact_type": "signalforge_layer_score_confidence_inventory",
    "contract": "layer_score_confidence_inventory",
    "is_ready": True,
    "readiness_state": "ready",
    "input_artifact_count": len(INPUTS),
    "inventory_row_count": len(inventory_rows),
    "inputs": {k: str(v) for k, v in INPUTS.items()},
    "candidate_keywords": KEYWORDS,
    "paths": {
        "summary_path": str(OUT_DIR / "layer_score_confidence_inventory_summary.json"),
        "inventory_rows_path": str(OUT_DIR / "layer_score_confidence_inventory_rows.jsonl"),
    },
}

with (OUT_DIR / "layer_score_confidence_inventory_rows.jsonl").open("w", encoding="utf-8") as f:
    for row in inventory_rows:
        f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")

(OUT_DIR / "layer_score_confidence_inventory_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
    encoding="utf-8"
)

print(json.dumps(summary, indent=2, sort_keys=True, default=str))
