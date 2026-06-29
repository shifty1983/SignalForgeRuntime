import json
from pathlib import Path
from collections import Counter

sizing_path = Path("artifacts/portfolio_position_sizing_replay_search15/signalforge_portfolio_position_sizing_replay.jsonl")
gate_rows_path = Path("artifacts/strategy_eligibility_native_family_gate_audit_v1_20210601_20260531/strategy_eligibility_native_family_gate_test_rows.jsonl")
gate_summary_path = Path("artifacts/strategy_eligibility_native_family_gate_audit_v1_20210601_20260531/strategy_eligibility_native_family_gate_audit_summary.json")

out_dir = Path("artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531")
out_dir.mkdir(parents=True, exist_ok=True)

rows_out_path = out_dir / "signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl"
summary_out_path = out_dir / "signalforge_portfolio_position_sizing_replay_strategy_gate_v1_summary.json"

def read_jsonl(path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def write_jsonl(path, rows):
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
            n += 1
    return n

gate_test_by_id = {
    str(r.get("sequence_id")): r
    for r in read_jsonl(gate_rows_path)
}

gate_summary = json.loads(gate_summary_path.read_text(encoding="utf-8"))

output_rows = []
state_counts = Counter()
gated_strategy_counts = Counter()
sizing_state_counts = Counter()

baseline_realized_pnl_sum = 0.0
gated_removed_pnl_sum = 0.0
kept_realized_pnl_sum = 0.0

for row in read_jsonl(sizing_path):
    out = dict(row)
    seq = str(row.get("sequence_id") or "")
    gate_row = gate_test_by_id.get(seq)

    out["strategy_eligibility_gate_v1"] = {
        "applied": False,
        "gate_type": "prior_window_strategy_family_gate_no_substitution",
        "does_select_strategy": False,
        "does_replace_gated_trades": False,
        "does_feed_result_to_expectancy": False,
        "does_change_exit": False,
        "does_change_position_size": False,
        "uses_prior_window_only_for_gate": True,
    }

    if row.get("sizing_state") == "sized":
        pnl = row.get("realized_pnl_dollars")
        try:
            baseline_realized_pnl_sum += float(pnl)
        except Exception:
            pass

    if gate_row and gate_row.get("eligibility_state") == "gated_off":
        original = dict(row)

        out["strategy_eligibility_gate_v1"] = {
            "applied": True,
            "gate_type": "prior_window_strategy_family_gate_no_substitution",
            "eligibility_state": "gated_off",
            "eligibility_policy": gate_row.get("eligibility_policy"),
            "original_sizing_state": row.get("sizing_state"),
            "original_realized_return": row.get("realized_return"),
            "original_realized_pnl_dollars": row.get("realized_pnl_dollars"),
            "original_portfolio_realization_date": row.get("portfolio_realization_date"),
            "original_outcome_availability_date": row.get("outcome_availability_date"),
            "does_select_strategy": False,
            "does_replace_gated_trades": False,
            "does_feed_result_to_expectancy": False,
            "does_change_exit": False,
            "does_change_position_size": False,
            "uses_prior_window_only_for_gate": True,
        }

        out["sizing_state"] = "skipped"
        out["selection_state"] = "strategy_family_gated_off"
        out["selected_outcome_state"] = "gated_off"
        out["realized_return"] = None
        out["realized_pnl_dollars"] = None
        out["portfolio_realization_date"] = row.get("decision_date")
        out["outcome_availability_date"] = None
        out["realization_date_source"] = "strategy_eligibility_gate_v1_no_trade"
        out["sizing_skip_reasons"] = list(row.get("sizing_skip_reasons") or []) + [
            "strategy_family_gated_off_prior_window_evidence"
        ]

        state_counts["gated_off"] += 1
        gated_strategy_counts[str(row.get("selected_strategy") or "unknown")] += 1

        try:
            gated_removed_pnl_sum += float(original.get("realized_pnl_dollars"))
        except Exception:
            pass

    else:
        if row.get("sizing_state") == "sized":
            state_counts["kept_sized"] += 1
            try:
                kept_realized_pnl_sum += float(row.get("realized_pnl_dollars"))
            except Exception:
                pass
        else:
            state_counts["kept_skipped"] += 1

    sizing_state_counts[str(out.get("sizing_state"))] += 1
    output_rows.append(out)

write_jsonl(rows_out_path, output_rows)

summary = {
    "adapter_type": "strategy_eligibility_gate_position_sizing_replay_builder",
    "artifact_type": "signalforge_portfolio_position_sizing_replay_strategy_gate_v1",
    "contract": "portfolio_position_sizing_replay",
    "is_ready": True,
    "readiness_state": "ready_for_equity_reconstruction",
    "input_row_count": len(output_rows),
    "output_row_count": len(output_rows),
    "row_state_counts": dict(state_counts),
    "sizing_state_counts": dict(sizing_state_counts),
    "gated_strategy_counts": dict(gated_strategy_counts),
    "baseline_realized_pnl_sum": baseline_realized_pnl_sum,
    "kept_realized_pnl_sum": kept_realized_pnl_sum,
    "gated_removed_pnl_sum": gated_removed_pnl_sum,
    "expected_delta_pnl_no_substitution": -gated_removed_pnl_sum,
    "source_gate_audit": gate_summary,
    "policy": {
        "does_select_strategy": False,
        "does_replace_gated_trades": False,
        "does_feed_result_to_expectancy": False,
        "does_change_exit": False,
        "does_change_position_size": False,
        "uses_prior_window_only_for_gate": True,
        "no_substitution_conservative_test": True,
        "production_candidate": True,
    },
    "paths": {
        "rows_path": str(rows_out_path),
        "summary_path": str(summary_out_path),
    },
}

summary_out_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True, default=str))
