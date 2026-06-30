import json
import os
from pathlib import Path
from collections import defaultdict, Counter
from math import sqrt

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_NATIVE_QUOTE_ATTRIBUTION_OUT_DIR",
    "artifacts/v3_2_2_native_quote_attribution_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_2_native_quote_attribution_summary.json"
GROUP_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_native_quote_attribution_groups.jsonl"
TOP_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_native_quote_attribution_top_rows.jsonl"

V322_STRESS_SUMMARY = env_path(
    "SIGNALFORGE_V3_2_2_NATIVE_QUOTE_ATTRIBUTION_STRESS_SUMMARY",
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/signalforge_v3_2_2_symbol_regime_walkforward_prune_stress_summary.json",
)

SCENARIOS = {
    "30k": {
        "starting_capital": 30000.0,
        "ledger": env_path(
            "SIGNALFORGE_V3_2_2_NATIVE_QUOTE_ATTRIBUTION_30K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_30k/ledger.jsonl",
        ),
    },
    "40k": {
        "starting_capital": 40000.0,
        "ledger": env_path(
            "SIGNALFORGE_V3_2_2_NATIVE_QUOTE_ATTRIBUTION_40K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_40k/ledger.jsonl",
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

DATE_FIELDS = [
    "decision_date",
    "entry_date",
    "trade_date",
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
    "option_liquidity": ["option_liquidity_state", "liquidity_state"],
    "bucket": ["strategy_bucket", "bucket", "portfolio_bucket", "rank_bucket"],
    "structure": ["strategy_structure", "structure"],
}

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

def date_str(row):
    v, _ = pick(row, DATE_FIELDS, "")
    return str(v)[:10] if v is not None else ""

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

def group_value(row, group_name):
    fields = GROUP_FIELDS[group_name]
    v, _ = pick(row, fields, "missing")
    return str(v)

def stress_meta(row):
    meta = row.get("native_quote_pnl_stress")
    if isinstance(meta, dict):
        return meta
    return {}

def quote_cost(row):
    meta = stress_meta(row)
    return fnum(meta.get("native_quote_cost_after_multiplier"), 0.0)

def commission_cost(row):
    meta = stress_meta(row)
    return fnum(meta.get("commission_cost"), 0.0)

def total_execution_cost(row):
    meta = stress_meta(row)
    return fnum(meta.get("total_execution_adjustment"), quote_cost(row) + commission_cost(row))

def quote_cost_method(row):
    meta = stress_meta(row)
    return str(meta.get("native_quote_cost_method", "missing"))

def quote_join(row):
    qj = row.get("native_quote_join")
    if isinstance(qj, dict):
        return qj
    return {}

def quote_unit_cost(row):
    qj = quote_join(row)
    return fnum(qj.get("round_trip_half_spread_cost_per_strategy_unit"), None)

def quote_cost_bucket(row):
    u = quote_unit_cost(row)
    if u is None:
        return "missing_quote"
    if u <= 25:
        return "00_25"
    if u <= 50:
        return "25_50"
    if u <= 100:
        return "50_100"
    if u <= 150:
        return "100_150"
    if u <= 250:
        return "150_250"
    return "250_plus"

def percentile(values, pct):
    vals = sorted([float(v) for v in values if v is not None])
    if not vals:
        return None
    idx = (len(vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac

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

def group_metrics(rows):
    active = [r for r in rows if accepted(r)]
    pnls = [pnl(r) for r in active]
    wins = [x for x in pnls if x > 0]
    losses = [abs(x) for x in pnls if x < 0]
    quote_costs = [quote_cost(r) for r in active]
    costs = [total_execution_cost(r) for r in active]
    unit_costs = [quote_unit_cost(r) for r in active if quote_unit_cost(r) is not None]

    gross_win = sum(wins)
    gross_loss = sum(losses)
    net_pnl = sum(pnls)
    total_cost = sum(costs)

    return {
        "trade_count": len(active),
        "contract_count": sum(quantity(r) for r in active),
        "net_pnl": net_pnl,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": gross_win / gross_loss if gross_loss else None,
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "avg_trade_pnl": net_pnl / len(pnls) if pnls else None,
        "total_execution_cost": total_cost,
        "total_native_quote_cost": sum(quote_costs),
        "quote_cost_per_trade_avg": sum(quote_costs) / len(active) if active else None,
        "quote_cost_unit_p50": percentile(unit_costs, 0.50),
        "quote_cost_unit_p90": percentile(unit_costs, 0.90),
        "quote_cost_unit_p95": percentile(unit_costs, 0.95),
    }

def round_dict(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 6)
        else:
            out[k] = v
    return out

def add_group_rows(capital_label, group_name, rows, out_rows, total_pnl, total_cost):
    buckets = defaultdict(list)

    for r in rows:
        if not accepted(r):
            continue

        if group_name == "quote_cost_bucket":
            key = quote_cost_bucket(r)
        else:
            key = group_value(r, group_name)

        buckets[key].append(r)

    for key, vals in buckets.items():
        m = group_metrics(vals)

        out_rows.append({
            "capital_label": capital_label,
            "group_name": group_name,
            "group_value": key,
            **round_dict(m),
            "share_of_total_pnl": round(m["net_pnl"] / total_pnl, 6) if total_pnl else None,
            "share_of_total_execution_cost": round(m["total_execution_cost"] / total_cost, 6) if total_cost else None,
            "is_negative_group": m["net_pnl"] < 0,
            "is_low_pf_group": (m["profit_factor"] is not None and m["profit_factor"] < 1.25),
            "is_material_group": abs(m["net_pnl"]) >= abs(total_pnl) * 0.02 if total_pnl else False,
        })

def concentration_summary(group_rows, capital_label, group_name):
    rows = [
        r for r in group_rows
        if r["capital_label"] == capital_label and r["group_name"] == group_name
    ]

    pos = sorted([r for r in rows if r["net_pnl"] > 0], key=lambda r: r["net_pnl"], reverse=True)
    cost = sorted(rows, key=lambda r: r["total_execution_cost"], reverse=True)
    neg = sorted([r for r in rows if r["net_pnl"] < 0], key=lambda r: r["net_pnl"])

    total_pnl = sum(r["net_pnl"] for r in rows)
    total_cost = sum(r["total_execution_cost"] for r in rows)

    top1_pnl_share = pos[0]["net_pnl"] / total_pnl if pos and total_pnl else None
    top3_pnl_share = sum(r["net_pnl"] for r in pos[:3]) / total_pnl if pos and total_pnl else None
    top5_pnl_share = sum(r["net_pnl"] for r in pos[:5]) / total_pnl if pos and total_pnl else None

    top1_cost_share = cost[0]["total_execution_cost"] / total_cost if cost and total_cost else None
    top3_cost_share = sum(r["total_execution_cost"] for r in cost[:3]) / total_cost if cost and total_cost else None
    top5_cost_share = sum(r["total_execution_cost"] for r in cost[:5]) / total_cost if cost and total_cost else None

    return {
        "capital_label": capital_label,
        "group_name": group_name,
        "group_count": len(rows),
        "top1_positive_pnl_share": round(top1_pnl_share, 6) if top1_pnl_share is not None else None,
        "top3_positive_pnl_share": round(top3_pnl_share, 6) if top3_pnl_share is not None else None,
        "top5_positive_pnl_share": round(top5_pnl_share, 6) if top5_pnl_share is not None else None,
        "top1_execution_cost_share": round(top1_cost_share, 6) if top1_cost_share is not None else None,
        "top3_execution_cost_share": round(top3_cost_share, 6) if top3_cost_share is not None else None,
        "top5_execution_cost_share": round(top5_cost_share, 6) if top5_cost_share is not None else None,
        "negative_group_count": len(neg),
        "largest_negative_group": neg[0]["group_value"] if neg else None,
        "largest_negative_group_pnl": round(neg[0]["net_pnl"], 6) if neg else None,
    }

blockers = []
warnings = []
scenario_summaries = []
all_group_rows = []
top_rows = []

stress_summary = None
if V322_STRESS_SUMMARY.exists():
    stress_summary = json.loads(V322_STRESS_SUMMARY.read_text(encoding="utf-8"))
else:
    blockers.append(f"missing_v3_2_2_stress_summary: {V322_STRESS_SUMMARY}")

for capital_label, cfg in SCENARIOS.items():
    if not cfg["ledger"].exists():
        blockers.append(f"missing_v3_2_2_ledger_{capital_label}: {cfg['ledger']}")
        continue

    rows = list(read_jsonl(cfg["ledger"]))
    active = [r for r in rows if accepted(r)]

    m = metrics(rows, cfg["starting_capital"])

    total_pnl = sum(pnl(r) for r in active)
    total_cost = sum(total_execution_cost(r) for r in active)
    total_quote_cost = sum(quote_cost(r) for r in active)
    total_commission = sum(commission_cost(r) for r in active)

    methods = Counter(quote_cost_method(r) for r in active)
    quote_buckets = Counter(quote_cost_bucket(r) for r in active)

    scenario_summaries.append({
        "capital_label": capital_label,
        "active_trade_count": len(active),
        "metrics": round_dict(m),
        "total_pnl": round(total_pnl, 6),
        "total_execution_cost": round(total_cost, 6),
        "total_native_quote_cost": round(total_quote_cost, 6),
        "total_commission_cost": round(total_commission, 6),
        "execution_cost_as_pct_of_native_pnl": round(total_cost / total_pnl, 6) if total_pnl else None,
        "quote_cost_method_counts": dict(methods),
        "quote_cost_bucket_counts": dict(quote_buckets),
    })

    for group_name in list(GROUP_FIELDS.keys()) + ["quote_cost_bucket"]:
        add_group_rows(capital_label, group_name, active, all_group_rows, total_pnl, total_cost)

    for idx, r in enumerate(sorted(active, key=lambda x: total_execution_cost(x), reverse=True)[:25]):
        top_rows.append({
            "capital_label": capital_label,
            "rank_type": "highest_execution_cost",
            "rank": idx + 1,
            "decision_date": date_str(r),
            "close_date": close_date_str(r),
            "symbol": group_value(r, "symbol"),
            "strategy": group_value(r, "strategy"),
            "regime": group_value(r, "regime"),
            "asset_behavior": group_value(r, "asset_behavior"),
            "option_behavior": group_value(r, "option_behavior"),
            "quantity": quantity(r),
            "pnl": pnl(r),
            "total_execution_cost": total_execution_cost(r),
            "native_quote_cost": quote_cost(r),
            "commission_cost": commission_cost(r),
            "quote_cost_unit": quote_unit_cost(r),
            "quote_cost_bucket": quote_cost_bucket(r),
            "quote_cost_method": quote_cost_method(r),
        })

    for idx, r in enumerate(sorted(active, key=lambda x: pnl(x))[:25]):
        top_rows.append({
            "capital_label": capital_label,
            "rank_type": "largest_native_quote_losses",
            "rank": idx + 1,
            "decision_date": date_str(r),
            "close_date": close_date_str(r),
            "symbol": group_value(r, "symbol"),
            "strategy": group_value(r, "strategy"),
            "regime": group_value(r, "regime"),
            "asset_behavior": group_value(r, "asset_behavior"),
            "option_behavior": group_value(r, "option_behavior"),
            "quantity": quantity(r),
            "pnl": pnl(r),
            "total_execution_cost": total_execution_cost(r),
            "native_quote_cost": quote_cost(r),
            "commission_cost": commission_cost(r),
            "quote_cost_unit": quote_unit_cost(r),
            "quote_cost_bucket": quote_cost_bucket(r),
            "quote_cost_method": quote_cost_method(r),
        })

concentration = []
for capital_label in SCENARIOS.keys():
    for group_name in ["strategy", "symbol", "regime", "asset_behavior", "option_behavior", "quote_cost_bucket"]:
        concentration.append(concentration_summary(all_group_rows, capital_label, group_name))

write_jsonl(GROUP_ROWS_PATH, all_group_rows)
write_jsonl(TOP_ROWS_PATH, top_rows)

follow_up_groups = []
for r in all_group_rows:
    if r["trade_count"] < 10:
        continue
    if r["net_pnl"] < 0:
        follow_up_groups.append({**r, "follow_up_reason": "negative_native_quote_group_with_10plus_trades"})
    elif r["profit_factor"] is not None and r["profit_factor"] < 1.25 and r["trade_count"] >= 20:
        follow_up_groups.append({**r, "follow_up_reason": "low_profit_factor_native_quote_group_with_20plus_trades"})

material_negative_groups = [
    r for r in follow_up_groups
    if r["is_material_group"] and r["net_pnl"] < 0
]

high_single_strategy_concentration = False
for c in concentration:
    if c["group_name"] == "strategy" and c["top1_positive_pnl_share"] is not None and c["top1_positive_pnl_share"] > 0.50:
        high_single_strategy_concentration = True

stress_passed = False
if stress_summary:
    pc = stress_summary.get("promotion_checks", {})
    stress_passed = (
        bool(pc.get("passes_baseline_native_quote"))
        and bool(pc.get("passes_extra_100_per_contract_stress"))
        and bool(pc.get("all_positive_delta_vs_v3_2_1_native"))
        and bool(pc.get("all_nonworse_drawdown_vs_v3_2_1_native"))
    )

if blockers:
    decision = "v3_2_2_native_quote_attribution_blocked"
elif stress_passed and not material_negative_groups and not high_single_strategy_concentration:
    decision = "v3_2_2_native_quote_attribution_passed"
elif stress_passed:
    decision = "v3_2_2_native_quote_attribution_passed_with_follow_up_flags"
else:
    decision = "v3_2_2_native_quote_attribution_failed_stress_not_passed"

if high_single_strategy_concentration:
    warnings.append("Top single strategy contributes more than 50% of positive native-quote PnL in at least one scenario.")

if material_negative_groups:
    warnings.append("Material negative native-quote groups found; inspect follow_up_groups.")

summary = {
    "adapter_type": "v3_2_2_native_quote_attribution_builder",
    "artifact_type": "signalforge_v3_2_2_native_quote_attribution",
    "contract": "v3_2_2_native_quote_attribution",
    "candidate_id": "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531",
    "parent_candidate": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
    "is_ready": len(blockers) == 0,
    "readiness_state": "ready" if not blockers else "blocked",
    "decision": decision,
    "blockers": blockers,
    "warnings": warnings,
    "v3_2_2_stress_decision": stress_summary.get("decision") if stress_summary else None,
    "scenario_summaries": scenario_summaries,
    "concentration_summary": concentration,
    "follow_up_group_count": len(follow_up_groups),
    "follow_up_groups_top_50": sorted(
        follow_up_groups,
        key=lambda r: (r["net_pnl"], -r["trade_count"])
    )[:50],
    "paths": {
        "summary": str(SUMMARY_PATH),
        "group_rows": str(GROUP_ROWS_PATH),
        "top_rows": str(TOP_ROWS_PATH),
    },
}

SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True, default=str))




