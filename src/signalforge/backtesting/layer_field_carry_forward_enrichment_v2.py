import json
import os
from pathlib import Path
from collections import defaultdict, Counter

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_OUT_DIR",
    "artifacts/layer_field_carry_forward_enrichment_v2_20210601_20260531",
))
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_PATH = Path(os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_BASE_PATH",
    "artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531/signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl",
))
SELECTION_PATH = Path(os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_SELECTION_PATH",
    "artifacts/historical_strategy_selection_rows_20210601_20260531/signalforge_historical_strategy_selection_rows.jsonl",
))
DECISION_PATH = Path(os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_DECISION_PATH",
    "artifacts/historical_decision_rows_20210601_20260531/signalforge_historical_decision_rows.jsonl",
))

ENRICHED_ROWS_PATH = OUT_DIR / os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_ROWS_NAME",
    "signalforge_layer_enriched_position_sizing_rows_v2.jsonl",
)
SUMMARY_PATH = OUT_DIR / os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_SUMMARY_NAME",
    "layer_field_carry_forward_enrichment_v2_summary.json",
)
UNMATCHED_SAMPLE_PATH = OUT_DIR / os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_UNMATCHED_NAME",
    "layer_field_unmatched_sample_v2.jsonl",
)

LEGACY_V1_MODE = os.environ.get(
    "SIGNALFORGE_LAYER_ENRICHMENT_LEGACY_V1",
    "",
).strip().lower() in {"1", "true", "yes", "y"}

LAYER_FIELDS = [
    "regime_state",
    "regime_source_date",
    "regime_source_state",
    "regime_asof_lag_days",

    "asset_behavior_state",
    "asset_behavior_source_date",
    "asset_behavior_source_state",

    "option_behavior_state",
    "option_behavior_source_date",
    "option_behavior_source_state",
    "option_iv_level",
    "option_liquidity_state",

    "term_structure_shape",
    "term_structure_state",
    "front_iv",
    "back_iv",
    "front_back_iv_spread",
    "front_back_iv_spread_pct",
    "front_dte",
    "back_dte",
]

def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")

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

def pick(flat, keys, default=None):
    for k in keys:
        v = flat.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return default

def clean(x):
    if x is None or str(x).strip() == "":
        return None
    return str(x).strip()

def fnum(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(x)
    except Exception:
        return None

def norm_date(x):
    if x is None:
        return None
    return str(x)[:10]

def decision_date_from(flat):
    return norm_date(pick(flat, [
        "decision_date",
        "date",
        "source_candidate.decision_date",
    ]))

def symbol_from(flat):
    return clean(pick(flat, [
        "symbol",
        "source_candidate.symbol",
    ]))

def strategy_from(flat):
    return clean(pick(flat, [
        "selected_strategy",
        "strategy",
        "strategy_family",
        "selected_strategy_family",
        "source_candidate.selected_strategy",
        "source_candidate.strategy",
    ]))

def round_num(x, places=8):
    n = fnum(x)
    if n is None:
        return None
    return round(n, places)

def expectancy_score_from(flat):
    return round_num(pick(flat, [
        "selected_expectancy_score",
        "source_candidate.selected_expectancy_score",
    ]), 8)

def expectancy_sample_from(flat):
    return round_num(pick(flat, [
        "selected_expectancy_sample_count",
        "source_candidate.selected_expectancy_sample_count",
    ]), 0)

def key_candidates(flat):
    keys = []

    for k in [
        "sequence_id",
        "source_sequence_reference",
        "trade_key",
        "selection_id",
        "strategy_selection_id",
        "position_sizing_id",
        "replay_index",
        "sequence_index",
        "source_candidate.sequence_id",
        "source_candidate.trade_key",
    ]:
        v = pick(flat, [k])
        if v is not None and str(v).strip() != "":
            keys.append((f"exact_{k}", str(v)))

    d = decision_date_from(flat)
    s = symbol_from(flat)
    st = strategy_from(flat)
    score = expectancy_score_from(flat)
    sample = expectancy_sample_from(flat)

    if d and s and st and score is not None and sample is not None:
        keys.append(("date_symbol_strategy_score_sample", f"{d}|{s}|{st}|{score}|{sample}"))

    if d and s and st and score is not None:
        keys.append(("date_symbol_strategy_score", f"{d}|{s}|{st}|{score}"))

    if d and s and st and sample is not None:
        keys.append(("date_symbol_strategy_sample", f"{d}|{s}|{st}|{sample}"))

    if d and s and st:
        keys.append(("date_symbol_strategy", f"{d}|{s}|{st}"))

    if d and s:
        keys.append(("date_symbol", f"{d}|{s}"))

    return keys

def derive_iv_level(option_behavior_state):
    s = clean(option_behavior_state)
    if not s:
        return None
    if s.startswith("iv_high"):
        return "high"
    if s.startswith("iv_low"):
        return "low"
    if s.startswith("iv_moderate"):
        return "moderate"
    return None

def derive_liquidity_state(option_behavior_state):
    s = clean(option_behavior_state)
    if not s:
        return None
    if "moderate_liquidity" in s:
        return "moderate_liquidity"
    if "illiquid" in s or "sparse" in s:
        return "illiquid_or_sparse"
    if "liquid" in s:
        return "liquid"
    return None

def payload_from_selection(flat):
    p = {
        "regime_state": pick(flat, [
            "regime_state",
            "source_candidate.regime_state",
            "source_candidate.regime.state",
            "regime.state",
        ]),
        "regime_source_date": pick(flat, [
            "regime_source_date",
            "source_candidate.regime_source_date",
            "source_candidate.regime.source_date",
            "regime.source_date",
        ]),
        "regime_source_state": pick(flat, [
            "regime_source_state",
            "source_candidate.regime.source_state",
            "regime.source_state",
        ]),
        "regime_asof_lag_days": pick(flat, [
            "regime_asof_lag_days",
            "source_candidate.regime.asof_lag_days",
            "regime.asof_lag_days",
        ]),

        "asset_behavior_state": pick(flat, [
            "asset_behavior_state",
            "source_candidate.asset_behavior_state",
            "source_candidate.asset_behavior.state",
            "asset_behavior.state",
        ]),
        "asset_behavior_source_date": pick(flat, [
            "asset_behavior_source_date",
            "source_candidate.asset_behavior_source_date",
            "source_candidate.asset_behavior.source_date",
            "asset_behavior.source_date",
        ]),
        "asset_behavior_source_state": pick(flat, [
            "asset_behavior_source_state",
            "source_candidate.asset_behavior.source_state",
            "asset_behavior.source_state",
        ]),

        "option_behavior_state": pick(flat, [
            "option_behavior_state",
            "source_candidate.option_behavior_state",
            "source_candidate.option_behavior.state",
            "option_behavior.state",
        ]),
        "option_behavior_source_date": pick(flat, [
            "option_behavior_source_date",
            "source_candidate.option_behavior_source_date",
            "source_candidate.option_behavior.source_date",
            "option_behavior.source_date",
        ]),
        "option_behavior_source_state": pick(flat, [
            "option_behavior_source_state",
            "source_candidate.option_behavior.source_state",
            "option_behavior.source_state",
        ]),
        "option_iv_level": pick(flat, [
            "option_iv_level",
            "source_candidate.option_iv_level",
        ]),
        "option_liquidity_state": pick(flat, [
            "option_liquidity_state",
            "source_candidate.option_liquidity_state",
        ]),

        "term_structure_shape": pick(flat, [
            "term_structure_shape",
            "source_candidate.option_behavior.term_structure_shape",
            "option_behavior.term_structure_shape",
        ]),
        "term_structure_state": pick(flat, [
            "term_structure_state",
            "source_candidate.option_behavior.term_structure_state",
            "option_behavior.term_structure_state",
        ]),
        "front_iv": pick(flat, [
            "front_iv",
            "source_candidate.option_behavior.front_iv",
            "option_behavior.front_iv",
        ]),
        "back_iv": pick(flat, [
            "back_iv",
            "source_candidate.option_behavior.back_iv",
            "option_behavior.back_iv",
        ]),
        "front_back_iv_spread": pick(flat, [
            "front_back_iv_spread",
            "source_candidate.option_behavior.front_back_iv_spread",
            "option_behavior.front_back_iv_spread",
        ]),
        "front_back_iv_spread_pct": pick(flat, [
            "front_back_iv_spread_pct",
            "source_candidate.option_behavior.front_back_iv_spread_pct",
            "option_behavior.front_back_iv_spread_pct",
        ]),
        "front_dte": pick(flat, [
            "front_dte",
            "source_candidate.option_behavior.front_dte",
            "option_behavior.front_dte",
        ]),
        "back_dte": pick(flat, [
            "back_dte",
            "source_candidate.option_behavior.back_dte",
            "option_behavior.back_dte",
        ]),
    }

    if not clean(p.get("option_iv_level")):
        p["option_iv_level"] = derive_iv_level(p.get("option_behavior_state"))

    if not clean(p.get("option_liquidity_state")):
        p["option_liquidity_state"] = derive_liquidity_state(p.get("option_behavior_state"))

    return p

def payload_from_decision(flat):
    p = {
        "regime_state": pick(flat, ["regime.state"]),
        "regime_source_date": pick(flat, ["regime.source_date"]),
        "regime_source_state": pick(flat, ["regime.source_state"]),
        "regime_asof_lag_days": pick(flat, ["regime.asof_lag_days"]),

        "asset_behavior_state": pick(flat, ["asset_behavior.state"]),
        "asset_behavior_source_date": pick(flat, ["asset_behavior.source_date"]),
        "asset_behavior_source_state": pick(flat, ["asset_behavior.source_state"]),

        "option_behavior_state": pick(flat, ["option_behavior.state"]),
        "option_behavior_source_date": pick(flat, ["option_behavior.source_date"]),
        "option_behavior_source_state": pick(flat, ["option_behavior.source_state"]),

        "term_structure_shape": pick(flat, ["option_behavior.term_structure_shape"]),
        "term_structure_state": pick(flat, ["option_behavior.term_structure_state"]),
        "front_iv": pick(flat, ["option_behavior.front_iv"]),
        "back_iv": pick(flat, ["option_behavior.back_iv"]),
        "front_back_iv_spread": pick(flat, ["option_behavior.front_back_iv_spread"]),
        "front_back_iv_spread_pct": pick(flat, ["option_behavior.front_back_iv_spread_pct"]),
        "front_dte": pick(flat, ["option_behavior.front_dte"]),
        "back_dte": pick(flat, ["option_behavior.back_dte"]),
    }

    p["option_iv_level"] = derive_iv_level(p.get("option_behavior_state"))
    p["option_liquidity_state"] = derive_liquidity_state(p.get("option_behavior_state"))

    return p

def build_selection_index(rows):
    temp = defaultdict(list)

    for raw in rows:
        flat = flatten(raw)
        for method, key in key_candidates(flat):
            temp[(method, key)].append(flat)

    unique = {}
    duplicates = Counter()

    for k, vals in temp.items():
        if len(vals) == 1:
            unique[k] = vals[0]
        else:
            duplicates[k[0]] += 1

    return unique, duplicates

def build_decision_index(rows):
    temp = defaultdict(list)

    for raw in rows:
        flat = flatten(raw)
        d = decision_date_from(flat)
        s = symbol_from(flat)
        if d and s:
            temp[f"{d}|{s}"].append(flat)

    unique = {}
    duplicate_count = 0

    for k, vals in temp.items():
        if len(vals) == 1:
            unique[k] = vals[0]
        else:
            duplicate_count += 1

    return unique, duplicate_count



def main() -> int:
    base_rows_raw = read_jsonl(BASE_PATH)
    selection_rows_raw = read_jsonl(SELECTION_PATH)
    decision_rows_raw = read_jsonl(DECISION_PATH)

    base_sized_rows = [r for r in base_rows_raw if r.get("sizing_state") == "sized"]

    selection_index, selection_duplicate_index = build_selection_index(selection_rows_raw)
    decision_index, decision_duplicate_count = build_decision_index(decision_rows_raw)

    match_counts = Counter()
    enriched_rows = []
    unmatched = []

    for raw in base_sized_rows:
        flat = flatten(raw)

        payload = {}
        selection_match = None
        selection_method = None
        selection_key = None

        for method, key in key_candidates(flat):
            candidate = selection_index.get((method, key))
            if candidate is not None:
                selection_match = candidate
                selection_method = method
                selection_key = key
                break

        if selection_match is not None:
            payload.update(payload_from_selection(selection_match))
            if LEGACY_V1_MODE:
                match_counts[selection_method] += 1
            else:
                match_counts[f"selection:{selection_method}"] += 1

        d = decision_date_from(flat)
        s = symbol_from(flat)
        decision_match = None
        if not LEGACY_V1_MODE:
            decision_match = decision_index.get(f"{d}|{s}") if d and s else None

        # Fill missing fields from historical_decision_rows fallback.
        decision_used = False
        if decision_match is not None:
            decision_payload = payload_from_decision(decision_match)
            for field in LAYER_FIELDS:
                if payload.get(field) is None or str(payload.get(field)).strip() == "":
                    payload[field] = decision_payload.get(field)
                    if decision_payload.get(field) is not None and str(decision_payload.get(field)).strip() != "":
                        decision_used = True

        if decision_used:
            match_counts["decision_fallback_used"] += 1

        if selection_match is None and decision_match is not None:
            match_counts["decision_only_match"] += 1

        if selection_match is None and decision_match is None:
            match_counts["unmatched"] += 1
            unmatched.append({
                "decision_date": d,
                "symbol": s,
                "selected_strategy": strategy_from(flat),
                "selected_expectancy_score": pick(flat, ["selected_expectancy_score"]),
                "selected_expectancy_sample_count": pick(flat, ["selected_expectancy_sample_count"]),
                "sequence_id": pick(flat, ["sequence_id"]),
                "trade_key": pick(flat, ["trade_key"]),
            })

        out = dict(raw)
        out["layer_field_carry_forward_v2"] = {
            "selection_matched": selection_match is not None,
            "selection_match_method": selection_method,
            "selection_match_key": selection_key,
            "decision_matched": decision_match is not None,
            "decision_fallback_used": decision_used,
        }

        for field in LAYER_FIELDS:
            out[field] = payload.get(field)

        enriched_rows.append(out)

    coverage = []

    for field in LAYER_FIELDS:
        values = [
            r.get(field) for r in enriched_rows
            if r.get(field) is not None and str(r.get(field)).strip() != ""
        ]
        nums = [fnum(v) for v in values if fnum(v) is not None]

        coverage.append({
            "field": field,
            "non_missing_count": len(values),
            "coverage": len(values) / len(enriched_rows) if enriched_rows else 0.0,
            "is_numeric": bool(nums),
            "numeric_min": min(nums) if nums else None,
            "numeric_median": sorted(nums)[len(nums)//2] if nums else None,
            "numeric_max": max(nums) if nums else None,
            "top_values": dict(Counter(str(v) for v in values).most_common(10)),
        })

    construction_non_missing = sum(
        1 for r in enriched_rows
        if r.get("construction_quality") is not None and str(r.get("construction_quality")).strip() != ""
    )

    required_coverage = {
        "regime_state": next(x["coverage"] for x in coverage if x["field"] == "regime_state"),
        "asset_behavior_state": next(x["coverage"] for x in coverage if x["field"] == "asset_behavior_state"),
        "option_behavior_state": next(x["coverage"] for x in coverage if x["field"] == "option_behavior_state"),
        "option_iv_level": next(x["coverage"] for x in coverage if x["field"] == "option_iv_level"),
        "option_liquidity_state": next(x["coverage"] for x in coverage if x["field"] == "option_liquidity_state"),
        "construction_quality": construction_non_missing / len(enriched_rows) if enriched_rows else 0.0,
    }

    production_ready_layer_coverage = all(v >= 0.95 for v in required_coverage.values())
    research_ready_layer_coverage = all(v >= 0.75 for v in required_coverage.values())

    rows_to_write = enriched_rows

    if LEGACY_V1_MODE:
        legacy_v2_only_fields = {
            "asset_behavior_source_state",
            "layer_field_carry_forward_v2",
            "option_behavior_source_state",
            "regime_asof_lag_days",
            "regime_source_state",
        }

        rows_to_write = []
        for enriched_row in enriched_rows:
            legacy_row = dict(enriched_row)
            meta = legacy_row.get("layer_field_carry_forward_v2") or {}

            for excluded_field in legacy_v2_only_fields:
                legacy_row.pop(excluded_field, None)

            legacy_row["layer_field_carry_forward_v1"] = {
                "match_key": meta.get("selection_match_key"),
                "match_method": meta.get("selection_match_method"),
                "matched_selection": bool(meta.get("selection_matched")),
            }

            rows_to_write.append(legacy_row)

    write_jsonl(ENRICHED_ROWS_PATH, rows_to_write)
    write_jsonl(UNMATCHED_SAMPLE_PATH, unmatched[:500])

    summary = {
        "adapter_type": "layer_field_carry_forward_enrichment_v2_builder",
        "artifact_type": "signalforge_layer_field_carry_forward_enrichment_v2",
        "contract": "layer_field_carry_forward_enrichment_v2",
        "is_ready": True,
        "readiness_state": "ready",

        "base_raw_row_count": len(base_rows_raw),
        "base_sized_row_count": len(base_sized_rows),
        "selection_row_count": len(selection_rows_raw),
        "decision_row_count": len(decision_rows_raw),

        "selection_unique_index_key_count": len(selection_index),
        "selection_duplicate_index_key_count_by_method": dict(selection_duplicate_index),
        "decision_unique_index_key_count": len(decision_index),
        "decision_duplicate_key_count": decision_duplicate_count,

        "match_counts_by_method": dict(match_counts),
        "selection_matched_count": sum(
            1 for r in enriched_rows
            if r["layer_field_carry_forward_v2"]["selection_matched"]
        ),
        "decision_matched_count": sum(
            1 for r in enriched_rows
            if r["layer_field_carry_forward_v2"]["decision_matched"]
        ),
        "any_matched_count": sum(
            1 for r in enriched_rows
            if r["layer_field_carry_forward_v2"]["selection_matched"]
            or r["layer_field_carry_forward_v2"]["decision_matched"]
        ),
        "unmatched_count": match_counts["unmatched"],
        "any_matched_rate": (
            sum(
                1 for r in enriched_rows
                if r["layer_field_carry_forward_v2"]["selection_matched"]
                or r["layer_field_carry_forward_v2"]["decision_matched"]
            ) / len(enriched_rows)
            if enriched_rows else 0.0
        ),

        "field_coverage": coverage,
        "required_coverage": required_coverage,
        "production_ready_layer_coverage": production_ready_layer_coverage,
        "research_ready_layer_coverage": research_ready_layer_coverage,
        "decision": (
            "ready_for_allocator_v3_bucket_research_and_candidate_testing"
            if production_ready_layer_coverage
            else "research_only_allocator_v3_not_promotable"
            if research_ready_layer_coverage
            else "coverage_insufficient_fix_upstream_carry_forward"
        ),
        "paths": {
            "enriched_rows_path": str(ENRICHED_ROWS_PATH),
            "summary_path": str(SUMMARY_PATH),
            "unmatched_sample_path": str(UNMATCHED_SAMPLE_PATH),
        },
        "policy": {
            "uses_historical_decision_rows_as_layer_field_fallback": True,
            "does_not_change_expectancy": True,
            "does_not_change_exit": True,
            "does_not_change_sizing": True,
            "purpose": "recover layer fields for allocator v3 bucket-definition testing",
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


