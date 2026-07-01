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

QUANTITY_FIELDS = [
    "quantity",
    "adjusted_quantity",
    "contract_count",
    "allocated_contract_count",
    "contracts",
    "position_size",
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
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


def cat(value: Any, default: str = "unknown") -> str:
    if value in (None, ""):
        return default
    return str(value)


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


def get_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            [
                "portfolio_realization_date",
                "realization_date",
                "exit_date",
                "close_date",
                "outcome_date",
                "decision_date",
                "entry_date",
                "trade_date",
                "date",
            ],
            "1900-01-01",
        )
    )[:10]


def get_strategy(row: dict[str, Any]) -> str:
    return cat(pick(row, ["selected_strategy", "strategy", "strategy_family"]), "unknown_strategy")


def get_symbol(row: dict[str, Any]) -> str:
    return cat(pick(row, ["symbol", "underlying_symbol"]), "unknown_symbol")


def get_regime(row: dict[str, Any]) -> str:
    return cat(pick(row, ["regime_state", "regime"]), "unknown_regime")


def get_asset_behavior(row: dict[str, Any]) -> str:
    direct = pick(row, ["asset_behavior_state", "selected_asset_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    rc = row.get("research_context") or {}
    if isinstance(rc, dict):
        ab = rc.get("asset_behavior") or {}
        if isinstance(ab, dict):
            return cat(ab.get("state"), "unknown_asset_behavior")

    return "unknown_asset_behavior"


def get_option_behavior(row: dict[str, Any]) -> str:
    direct = pick(row, ["option_behavior_state", "selected_option_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    rc = row.get("research_context") or {}
    if isinstance(rc, dict):
        ob = rc.get("option_behavior") or {}
        if isinstance(ob, dict):
            return cat(ob.get("state"), "unknown_option_behavior")

    return "unknown_option_behavior"


def close_date(row: dict[str, Any]) -> str:
    return get_date(row)


def metrics(rows: list[dict[str, Any]], starting_capital: float, rule: dict[str, Any] | None = None) -> dict[str, Any]:
    trade_pnls = []
    by_close = defaultdict(float)

    skipped_count = 0
    throttled_count = 0
    affected_original_pnl = 0.0

    for row in rows:
        if not is_active(row):
            continue

        pnl = pnl_value(row)
        multiplier = 1.0

        if rule and matches_rule(row, rule):
            affected_original_pnl += pnl
            action = rule["action"]
            if action == "skip":
                multiplier = 0.0
                skipped_count += 1
            elif action == "throttle":
                multiplier = float(rule["multiplier"])
                throttled_count += 1

        final_pnl = pnl * multiplier

        if multiplier > 0:
            trade_pnls.append(final_pnl)
            by_close[close_date(row)] += final_pnl

    wins = [x for x in trade_pnls if x > 0]
    losses = [abs(x) for x in trade_pnls if x < 0]

    equity = starting_capital
    peak = starting_capital
    max_dd = 0.0

    for d in sorted(by_close):
        equity += by_close[d]
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd

    total_pnl = equity - starting_capital

    return {
        "trade_count": len(trade_pnls),
        "ending_equity": equity,
        "total_pnl_dollars": total_pnl,
        "total_return_pct": total_pnl / starting_capital if starting_capital else None,
        "profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
        "max_drawdown_pct": max_dd,
        "gross_win_dollars": sum(wins),
        "gross_loss_dollars": sum(losses),
        "skipped_count": skipped_count,
        "throttled_count": throttled_count,
        "affected_original_pnl": affected_original_pnl,
    }


def matches_rule(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    strategy = get_strategy(row)
    symbol = get_symbol(row)
    regime = get_regime(row)
    asset = get_asset_behavior(row)
    option = get_option_behavior(row)

    kind = rule["kind"]

    if kind == "strategy_option_behavior":
        return strategy == rule["strategy"] and option == rule["option_behavior"]

    if kind == "strategy_regime_asset_option":
        return (
            strategy == rule["strategy"]
            and regime == rule["regime_state"]
            and asset == rule["asset_behavior_state"]
            and option == rule["option_behavior_state"]
        )

    if kind == "symbol_strategy_list":
        return f"{symbol}|{strategy}" in set(rule["symbol_strategy_values"])

    if kind == "symbol_strategy":
        return symbol == rule["symbol"] and strategy == rule["strategy"]

    if kind == "symbol_regime":
        return symbol == rule["symbol"] and regime == rule["regime_state"]

    return False


def scenario_rules() -> list[dict[str, Any]]:
    base_rules = [
        {
            "label": "skip_long_put_iv_low_liquid",
            "kind": "strategy_option_behavior",
            "strategy": "long_put",
            "option_behavior": "iv_low_liquid",
        },
        {
            "label": "skip_long_put_goldilocks_defensive_iv_low_liquid",
            "kind": "strategy_regime_asset_option",
            "strategy": "long_put",
            "regime_state": "goldilocks",
            "asset_behavior_state": "defensive",
            "option_behavior_state": "iv_low_liquid",
        },
        {
            "label": "skip_long_put_late_cycle_defensive_iv_low_liquid",
            "kind": "strategy_regime_asset_option",
            "strategy": "long_put",
            "regime_state": "late_cycle_overheating",
            "asset_behavior_state": "defensive",
            "option_behavior_state": "iv_low_liquid",
        },
        {
            "label": "skip_worst_long_put_symbols",
            "kind": "symbol_strategy_list",
            "symbol_strategy_values": [
                "DIA|long_put",
                "EFA|long_put",
                "HYG|long_put",
                "IEF|long_put",
                "RSP|long_put",
                "XLK|long_put",
                "XLI|long_put",
                "XLF|long_put",
                "EEM|long_put",
                "VNQ|long_put",
            ],
        },
        {
            "label": "skip_worst_symbol_strategy_pockets",
            "kind": "symbol_strategy_list",
            "symbol_strategy_values": [
                "DIA|long_put",
                "GLD|long_call",
                "VXX|put_credit_spread",
                "EFA|long_put",
                "LQD|long_call",
                "XLE|long_call",
                "IYR|long_call",
                "HYG|long_put",
                "IAU|long_call",
                "FEZ|long_call",
                "IEF|long_call",
                "XLU|long_call",
                "IEF|long_put",
                "RSP|long_put",
                "EWW|long_call",
                "XLK|long_put",
                "XLI|long_put",
            ],
        },
        {
            "label": "skip_gld_goldilocks",
            "kind": "symbol_regime",
            "symbol": "GLD",
            "regime_state": "goldilocks",
        },
    ]

    out = []

    for rule in base_rules:
        skip_rule = dict(rule)
        skip_rule["action"] = "skip"
        skip_rule["multiplier"] = 0.0
        out.append(skip_rule)

        for mult in [0.25, 0.50, 0.75]:
            throttle_rule = dict(rule)
            throttle_rule["label"] = rule["label"].replace("skip_", f"throttle_{str(mult).replace('.', 'p')}_")
            throttle_rule["action"] = "throttle"
            throttle_rule["multiplier"] = mult
            out.append(throttle_rule)

    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input_ledger))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = metrics(rows, args.starting_capital, None)

    scenario_rows = []

    for rule in scenario_rules():
        candidate = metrics(rows, args.starting_capital, rule)

        delta_pnl = candidate["total_pnl_dollars"] - baseline["total_pnl_dollars"]
        delta_pf = (candidate["profit_factor"] or 0.0) - (baseline["profit_factor"] or 0.0)
        delta_dd = candidate["max_drawdown_pct"] - baseline["max_drawdown_pct"]

        scenario_rows.append({
            "label": rule["label"],
            "kind": rule["kind"],
            "action": rule["action"],
            "multiplier": rule["multiplier"],
            "affected_original_pnl": candidate["affected_original_pnl"],
            "skipped_count": candidate["skipped_count"],
            "throttled_count": candidate["throttled_count"],
            "baseline_trade_count": baseline["trade_count"],
            "candidate_trade_count": candidate["trade_count"],
            "baseline_total_return_pct": baseline["total_return_pct"],
            "candidate_total_return_pct": candidate["total_return_pct"],
            "delta_pnl_dollars": delta_pnl,
            "baseline_profit_factor": baseline["profit_factor"],
            "candidate_profit_factor": candidate["profit_factor"],
            "delta_profit_factor": delta_pf,
            "baseline_max_drawdown_pct": baseline["max_drawdown_pct"],
            "candidate_max_drawdown_pct": candidate["max_drawdown_pct"],
            "delta_max_drawdown_pct": delta_dd,
            "return_non_degradation": delta_pnl >= 0,
            "profit_factor_non_degradation": delta_pf >= 0,
            "drawdown_non_degradation": delta_dd >= 0,
            "rule": rule,
        })

    passing = [
        r for r in scenario_rows
        if r["return_non_degradation"]
        and r["profit_factor_non_degradation"]
        and r["drawdown_non_degradation"]
        and (r["skipped_count"] > 0 or r["throttled_count"] > 0)
    ]

    scenario_rows.sort(key=lambda r: (r["delta_pnl_dollars"], r["delta_profit_factor"]), reverse=True)

    summary = {
        "adapter_type": "portfolio_loss_pocket_rule_sweep_builder",
        "artifact_type": "signalforge_portfolio_loss_pocket_rule_sweep",
        "contract": "portfolio_loss_pocket_rule_sweep",
        "is_ready": True,
        "readiness_state": "diagnostic_only_full_period_rule_sweep",
        "input_ledger": args.input_ledger,
        "baseline_metrics": baseline,
        "scenario_count": len(scenario_rows),
        "passing_scenario_count": len(passing),
        "policy": {
            "diagnostic_only": True,
            "uses_full_period_realized_outcomes_for_rule_discovery": True,
            "not_live_safe_until_converted_to_walk_forward_or_prior_rule": True,
        },
        "paths": {
            "summary": str(output_dir / "signalforge_portfolio_loss_pocket_rule_sweep_summary.json"),
            "scenario_rows": str(output_dir / "signalforge_portfolio_loss_pocket_rule_sweep_rows.jsonl"),
        },
        "top_scenarios": scenario_rows[:10],
    }

    write_json(output_dir / "signalforge_portfolio_loss_pocket_rule_sweep_summary.json", summary)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pocket_rule_sweep_rows.jsonl", scenario_rows)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--starting-capital", type=float, required=True)
    args = parser.parse_args()

    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "scenario_count": summary["scenario_count"],
        "passing_scenario_count": summary["passing_scenario_count"],
        "baseline_return": summary["baseline_metrics"]["total_return_pct"],
        "baseline_pf": summary["baseline_metrics"]["profit_factor"],
        "baseline_max_dd": summary["baseline_metrics"]["max_drawdown_pct"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
