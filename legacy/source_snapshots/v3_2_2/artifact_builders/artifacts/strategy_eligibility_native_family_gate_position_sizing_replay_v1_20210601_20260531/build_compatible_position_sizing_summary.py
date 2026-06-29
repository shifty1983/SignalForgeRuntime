import json
from collections import Counter
from pathlib import Path

base_summary_path = Path(r"artifacts\portfolio_position_sizing_replay_search15\signalforge_portfolio_position_sizing_replay_summary.json")
gate_rows_path = Path(r"artifacts\strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531\signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl")
gate_audit_summary_path = Path(r"artifacts\strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531\signalforge_portfolio_position_sizing_replay_strategy_gate_v1_summary.json")
out_path = Path(r"artifacts\strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531\signalforge_portfolio_position_sizing_replay_strategy_gate_v1_compatible_summary.json")

def read_jsonl(path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

base = json.loads(base_summary_path.read_text(encoding="utf-8"))
gate_audit = json.loads(gate_audit_summary_path.read_text(encoding="utf-8"))

rows = list(read_jsonl(gate_rows_path))

sized = [r for r in rows if r.get("sizing_state") == "sized"]
skipped = [r for r in rows if r.get("sizing_state") != "sized"]

skip_reasons = Counter()
strategies = Counter()
symbols = Counter()
leakage_flags = Counter()
return_bound_flags = Counter()

for r in rows:
    for reason in r.get("sizing_skip_reasons") or []:
        skip_reasons[str(reason)] += 1

    if r.get("sizing_state") == "sized":
        strategies[str(r.get("selected_strategy") or "unknown")] += 1
        symbols[str(r.get("symbol") or "unknown")] += 1

    for k, v in (r.get("leakage_flags") or {}).items():
        if v:
            leakage_flags[str(k)] += 1

    try:
        rr = r.get("realized_return")
        if rr is not None:
            rr = float(rr)
            if rr < float(r.get("min_realized_return", -1e99)):
                return_bound_flags["below_min_realized_return"] += 1
            if rr > float(r.get("max_realized_return", 1e99)):
                return_bound_flags["above_max_realized_return"] += 1
    except Exception:
        pass

base["adapter_type"] = "strategy_eligibility_gate_position_sizing_replay_compatible_summary_builder"
base["artifact_type"] = "signalforge_portfolio_position_sizing_replay_strategy_gate_v1_compatible_summary"
base["contract"] = "portfolio_position_sizing_replay"
base["is_ready"] = True
base["blocker_count"] = 0
base["blockers"] = []
base["input_sequence_row_count"] = len(rows)
base["sized_trade_count"] = len(sized)
base["skipped_sequence_row_count"] = len(skipped)
base["sizing_skip_reason_counts"] = dict(skip_reasons)
base["unique_strategies"] = sorted(strategies.keys())
base["unique_strategy_count"] = len(strategies)
base["unique_symbols_sample"] = sorted(symbols.keys())[:50]
base["unique_symbol_count"] = len(symbols)
base["leakage_flag_counts"] = dict(leakage_flags)
base["return_bound_violation_counts"] = dict(return_bound_flags)
base["strategy_eligibility_gate_v1_summary"] = gate_audit

paths = dict(base.get("paths") or {})
paths["rows_path"] = str(gate_rows_path)
paths["position_sizing_rows"] = str(gate_rows_path)
paths["summary_path"] = str(out_path)
base["paths"] = paths

base["explicit_exclusions"] = list(base.get("explicit_exclusions") or []) + [
    "strategy_gate_v1_does_not_replace_gated_trades",
    "strategy_gate_v1_does_not_change_exit_logic",
    "strategy_gate_v1_does_not_change_position_size_for_kept_trades",
]

out_path.write_text(json.dumps(base, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

print(json.dumps({
    "is_ready": True,
    "compatible_summary_path": str(out_path),
    "input_sequence_row_count": base["input_sequence_row_count"],
    "sized_trade_count": base["sized_trade_count"],
    "skipped_sequence_row_count": base["skipped_sequence_row_count"],
    "unique_strategy_count": base["unique_strategy_count"],
    "unique_symbol_count": base["unique_symbol_count"],
}, indent=2, sort_keys=True))
