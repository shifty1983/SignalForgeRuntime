import json
import os
from pathlib import Path
from collections import defaultdict
from math import sqrt

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_NATIVE_QUOTE_PNL_STRESS_OUT_DIR",
    "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))



REQUESTED_ROBUSTNESS_STRESS_CASE_COVERAGE = {
    "stress_case_1_25pct_worse_fills": {
        "coverage_state": "covered_by_native_quote_cost_multiplier",
        "mapped_engine_case": "native_quote_1_25x_commission_150",
        "quote_cost_multiplier": 1.25,
        "commission_per_contract": 1.50,
    },
    "stress_case_2_50pct_worse_fills": {
        "coverage_state": "covered_by_native_quote_cost_multiplier",
        "mapped_engine_case": "native_quote_1_5x_commission_150",
        "quote_cost_multiplier": 1.50,
        "commission_per_contract": 1.50,
    },
    "stress_case_3_100pct_worse_fills": {
        "coverage_state": "covered_by_native_quote_cost_multiplier",
        "mapped_engine_case": "native_quote_2x_commission_150",
        "quote_cost_multiplier": 2.00,
        "commission_per_contract": 1.50,
    },
    "stress_case_4_no_mid_conservative_bid_ask_fills": {
        "coverage_state": "covered_by_native_quote_cost_model",
        "mapped_engine_case": "native_quote_1x_commission_150",
        "model": "round_trip_half_spread_cost_estimate_for_row",
        "interpretation": "mid-to-bid/ask adverse fill cost using joined entry and exit quotes",
        "commission_per_contract": 1.50,
    },
    "stress_case_5_skip_trades_where_spread_exceeds_threshold": {
        "coverage_state": "covered_upstream_by_v3_2_1_spread_guardrail",
        "mapped_rule": "spread_pct_gt_12_5pct_skip",
        "candidate_id": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
    },
    "stress_case_6_ibkr_like_commissions_and_fees": {
        "coverage_state": "covered_by_commission_model",
        "mapped_engine_cases": [
            "native_quote_1x_commission_150",
            "native_quote_1_25x_commission_150",
            "native_quote_1_5x_commission_150",
            "native_quote_2x_commission_150",
            "native_quote_3x_commission_150",
        ],
        "commission_per_contract": 1.50,
    },
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_pnl_stress_summary.json"
    STRESS_ROWS_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_pnl_stress_results.jsonl"
    BREAKEVEN_ROWS_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_breakeven_curve.jsonl"

    SCENARIOS = {
        "30k": {
            "starting_capital": 30000.0,
            "input_ledger": env_path(
                "SIGNALFORGE_NATIVE_QUOTE_PNL_STRESS_30K_LEDGER",
                "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531/v3_2_1_native_quote_join_30k/ledger.jsonl",
            ),
            "output_ledger": OUT_DIR / "v3_2_1_native_quote_30k" / "ledger.jsonl",
        },
        "40k": {
            "starting_capital": 40000.0,
            "input_ledger": env_path(
                "SIGNALFORGE_NATIVE_QUOTE_PNL_STRESS_40K_LEDGER",
                "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531/v3_2_1_native_quote_join_40k/ledger.jsonl",
            ),
            "output_ledger": OUT_DIR / "v3_2_1_native_quote_40k" / "ledger.jsonl",
        },
    }

    STRESS_CASES = [
        {
            "stress_case": "v3_2_1_original_no_native_quote_cost",
            "quote_cost_multiplier": 0.0,
            "commission_per_contract": 0.0,
        },
        {
            "stress_case": "native_quote_1x_commission_150",
            "quote_cost_multiplier": 1.0,
            "commission_per_contract": 1.50,
        },
        {
            "stress_case": "native_quote_1_25x_commission_150",
            "quote_cost_multiplier": 1.25,
            "commission_per_contract": 1.50,
        },
        {
            "stress_case": "native_quote_1_5x_commission_150",
            "quote_cost_multiplier": 1.5,
            "commission_per_contract": 1.50,
        },
        {
            "stress_case": "native_quote_2x_commission_150",
            "quote_cost_multiplier": 2.0,
            "commission_per_contract": 1.50,
        },
        {
            "stress_case": "native_quote_3x_commission_150",
            "quote_cost_multiplier": 3.0,
            "commission_per_contract": 1.50,
        },
    ]

    BREAKEVEN_MULTIPLIERS = [round(x / 10.0, 2) for x in range(0, 61)]
    BREAKEVEN_COMMISSION_PER_CONTRACT = 1.50

    QUANTITY_FIELDS = [
        "quantity",
        "adjusted_quantity",
        "contract_count",
        "allocated_contract_count",
        "contracts",
    ]

    PNL_FIELDS = [
        "allocated_pnl",
        "adjusted_allocated_pnl",
        "realized_pnl_dollars",
        "pnl_dollars",
        "realized_pnl",
    ]

    CLOSE_DATE_FIELDS = [
        "realization_date",
        "portfolio_realization_date",
        "exit_date",
        "close_date",
        "outcome_date",
        "decision_date",
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
            if x is None:
                return default
            s = str(x).strip()
            if s == "":
                return default
            return float(s)
        except Exception:
            return default

    def pick(row, fields, default=None):
        for field in fields:
            if field in row and row[field] is not None and str(row[field]).strip() != "":
                return row[field], field
        return default, None

    def quantity(row):
        v, _ = pick(row, QUANTITY_FIELDS, 0.0)
        return fnum(v, 0.0)

    def pnl(row):
        v, _ = pick(row, PNL_FIELDS, 0.0)
        return fnum(v, 0.0)

    def set_pnl(row, value):
        found = False
        for field in PNL_FIELDS:
            if field in row:
                row[field] = value
                found = True
        if not found:
            row["allocated_pnl"] = value

    def close_date_str(row):
        v, _ = pick(row, CLOSE_DATE_FIELDS, "")
        return str(v)[:10] if v is not None else ""

    def row_state(row):
        v, _ = pick(row, ["row_state", "sizing_state", "adjusted_row_state"], "accepted")
        return str(v).lower()

    def accepted(row):
        if quantity(row) <= 0:
            return False
        s = row_state(row)
        return not ("skip" in s or "reject" in s)

    def quote_join(row):
        qj = row.get("native_quote_join")
        if isinstance(qj, dict):
            return qj
        return {}

    def has_complete_native_quote(row):
        return bool(quote_join(row).get("entry_exit_quote_complete"))

    def native_quote_cost_for_row(row, fallback_cost_per_strategy_unit=None):
        qj = quote_join(row)

        if qj.get("entry_exit_quote_complete"):
            v = qj.get("round_trip_half_spread_cost_estimate_for_row")
            return fnum(v, 0.0), "actual_joined_quote_cost"

        if fallback_cost_per_strategy_unit is not None:
            return fallback_cost_per_strategy_unit * quantity(row), "missing_quote_p95_penalty"

        return 0.0, "missing_quote_no_penalty"

    def percentile(values, pct):
        vals = sorted([float(v) for v in values if v is not None])
        if not vals:
            return None
        idx = (len(vals) - 1) * pct
        lo = int(idx)
        hi = min(lo + 1, len(vals) - 1)
        frac = idx - lo
        return vals[lo] * (1 - frac) + vals[hi] * frac

    def native_cost_inventory(rows):
        active = [r for r in rows if accepted(r)]
        complete = [r for r in active if has_complete_native_quote(r)]

        costs_per_row = []
        costs_per_unit = []

        for r in complete:
            qj = quote_join(r)
            row_cost = fnum(qj.get("round_trip_half_spread_cost_estimate_for_row"), None)
            unit_cost = fnum(qj.get("round_trip_half_spread_cost_per_strategy_unit"), None)

            if row_cost is not None:
                costs_per_row.append(row_cost)
            if unit_cost is not None:
                costs_per_unit.append(unit_cost)

        return {
            "active_trade_count": len(active),
            "complete_native_quote_count": len(complete),
            "complete_native_quote_coverage": len(complete) / len(active) if active else 0.0,
            "missing_complete_native_quote_count": len(active) - len(complete),
            "round_trip_half_spread_cost_per_row_p50": percentile(costs_per_row, 0.50),
            "round_trip_half_spread_cost_per_row_p90": percentile(costs_per_row, 0.90),
            "round_trip_half_spread_cost_per_row_p95": percentile(costs_per_row, 0.95),
            "round_trip_half_spread_cost_per_row_p99": percentile(costs_per_row, 0.99),
            "round_trip_half_spread_cost_per_strategy_unit_p50": percentile(costs_per_unit, 0.50),
            "round_trip_half_spread_cost_per_strategy_unit_p90": percentile(costs_per_unit, 0.90),
            "round_trip_half_spread_cost_per_strategy_unit_p95": percentile(costs_per_unit, 0.95),
            "round_trip_half_spread_cost_per_strategy_unit_p99": percentile(costs_per_unit, 0.99),
        }

    def metrics(rows, starting_capital):
        active = [r for r in rows if accepted(r)]
        trade_pnls = [pnl(r) for r in active]
        wins = [x for x in trade_pnls if x > 0]
        losses = [abs(x) for x in trade_pnls if x < 0]

        by_day = defaultdict(float)
        for r in active:
            by_day[close_date_str(r)] += pnl(r)

        equity = starting_capital
        peak = starting_capital
        max_dd = 0.0
        worst_dd_date = None
        daily_pnls = []

        for d in sorted(by_day):
            day_pnl = by_day[d]
            daily_pnls.append(day_pnl)
            equity += day_pnl

            if equity > peak:
                peak = equity

            dd = (equity - peak) / peak if peak else 0.0
            if dd < max_dd:
                max_dd = dd
                worst_dd_date = d

        daily_wins = [x for x in daily_pnls if x > 0]
        daily_losses = [abs(x) for x in daily_pnls if x < 0]

        mean_daily = sum(daily_pnls) / len(daily_pnls) if daily_pnls else 0.0
        variance = sum((x - mean_daily) ** 2 for x in daily_pnls) / (len(daily_pnls) - 1) if len(daily_pnls) > 1 else 0.0
        stdev = sqrt(variance) if variance > 0 else 0.0

        downside = [x for x in daily_pnls if x < 0]
        downside_dev = sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0.0

        return {
            "starting_capital": starting_capital,
            "ending_equity": equity,
            "total_pnl_dollars": equity - starting_capital,
            "total_return_pct": (equity - starting_capital) / starting_capital if starting_capital else None,
            "pnl_multiple": (equity - starting_capital) / starting_capital if starting_capital else None,
            "ending_equity_multiple": equity / starting_capital if starting_capital else None,
            "max_drawdown_pct": max_dd,
            "worst_drawdown_date": worst_dd_date,
            "row_count": len(rows),
            "trade_count": len(active),
            "skipped_row_count": len(rows) - len(active),
            "contract_count": sum(quantity(r) for r in active),
            "win_rate": len(wins) / len(trade_pnls) if trade_pnls else None,
            "trade_profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
            "daily_profit_factor": sum(daily_wins) / sum(daily_losses) if sum(daily_losses) else None,
            "sharpe_proxy": (mean_daily / stdev * sqrt(252)) if stdev else None,
            "sortino_proxy": (mean_daily / downside_dev * sqrt(252)) if downside_dev else None,
            "gross_win_dollars": sum(wins),
            "gross_loss_dollars": sum(losses),
            "worst_daily_pnl": min(daily_pnls) if daily_pnls else None,
            "best_daily_pnl": max(daily_pnls) if daily_pnls else None,
            "trading_day_count": len(daily_pnls),
        }

    def round_metrics(m):
        out = {}
        for k, v in m.items():
            if isinstance(v, float):
                out[k] = round(v, 6)
            else:
                out[k] = v
        return out

    def apply_native_quote_stress(rows, quote_cost_multiplier, commission_per_contract, fallback_cost_per_strategy_unit):
        stressed = []
        total_quote_cost = 0.0
        total_commission = 0.0
        actual_quote_cost_rows = 0
        fallback_quote_cost_rows = 0

        for r in rows:
            new = dict(r)

            if accepted(new):
                q = quantity(new)
                quote_cost, method = native_quote_cost_for_row(
                    new,
                    fallback_cost_per_strategy_unit=fallback_cost_per_strategy_unit,
                )

                if method == "actual_joined_quote_cost":
                    actual_quote_cost_rows += 1
                elif method == "missing_quote_p95_penalty":
                    fallback_quote_cost_rows += 1

                quote_adjustment = quote_cost * quote_cost_multiplier
                commission_adjustment = commission_per_contract * q
                total_adjustment = quote_adjustment + commission_adjustment

                set_pnl(new, pnl(new) - total_adjustment)

                new["native_quote_pnl_stress"] = {
                    "quote_cost_multiplier": quote_cost_multiplier,
                    "commission_per_contract": commission_per_contract,
                    "native_quote_cost_method": method,
                    "native_quote_cost_before_multiplier": quote_cost,
                    "native_quote_cost_after_multiplier": quote_adjustment,
                    "commission_cost": commission_adjustment,
                    "total_execution_adjustment": total_adjustment,
                }

                total_quote_cost += quote_adjustment
                total_commission += commission_adjustment

            stressed.append(new)

        return stressed, {
            "total_native_quote_cost": total_quote_cost,
            "total_commission_cost": total_commission,
            "actual_quote_cost_rows": actual_quote_cost_rows,
            "fallback_quote_cost_rows": fallback_quote_cost_rows,
        }

    blockers = []
    warnings = []
    stress_rows = []
    breakeven_rows = []
    scenario_summaries = []

    for capital_label, cfg in SCENARIOS.items():
        if not cfg["input_ledger"].exists():
            blockers.append(f"missing_native_quote_join_ledger_{capital_label}: {cfg['input_ledger']}")
            continue

        rows = list(read_jsonl(cfg["input_ledger"]))

        inv = native_cost_inventory(rows)
        fallback_unit_cost = inv["round_trip_half_spread_cost_per_strategy_unit_p95"]

        if inv["complete_native_quote_coverage"] < 0.95:
            blockers.append(f"native_quote_coverage_below_95pct_{capital_label}")

        original_metrics = metrics(rows, cfg["starting_capital"])

        scenario_summary = {
            "capital_label": capital_label,
            "starting_capital": cfg["starting_capital"],
            "input_ledger": str(cfg["input_ledger"]),
            "output_native_quote_ledger": str(cfg["output_ledger"]),
            "native_quote_cost_inventory": inv,
            "missing_quote_fallback_cost_per_strategy_unit": fallback_unit_cost,
            "original_v3_2_1_metrics": round_metrics(original_metrics),
        }

        for case in STRESS_CASES:
            stressed, cost_summary = apply_native_quote_stress(
                rows,
                case["quote_cost_multiplier"],
                case["commission_per_contract"],
                fallback_cost_per_strategy_unit=fallback_unit_cost,
            )

            m = metrics(stressed, cfg["starting_capital"])

            stress_row = {
                "capital_label": capital_label,
                "stress_case": case["stress_case"],
                "quote_cost_multiplier": case["quote_cost_multiplier"],
                "commission_per_contract": case["commission_per_contract"],
                **round_metrics(m),
                **{k: round(v, 6) if isinstance(v, float) else v for k, v in cost_summary.items()},
                "pnl_retention_vs_original_v3_2_1": round(
                    m["total_pnl_dollars"] / original_metrics["total_pnl_dollars"], 6
                ) if original_metrics["total_pnl_dollars"] else None,
                "passes_positive_pnl": m["total_pnl_dollars"] > 0,
                "passes_pf_gt_1": m["trade_profit_factor"] is not None and m["trade_profit_factor"] > 1.0,
                "passes_dd_under_35pct": m["max_drawdown_pct"] > -0.35,
            }

            stress_row["passes_native_quote_stress"] = (
                stress_row["passes_positive_pnl"]
                and stress_row["passes_pf_gt_1"]
                and stress_row["passes_dd_under_35pct"]
            )

            stress_rows.append(stress_row)

            if case["stress_case"] == "native_quote_1x_commission_150":
                write_jsonl(cfg["output_ledger"], stressed)
                scenario_summary["native_quote_1x_metrics"] = round_metrics(m)
                scenario_summary["native_quote_1x_cost_summary"] = {
                    k: round(v, 6) if isinstance(v, float) else v
                    for k, v in cost_summary.items()
                }

        for mult in BREAKEVEN_MULTIPLIERS:
            stressed, cost_summary = apply_native_quote_stress(
                rows,
                mult,
                BREAKEVEN_COMMISSION_PER_CONTRACT,
                fallback_cost_per_strategy_unit=fallback_unit_cost,
            )

            m = metrics(stressed, cfg["starting_capital"])

            breakeven_rows.append({
                "capital_label": capital_label,
                "quote_cost_multiplier": mult,
                "commission_per_contract": BREAKEVEN_COMMISSION_PER_CONTRACT,
                **round_metrics(m),
                **{k: round(v, 6) if isinstance(v, float) else v for k, v in cost_summary.items()},
                "passes_positive_pnl": m["total_pnl_dollars"] > 0,
                "passes_pf_gt_1": m["trade_profit_factor"] is not None and m["trade_profit_factor"] > 1.0,
                "passes_dd_under_35pct": m["max_drawdown_pct"] > -0.35,
                "passes_all": (
                    m["total_pnl_dollars"] > 0
                    and m["trade_profit_factor"] is not None
                    and m["trade_profit_factor"] > 1.0
                    and m["max_drawdown_pct"] > -0.35
                ),
            })

        scenario_summaries.append(scenario_summary)

    write_jsonl(STRESS_ROWS_PATH, stress_rows)
    write_jsonl(BREAKEVEN_ROWS_PATH, breakeven_rows)

    breakeven_summary = []

    for capital_label in SCENARIOS:
        rows = [r for r in breakeven_rows if r["capital_label"] == capital_label]

        def max_mult(predicate):
            vals = [r["quote_cost_multiplier"] for r in rows if predicate(r)]
            return max(vals) if vals else None

        breakeven_summary.append({
            "capital_label": capital_label,
            "max_quote_cost_multiplier_passing_all": max_mult(lambda r: r["passes_all"]),
            "max_quote_cost_multiplier_positive_pnl": max_mult(lambda r: r["passes_positive_pnl"]),
            "max_quote_cost_multiplier_pf_gt_1": max_mult(lambda r: r["passes_pf_gt_1"]),
            "max_quote_cost_multiplier_dd_under_35pct": max_mult(lambda r: r["passes_dd_under_35pct"]),
        })

    native_1x_rows = [r for r in stress_rows if r["stress_case"] == "native_quote_1x_commission_150"]
    native_2x_rows = [r for r in stress_rows if r["stress_case"] == "native_quote_2x_commission_150"]
    native_3x_rows = [r for r in stress_rows if r["stress_case"] == "native_quote_3x_commission_150"]

    passes_1x = bool(native_1x_rows) and all(r["passes_native_quote_stress"] for r in native_1x_rows)
    passes_2x = bool(native_2x_rows) and all(r["passes_native_quote_stress"] for r in native_2x_rows)
    passes_3x = bool(native_3x_rows) and all(r["passes_native_quote_stress"] for r in native_3x_rows)

    min_native_1x_retention = min(
        (r["pnl_retention_vs_original_v3_2_1"] for r in native_1x_rows),
        default=None,
    )

    if blockers:
        decision = "native_quote_pnl_stress_blocked"
    elif passes_1x and passes_2x:
        decision = "native_quote_execution_validation_passed"
    elif passes_1x:
        decision = "native_quote_execution_validation_passed_1x_only"
    else:
        decision = "native_quote_execution_validation_failed"

    if passes_3x:
        warnings.append("Native quote stress also passed at 3x quote cost.")
    else:
        warnings.append("Native quote stress did not pass all 3x quote-cost criteria, or 3x was not evaluated as pass.")

    summary = {
        "adapter_type": "v3_2_1_native_quote_pnl_stress_builder",
        "artifact_type": "signalforge_v3_2_1_native_quote_pnl_stress",
        "contract": "v3_2_1_native_quote_pnl_stress",
        "candidate_id": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
        "is_ready": len(blockers) == 0,
        "readiness_state": "ready" if len(blockers) == 0 else "blocked",
        "decision": decision,
        "blockers": blockers,
        "warnings": warnings,
        "native_quote_cost_model": {
            "model": "round_trip_half_spread_cost_estimate_for_row",
            "interpretation": "mid-to-bid/ask adverse fill cost using joined entry and exit quotes",
            "missing_complete_quote_policy": "penalize_missing_rows_with_scenario_p95_cost_per_strategy_unit",
            "commission_per_contract_default": 1.50,
        },
        "promotion_checks": {
            "passes_native_quote_1x_commission_stress": passes_1x,
            "passes_native_quote_2x_commission_stress": passes_2x,
            "passes_native_quote_3x_commission_stress": passes_3x,
            "min_native_1x_pnl_retention_vs_original_v3_2_1": min_native_1x_retention,
        },
        "requested_robustness_stress_case_coverage": REQUESTED_ROBUSTNESS_STRESS_CASE_COVERAGE,
        "scenario_summaries": scenario_summaries,
        "stress_results": stress_rows,
        "breakeven_summary": breakeven_summary,
        "paths": {
            "summary": str(SUMMARY_PATH),
            "stress_rows": str(STRESS_ROWS_PATH),
            "breakeven_rows": str(BREAKEVEN_ROWS_PATH),
            "native_quote_30k_ledger": str(SCENARIOS["30k"]["output_ledger"]),
            "native_quote_40k_ledger": str(SCENARIOS["40k"]["output_ledger"]),
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


