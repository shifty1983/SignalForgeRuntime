import json
from pathlib import Path
from collections import Counter, defaultdict
from math import sqrt

OUT_DIR = Path("artifacts/v3_2_reconciled_canonical_from_v2_locked_actions_20230101_20260531")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_reconciled_canonical_summary.json"
    METRICS_PATH = OUT_DIR / "signalforge_v3_2_reconciled_canonical_metrics.json"
    COMPARISON_PATH = OUT_DIR / "signalforge_v3_2_reconciled_canonical_comparison_rows.jsonl"

    SCENARIOS = {
        "30k": {
            "starting_capital": 30000.0,
            "v2_candidates": [
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/v2_30k/ledger.jsonl"),
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/30k/ledger.jsonl"),
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/portfolio_30k_ledger.jsonl"),
            ],
            "locked_v3_2": Path("artifacts/v3_2_neutral_short_premium_throttle_validation_20230101_20260531/v3_2_30k/ledger.jsonl"),
            "output": OUT_DIR / "v3_2_reconciled_canonical_30k" / "ledger.jsonl",
        },
        "40k": {
            "starting_capital": 40000.0,
            "v2_candidates": [
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/v2_40k/ledger.jsonl"),
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/40k/ledger.jsonl"),
                Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531/portfolio_40k_ledger.jsonl"),
            ],
            "locked_v3_2": Path("artifacts/v3_2_neutral_short_premium_throttle_validation_20230101_20260531/v3_2_40k/ledger.jsonl"),
            "output": OUT_DIR / "v3_2_reconciled_canonical_40k" / "ledger.jsonl",
        },
    }

    SEARCH_ROOTS = [
        Path("artifacts/portfolio_value_ranked_allocator_v2_canonical_ledgers_20230101_20260531"),
        Path("artifacts/portfolio_value_ranked_allocator_v2_continuous_replay_20210601_20260531"),
        Path("artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531"),
    ]

    QUANTITY_FIELDS = ["quantity", "adjusted_quantity", "contract_count", "allocated_contract_count", "contracts"]
    PNL_FIELDS = ["allocated_pnl", "adjusted_allocated_pnl", "realized_pnl_dollars", "pnl_dollars", "realized_pnl"]
    DATE_FIELDS = ["decision_date", "entry_date", "trade_date", "date"]
    CLOSE_DATE_FIELDS = ["realization_date", "portfolio_realization_date", "exit_date", "close_date", "outcome_date", "decision_date"]
    STRATEGY_FIELDS = ["selected_strategy", "strategy", "strategy_family", "strategy_name"]
    SYMBOL_FIELDS = ["symbol", "underlying_symbol", "ticker"]

    COPY_FIELDS_FROM_LOCKED = [
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "option_iv_level",
        "option_liquidity_state",
        "v3_1_rule_id",
        "v3_1_gate_action",
        "v3_1_parent_quantity",
        "v3_1_parent_allocated_pnl",
        "v3_1_prior_count",
        "v3_1_prior_avg_pnl",
        "v3_1_prior_final_negative_rate",
        "v3_2_rule_id",
        "v3_2_throttle_action",
        "v3_2_parent_quantity",
        "v3_2_parent_allocated_pnl",
        "v3_2_adjusted_quantity",
        "v3_2_adjusted_allocated_pnl",
        "v3_2_delta_quantity",
        "v3_2_delta_pnl",
        "v3_2_strategy_structure",
        "v3_2_regime_unstable",
        "skip_reason",
        "row_state",
        "sizing_state",
        "adjusted_row_state",
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

    def pick(row, fields, default=None):
        for field in fields:
            if field in row and row[field] is not None and str(row[field]).strip() != "":
                return row[field]
        return default

    def date_str(row):
        v = pick(row, DATE_FIELDS, "")
        return str(v)[:10] if v is not None else ""

    def close_date_str(row):
        v = pick(row, CLOSE_DATE_FIELDS, "")
        return str(v)[:10] if v is not None else ""

    def symbol(row):
        return str(pick(row, SYMBOL_FIELDS, "missing")).strip()

    def strategy(row):
        return str(pick(row, STRATEGY_FIELDS, "missing")).strip()

    def quantity(row):
        return fnum(pick(row, QUANTITY_FIELDS, 0.0))

    def pnl(row):
        return fnum(pick(row, PNL_FIELDS, 0.0))

    def state(row):
        return str(pick(row, ["row_state", "sizing_state", "adjusted_row_state"], "accepted")).lower()

    def accepted(row):
        if quantity(row) <= 0:
            return False
        s = state(row)
        if "skip" in s or "reject" in s:
            return False
        return True

    def set_quantity(row, q):
        found = False
        for field in QUANTITY_FIELDS:
            if field in row:
                row[field] = q
                found = True
        if not found:
            row["quantity"] = q

    def set_pnl(row, p):
        found = False
        for field in PNL_FIELDS:
            if field in row:
                row[field] = p
                found = True
        if not found:
            row["allocated_pnl"] = p

    def row_key(row):
        return (
            date_str(row),
            close_date_str(row),
            symbol(row),
            strategy(row),
        )

    def row_key_with_pnl_quantity(row):
        return (
            date_str(row),
            close_date_str(row),
            symbol(row),
            strategy(row),
            round(quantity(row), 8),
            round(pnl(row), 8),
        )

    def discover_v2(capital_label, candidates):
        for p in candidates:
            if p.exists():
                return p

        scored = []

        for root in SEARCH_ROOTS:
            if not root.exists():
                continue

            for p in root.rglob("*.jsonl"):
                s = str(p).lower()
                score = 0

                if "ledger" in s:
                    score += 100
                if capital_label in s:
                    score += 200
                if "canonical" in s:
                    score += 50
                if "summary" in s or "comparison" in s or "action" in s or "audit" in s:
                    score -= 300

                if score > 0:
                    scored.append((score, p))

        scored.sort(reverse=True, key=lambda x: x[0])

        if scored:
            return scored[0][1]

        return None

    def metrics(rows, starting_capital):
        active = [r for r in rows if accepted(r)]

        trade_pnls = [pnl(r) for r in active]
        wins = [x for x in trade_pnls if x > 0]
        losses = [abs(x) for x in trade_pnls if x < 0]

        gross_wins = sum(wins)
        gross_losses = sum(losses)

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

        if len(daily_pnls) > 1:
            variance = sum((x - mean_daily) ** 2 for x in daily_pnls) / (len(daily_pnls) - 1)
        else:
            variance = 0.0

        stdev = sqrt(variance) if variance > 0 else 0.0

        downside = [x for x in daily_pnls if x < 0]
        downside_dev = sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0.0

        return {
            "starting_capital": starting_capital,
            "ending_equity": equity,
            "total_pnl_dollars": equity - starting_capital,
            "total_return_pct": ((equity - starting_capital) / starting_capital) if starting_capital else None,
            "pnl_multiple": ((equity - starting_capital) / starting_capital) if starting_capital else None,
            "max_drawdown_pct": max_dd,
            "worst_drawdown_date": worst_dd_date,
            "row_count": len(rows),
            "trade_count": len(active),
            "skipped_row_count": len(rows) - len(active),
            "contract_count": sum(quantity(r) for r in active),
            "win_rate": len(wins) / len(trade_pnls) if trade_pnls else None,
            "trade_profit_factor": gross_wins / gross_losses if gross_losses else None,
            "daily_profit_factor": sum(daily_wins) / sum(daily_losses) if sum(daily_losses) else None,
            "sharpe_proxy": (mean_daily / stdev * sqrt(252)) if stdev else None,
            "sortino_proxy": (mean_daily / downside_dev * sqrt(252)) if downside_dev else None,
            "gross_win_dollars": gross_wins,
            "gross_loss_dollars": gross_losses,
            "average_trade_pnl": sum(trade_pnls) / len(trade_pnls) if trade_pnls else None,
            "largest_trade_win": max(trade_pnls) if trade_pnls else None,
            "largest_trade_loss": min(trade_pnls) if trade_pnls else None,
            "best_daily_pnl": max(daily_pnls) if daily_pnls else None,
            "worst_daily_pnl": min(daily_pnls) if daily_pnls else None,
            "trading_day_count": len(daily_pnls),
        }

    def rounded_metrics(m):
        out = {}
        for k, v in m.items():
            if isinstance(v, float):
                out[k] = round(v, 6)
            else:
                out[k] = v
        return out

    def build_locked_index(locked_rows):
        exact = defaultdict(list)
        loose = defaultdict(list)

        for i, r in enumerate(locked_rows):
            exact[row_key_with_pnl_quantity(r)].append((i, r))
            loose[row_key(r)].append((i, r))

        return exact, loose

    def match_rows(v2_rows, locked_rows):
        exact, loose = build_locked_index(locked_rows)
        used = set()
        matches = {}
        unmatched_v2 = []

        for i, r in enumerate(v2_rows):
            k = row_key_with_pnl_quantity(r)
            candidates = exact.get(k, [])

            chosen = None
            for j, lr in candidates:
                if j not in used:
                    chosen = (j, lr, "exact_date_close_symbol_strategy_qty_pnl")
                    break

            if chosen is None:
                k2 = row_key(r)
                candidates = loose.get(k2, [])
                for j, lr in candidates:
                    if j not in used:
                        chosen = (j, lr, "loose_date_close_symbol_strategy")
                        break

            if chosen is None:
                unmatched_v2.append(i)
            else:
                j, lr, method = chosen
                used.add(j)
                matches[i] = {
                    "locked_index": j,
                    "locked_row": lr,
                    "method": method,
                }

        unmatched_locked = [j for j in range(len(locked_rows)) if j not in used]

        return matches, unmatched_v2, unmatched_locked

    def reconcile_row(v2_row, locked_row):
        new = dict(v2_row)

        new["canonical_rebuild_method"] = "v2_baseline_with_locked_v3_2_action_replay"
        new["canonical_rebuild_source"] = "v2_baseline"
        new["canonical_action_source"] = "locked_v3_2_paper_candidate"

        locked_q = quantity(locked_row)
        locked_pnl = pnl(locked_row)

        set_quantity(new, locked_q)
        set_pnl(new, locked_pnl)

        for field in COPY_FIELDS_FROM_LOCKED:
            if field in locked_row:
                new[field] = locked_row[field]

        new["canonical_locked_quantity"] = locked_q
        new["canonical_locked_allocated_pnl"] = locked_pnl
        new["canonical_parent_v2_quantity"] = quantity(v2_row)
        new["canonical_parent_v2_allocated_pnl"] = pnl(v2_row)
        new["canonical_delta_quantity_vs_v2"] = locked_q - quantity(v2_row)
        new["canonical_delta_pnl_vs_v2"] = locked_pnl - pnl(v2_row)

        return new

    blockers = []
    warnings = []
    scenario_summaries = []
    metrics_rows = []
    comparison_rows = []

    for capital_label, cfg in SCENARIOS.items():
        v2_path = discover_v2(capital_label, cfg["v2_candidates"])
        locked_path = cfg["locked_v3_2"]

        if v2_path is None or not v2_path.exists():
            blockers.append(f"missing_v2_baseline_ledger_{capital_label}")
            continue

        if not locked_path.exists():
            blockers.append(f"missing_locked_v3_2_ledger_{capital_label}: {locked_path}")
            continue

        v2_rows = list(read_jsonl(v2_path))
        locked_rows = list(read_jsonl(locked_path))

        matches, unmatched_v2, unmatched_locked = match_rows(v2_rows, locked_rows)

        reconciled_rows = []

        for i, row in enumerate(v2_rows):
            if i in matches:
                reconciled_rows.append(reconcile_row(row, matches[i]["locked_row"]))
            else:
                new = dict(row)
                new["canonical_rebuild_method"] = "unmatched_v2_row_carried_forward"
                new["canonical_rebuild_source"] = "v2_baseline"
                new["canonical_action_source"] = "missing_locked_match"
                reconciled_rows.append(new)

        write_jsonl(cfg["output"], reconciled_rows)

        v2_metrics = metrics(v2_rows, cfg["starting_capital"])
        locked_metrics = metrics(locked_rows, cfg["starting_capital"])
        reconciled_metrics = metrics(reconciled_rows, cfg["starting_capital"])

        match_methods = Counter(m["method"] for m in matches.values())

        v3_1_skips = sum(
            1 for r in reconciled_rows
            if str(r.get("v3_1_gate_action", "")) == "skip_weak_prior_cohort"
            or "skip" in str(r.get("row_state", "")).lower()
        )

        v3_2_throttles = sum(
            1 for r in reconciled_rows
            if str(r.get("v3_2_throttle_action", "")) == "bucket5_neutral_short_premium_unstable_to2"
        )

        only_reconciled_sig = Counter(row_key_with_pnl_quantity(r) for r in reconciled_rows)
        locked_sig = Counter(row_key_with_pnl_quantity(r) for r in locked_rows)

        sig_only_reconciled = sum((only_reconciled_sig - locked_sig).values())
        sig_only_locked = sum((locked_sig - only_reconciled_sig).values())

        scenario_summary = {
            "capital_label": capital_label,
            "starting_capital": cfg["starting_capital"],
            "v2_baseline_path": str(v2_path),
            "locked_v3_2_path": str(locked_path),
            "reconciled_output_path": str(cfg["output"]),
            "v2_row_count": len(v2_rows),
            "locked_row_count": len(locked_rows),
            "reconciled_row_count": len(reconciled_rows),
            "matched_row_count": len(matches),
            "unmatched_v2_row_count": len(unmatched_v2),
            "unmatched_locked_row_count": len(unmatched_locked),
            "match_methods": dict(match_methods),
            "signature_rows_only_in_reconciled": sig_only_reconciled,
            "signature_rows_only_in_locked": sig_only_locked,
            "v3_1_skip_rows": v3_1_skips,
            "v3_2_throttle_rows": v3_2_throttles,
            "v2_metrics": rounded_metrics(v2_metrics),
            "locked_v3_2_metrics": rounded_metrics(locked_metrics),
            "reconciled_metrics": rounded_metrics(reconciled_metrics),
            "delta_pnl_reconciled_minus_locked": reconciled_metrics["total_pnl_dollars"] - locked_metrics["total_pnl_dollars"],
            "delta_dd_reconciled_minus_locked": reconciled_metrics["max_drawdown_pct"] - locked_metrics["max_drawdown_pct"],
            "reconciliation_state": (
                "matches_locked_v3_2"
                if len(unmatched_v2) == 0
                and len(unmatched_locked) == 0
                and sig_only_reconciled == 0
                and sig_only_locked == 0
                and abs(reconciled_metrics["total_pnl_dollars"] - locked_metrics["total_pnl_dollars"]) < 0.01
                else "review_required"
            ),
        }

        if scenario_summary["reconciliation_state"] != "matches_locked_v3_2":
            warnings.append(f"{capital_label}_reconciliation_review_required")

        scenario_summaries.append(scenario_summary)

        metrics_rows.append({
            "capital_label": capital_label,
            **rounded_metrics(reconciled_metrics),
            "v3_1_skip_rows": v3_1_skips,
            "v3_2_throttle_rows": v3_2_throttles,
            "reconciliation_state": scenario_summary["reconciliation_state"],
        })

        comparison_rows.append(scenario_summary)

    write_jsonl(COMPARISON_PATH, comparison_rows)

    is_ready = len(blockers) == 0
    all_match = is_ready and scenario_summaries and all(s["reconciliation_state"] == "matches_locked_v3_2" for s in scenario_summaries)

    summary = {
        "adapter_type": "v3_2_reconciled_canonical_from_v2_locked_actions_builder",
        "artifact_type": "signalforge_v3_2_reconciled_canonical_from_v2_locked_actions",
        "contract": "v3_2_reconciled_canonical_from_v2_locked_actions",
        "is_ready": is_ready,
        "readiness_state": "ready" if is_ready else "blocked",
        "decision": "reconciled_canonical_matches_locked_v3_2" if all_match else "reconciled_canonical_review_required" if is_ready else "blocked",
        "blockers": blockers,
        "warnings": warnings + [
            "This is a reconciliation rebuild from V2 baseline plus locked V3.2 paper-candidate actions.",
            "Use this to repair canonical portfolio metrics.",
            "Final live promotion still requires rule-native rebuild with quote-native fill/slippage fields restored.",
        ],
        "scenario_summaries": scenario_summaries,
        "paths": {
            "summary": str(SUMMARY_PATH),
            "metrics": str(METRICS_PATH),
            "comparison_rows": str(COMPARISON_PATH),
            "reconciled_30k_ledger": str(SCENARIOS["30k"]["output"]),
            "reconciled_40k_ledger": str(SCENARIOS["40k"]["output"]),
        },
    }

    metrics_summary = {
        "adapter_type": "v3_2_reconciled_canonical_portfolio_metrics_builder",
        "artifact_type": "signalforge_v3_2_reconciled_canonical_portfolio_metrics",
        "candidate": "v3_2_reconciled_canonical_from_v2_locked_actions",
        "metrics": metrics_rows,
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    METRICS_PATH.write_text(json.dumps(metrics_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

