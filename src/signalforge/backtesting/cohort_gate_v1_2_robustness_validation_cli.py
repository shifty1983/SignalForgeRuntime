from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Any


PNL_FIELDS = [
    "realized_pnl_dollars",
    "allocated_pnl",
    "strategy_pnl",
    "portfolio_pnl",
    "pnl",
    "trade_pnl",
    "net_pnl",
]

RISK_FIELDS = [
    "position_risk_dollars",
    "risk_capital",
    "allocated_risk_dollars",
    "max_loss_dollars",
]

RETURN_FIELDS = [
    "realized_return",
    "strategy_adjusted_return",
    "strategy_return",
]

QUANTITY_FIELDS = [
    "quantity",
    "adjusted_quantity",
    "contract_count",
    "allocated_contract_count",
    "contracts",
    "position_size",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def pick(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return default


def parse_date(value: Any) -> date:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return date(1900, 1, 1)


def close_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            [
                "outcome_availability_date",
                "portfolio_realization_date",
                "realization_date",
                "exit_date",
                "close_date",
                "outcome_date",
                "target_exit_date",
                "decision_date",
            ],
            "1900-01-01",
        )
    )[:10]


def is_active(row: dict[str, Any]) -> bool:
    state_text = " ".join(
        str(row.get(k) or "").lower()
        for k in [
            "row_state",
            "sizing_state",
            "allocation_state",
            "selection_state",
            "portfolio_state",
            "trade_state",
        ]
    )

    if "skip" in state_text or "reject" in state_text or "blocked" in state_text:
        return False

    qtys = [fnum(row.get(k), None) for k in QUANTITY_FIELDS if k in row]
    qtys = [x for x in qtys if x is not None]

    if qtys and max(qtys) <= 0:
        return False

    return True


def pnl_value(row: dict[str, Any]) -> float:
    for field in PNL_FIELDS:
        if row.get(field) not in (None, ""):
            return fnum(row.get(field))

    risk = fnum(pick(row, RISK_FIELDS, 0.0))
    ret = fnum(pick(row, RETURN_FIELDS, 0.0))
    return risk * ret


def quantity_value(row: dict[str, Any]) -> float:
    return fnum(pick(row, QUANTITY_FIELDS, 0.0))


def strategy(row: dict[str, Any]) -> str:
    return str(pick(row, ["selected_strategy", "strategy", "strategy_family"], "unknown"))


def symbol(row: dict[str, Any]) -> str:
    return str(pick(row, ["symbol", "underlying_symbol"], "unknown"))


def stressed_pnl(base_pnl: float, scenario: dict[str, Any], row: dict[str, Any]) -> float:
    loss_multiplier = float(scenario.get("loss_multiplier", 1.0))
    win_haircut = float(scenario.get("win_haircut", 0.0))
    flat_cost = float(scenario.get("flat_cost_per_contract", 0.0))
    proportional_cost = float(scenario.get("proportional_pnl_cost", 0.0))

    pnl = base_pnl

    if pnl < 0:
        pnl = pnl * loss_multiplier
    elif pnl > 0:
        pnl = pnl * (1.0 - win_haircut)

    pnl -= abs(base_pnl) * proportional_cost
    pnl -= abs(quantity_value(row)) * flat_cost

    return pnl


def metrics(rows: list[dict[str, Any]], starting_capital: float, scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    active = [r for r in rows if is_active(r)]

    trade_pnls = []
    by_close = defaultdict(float)
    by_strategy = defaultdict(float)
    by_symbol = defaultdict(float)

    for row in active:
        pnl = pnl_value(row)

        if scenario:
            pnl = stressed_pnl(pnl, scenario, row)

        trade_pnls.append(pnl)
        by_close[close_date(row)] += pnl
        by_strategy[strategy(row)] += pnl
        by_symbol[symbol(row)] += pnl

    wins = [x for x in trade_pnls if x > 0]
    losses = [abs(x) for x in trade_pnls if x < 0]

    equity = starting_capital
    peak = starting_capital
    max_dd = 0.0
    worst_dd_date = None

    for d in sorted(by_close):
        equity += by_close[d]
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            worst_dd_date = d

    total_pnl = equity - starting_capital
    positive_pnl = sum(x for x in by_strategy.values() if x > 0)

    top_strategy = None
    top_strategy_positive_contribution = None
    if positive_pnl > 0:
        top_strategy, top_pnl = max(by_strategy.items(), key=lambda kv: kv[1])
        top_strategy_positive_contribution = top_pnl / positive_pnl if top_pnl > 0 else 0.0

    top_symbol = None
    top_symbol_positive_contribution = None
    positive_symbol_pnl = sum(x for x in by_symbol.values() if x > 0)
    if positive_symbol_pnl > 0:
        top_symbol, top_symbol_pnl = max(by_symbol.items(), key=lambda kv: kv[1])
        top_symbol_positive_contribution = top_symbol_pnl / positive_symbol_pnl if top_symbol_pnl > 0 else 0.0

    return {
        "trade_count": len(active),
        "ending_equity": equity,
        "total_pnl_dollars": total_pnl,
        "total_return_pct": total_pnl / starting_capital if starting_capital else None,
        "max_drawdown_pct": max_dd,
        "worst_drawdown_date": worst_dd_date,
        "win_rate": len(wins) / len(trade_pnls) if trade_pnls else None,
        "profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
        "gross_win_dollars": sum(wins),
        "gross_loss_dollars": sum(losses),
        "top_strategy": top_strategy,
        "top_strategy_positive_contribution": top_strategy_positive_contribution,
        "top_symbol": top_symbol,
        "top_symbol_positive_contribution": top_symbol_positive_contribution,
    }


SCENARIOS = [
    {
        "scenario_name": "baseline",
        "loss_multiplier": 1.0,
        "win_haircut": 0.0,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "losses_25pct_worse",
        "loss_multiplier": 1.25,
        "win_haircut": 0.0,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "losses_50pct_worse",
        "loss_multiplier": 1.50,
        "win_haircut": 0.0,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "wins_10pct_haircut",
        "loss_multiplier": 1.0,
        "win_haircut": 0.10,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "wins_20pct_haircut",
        "loss_multiplier": 1.0,
        "win_haircut": 0.20,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "losses_25pct_worse_wins_10pct_haircut",
        "loss_multiplier": 1.25,
        "win_haircut": 0.10,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "ibkr_like_contract_cost_1p50",
        "loss_multiplier": 1.0,
        "win_haircut": 0.0,
        "flat_cost_per_contract": 1.50,
        "proportional_pnl_cost": 0.0,
    },
    {
        "scenario_name": "pnl_cost_2pct",
        "loss_multiplier": 1.0,
        "win_haircut": 0.0,
        "flat_cost_per_contract": 0.0,
        "proportional_pnl_cost": 0.02,
    },
]


def run(args: argparse.Namespace) -> dict[str, Any]:
    baseline_rows = read_jsonl(Path(args.baseline_ledger))
    candidate_rows = read_jsonl(Path(args.candidate_ledger))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    blocker_count = 0
    blockers = []

    for scenario in SCENARIOS:
        base = metrics(baseline_rows, args.starting_capital, scenario)
        cand = metrics(candidate_rows, args.starting_capital, scenario)

        delta_pnl = cand["total_pnl_dollars"] - base["total_pnl_dollars"]
        delta_pf = (cand["profit_factor"] or 0) - (base["profit_factor"] or 0)
        delta_dd = cand["max_drawdown_pct"] - base["max_drawdown_pct"]

        row = {
            "scenario_name": scenario["scenario_name"],
            "baseline_total_return_pct": base["total_return_pct"],
            "candidate_total_return_pct": cand["total_return_pct"],
            "delta_pnl_dollars": delta_pnl,
            "baseline_profit_factor": base["profit_factor"],
            "candidate_profit_factor": cand["profit_factor"],
            "delta_profit_factor": delta_pf,
            "baseline_max_drawdown_pct": base["max_drawdown_pct"],
            "candidate_max_drawdown_pct": cand["max_drawdown_pct"],
            "delta_max_drawdown_pct": delta_dd,
            "baseline_trade_count": base["trade_count"],
            "candidate_trade_count": cand["trade_count"],
            "candidate_top_strategy": cand["top_strategy"],
            "candidate_top_strategy_positive_contribution": cand["top_strategy_positive_contribution"],
            "candidate_top_symbol": cand["top_symbol"],
            "candidate_top_symbol_positive_contribution": cand["top_symbol_positive_contribution"],
            "return_non_degradation": delta_pnl >= 0,
            "profit_factor_non_degradation": delta_pf >= 0,
            "drawdown_non_degradation": delta_dd >= 0,
        }

        rows.append(row)

    passing_rows = [
        r for r in rows
        if r["return_non_degradation"]
        and r["profit_factor_non_degradation"]
        and r["drawdown_non_degradation"]
    ]

    if len(passing_rows) < len(rows):
        blocker_count += 1
        blockers.append("one_or_more_stress_scenarios_failed_non_degradation")

    summary = {
        "adapter_type": "cohort_risk_rejection_gate_v1_2_allocator_calibrated_robustness_validation_builder",
        "artifact_type": "signalforge_cohort_risk_rejection_gate_v1_2_allocator_calibrated_robustness_validation",
        "contract": "cohort_risk_rejection_gate_v1_2_allocator_calibrated_robustness_validation",
        "is_ready": blocker_count == 0,
        "readiness_state": "pass" if blocker_count == 0 else "review_required",
        "blocker_count": blocker_count,
        "blockers": blockers,
        "warning_count": 1,
        "warnings": ["stress_model_is_pnl_approximation_not_quote_native_repricing"],
        "baseline_ledger": args.baseline_ledger,
        "candidate_ledger": args.candidate_ledger,
        "scenario_count": len(rows),
        "passing_scenario_count": len(passing_rows),
        "scenario_rows_path": str(output_dir / "signalforge_cohort_gate_v1_2_robustness_scenario_rows.jsonl"),
        "summary_path": str(output_dir / "signalforge_cohort_gate_v1_2_robustness_summary.json"),
        "scenario_rows": rows,
    }

    write_jsonl(output_dir / "signalforge_cohort_gate_v1_2_robustness_scenario_rows.jsonl", rows)
    write_json(output_dir / "signalforge_cohort_gate_v1_2_robustness_summary.json", summary)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ledger", required=True)
    parser.add_argument("--candidate-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--starting-capital", type=float, required=True)
    args = parser.parse_args()

    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "blocker_count": summary["blocker_count"],
        "scenario_count": summary["scenario_count"],
        "passing_scenario_count": summary["passing_scenario_count"],
        "warnings": summary["warnings"],
        "paths": {
            "summary": summary["summary_path"],
            "scenario_rows": summary["scenario_rows_path"],
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
