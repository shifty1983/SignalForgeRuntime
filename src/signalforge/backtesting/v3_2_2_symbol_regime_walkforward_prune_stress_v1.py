import json
import os
from pathlib import Path
from collections import defaultdict
from math import sqrt

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_SYMBOL_REGIME_PRUNE_STRESS_OUT_DIR",
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_2_symbol_regime_walkforward_prune_stress_summary.json"
    STRESS_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_symbol_regime_walkforward_prune_stress_results.jsonl"
    SKIPPED_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_symbol_regime_walkforward_prune_skipped_rows.jsonl"

    SCENARIOS = {
        "30k": {
            "starting_capital": 30000.0,
            "ledger": env_path(
            "SIGNALFORGE_V3_2_2_SYMBOL_REGIME_PRUNE_STRESS_30K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_30k/ledger.jsonl",
        ),
            "output_ledger": OUT_DIR / "v3_2_2_30k" / "ledger.jsonl",
        },
        "40k": {
            "starting_capital": 40000.0,
            "ledger": env_path(
            "SIGNALFORGE_V3_2_2_SYMBOL_REGIME_PRUNE_STRESS_40K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_40k/ledger.jsonl",
        ),
            "output_ledger": OUT_DIR / "v3_2_2_40k" / "ledger.jsonl",
        },
    }

    RULE = {
        "rule_id": "prior_symbol_regime_m8_netneg_pf090_v1",
        "scope": ["symbol", "regime"],
        "min_prior": 8,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
    }

    STRESS_CASES = [
        {"stress_case": "baseline_native_quote_1x", "extra_pnl_per_contract": 0.0},
        {"stress_case": "extra_slip_25_per_contract", "extra_pnl_per_contract": -25.0},
        {"stress_case": "extra_slip_50_per_contract", "extra_pnl_per_contract": -50.0},
        {"stress_case": "extra_slip_100_per_contract", "extra_pnl_per_contract": -100.0},
    ]

    QUANTITY_FIELDS = ["quantity", "adjusted_quantity", "contract_count", "allocated_contract_count", "contracts"]
    PNL_FIELDS = ["allocated_pnl", "adjusted_allocated_pnl", "realized_pnl_dollars", "pnl_dollars", "realized_pnl"]
    ENTRY_DATE_FIELDS = ["entry_date", "trade_date", "decision_date", "date"]
    CLOSE_DATE_FIELDS = ["realization_date", "portfolio_realization_date", "exit_date", "close_date", "outcome_date", "decision_date"]

    GROUP_FIELDS = {
        "symbol": ["symbol", "underlying_symbol", "ticker"],
        "regime": ["regime_state", "market_regime", "regime"],
        "strategy": ["selected_strategy", "strategy", "strategy_family", "strategy_name"],
    }

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

    def set_quantity(row, value):
        found = False
        for field in QUANTITY_FIELDS:
            if field in row:
                row[field] = value
                found = True
        if not found:
            row["quantity"] = value

    def set_pnl(row, value):
        found = False
        for field in PNL_FIELDS:
            if field in row:
                row[field] = value
                found = True
        if not found:
            row["allocated_pnl"] = value

    def date10(x):
        if x is None:
            return ""
        return str(x)[:10]

    def entry_date(row):
        v, _ = pick(row, ENTRY_DATE_FIELDS, "")
        return date10(v)

    def close_date(row):
        v, _ = pick(row, CLOSE_DATE_FIELDS, "")
        return date10(v)

    def row_state(row):
        v, _ = pick(row, ["row_state", "sizing_state", "adjusted_row_state"], "accepted")
        return str(v).lower()

    def accepted(row):
        if quantity(row) <= 0:
            return False
        s = row_state(row)
        return not ("skip" in s or "reject" in s)

    def group_value(row, name):
        fields = GROUP_FIELDS[name]
        v, _ = pick(row, fields, "missing")
        return str(v)

    def scope_key(row):
        return tuple(group_value(row, name) for name in RULE["scope"])

    def prior_stats(prior_pnls):
        pnls = list(prior_pnls)
        wins = [x for x in pnls if x > 0]
        losses = [abs(x) for x in pnls if x < 0]
        gross_win = sum(wins)
        gross_loss = sum(losses)
        return {
            "prior_count": len(pnls),
            "prior_net_pnl": sum(pnls),
            "prior_pf": gross_win / gross_loss if gross_loss else None,
            "prior_win_rate": len(wins) / len(pnls) if pnls else None,
        }

    def rule_triggers(stats):
        if stats["prior_count"] < RULE["min_prior"]:
            return False
        if stats["prior_net_pnl"] > RULE["prior_net_pnl_max"]:
            return False
        if stats["prior_pf"] is None:
            return False
        if stats["prior_pf"] > RULE["prior_pf_max"]:
            return False
        return True

    def apply_walkforward_rule(rows, capital_label):
        out_by_idx = {}
        skipped = []

        accepted_items = []
        inactive_items = []

        for idx, r in enumerate(rows):
            item = {
                "idx": idx,
                "row": r,
                "entry_date": entry_date(r),
                "close_date": close_date(r),
                "pnl": pnl(r),
                "accepted": accepted(r),
            }
            if accepted(r):
                accepted_items.append(item)
            else:
                inactive_items.append(item)

        accepted_items.sort(key=lambda x: (x["entry_date"], x["close_date"], x["idx"]))
        pending = sorted(accepted_items, key=lambda x: (x["close_date"], x["idx"]))
        pending_pos = 0
        history = defaultdict(list)

        for item in accepted_items:
            current_entry = item["entry_date"]

            while pending_pos < len(pending):
                prior_item = pending[pending_pos]
                if prior_item["close_date"] >= current_entry:
                    break
                history[scope_key(prior_item["row"])].append(prior_item["pnl"])
                pending_pos += 1

            new = dict(item["row"])
            key = scope_key(new)
            stats = prior_stats(history[key])

            if rule_triggers(stats):
                old_q = quantity(new)
                old_pnl = pnl(new)
                set_quantity(new, 0.0)
                set_pnl(new, 0.0)
                new["row_state"] = "skipped"
                new["v3_2_2_rule_id"] = RULE["rule_id"]
                new["v3_2_2_scope_key"] = key
                new["v3_2_2_prior_count"] = stats["prior_count"]
                new["v3_2_2_prior_net_pnl"] = stats["prior_net_pnl"]
                new["v3_2_2_prior_pf"] = stats["prior_pf"]
                new["v3_2_2_parent_quantity"] = old_q
                new["v3_2_2_parent_pnl"] = old_pnl

                skipped.append({
                    "capital_label": capital_label,
                    "row_index": item["idx"],
                    "entry_date": item["entry_date"],
                    "close_date": item["close_date"],
                    "symbol": group_value(item["row"], "symbol"),
                    "regime": group_value(item["row"], "regime"),
                    "strategy": group_value(item["row"], "strategy"),
                    "quantity": old_q,
                    "pnl": old_pnl,
                    **stats,
                })

            out_by_idx[item["idx"]] = new

        for item in inactive_items:
            out_by_idx[item["idx"]] = dict(item["row"])

        return [out_by_idx[i] for i in sorted(out_by_idx)], skipped

    def apply_extra_stress(rows, extra_pnl_per_contract):
        out = []
        for r in rows:
            new = dict(r)
            if accepted(new):
                set_pnl(new, pnl(new) + extra_pnl_per_contract * quantity(new))
            out.append(new)
        return out

    def metrics(rows, starting_capital):
        active = [r for r in rows if accepted(r)]
        trade_pnls = [pnl(r) for r in active]
        wins = [x for x in trade_pnls if x > 0]
        losses = [abs(x) for x in trade_pnls if x < 0]

        by_day = defaultdict(float)
        for r in active:
            by_day[close_date(r)] += pnl(r)

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
            "ending_equity": equity,
            "total_pnl_dollars": equity - starting_capital,
            "pnl_multiple": (equity - starting_capital) / starting_capital if starting_capital else None,
            "max_drawdown_pct": max_dd,
            "worst_drawdown_date": worst_dd_date,
            "trade_count": len(active),
            "contract_count": sum(quantity(r) for r in active),
            "win_rate": len(wins) / len(trade_pnls) if trade_pnls else None,
            "trade_profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
            "daily_profit_factor": sum(daily_wins) / sum(daily_losses) if sum(daily_losses) else None,
            "sharpe_proxy": mean_daily / stdev * sqrt(252) if stdev else None,
            "sortino_proxy": mean_daily / downside_dev * sqrt(252) if downside_dev else None,
            "gross_win_dollars": sum(wins),
            "gross_loss_dollars": sum(losses),
            "worst_daily_pnl": min(daily_pnls) if daily_pnls else None,
            "best_daily_pnl": max(daily_pnls) if daily_pnls else None,
            "trading_day_count": len(daily_pnls),
        }

    def round_dict(d):
        out = {}
        for k, v in d.items():
            if isinstance(v, float):
                out[k] = round(v, 6)
            else:
                out[k] = v
        return out

    blockers = []
    warnings = []
    stress_rows = []
    skipped_rows_all = []
    scenario_summaries = []

    for capital_label, cfg in SCENARIOS.items():
        if not cfg["ledger"].exists():
            blockers.append(f"missing_native_quote_ledger_{capital_label}: {cfg['ledger']}")
            continue

        original_rows = list(read_jsonl(cfg["ledger"]))
        baseline_metrics = metrics(original_rows, cfg["starting_capital"])

        candidate_rows, skipped = apply_walkforward_rule(original_rows, capital_label)
        write_jsonl(cfg["output_ledger"], candidate_rows)

        candidate_metrics = metrics(candidate_rows, cfg["starting_capital"])

        skipped_rows_all.extend(skipped)

        scenario_summaries.append({
            "capital_label": capital_label,
            "baseline_metrics": round_dict(baseline_metrics),
            "candidate_metrics": round_dict(candidate_metrics),
            "skipped_trade_count": len(skipped),
            "skipped_original_pnl": round(sum(x["pnl"] for x in skipped), 6),
            "delta_pnl_vs_baseline": round(candidate_metrics["total_pnl_dollars"] - baseline_metrics["total_pnl_dollars"], 6),
            "delta_drawdown_vs_baseline": round(candidate_metrics["max_drawdown_pct"] - baseline_metrics["max_drawdown_pct"], 6),
            "pnl_retention_vs_baseline": round(candidate_metrics["total_pnl_dollars"] / baseline_metrics["total_pnl_dollars"], 6),
        })

        for case in STRESS_CASES:
            stressed = apply_extra_stress(candidate_rows, case["extra_pnl_per_contract"])
            m = metrics(stressed, cfg["starting_capital"])

            stress_rows.append({
                "capital_label": capital_label,
                "stress_case": case["stress_case"],
                "extra_pnl_per_contract": case["extra_pnl_per_contract"],
                **round_dict(m),
                "pnl_retention_vs_v3_2_1_native_baseline": round(
                    m["total_pnl_dollars"] / baseline_metrics["total_pnl_dollars"], 6
                ) if baseline_metrics["total_pnl_dollars"] else None,
                "passes_positive_pnl": m["total_pnl_dollars"] > 0,
                "passes_pf_gt_1": m["trade_profit_factor"] is not None and m["trade_profit_factor"] > 1.0,
                "passes_dd_under_35pct": m["max_drawdown_pct"] > -0.35,
                "passes_stress": (
                    m["total_pnl_dollars"] > 0
                    and m["trade_profit_factor"] is not None
                    and m["trade_profit_factor"] > 1.0
                    and m["max_drawdown_pct"] > -0.35
                ),
            })

    write_jsonl(STRESS_ROWS_PATH, stress_rows)
    write_jsonl(SKIPPED_ROWS_PATH, skipped_rows_all)

    stress_case_names = sorted(set(r["stress_case"] for r in stress_rows))
    stress_rollups = []

    for case_name in stress_case_names:
        rows = [r for r in stress_rows if r["stress_case"] == case_name]
        stress_rollups.append({
            "stress_case": case_name,
            "scenario_count": len(rows),
            "all_pass": all(r["passes_stress"] for r in rows),
            "min_pnl_retention_vs_v3_2_1_native_baseline": min(r["pnl_retention_vs_v3_2_1_native_baseline"] for r in rows),
            "min_total_pnl": min(r["total_pnl_dollars"] for r in rows),
            "worst_drawdown": min(r["max_drawdown_pct"] for r in rows),
            "min_trade_pf": min(r["trade_profit_factor"] for r in rows if r["trade_profit_factor"] is not None),
        })

    baseline_candidate_rows = [r for r in stress_rows if r["stress_case"] == "baseline_native_quote_1x"]
    extra_100_rows = [r for r in stress_rows if r["stress_case"] == "extra_slip_100_per_contract"]

    passes_baseline = bool(baseline_candidate_rows) and all(r["passes_stress"] for r in baseline_candidate_rows)
    passes_extra_100 = bool(extra_100_rows) and all(r["passes_stress"] for r in extra_100_rows)
    all_positive_delta = all(s["delta_pnl_vs_baseline"] > 0 for s in scenario_summaries)
    all_nonworse_dd = all(s["delta_drawdown_vs_baseline"] >= 0 for s in scenario_summaries)

    if blockers:
        decision = "v3_2_2_symbol_regime_prune_blocked"
    elif passes_baseline and passes_extra_100 and all_positive_delta and all_nonworse_dd:
        decision = "promote_to_v3_2_2_research_candidate_for_review"
    elif passes_baseline and all_positive_delta:
        decision = "v3_2_2_research_candidate_needs_review"
    else:
        decision = "do_not_promote_v3_2_2_candidate"

    summary = {
        "adapter_type": "v3_2_2_symbol_regime_walkforward_prune_stress_builder",
        "artifact_type": "signalforge_v3_2_2_symbol_regime_walkforward_prune_stress",
        "contract": "v3_2_2_symbol_regime_walkforward_prune_stress",
        "candidate_id": "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531",
        "parent_candidate": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
        "is_ready": len(blockers) == 0,
        "readiness_state": "ready" if not blockers else "blocked",
        "decision": decision,
        "rule": RULE,
        "blockers": blockers,
        "warnings": warnings,
        "promotion_checks": {
            "passes_baseline_native_quote": passes_baseline,
            "passes_extra_100_per_contract_stress": passes_extra_100,
            "all_positive_delta_vs_v3_2_1_native": all_positive_delta,
            "all_nonworse_drawdown_vs_v3_2_1_native": all_nonworse_dd,
        },
        "scenario_summaries": scenario_summaries,
        "stress_rollups": stress_rollups,
        "stress_results": stress_rows,
        "paths": {
            "summary": str(SUMMARY_PATH),
            "stress_rows": str(STRESS_ROWS_PATH),
            "skipped_rows": str(SKIPPED_ROWS_PATH),
            "v3_2_2_30k_ledger": str(SCENARIOS["30k"]["output_ledger"]),
            "v3_2_2_40k_ledger": str(SCENARIOS["40k"]["output_ledger"]),
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


