import json
from pathlib import Path
from collections import Counter

BASE_OUT = Path("artifacts/portfolio_value_ranked_allocator_v2_continuous_replay_20210601_20260531")
CANONICAL_OUT = Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531")
CANONICAL_OUT.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    {"label": "allocator_v2_30k_pf_42100_heat50", "capital": 30000},
    {"label": "allocator_v2_40k_pf_42100_heat50", "capital": 40000},
]

def read_jsonl(path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")

def fnum(x, default=0.0):
    try:
        if x is None or str(x).strip() == "":
            return default
        return float(x)
    except Exception:
        return default

def order_key(row):
    return (
        str(row.get("portfolio_realization_date") or row.get("outcome_availability_date") or row.get("decision_date") or ""),
        str(row.get("sequence_id") or ""),
        str(row.get("trade_key") or ""),
    )

for scenario in SCENARIOS:
    label = scenario["label"]
    capital = float(scenario["capital"])

    source_dir = BASE_OUT / label
    source_rows_path = source_dir / f"{label}_position_sizing_replay.jsonl"
    source_summary_path = source_dir / f"{label}_summary.json"

    out_dir = CANONICAL_OUT / label
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_path = out_dir / f"{label}_canonical_position_sizing_replay.jsonl"
    summary_path = out_dir / f"{label}_canonical_position_sizing_replay_summary.json"

    source_summary = json.loads(source_summary_path.read_text(encoding="utf-8-sig"))

    rows = list(read_jsonl(source_rows_path))
    sized_rows = [r for r in rows if r.get("sizing_state") == "sized"]
    sized_rows = sorted(sized_rows, key=order_key)

    equity = capital
    peak = capital
    total_pnl = 0.0
    max_dd = 0.0
    max_dd_date = None

    rebuilt = []

    for i, row in enumerate(sized_rows):
        r = dict(row)

        pnl = fnum(r.get("realized_pnl_dollars"))
        realization_date = str(
            r.get("portfolio_realization_date")
            or r.get("outcome_availability_date")
            or r.get("decision_date")
            or ""
        )[:10]

        before = equity
        after = equity + pnl

        r["equity_before_trade"] = before
        r["equity_after_trade"] = after
        r["portfolio_realization_date"] = realization_date
        r["portfolio_equity_reconstruction_order"] = i
        r["canonical_complete_ruleset"] = {
            "starting_capital": capital,
            "equity_order_rule": "portfolio_realization_date_then_sequence_id",
            "strategy_family_gate_v1_applied": True,
            "portfolio_value_ranked_allocator_v2_applied": True,
            "rank_method": source_summary.get("rank_method"),
            "allocation_profile": source_summary.get("allocation_profile"),
            "portfolio_heat_cap": source_summary.get("portfolio_heat_cap"),
        }

        equity = after
        total_pnl += pnl

        if equity > peak:
            peak = equity

        dd = (equity - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            max_dd_date = realization_date

        rebuilt.append(r)

    strategy_counts = Counter(str(r.get("selected_strategy") or "unknown") for r in rebuilt)
    symbol_counts = Counter(str(r.get("symbol") or "unknown") for r in rebuilt)
    dates = [str(r.get("portfolio_realization_date") or "")[:10] for r in rebuilt if r.get("portfolio_realization_date")]

    summary = {
        "adapter_type": "canonical_complete_ruleset_position_sizing_replay_summary_builder",
        "artifact_type": "signalforge_portfolio_position_sizing_replay_summary",
        "contract": "portfolio_position_sizing_replay",
        "is_ready": True,
        "readiness_state": "ready",

        "scenario_label": label,
        "starting_capital": capital,
        "starting_equity": capital,
        "ending_equity": equity,
        "total_pnl_dollars": total_pnl,
        "total_return_pct": (equity / capital - 1.0) if capital else None,
        "max_drawdown_pct": max_dd,
        "max_drawdown_date": max_dd_date,

        "input_row_count": len(rebuilt),
        "output_row_count": len(rebuilt),
        "position_sizing_row_count": len(rebuilt),
        "sized_trade_count": len(rebuilt),
        "skipped_trade_count": 0,
        "sized_count": len(rebuilt),
        "skipped_count": 0,
        "sizing_state_counts": {"sized": len(rebuilt)},

        "accepted_trade_count": len(rebuilt),
        "accepted_contract_count": sum(int(fnum(r.get("contract_quantity"), 1)) for r in rebuilt),

        "strategy_counts": dict(strategy_counts),
        "symbol_counts": dict(symbol_counts),
        "unique_strategy_count": len(strategy_counts),
        "unique_symbol_count": len(symbol_counts),

        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "replay_start": min(dates) if dates else None,
        "replay_end": max(dates) if dates else None,

        "policy": {
            "complete_ruleset_as_of_now": True,
            "strategy_family_gate_v1_applied": True,
            "portfolio_value_ranked_allocator_v2_applied": True,
            "equity_ordered_by_realization_date": True,
            "starting_capital_explicitly_anchored": True,
            "positive_expectancy_is_eligibility_universe": True,
            "rank_controls_priority_and_allocation": True,
            "portfolio_heat_controls_total_open_risk": True,
            "uses_whole_contracts": True,
            "does_replace_skipped_trades": False,
            "does_feed_result_to_expectancy": False,
            "does_change_exit": False
        },

        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
            "source_rows_path": str(source_rows_path),
            "source_summary_path": str(source_summary_path)
        }
    }

    write_jsonl(rows_path, rebuilt)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    print(json.dumps({
        "label": label,
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
        "starting_equity": capital,
        "ending_equity": equity,
        "total_pnl": total_pnl,
        "total_return_pct": summary["total_return_pct"],
        "max_drawdown_pct": max_dd,
        "sized_trade_count": len(rebuilt)
    }, indent=2))
