import json
import os
from pathlib import Path
from collections import defaultdict, deque
from math import sqrt

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_NATIVE_QUOTE_WALKFORWARD_PRUNE_VALIDATION_OUT_DIR",
    "artifacts/v3_2_1_native_quote_walkforward_prune_validation_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_walkforward_prune_validation_summary.json"
RESULTS_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_walkforward_prune_validation_results.jsonl"
SKIPPED_ROWS_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_walkforward_prune_validation_skipped_rows.jsonl"

SCENARIOS = {
    "30k": {
        "starting_capital": 30000.0,
        "ledger": env_path(
            "SIGNALFORGE_NATIVE_QUOTE_WALKFORWARD_PRUNE_VALIDATION_30K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_30k/ledger.jsonl",
        ),
    },
    "40k": {
        "starting_capital": 40000.0,
        "ledger": env_path(
            "SIGNALFORGE_NATIVE_QUOTE_WALKFORWARD_PRUNE_VALIDATION_40K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_40k/ledger.jsonl",
        ),
    },
}

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

ENTRY_DATE_FIELDS = [
    "entry_date",
    "trade_date",
    "decision_date",
    "date",
]

CLOSE_DATE_FIELDS = [
    "realization_date",
    "portfolio_realization_date",
    "exit_date",
    "close_date",
    "outcome_date",
    "decision_date",
]

GROUP_FIELDS = {
    "strategy": ["selected_strategy", "strategy", "strategy_family", "strategy_name"],
    "symbol": ["symbol", "underlying_symbol", "ticker"],
    "regime": ["regime_state", "market_regime", "regime"],
    "asset_behavior": ["asset_behavior_state", "asset_state", "behavior_state"],
    "option_behavior": ["option_behavior_state", "option_state"],
    "bucket": ["strategy_bucket", "bucket", "portfolio_bucket", "rank_bucket"],
}

CASES = [
    {
        "case_name": "baseline_native_quote_1x",
        "rule_type": "baseline",
    },
    {
        "case_name": "prior_symbol_m10_netneg_pf075",
        "rule_type": "symbol_prior",
        "scope": ["symbol"],
        "min_prior": 10,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.75,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_m10_netneg_pf090",
        "rule_type": "symbol_prior",
        "scope": ["symbol"],
        "min_prior": 10,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_m15_netneg_pf090",
        "rule_type": "symbol_prior",
        "scope": ["symbol"],
        "min_prior": 15,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_rolling20_netneg_pf090",
        "rule_type": "symbol_prior",
        "scope": ["symbol"],
        "min_prior": 10,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": 20,
    },
    {
        "case_name": "prior_strategy_m30_netneg_pf090",
        "rule_type": "strategy_prior",
        "scope": ["strategy"],
        "min_prior": 30,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_strategy_m50_netneg_pf100",
        "rule_type": "strategy_prior",
        "scope": ["strategy"],
        "min_prior": 50,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 1.00,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_strategy_m8_netneg_pf090",
        "rule_type": "symbol_strategy_prior",
        "scope": ["symbol", "strategy"],
        "min_prior": 8,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_regime_m8_netneg_pf090",
        "rule_type": "symbol_regime_prior",
        "scope": ["symbol", "regime"],
        "min_prior": 8,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
    {
        "case_name": "prior_symbol_option_m8_netneg_pf090",
        "rule_type": "symbol_option_prior",
        "scope": ["symbol", "option_behavior"],
        "min_prior": 8,
        "prior_net_pnl_max": 0.0,
        "prior_pf_max": 0.90,
        "lookback_trades": None,
    },
]

def read_jsonl(path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def write_jsonl(path, rows):
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

def scope_key(row, scope):
    return tuple(group_value(row, name) for name in scope)

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

def rule_triggers(stats, case):
    if case["rule_type"] == "baseline":
        return False

    if stats["prior_count"] < case["min_prior"]:
        return False

    if stats["prior_net_pnl"] > case["prior_net_pnl_max"]:
        return False

    pf = stats["prior_pf"]

    # If there are no losses, do not reject.
    if pf is None:
        return False

    if pf > case["prior_pf_max"]:
        return False

    return True

def apply_walkforward_case(rows, capital_label, case):
    if case["rule_type"] == "baseline":
        return [dict(r) for r in rows], []

    out_by_original_index = {}
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
            "quantity": quantity(r),
            "accepted": accepted(r),
        }
        if accepted(r):
            accepted_items.append(item)
        else:
            inactive_items.append(item)

    # Sort by entry date. Prior outcomes only become available after close date < current entry date.
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

            # Add original baseline outcome into prior history.
            # This is a prior-available predictive audit, not yet a live state machine.
            for prior_case_scope in [case["scope"]]:
                key = scope_key(prior_item["row"], prior_case_scope)
                history[key].append(prior_item["pnl"])

            pending_pos += 1

        new = dict(item["row"])
        key = scope_key(new, case["scope"])
        prior_pnls = history[key]

        if case.get("lookback_trades") is not None:
            prior_pnls_for_rule = prior_pnls[-int(case["lookback_trades"]):]
        else:
            prior_pnls_for_rule = prior_pnls

        stats = prior_stats(prior_pnls_for_rule)

        if rule_triggers(stats, case):
            old_q = quantity(new)
            old_pnl = pnl(new)
            set_quantity(new, 0.0)
            set_pnl(new, 0.0)
            new["row_state"] = "skipped"
            new["walkforward_prune_case"] = case["case_name"]
            new["walkforward_prune_scope"] = case["scope"]
            new["walkforward_prune_scope_key"] = key
            new["walkforward_prune_prior_count"] = stats["prior_count"]
            new["walkforward_prune_prior_net_pnl"] = stats["prior_net_pnl"]
            new["walkforward_prune_prior_pf"] = stats["prior_pf"]
            new["walkforward_prune_parent_quantity"] = old_q
            new["walkforward_prune_parent_pnl"] = old_pnl

            skipped.append({
                "capital_label": capital_label,
                "case_name": case["case_name"],
                "row_index": item["idx"],
                "entry_date": item["entry_date"],
                "close_date": item["close_date"],
                "symbol": group_value(item["row"], "symbol"),
                "strategy": group_value(item["row"], "strategy"),
                "scope": case["scope"],
                "scope_key": key,
                "quantity": old_q,
                "pnl": old_pnl,
                **stats,
            })

        out_by_original_index[item["idx"]] = new

    for item in inactive_items:
        out_by_original_index[item["idx"]] = dict(item["row"])

    return [out_by_original_index[i] for i in sorted(out_by_original_index)], skipped

blockers = []
warnings = []
result_rows = []
all_skipped = []
scenario_summaries = []

for capital_label, cfg in SCENARIOS.items():
    if not cfg["ledger"].exists():
        blockers.append(f"missing_native_quote_ledger_{capital_label}: {cfg['ledger']}")
        continue

    rows = list(read_jsonl(cfg["ledger"]))

    baseline_rows, _ = apply_walkforward_case(
        rows,
        capital_label,
        {"case_name": "baseline_native_quote_1x", "rule_type": "baseline"},
    )
    baseline_metrics = metrics(baseline_rows, cfg["starting_capital"])

    scenario_summaries.append({
        "capital_label": capital_label,
        "baseline_metrics": round_dict(baseline_metrics),
    })

    for case in CASES:
        case_rows, skipped = apply_walkforward_case(rows, capital_label, case)
        m = metrics(case_rows, cfg["starting_capital"])

        delta_pnl = m["total_pnl_dollars"] - baseline_metrics["total_pnl_dollars"]
        delta_dd = m["max_drawdown_pct"] - baseline_metrics["max_drawdown_pct"]
        pnl_retention = m["total_pnl_dollars"] / baseline_metrics["total_pnl_dollars"] if baseline_metrics["total_pnl_dollars"] else None
        trade_retention = m["trade_count"] / baseline_metrics["trade_count"] if baseline_metrics["trade_count"] else None

        passes_native_quality = (
            m["total_pnl_dollars"] > 0
            and m["trade_profit_factor"] is not None
            and m["trade_profit_factor"] > 1.0
            and m["max_drawdown_pct"] > -0.35
        )

        candidate_pass = (
            case["rule_type"] != "baseline"
            and delta_pnl > 0
            and delta_dd >= 0
            and passes_native_quality
            and len(skipped) >= 10
        )

        result_rows.append({
            "capital_label": capital_label,
            "case_name": case["case_name"],
            "rule_type": case["rule_type"],
            "scope": case.get("scope"),
            "min_prior": case.get("min_prior"),
            "prior_pf_max": case.get("prior_pf_max"),
            "lookback_trades": case.get("lookback_trades"),
            **round_dict(m),
            "skipped_trade_count": len(skipped),
            "skipped_original_pnl": round(sum(x["pnl"] for x in skipped), 6),
            "delta_pnl_vs_baseline": round(delta_pnl, 6),
            "delta_drawdown_vs_baseline": round(delta_dd, 6),
            "pnl_retention_vs_baseline": round(pnl_retention, 6) if pnl_retention is not None else None,
            "trade_retention_vs_baseline": round(trade_retention, 6) if trade_retention is not None else None,
            "passes_native_quality": passes_native_quality,
            "candidate_pass": candidate_pass,
        })

        all_skipped.extend(skipped)

write_jsonl(RESULTS_PATH, result_rows)
write_jsonl(SKIPPED_ROWS_PATH, all_skipped)

case_names = sorted(set(r["case_name"] for r in result_rows if r["case_name"] != "baseline_native_quote_1x"))

case_rollups = []

for case_name in case_names:
    rows = [r for r in result_rows if r["case_name"] == case_name]

    case_rollups.append({
        "case_name": case_name,
        "scenario_count": len(rows),
        "all_candidate_pass": all(r["candidate_pass"] for r in rows),
        "all_positive_delta_pnl": all(r["delta_pnl_vs_baseline"] > 0 for r in rows),
        "all_nonworse_drawdown": all(r["delta_drawdown_vs_baseline"] >= 0 for r in rows),
        "min_delta_pnl": min(r["delta_pnl_vs_baseline"] for r in rows),
        "max_delta_pnl": max(r["delta_pnl_vs_baseline"] for r in rows),
        "min_pnl_retention": min(r["pnl_retention_vs_baseline"] for r in rows),
        "total_skipped_trade_count": sum(r["skipped_trade_count"] for r in rows),
        "total_skipped_original_pnl": sum(r["skipped_original_pnl"] for r in rows),
    })

promoted_research_candidates = [
    r for r in case_rollups
    if r["all_candidate_pass"]
]

if blockers:
    decision = "walkforward_prune_validation_blocked"
elif promoted_research_candidates:
    decision = "walkforward_prune_candidates_found"
else:
    decision = "walkforward_prune_no_promotion_candidate"

if promoted_research_candidates:
    warnings.append("Walk-forward prune candidates found. Treat as research candidates only until stress/attribution confirms robustness.")
else:
    warnings.append("No prior-only prune candidate passed all scenarios. Do not promote in-sample weak-symbol pruning.")

summary = {
    "adapter_type": "v3_2_1_native_quote_walkforward_prune_validation_builder",
    "artifact_type": "signalforge_v3_2_1_native_quote_walkforward_prune_validation",
    "contract": "v3_2_1_native_quote_walkforward_prune_validation",
    "candidate_id": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
    "is_ready": len(blockers) == 0,
    "readiness_state": "ready" if not blockers else "blocked",
    "decision": decision,
    "blockers": blockers,
    "warnings": warnings,
    "scenario_summaries": scenario_summaries,
    "case_rollups": case_rollups,
    "promoted_research_candidate_count": len(promoted_research_candidates),
    "promoted_research_candidates": promoted_research_candidates,
    "paths": {
        "summary": str(SUMMARY_PATH),
        "results": str(RESULTS_PATH),
        "skipped_rows": str(SKIPPED_ROWS_PATH),
    },
}

SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True, default=str))
