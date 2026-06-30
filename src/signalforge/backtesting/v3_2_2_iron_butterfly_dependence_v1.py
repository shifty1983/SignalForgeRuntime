import json
import os
from pathlib import Path
from collections import defaultdict
from math import sqrt

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_IRON_BUTTERFLY_DEPENDENCE_OUT_DIR",
    "artifacts/v3_2_2_iron_butterfly_dependence_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_2_iron_butterfly_dependence_summary.json"
RESULTS_PATH = OUT_DIR / "signalforge_v3_2_2_iron_butterfly_dependence_results.jsonl"

SCENARIOS = {
    "30k": {
        "starting_capital": 30000.0,
        "ledger": env_path(
            "SIGNALFORGE_V3_2_2_IRON_BUTTERFLY_DEPENDENCE_30K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_30k/ledger.jsonl",
        ),
    },
    "40k": {
        "starting_capital": 40000.0,
        "ledger": env_path(
            "SIGNALFORGE_V3_2_2_IRON_BUTTERFLY_DEPENDENCE_40K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_40k/ledger.jsonl",
        ),
    },
}

CASES = [
    {"case_name": "baseline_v3_2_2", "case_type": "baseline"},
    {"case_name": "skip_iron_butterfly", "case_type": "dependency_removal"},
    {"case_name": "cap_iron_butterfly_to_3", "case_type": "quantity_cap", "cap": 3},
    {"case_name": "cap_iron_butterfly_to_2", "case_type": "quantity_cap", "cap": 2},
    {"case_name": "cap_iron_butterfly_to_1", "case_type": "quantity_cap", "cap": 1},
]

QUANTITY_FIELDS = ["quantity", "adjusted_quantity", "contract_count", "allocated_contract_count", "contracts"]
PNL_FIELDS = ["allocated_pnl", "adjusted_allocated_pnl", "realized_pnl_dollars", "pnl_dollars", "realized_pnl"]
CLOSE_DATE_FIELDS = ["realization_date", "portfolio_realization_date", "exit_date", "close_date", "outcome_date", "decision_date"]
STRATEGY_FIELDS = ["selected_strategy", "strategy", "strategy_family", "strategy_name"]

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

def close_date(row):
    v, _ = pick(row, CLOSE_DATE_FIELDS, "")
    return str(v)[:10] if v is not None else ""

def strategy(row):
    v, _ = pick(row, STRATEGY_FIELDS, "missing")
    return str(v)

def row_state(row):
    v, _ = pick(row, ["row_state", "sizing_state", "adjusted_row_state"], "accepted")
    return str(v).lower()

def accepted(row):
    if quantity(row) <= 0:
        return False
    s = row_state(row)
    return not ("skip" in s or "reject" in s)

def apply_case(rows, case):
    out = []
    adjusted_count = 0
    original_removed_pnl = 0.0
    original_removed_contracts = 0.0

    for r in rows:
        new = dict(r)

        if not accepted(new):
            out.append(new)
            continue

        if strategy(new) != "iron_butterfly":
            out.append(new)
            continue

        old_q = quantity(new)
        old_pnl = pnl(new)

        if case["case_type"] == "baseline":
            out.append(new)
            continue

        if case["case_type"] == "dependency_removal":
            set_quantity(new, 0.0)
            set_pnl(new, 0.0)
            new["row_state"] = "skipped"
            new["iron_butterfly_dependence_case"] = case["case_name"]
            adjusted_count += 1
            original_removed_pnl += old_pnl
            original_removed_contracts += old_q
            out.append(new)
            continue

        if case["case_type"] == "quantity_cap":
            cap = float(case["cap"])

            if old_q > cap:
                scale = cap / old_q if old_q else 0.0
                new_pnl = old_pnl * scale
                removed_pnl = old_pnl - new_pnl

                set_quantity(new, cap)
                set_pnl(new, new_pnl)
                new["iron_butterfly_dependence_case"] = case["case_name"]
                new["iron_butterfly_parent_quantity"] = old_q
                new["iron_butterfly_parent_pnl"] = old_pnl
                new["iron_butterfly_scaled_quantity"] = cap
                new["iron_butterfly_scaled_pnl"] = new_pnl

                adjusted_count += 1
                original_removed_pnl += removed_pnl
                original_removed_contracts += old_q - cap

        out.append(new)

    return out, {
        "adjusted_trade_count": adjusted_count,
        "removed_or_scaled_pnl": original_removed_pnl,
        "removed_or_scaled_contracts": original_removed_contracts,
    }

def metrics(rows, starting_capital):
    active = [r for r in rows if accepted(r)]
    trade_pnls = [pnl(r) for r in active]
    wins = [x for x in trade_pnls if x > 0]
    losses = [abs(x) for x in trade_pnls if x < 0]

    by_day = defaultdict(float)
    by_strategy = defaultdict(float)

    for r in active:
        by_day[close_date(r)] += pnl(r)
        by_strategy[strategy(r)] += pnl(r)

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

    positive_strategy = sorted(
        [(k, v) for k, v in by_strategy.items() if v > 0],
        key=lambda kv: kv[1],
        reverse=True
    )
    total_positive_strategy_pnl = sum(v for _, v in positive_strategy)

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
        "top_strategy": positive_strategy[0][0] if positive_strategy else None,
        "top_strategy_positive_pnl": positive_strategy[0][1] if positive_strategy else None,
        "top_strategy_positive_pnl_share": positive_strategy[0][1] / total_positive_strategy_pnl if positive_strategy and total_positive_strategy_pnl else None,
        "iron_butterfly_pnl": by_strategy.get("iron_butterfly", 0.0),
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
result_rows = []
scenario_summaries = []

for capital_label, cfg in SCENARIOS.items():
    if not cfg["ledger"].exists():
        blockers.append(f"missing_v3_2_2_ledger_{capital_label}: {cfg['ledger']}")
        continue

    rows = list(read_jsonl(cfg["ledger"]))

    baseline_case_rows, baseline_adjust = apply_case(rows, CASES[0])
    baseline_metrics = metrics(baseline_case_rows, cfg["starting_capital"])

    scenario_summaries.append({
        "capital_label": capital_label,
        "baseline_metrics": round_dict(baseline_metrics),
    })

    for case in CASES:
        case_rows, adjust = apply_case(rows, case)
        m = metrics(case_rows, cfg["starting_capital"])

        delta_pnl = m["total_pnl_dollars"] - baseline_metrics["total_pnl_dollars"]
        delta_dd = m["max_drawdown_pct"] - baseline_metrics["max_drawdown_pct"]

        passes_survival = (
            m["total_pnl_dollars"] > 0
            and m["trade_profit_factor"] is not None
            and m["trade_profit_factor"] > 1.0
            and m["max_drawdown_pct"] > -0.35
        )

        concentration_resolved = (
            m["top_strategy_positive_pnl_share"] is not None
            and m["top_strategy_positive_pnl_share"] <= 0.50
        )

        balanced_cap_candidate = (
            case["case_type"] == "quantity_cap"
            and passes_survival
            and concentration_resolved
            and m["total_pnl_dollars"] >= baseline_metrics["total_pnl_dollars"] * 0.90
            and m["max_drawdown_pct"] >= baseline_metrics["max_drawdown_pct"]
        )

        result_rows.append({
            "capital_label": capital_label,
            "case_name": case["case_name"],
            "case_type": case["case_type"],
            **round_dict(m),
            **round_dict(adjust),
            "delta_pnl_vs_baseline": round(delta_pnl, 6),
            "delta_drawdown_vs_baseline": round(delta_dd, 6),
            "pnl_retention_vs_baseline": round(
                m["total_pnl_dollars"] / baseline_metrics["total_pnl_dollars"], 6
            ) if baseline_metrics["total_pnl_dollars"] else None,
            "passes_survival": passes_survival,
            "concentration_resolved": concentration_resolved,
            "balanced_cap_candidate": balanced_cap_candidate,
        })

write_jsonl(RESULTS_PATH, result_rows)

case_names = sorted(set(r["case_name"] for r in result_rows))

case_rollups = []
for name in case_names:
    rows = [r for r in result_rows if r["case_name"] == name]

    case_rollups.append({
        "case_name": name,
        "scenario_count": len(rows),
        "all_pass_survival": all(r["passes_survival"] for r in rows),
        "all_concentration_resolved": all(r["concentration_resolved"] for r in rows),
        "all_balanced_cap_candidate": all(r["balanced_cap_candidate"] for r in rows),
        "min_pnl_retention": min(r["pnl_retention_vs_baseline"] for r in rows),
        "min_total_pnl": min(r["total_pnl_dollars"] for r in rows),
        "worst_drawdown": min(r["max_drawdown_pct"] for r in rows),
        "max_top_strategy_positive_pnl_share": max(
            r["top_strategy_positive_pnl_share"]
            for r in rows
            if r["top_strategy_positive_pnl_share"] is not None
        ),
    })

balanced_candidates = [
    r for r in case_rollups
    if r["all_balanced_cap_candidate"]
]

skip_rows = [r for r in case_rollups if r["case_name"] == "skip_iron_butterfly"]
skip_passes = bool(skip_rows) and all(r["all_pass_survival"] for r in skip_rows)

if blockers:
    decision = "v3_2_2_iron_butterfly_dependence_blocked"
elif balanced_candidates:
    decision = "iron_butterfly_balanced_cap_candidates_found"
elif skip_passes:
    decision = "iron_butterfly_dependency_survival_passed_no_cap_candidate"
else:
    decision = "iron_butterfly_dependency_survival_failed"

if balanced_candidates:
    warnings.append("Balanced cap candidates found. Validate with full native quote stress before promotion.")
elif skip_passes:
    warnings.append("System survives removal of iron_butterfly, but no balanced cap candidate met concentration and retention requirements.")
else:
    warnings.append("System does not cleanly survive iron_butterfly removal under configured criteria.")

summary = {
    "adapter_type": "v3_2_2_iron_butterfly_dependence_builder",
    "artifact_type": "signalforge_v3_2_2_iron_butterfly_dependence",
    "contract": "v3_2_2_iron_butterfly_dependence",
    "candidate_id": "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531",
    "is_ready": len(blockers) == 0,
    "readiness_state": "ready" if not blockers else "blocked",
    "decision": decision,
    "blockers": blockers,
    "warnings": warnings,
    "scenario_summaries": scenario_summaries,
    "case_rollups": case_rollups,
    "balanced_cap_candidates": balanced_candidates,
    "paths": {
        "summary": str(SUMMARY_PATH),
        "results": str(RESULTS_PATH),
    },
}

SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True, default=str))


