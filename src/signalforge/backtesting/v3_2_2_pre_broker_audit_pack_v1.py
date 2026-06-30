import json
import os
from pathlib import Path
from collections import defaultdict, Counter
from math import sqrt
from datetime import datetime

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_PRE_BROKER_AUDIT_PACK_OUT_DIR",
    "artifacts/v3_2_2_pre_broker_audit_pack_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_2_pre_broker_audit_pack_summary.json"
LINEAGE_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_no_lookahead_lineage_rows.jsonl"
STABILITY_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_period_stability_rows.jsonl"
CAPACITY_ROWS_PATH = OUT_DIR / "signalforge_v3_2_2_capacity_liquidity_rows.jsonl"

RULE_ID = "prior_symbol_regime_m8_netneg_pf090_v1"

SCENARIOS = {
    "30k": {
        "starting_capital": 30000.0,
        "parent_ledger": env_path(
            "SIGNALFORGE_V3_2_2_PRE_BROKER_AUDIT_PACK_PARENT_30K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_30k/ledger.jsonl",
        ),
        "candidate_ledger": env_path(
            "SIGNALFORGE_V3_2_2_PRE_BROKER_AUDIT_PACK_CANDIDATE_30K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_30k/ledger.jsonl",
        ),
    },
    "40k": {
        "starting_capital": 40000.0,
        "parent_ledger": env_path(
            "SIGNALFORGE_V3_2_2_PRE_BROKER_AUDIT_PACK_PARENT_40K_LEDGER",
            "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531/v3_2_1_native_quote_40k/ledger.jsonl",
        ),
        "candidate_ledger": env_path(
            "SIGNALFORGE_V3_2_2_PRE_BROKER_AUDIT_PACK_CANDIDATE_40K_LEDGER",
            "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531/v3_2_2_40k/ledger.jsonl",
        ),
    },
}

QUANTITY_FIELDS = ["quantity", "adjusted_quantity", "contract_count", "allocated_contract_count", "contracts"]
PNL_FIELDS = ["allocated_pnl", "adjusted_allocated_pnl", "realized_pnl_dollars", "pnl_dollars", "realized_pnl"]

ENTRY_DATE_FIELDS = ["entry_date", "trade_date", "decision_date", "date"]
CLOSE_DATE_FIELDS = ["realization_date", "portfolio_realization_date", "exit_date", "close_date", "outcome_date", "decision_date"]

GROUP_FIELDS = {
    "symbol": ["symbol", "underlying_symbol", "ticker"],
    "regime": ["regime_state", "market_regime", "regime"],
    "strategy": ["selected_strategy", "strategy", "strategy_family", "strategy_name"],
    "asset_behavior": ["asset_behavior_state", "asset_state", "behavior_state"],
    "option_behavior": ["option_behavior_state", "option_state"],
    "option_liquidity": ["option_liquidity_state", "liquidity_state"],
    "bucket": ["strategy_bucket", "bucket", "portfolio_bucket", "rank_bucket"],
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

def group_value(row, group_name):
    fields = GROUP_FIELDS[group_name]
    v, _ = pick(row, fields, "missing")
    return str(v)

def symbol_regime_key(row):
    return (group_value(row, "symbol"), group_value(row, "regime"))

def prior_stats(prior_items):
    pnls = [x["pnl"] for x in prior_items]
    wins = [x for x in pnls if x > 0]
    losses = [abs(x) for x in pnls if x < 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    return {
        "prior_count": len(pnls),
        "prior_net_pnl": sum(pnls),
        "prior_pf": gross_win / gross_loss if gross_loss else None,
        "prior_win_rate": len(wins) / len(pnls) if pnls else None,
        "max_prior_close_date": max([x["close_date"] for x in prior_items], default=None),
    }

def v322_rule_triggers(stats):
    if stats["prior_count"] < 8:
        return False
    if stats["prior_net_pnl"] > 0:
        return False
    if stats["prior_pf"] is None:
        return False
    if stats["prior_pf"] > 0.90:
        return False
    return True

def round_float(x, places=6):
    if isinstance(x, float):
        return round(x, places)
    return x

def round_dict(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 6)
        else:
            out[k] = v
    return out

def metric_rows(rows, starting_capital):
    active = [r for r in rows if accepted(r)]
    pnls = [pnl(r) for r in active]
    wins = [x for x in pnls if x > 0]
    losses = [abs(x) for x in pnls if x < 0]

    by_day = defaultdict(float)
    for r in active:
        by_day[close_date(r)] += pnl(r)

    equity = starting_capital
    peak = starting_capital
    max_dd = 0.0
    worst_dd_date = None
    daily = []

    for d in sorted(by_day):
        x = by_day[d]
        daily.append(x)
        equity += x
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            worst_dd_date = d

    day_wins = [x for x in daily if x > 0]
    day_losses = [abs(x) for x in daily if x < 0]

    mean_daily = sum(daily) / len(daily) if daily else 0.0
    var = sum((x - mean_daily) ** 2 for x in daily) / (len(daily) - 1) if len(daily) > 1 else 0.0
    stdev = sqrt(var) if var > 0 else 0.0

    return {
        "ending_equity": equity,
        "total_pnl_dollars": equity - starting_capital,
        "trade_count": len(active),
        "contract_count": sum(quantity(r) for r in active),
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "trade_profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
        "daily_profit_factor": sum(day_wins) / sum(day_losses) if sum(day_losses) else None,
        "max_drawdown_pct": max_dd,
        "worst_drawdown_date": worst_dd_date,
        "sharpe_proxy": mean_daily / stdev * sqrt(252) if stdev else None,
        "worst_daily_pnl": min(daily) if daily else None,
        "best_daily_pnl": max(daily) if daily else None,
    }

def period_key(d, period_type):
    if not d:
        return "missing"
    dt = datetime.strptime(d[:10], "%Y-%m-%d")
    if period_type == "year":
        return f"{dt.year}"
    if period_type == "quarter":
        q = ((dt.month - 1) // 3) + 1
        return f"{dt.year}-Q{q}"
    if period_type == "month":
        return f"{dt.year}-{dt.month:02d}"
    return "missing"

def percentile(values, pct):
    vals = sorted([float(v) for v in values if v is not None])
    if not vals:
        return None
    idx = (len(vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac

def walk_values(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else str(k)
            yield from walk_values(v, new_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_path = f"{path}[{i}]"
            yield from walk_values(v, new_path)
    else:
        yield path, obj

def first_numeric_by_key(row, needles):
    needles = [n.lower() for n in needles]
    candidates = []
    for path, value in walk_values(row):
        key = path.lower()
        if any(n in key for n in needles):
            val = fnum(value, None)
            if val is not None:
                candidates.append((path, val))
    if candidates:
        return candidates[0][1], candidates[0][0]
    return None, None

def all_numeric_by_key(row, needles):
    needles = [n.lower() for n in needles]
    values = []
    for path, value in walk_values(row):
        key = path.lower()
        if any(n in key for n in needles):
            val = fnum(value, None)
            if val is not None:
                values.append((path, val))
    return values

def native_quote_join(row):
    q = row.get("native_quote_join")
    return q if isinstance(q, dict) else {}

def native_quote_stress(row):
    q = row.get("native_quote_pnl_stress")
    return q if isinstance(q, dict) else {}

def quote_unit_cost(row):
    q = native_quote_join(row)
    return fnum(q.get("round_trip_half_spread_cost_per_strategy_unit"), None)

def native_quote_cost_method(row):
    q = native_quote_stress(row)
    return str(q.get("native_quote_cost_method", "missing"))

def native_quote_cost(row):
    q = native_quote_stress(row)
    return fnum(q.get("native_quote_cost_after_multiplier"), 0.0)

def commission_cost(row):
    q = native_quote_stress(row)
    return fnum(q.get("commission_cost"), 0.0)

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

def get_spread_pct(row):
    val, path = first_numeric_by_key(row, ["spread_pct", "spread_percent"])
    if val is None:
        return None, None
    # Normalize obvious percentage values.
    if val > 1.0 and val <= 100.0:
        val = val / 100.0
    return val, path

def get_volume_oi(row):
    volume, volume_path = first_numeric_by_key(row, ["option_volume", "contract_volume", "volume"])
    oi, oi_path = first_numeric_by_key(row, ["open_interest", "option_open_interest"])
    return volume, volume_path, oi, oi_path

def no_lookahead_audit(capital_label, parent_rows, candidate_rows):
    lineage_rows = []
    blockers = []
    warnings = []

    if len(parent_rows) != len(candidate_rows):
        blockers.append(f"{capital_label}: parent/candidate row count mismatch {len(parent_rows)} vs {len(candidate_rows)}")

    n = min(len(parent_rows), len(candidate_rows))

    parent_items = []
    for idx in range(n):
        p = parent_rows[idx]
        if accepted(p):
            parent_items.append({
                "idx": idx,
                "row": p,
                "entry_date": entry_date(p),
                "close_date": close_date(p),
                "pnl": pnl(p),
                "key": symbol_regime_key(p),
            })

    parent_items_sorted = sorted(parent_items, key=lambda x: (x["entry_date"], x["close_date"], x["idx"]))
    pending = sorted(parent_items, key=lambda x: (x["close_date"], x["idx"]))
    pending_pos = 0
    history = defaultdict(list)

    expected_skip_count = 0
    actual_skip_count = 0
    false_positive_count = 0
    false_negative_count = 0
    future_prior_violation_count = 0
    stored_prior_mismatch_count = 0

    for item in parent_items_sorted:
        current_entry = item["entry_date"]

        while pending_pos < len(pending):
            prior = pending[pending_pos]
            if prior["close_date"] >= current_entry:
                break
            history[prior["key"]].append(prior)
            pending_pos += 1

        stats = prior_stats(history[item["key"]])
        triggered = v322_rule_triggers(stats)

        child = candidate_rows[item["idx"]]
        actual_skipped = not accepted(child)
        rule_id = child.get("v3_2_2_rule_id")
        actual_v322_skip = actual_skipped and (rule_id == RULE_ID or child.get("v3_2_2_scope_key") is not None)

        if triggered:
            expected_skip_count += 1
        if actual_v322_skip:
            actual_skip_count += 1

        if triggered and not actual_v322_skip:
            false_negative_count += 1
        if actual_v322_skip and not triggered:
            false_positive_count += 1

        if stats["max_prior_close_date"] is not None and stats["max_prior_close_date"] >= current_entry:
            future_prior_violation_count += 1

        stored_mismatch = False
        if actual_v322_skip:
            stored_count = fnum(child.get("v3_2_2_prior_count"), None)
            stored_net = fnum(child.get("v3_2_2_prior_net_pnl"), None)
            stored_pf = fnum(child.get("v3_2_2_prior_pf"), None)

            if stored_count is not None and int(stored_count) != int(stats["prior_count"]):
                stored_mismatch = True
            if stored_net is not None and abs(stored_net - stats["prior_net_pnl"]) > 1e-4:
                stored_mismatch = True
            if stored_pf is not None and stats["prior_pf"] is not None and abs(stored_pf - stats["prior_pf"]) > 1e-6:
                stored_mismatch = True

            if stored_mismatch:
                stored_prior_mismatch_count += 1

        if triggered or actual_v322_skip or stored_mismatch:
            lineage_rows.append({
                "capital_label": capital_label,
                "row_index": item["idx"],
                "entry_date": current_entry,
                "close_date": item["close_date"],
                "symbol": item["key"][0],
                "regime": item["key"][1],
                "parent_pnl": round(item["pnl"], 6),
                "expected_rule_trigger": triggered,
                "actual_v3_2_2_skip": actual_v322_skip,
                "false_positive_skip": actual_v322_skip and not triggered,
                "false_negative_skip": triggered and not actual_v322_skip,
                "prior_count": stats["prior_count"],
                "prior_net_pnl": round(stats["prior_net_pnl"], 6),
                "prior_pf": round(stats["prior_pf"], 6) if stats["prior_pf"] is not None else None,
                "max_prior_close_date": stats["max_prior_close_date"],
                "stored_prior_mismatch": stored_mismatch,
            })

    if false_positive_count:
        blockers.append(f"{capital_label}: V3.2.2 skipped rows that did not satisfy prior-only rule: {false_positive_count}")
    if false_negative_count:
        blockers.append(f"{capital_label}: rows satisfied V3.2.2 rule but were not skipped: {false_negative_count}")
    if future_prior_violation_count:
        blockers.append(f"{capital_label}: future/same-day prior close-date violations: {future_prior_violation_count}")
    if stored_prior_mismatch_count:
        blockers.append(f"{capital_label}: stored prior stats mismatched recomputed stats: {stored_prior_mismatch_count}")

    parent_active_pnl = sum(pnl(r) for r in parent_rows if accepted(r))
    candidate_active_pnl = sum(pnl(r) for r in candidate_rows if accepted(r))
    skipped_parent_pnl = 0.0

    for idx in range(n):
        if accepted(parent_rows[idx]) and not accepted(candidate_rows[idx]):
            skipped_parent_pnl += pnl(parent_rows[idx])

    delta = candidate_active_pnl - parent_active_pnl
    expected_delta = -skipped_parent_pnl

    if abs(delta - expected_delta) > 1e-4:
        blockers.append(f"{capital_label}: candidate delta does not reconcile to skipped parent PnL")

    return {
        "capital_label": capital_label,
        "parent_row_count": len(parent_rows),
        "candidate_row_count": len(candidate_rows),
        "parent_active_trade_count": sum(1 for r in parent_rows if accepted(r)),
        "candidate_active_trade_count": sum(1 for r in candidate_rows if accepted(r)),
        "expected_skip_count": expected_skip_count,
        "actual_v3_2_2_skip_count": actual_skip_count,
        "false_positive_skip_count": false_positive_count,
        "false_negative_skip_count": false_negative_count,
        "future_prior_violation_count": future_prior_violation_count,
        "stored_prior_mismatch_count": stored_prior_mismatch_count,
        "parent_active_pnl": round(parent_active_pnl, 6),
        "candidate_active_pnl": round(candidate_active_pnl, 6),
        "skipped_parent_pnl": round(skipped_parent_pnl, 6),
        "delta_pnl_candidate_minus_parent": round(delta, 6),
        "expected_delta_from_skips": round(expected_delta, 6),
        "audit_passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }, lineage_rows

def stability_audit(capital_label, rows, starting_capital):
    active = [r for r in rows if accepted(r)]
    total_pnl = sum(pnl(r) for r in active)
    out = []

    group_specs = []

    for period_type in ["year", "quarter", "month"]:
        buckets = defaultdict(list)
        for r in active:
            buckets[period_key(close_date(r), period_type)].append(r)
        for key, vals in buckets.items():
            group_specs.append((period_type, key, vals))

    for group_name in ["regime", "strategy", "asset_behavior", "option_behavior"]:
        buckets = defaultdict(list)
        for r in active:
            buckets[group_value(r, group_name)].append(r)
        for key, vals in buckets.items():
            group_specs.append((group_name, key, vals))

    for period_type, key, vals in group_specs:
        m = metric_rows(vals, 0.0)
        group_pnl = sum(pnl(r) for r in vals)
        out.append({
            "capital_label": capital_label,
            "group_type": period_type,
            "group_value": key,
            "trade_count": len([r for r in vals if accepted(r)]),
            "contract_count": sum(quantity(r) for r in vals if accepted(r)),
            "net_pnl": round(group_pnl, 6),
            "share_of_total_pnl": round(group_pnl / total_pnl, 6) if total_pnl else None,
            "trade_profit_factor": round_float(m["trade_profit_factor"]),
            "daily_profit_factor": round_float(m["daily_profit_factor"]),
            "win_rate": round_float(m["win_rate"]),
            "max_drawdown_pct": round_float(m["max_drawdown_pct"]),
            "worst_daily_pnl": round_float(m["worst_daily_pnl"]),
            "best_daily_pnl": round_float(m["best_daily_pnl"]),
            "is_negative": group_pnl < 0,
        })

    return out

def capacity_liquidity_audit(capital_label, rows):
    active = [r for r in rows if accepted(r)]
    total_pnl = sum(pnl(r) for r in active)

    spread_values = []
    spread_paths = Counter()
    volume_ratios = []
    oi_ratios = []
    volume_values = []
    oi_values = []
    missing_spread = 0
    missing_volume = 0
    missing_oi = 0

    quote_unit_values = []
    quote_costs = []
    commissions = []
    quote_methods = Counter()
    quote_buckets = Counter()
    liquidity_states = Counter()
    strategy_counts = Counter()
    symbol_counts = Counter()

    detail_rows = []

    for idx, r in enumerate(active):
        q = quantity(r)
        p = pnl(r)

        spread, spread_path = get_spread_pct(r)
        if spread is None:
            missing_spread += 1
        else:
            spread_values.append(spread)
            spread_paths[spread_path] += 1

        volume, volume_path, oi, oi_path = get_volume_oi(r)
        if volume is None or volume <= 0:
            missing_volume += 1
        else:
            volume_values.append(volume)
            volume_ratios.append(q / volume)

        if oi is None or oi <= 0:
            missing_oi += 1
        else:
            oi_values.append(oi)
            oi_ratios.append(q / oi)

        u = quote_unit_cost(r)
        if u is not None:
            quote_unit_values.append(u)

        qc = native_quote_cost(r)
        cm = commission_cost(r)
        quote_costs.append(qc)
        commissions.append(cm)
        quote_methods[native_quote_cost_method(r)] += 1
        quote_buckets[quote_cost_bucket(r)] += 1
        liquidity_states[group_value(r, "option_liquidity")] += 1
        strategy_counts[group_value(r, "strategy")] += 1
        symbol_counts[group_value(r, "symbol")] += 1

        high_risk = False
        flags = []

        if spread is not None and spread > 0.125:
            high_risk = True
            flags.append("spread_gt_12_5pct_after_guardrail")
        if u is not None and u > 250:
            flags.append("quote_unit_cost_gt_250")
        if volume is not None and volume > 0 and q / volume > 0.10:
            flags.append("quantity_gt_10pct_volume")
        if oi is not None and oi > 0 and q / oi > 0.10:
            flags.append("quantity_gt_10pct_open_interest")
        if native_quote_cost_method(r) != "actual_complete_quote":
            flags.append("non_actual_complete_quote_cost_method")

        if flags:
            detail_rows.append({
                "capital_label": capital_label,
                "row_index_active_only": idx,
                "symbol": group_value(r, "symbol"),
                "strategy": group_value(r, "strategy"),
                "regime": group_value(r, "regime"),
                "entry_date": entry_date(r),
                "close_date": close_date(r),
                "quantity": q,
                "pnl": round(p, 6),
                "spread_pct": round(spread, 6) if spread is not None else None,
                "quote_unit_cost": round(u, 6) if u is not None else None,
                "native_quote_cost": round(qc, 6),
                "commission_cost": round(cm, 6),
                "volume": volume,
                "open_interest": oi,
                "quantity_to_volume": round(q / volume, 6) if volume and volume > 0 else None,
                "quantity_to_open_interest": round(q / oi, 6) if oi and oi > 0 else None,
                "quote_cost_method": native_quote_cost_method(r),
                "flags": flags,
            })

    n = len(active)

    summary = {
        "capital_label": capital_label,
        "active_trade_count": n,
        "total_pnl": round(total_pnl, 6),
        "contract_count": sum(quantity(r) for r in active),

        "spread_pct_coverage": round((n - missing_spread) / n, 6) if n else None,
        "spread_pct_p50": round_float(percentile(spread_values, 0.50)),
        "spread_pct_p90": round_float(percentile(spread_values, 0.90)),
        "spread_pct_p95": round_float(percentile(spread_values, 0.95)),
        "spread_pct_p99": round_float(percentile(spread_values, 0.99)),
        "spread_pct_max": round_float(max(spread_values) if spread_values else None),
        "spread_gt_12_5pct_count": sum(1 for x in spread_values if x > 0.125),

        "quote_unit_cost_coverage": round(len(quote_unit_values) / n, 6) if n else None,
        "quote_unit_cost_p50": round_float(percentile(quote_unit_values, 0.50)),
        "quote_unit_cost_p90": round_float(percentile(quote_unit_values, 0.90)),
        "quote_unit_cost_p95": round_float(percentile(quote_unit_values, 0.95)),
        "quote_unit_cost_p99": round_float(percentile(quote_unit_values, 0.99)),
        "quote_unit_cost_max": round_float(max(quote_unit_values) if quote_unit_values else None),

        "total_native_quote_cost": round(sum(quote_costs), 6),
        "total_commission_cost": round(sum(commissions), 6),
        "execution_cost_as_pct_of_pnl": round((sum(quote_costs) + sum(commissions)) / total_pnl, 6) if total_pnl else None,
        "quote_cost_method_counts": dict(quote_methods),
        "quote_cost_bucket_counts": dict(quote_buckets),

        "volume_coverage": round((n - missing_volume) / n, 6) if n else None,
        "open_interest_coverage": round((n - missing_oi) / n, 6) if n else None,
        "quantity_to_volume_p95": round_float(percentile(volume_ratios, 0.95)),
        "quantity_to_volume_max": round_float(max(volume_ratios) if volume_ratios else None),
        "quantity_to_open_interest_p95": round_float(percentile(oi_ratios, 0.95)),
        "quantity_to_open_interest_max": round_float(max(oi_ratios) if oi_ratios else None),

        "liquidity_state_counts": dict(liquidity_states),
        "top_strategy_trade_counts": dict(strategy_counts.most_common(10)),
        "top_symbol_trade_counts": dict(symbol_counts.most_common(10)),
        "spread_source_paths_top": dict(spread_paths.most_common(5)),
        "flagged_detail_row_count": len(detail_rows),
    }

    return summary, detail_rows

blockers = []
warnings = []

lineage_summaries = []
lineage_rows_all = []
stability_rows_all = []
capacity_summaries = []
capacity_detail_rows_all = []

for capital_label, cfg in SCENARIOS.items():
    if not cfg["parent_ledger"].exists():
        blockers.append(f"missing_parent_ledger_{capital_label}: {cfg['parent_ledger']}")
        continue
    if not cfg["candidate_ledger"].exists():
        blockers.append(f"missing_candidate_ledger_{capital_label}: {cfg['candidate_ledger']}")
        continue

    parent_rows = list(read_jsonl(cfg["parent_ledger"]))
    candidate_rows = list(read_jsonl(cfg["candidate_ledger"]))

    lineage_summary, lineage_rows = no_lookahead_audit(capital_label, parent_rows, candidate_rows)
    lineage_summaries.append(lineage_summary)
    lineage_rows_all.extend(lineage_rows)

    for b in lineage_summary["blockers"]:
        blockers.append(b)
    for w in lineage_summary["warnings"]:
        warnings.append(w)

    stability_rows = stability_audit(capital_label, candidate_rows, cfg["starting_capital"])
    stability_rows_all.extend(stability_rows)

    capacity_summary, capacity_rows = capacity_liquidity_audit(capital_label, candidate_rows)
    capacity_summaries.append(capacity_summary)
    capacity_detail_rows_all.extend(capacity_rows)

# Stability rollups
stability_rollups = []

for capital_label in SCENARIOS.keys():
    cap_rows = [r for r in stability_rows_all if r["capital_label"] == capital_label]

    year_rows = [r for r in cap_rows if r["group_type"] == "year"]
    quarter_rows = [r for r in cap_rows if r["group_type"] == "quarter"]
    month_rows = [r for r in cap_rows if r["group_type"] == "month"]

    total_pnl = sum(r["net_pnl"] for r in year_rows)

    largest_year_share = max([abs(r["net_pnl"]) / abs(total_pnl) for r in year_rows], default=None) if total_pnl else None
    largest_quarter_share = max([abs(r["net_pnl"]) / abs(total_pnl) for r in quarter_rows], default=None) if total_pnl else None

    stability_rollups.append({
        "capital_label": capital_label,
        "year_count": len(year_rows),
        "negative_year_count": sum(1 for r in year_rows if r["net_pnl"] < 0),
        "negative_quarter_count": sum(1 for r in quarter_rows if r["net_pnl"] < 0),
        "negative_month_count": sum(1 for r in month_rows if r["net_pnl"] < 0),
        "total_year_pnl": round(total_pnl, 6),
        "largest_year_abs_pnl_share": round(largest_year_share, 6) if largest_year_share is not None else None,
        "largest_quarter_abs_pnl_share": round(largest_quarter_share, 6) if largest_quarter_share is not None else None,
        "worst_year": min(year_rows, key=lambda r: r["net_pnl"])["group_value"] if year_rows else None,
        "worst_year_pnl": min([r["net_pnl"] for r in year_rows], default=None),
        "best_year": max(year_rows, key=lambda r: r["net_pnl"])["group_value"] if year_rows else None,
        "best_year_pnl": max([r["net_pnl"] for r in year_rows], default=None),
        "worst_quarter": min(quarter_rows, key=lambda r: r["net_pnl"])["group_value"] if quarter_rows else None,
        "worst_quarter_pnl": min([r["net_pnl"] for r in quarter_rows], default=None),
        "best_quarter": max(quarter_rows, key=lambda r: r["net_pnl"])["group_value"] if quarter_rows else None,
        "best_quarter_pnl": max([r["net_pnl"] for r in quarter_rows], default=None),
    })

for s in stability_rollups:
    if s["negative_year_count"] > 0:
        warnings.append(f"{s['capital_label']}: one or more negative years found.")
    if s["largest_year_abs_pnl_share"] is not None and s["largest_year_abs_pnl_share"] > 0.70:
        warnings.append(f"{s['capital_label']}: one year contributes more than 70% of absolute yearly PnL.")
    if s["negative_quarter_count"] > 0:
        warnings.append(f"{s['capital_label']}: one or more negative quarters found; inspect stability rows.")

# Capacity warnings/blockers
for c in capacity_summaries:
    if c["spread_gt_12_5pct_count"] > 0:
        blockers.append(f"{c['capital_label']}: active trades remain above 12.5% spread guardrail.")
    if c["spread_pct_coverage"] is not None and c["spread_pct_coverage"] < 0.95:
        warnings.append(f"{c['capital_label']}: spread_pct coverage below 95%.")
    if c["quote_unit_cost_coverage"] is not None and c["quote_unit_cost_coverage"] < 0.95:
        warnings.append(f"{c['capital_label']}: quote unit cost coverage below 95%.")
    if c["volume_coverage"] is not None and c["volume_coverage"] < 0.50:
        warnings.append(f"{c['capital_label']}: option volume coverage below 50%; capacity audit is limited.")
    if c["open_interest_coverage"] is not None and c["open_interest_coverage"] < 0.50:
        warnings.append(f"{c['capital_label']}: open interest coverage below 50%; capacity audit is limited.")
    if c["quote_cost_method_counts"].get("fallback_p95_quote_cost", 0) > 0:
        warnings.append(f"{c['capital_label']}: fallback quote-cost rows remain.")

write_jsonl(LINEAGE_ROWS_PATH, lineage_rows_all)
write_jsonl(STABILITY_ROWS_PATH, stability_rows_all)
write_jsonl(CAPACITY_ROWS_PATH, capacity_detail_rows_all)

lineage_passed = all(x["audit_passed"] for x in lineage_summaries) and not any("lookahead" in b.lower() for b in blockers)
stability_ready = len(stability_rollups) > 0
capacity_ready = len(capacity_summaries) > 0 and not any("spread guardrail" in b.lower() for b in blockers)

if blockers:
    decision = "v3_2_2_pre_broker_audits_blocked"
elif lineage_passed and stability_ready and capacity_ready and warnings:
    decision = "v3_2_2_pre_broker_audits_passed_with_follow_up_flags"
elif lineage_passed and stability_ready and capacity_ready:
    decision = "v3_2_2_pre_broker_audits_passed"
else:
    decision = "v3_2_2_pre_broker_audits_need_review"

summary = {
    "adapter_type": "v3_2_2_pre_broker_audit_pack_builder",
    "artifact_type": "signalforge_v3_2_2_pre_broker_audit_pack",
    "contract": "v3_2_2_pre_broker_audit_pack",
    "candidate_id": "signalforge_v3_2_2_symbol_regime_walkforward_prune_20230101_20260531",
    "is_ready": len(blockers) == 0,
    "readiness_state": "ready" if not blockers else "blocked",
    "decision": decision,
    "audit_scope": [
        "no_lookahead_data_lineage",
        "year_quarter_month_stability",
        "capacity_liquidity_realism",
    ],
    "lineage_summaries": lineage_summaries,
    "stability_rollups": stability_rollups,
    "capacity_summaries": capacity_summaries,
    "blockers": blockers,
    "warnings": warnings,
    "paths": {
        "summary": str(SUMMARY_PATH),
        "lineage_rows": str(LINEAGE_ROWS_PATH),
        "stability_rows": str(STABILITY_ROWS_PATH),
        "capacity_rows": str(CAPACITY_ROWS_PATH),
    },
}

SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True, default=str))

