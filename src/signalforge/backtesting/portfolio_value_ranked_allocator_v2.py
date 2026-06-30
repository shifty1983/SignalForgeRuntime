import json
from pathlib import Path
from datetime import date
from collections import defaultdict, Counter



def main() -> int:
    rows_path = Path("artifacts/strategy_eligibility_native_family_gate_position_sizing_replay_v1_20210601_20260531/signalforge_portfolio_position_sizing_replay_strategy_gate_v1.jsonl")
    out_dir = Path("artifacts/portfolio_value_ranked_allocator_v2_20210601_20260531")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "portfolio_value_ranked_allocator_v2_summary.json"
    scenario_rows_path = out_dir / "portfolio_value_ranked_allocator_v2_scenarios.jsonl"
    aggregate_rows_path = out_dir / "portfolio_value_ranked_allocator_v2_aggregate_rows.jsonl"

    CAPITALS = [30000, 40000, 50000, 100000, 150000, 200000]
    PORTFOLIO_HEAT_CAPS = [0.20, 0.25, 0.35, 0.50]

    RANK_METHODS = [
        "strategy_prior_return_mean",
        "strategy_prior_profit_factor",
        "expectancy_score_raw_benchmark",
        "fcfs_no_rank_benchmark",
    ]

    # bucket 5 = highest rank, bucket 1 = lowest rank.
    # Values are max contracts allowed per trade in that rank bucket.
    ALLOCATION_PROFILES = {
        "equal_all_11111":           {5: 1, 4: 1, 3: 1, 2: 1, 1: 1},
        "top4_drop_lowest_11110":    {5: 1, 4: 1, 3: 1, 2: 1, 1: 0},
        "top3_only_11100":           {5: 1, 4: 1, 3: 1, 2: 0, 1: 0},
        "top2_only_11000":           {5: 1, 4: 1, 3: 0, 2: 0, 1: 0},
        "top1_only_10000":           {5: 1, 4: 0, 3: 0, 2: 0, 1: 0},

        "top_heavy_21100":           {5: 2, 4: 1, 3: 1, 2: 0, 1: 0},
        "top_heavy_32100":           {5: 3, 4: 2, 3: 1, 2: 0, 1: 0},
        "top_heavy_42100":           {5: 4, 4: 2, 3: 1, 2: 0, 1: 0},
        "top_heavy_33210":           {5: 3, 4: 3, 3: 2, 2: 1, 1: 0},
        "broad_top_heavy_21111":      {5: 2, 4: 1, 3: 1, 2: 1, 1: 1},
    }

    FOLDS = [
        {
            "fold_name": "train_through_2022_test_2023",
            "train_end": "2022-12-31",
            "test_start": "2023-01-01",
            "test_end": "2023-12-31",
        },
        {
            "fold_name": "train_through_2023_test_2024",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-12-31",
        },
        {
            "fold_name": "train_through_2024_test_2025",
            "train_end": "2024-12-31",
            "test_start": "2025-01-01",
            "test_end": "2025-12-31",
        },
        {
            "fold_name": "train_through_2025_test_2026_partial",
            "train_end": "2025-12-31",
            "test_start": "2026-01-01",
            "test_end": "2026-12-31",
        },
    ]

    BUCKET_COUNT = 5

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

    def parse_date(x):
        try:
            return date.fromisoformat(str(x)[:10])
        except Exception:
            return None

    def fnum(x, default=0.0):
        try:
            if x is None or str(x).strip() == "":
                return default
            return float(x)
        except Exception:
            return default

    def percentile(vals, p):
        vals = sorted(vals)
        if not vals:
            return None
        return vals[int(p * (len(vals) - 1))]

    def quantile_edges(vals, bucket_count):
        vals = sorted(vals)
        if not vals:
            return []
        return [percentile(vals, i / bucket_count) for i in range(1, bucket_count)]

    def assign_bucket(value, edge_list):
        bucket = 1
        for edge in edge_list:
            if value > edge:
                bucket += 1
        return bucket

    def strategy_stats(train_rows):
        by_strategy = defaultdict(list)
        for r in train_rows:
            by_strategy[r["selected_strategy"]].append(r)

        out = {}
        for strategy, group in by_strategy.items():
            pnl = [g["realized_pnl_dollars"] for g in group]
            rets = [g["realized_return"] for g in group]
            wins = [x for x in pnl if x > 0]
            losses = [abs(x) for x in pnl if x < 0]

            out[strategy] = {
                "trade_count": len(group),
                "pnl_sum": sum(pnl),
                "return_mean": sum(rets) / len(rets) if rets else 0.0,
                "profit_factor": (sum(wins) / sum(losses)) if sum(losses) else 999.0,
                "win_rate": len(wins) / len(group) if group else 0.0,
            }

        return out

    def rank_value(row, method, stats):
        if method == "fcfs_no_rank_benchmark":
            return 0.0

        s = stats.get(row["selected_strategy"], {})

        if method == "strategy_prior_return_mean":
            return s.get("return_mean", 0.0)

        if method == "strategy_prior_profit_factor":
            return s.get("profit_factor", 1.0)

        if method == "expectancy_score_raw_benchmark":
            return row["selected_expectancy_score"]

        raise ValueError(method)

    rows = []

    for raw in read_jsonl(rows_path):
        if raw.get("sizing_state") != "sized":
            continue

        entry_date = parse_date(raw.get("decision_date"))
        exit_date = parse_date(raw.get("portfolio_realization_date") or raw.get("outcome_availability_date"))

        if entry_date is None or exit_date is None:
            continue

        if exit_date < entry_date:
            exit_date = entry_date

        rows.append({
            "sequence_id": raw.get("sequence_id"),
            "entry_date": entry_date,
            "exit_date": exit_date,
            "symbol": raw.get("symbol") or "unknown",
            "selected_strategy": raw.get("selected_strategy") or "unknown",
            "selected_expectancy_score": fnum(raw.get("selected_expectancy_score")),
            "selected_expectancy_sample_count": fnum(raw.get("selected_expectancy_sample_count")),
            "one_contract_risk_dollars": fnum(raw.get("position_risk_dollars"), 1000.0),
            "realized_return": fnum(raw.get("realized_return")),
            "realized_pnl_dollars": fnum(raw.get("realized_pnl_dollars")),
        })

    scenario_rows = []

    for fold in FOLDS:
        train_end = parse_date(fold["train_end"])
        test_start = parse_date(fold["test_start"])
        test_end = parse_date(fold["test_end"])

        train_rows = [r for r in rows if r["entry_date"] <= train_end]
        test_rows = [r for r in rows if test_start <= r["entry_date"] <= test_end]

        stats = strategy_stats(train_rows)

        for rank_method in RANK_METHODS:
            train_rank_values = [rank_value(r, rank_method, stats) for r in train_rows]
            rank_edges = quantile_edges(train_rank_values, BUCKET_COUNT)

            enriched_test = []

            for r in test_rows:
                rv = rank_value(r, rank_method, stats)
                bucket = assign_bucket(rv, rank_edges)

                # FCFS benchmark treats everything as same bucket.
                if rank_method == "fcfs_no_rank_benchmark":
                    bucket = 3

                x = dict(r)
                x["rank_value"] = rv
                x["rank_bucket"] = bucket
                enriched_test.append(x)

            entries_by_date = defaultdict(list)
            exits_by_date = defaultdict(list)

            for r in enriched_test:
                entries_by_date[r["entry_date"]].append(r)
                exits_by_date[r["exit_date"]].append(r)

            all_dates = sorted(set(list(entries_by_date.keys()) + list(exits_by_date.keys())))

            for starting_capital in CAPITALS:
                for heat_cap in PORTFOLIO_HEAT_CAPS:
                    for profile_name, profile in ALLOCATION_PROFILES.items():
                        equity = float(starting_capital)
                        peak_equity = equity
                        max_drawdown_pct = 0.0

                        active = []
                        accepted = []
                        skipped = []

                        pnl_sum = 0.0
                        gross_profit = 0.0
                        gross_loss = 0.0
                        wins = 0
                        losses = 0
                        flats = 0

                        open_risk_values = []
                        open_count_values = []
                        accepted_bucket_counts = Counter()
                        skipped_bucket_counts = Counter()
                        accepted_qty_by_bucket = Counter()
                        skip_reason_counts = Counter()

                        for current_date in all_dates:
                            # Close positions before same-day entries.
                            still_active = []

                            for p in active:
                                if p["exit_date"] <= current_date:
                                    pnl = p["realized_return"] * p["one_contract_risk_dollars"] * p["quantity"]
                                    equity += pnl
                                    pnl_sum += pnl

                                    if pnl > 0:
                                        wins += 1
                                        gross_profit += pnl
                                    elif pnl < 0:
                                        losses += 1
                                        gross_loss += abs(pnl)
                                    else:
                                        flats += 1

                                    if equity > peak_equity:
                                        peak_equity = equity

                                    dd = (equity - peak_equity) / peak_equity if peak_equity else 0.0
                                    if dd < max_drawdown_pct:
                                        max_drawdown_pct = dd
                                else:
                                    still_active.append(p)

                            active = still_active

                            open_risk = sum(p["one_contract_risk_dollars"] * p["quantity"] for p in active)
                            max_open_risk = equity * heat_cap

                            todays_entries = entries_by_date.get(current_date, [])

                            if rank_method == "fcfs_no_rank_benchmark":
                                todays_entries = sorted(
                                    todays_entries,
                                    key=lambda r: str(r.get("sequence_id") or "")
                                )
                            else:
                                todays_entries = sorted(
                                    todays_entries,
                                    key=lambda r: (
                                        r["rank_bucket"],
                                        r["rank_value"],
                                        r["selected_expectancy_sample_count"],
                                        -r["one_contract_risk_dollars"],
                                        str(r.get("sequence_id") or ""),
                                    ),
                                    reverse=True,
                                )

                            for t in todays_entries:
                                desired_qty = int(profile.get(t["rank_bucket"], 0))

                                if desired_qty <= 0:
                                    skipped.append(t)
                                    skipped_bucket_counts[t["rank_bucket"]] += 1
                                    skip_reason_counts["profile_bucket_zero_allocation"] += 1
                                    continue

                                affordable_qty = int((max_open_risk - open_risk) // t["one_contract_risk_dollars"])
                                qty = min(desired_qty, affordable_qty)

                                if qty <= 0:
                                    skipped.append(t)
                                    skipped_bucket_counts[t["rank_bucket"]] += 1
                                    skip_reason_counts["portfolio_heat_cap"] += 1
                                    continue

                                pos = dict(t)
                                pos["quantity"] = qty
                                active.append(pos)
                                accepted.append(pos)

                                accepted_bucket_counts[t["rank_bucket"]] += 1
                                accepted_qty_by_bucket[t["rank_bucket"]] += qty
                                open_risk += t["one_contract_risk_dollars"] * qty

                            open_risk_values.append(open_risk)
                            open_count_values.append(len(active))

                        # Close remaining positions.
                        for p in active:
                            pnl = p["realized_return"] * p["one_contract_risk_dollars"] * p["quantity"]
                            equity += pnl
                            pnl_sum += pnl

                            if pnl > 0:
                                wins += 1
                                gross_profit += pnl
                            elif pnl < 0:
                                losses += 1
                                gross_loss += abs(pnl)
                            else:
                                flats += 1

                            if equity > peak_equity:
                                peak_equity = equity

                            dd = (equity - peak_equity) / peak_equity if peak_equity else 0.0
                            if dd < max_drawdown_pct:
                                max_drawdown_pct = dd

                        accepted_trade_count = len(accepted)
                        skipped_trade_count = len(skipped)
                        total_decision_count = accepted_trade_count + skipped_trade_count
                        accepted_trade_rate = accepted_trade_count / total_decision_count if total_decision_count else 0.0
                        accepted_contract_count = sum(p["quantity"] for p in accepted)

                        profit_factor = gross_profit / gross_loss if gross_loss else None
                        win_rate = wins / accepted_trade_count if accepted_trade_count else None

                        scenario_rows.append({
                            "fold_name": fold["fold_name"],
                            "starting_capital": starting_capital,
                            "portfolio_heat_cap": heat_cap,
                            "rank_method": rank_method,
                            "allocation_profile": profile_name,
                            "ending_equity": equity,
                            "ending_equity_multiple": equity / starting_capital if starting_capital else None,
                            "total_pnl_dollars": pnl_sum,
                            "total_return_pct": (equity / starting_capital - 1.0) if starting_capital else None,
                            "max_drawdown_pct": max_drawdown_pct,
                            "accepted_trade_count": accepted_trade_count,
                            "skipped_trade_count": skipped_trade_count,
                            "accepted_trade_rate": accepted_trade_rate,
                            "accepted_contract_count": accepted_contract_count,
                            "gross_profit": gross_profit,
                            "gross_loss": gross_loss,
                            "profit_factor": profit_factor,
                            "win_rate": win_rate,
                            "winning_trade_count": wins,
                            "losing_trade_count": losses,
                            "flat_trade_count": flats,
                            "max_open_risk_dollars": max(open_risk_values) if open_risk_values else 0.0,
                            "p95_open_risk_dollars": percentile(open_risk_values, 0.95),
                            "max_open_trade_count": max(open_count_values) if open_count_values else 0,
                            "p95_open_trade_count": percentile(open_count_values, 0.95),
                            "accepted_bucket_counts": dict(accepted_bucket_counts),
                            "accepted_quantity_by_bucket": dict(accepted_qty_by_bucket),
                            "skipped_bucket_counts": dict(skipped_bucket_counts),
                            "skip_reason_counts": dict(skip_reason_counts),
                        })

    groups = defaultdict(list)

    for r in scenario_rows:
        key = (
            r["starting_capital"],
            r["portfolio_heat_cap"],
            r["rank_method"],
            r["allocation_profile"],
        )
        groups[key].append(r)

    aggregate_rows = []

    for key, group in groups.items():
        starting_capital, heat_cap, rank_method, profile_name = key

        positive_folds = sum(1 for g in group if g["total_pnl_dollars"] > 0)
        negative_folds = sum(1 for g in group if g["total_pnl_dollars"] < 0)

        aggregate_rows.append({
            "starting_capital": starting_capital,
            "portfolio_heat_cap": heat_cap,
            "rank_method": rank_method,
            "allocation_profile": profile_name,
            "fold_count": len(group),
            "positive_fold_count": positive_folds,
            "negative_fold_count": negative_folds,
            "total_pnl_dollars": sum(g["total_pnl_dollars"] for g in group),
            "avg_total_return_pct": sum(g["total_return_pct"] for g in group) / len(group),
            "worst_fold_drawdown_pct": min(g["max_drawdown_pct"] for g in group),
            "avg_accepted_trade_rate": sum(g["accepted_trade_rate"] for g in group) / len(group),
            "total_accepted_trade_count": sum(g["accepted_trade_count"] for g in group),
            "total_skipped_trade_count": sum(g["skipped_trade_count"] for g in group),
            "total_accepted_contract_count": sum(g["accepted_contract_count"] for g in group),
            "avg_profit_factor": sum(g["profit_factor"] or 0.0 for g in group) / len(group),
            "is_basic_candidate": (
                positive_folds >= 3
                and negative_folds <= 1
                and sum(g["total_pnl_dollars"] for g in group) > 0
                and min(g["max_drawdown_pct"] for g in group) >= -0.35
            ),
        })

    # Compare each profile to equal_all_11111 for same capital / heat / rank_method.
    baseline_map = {}

    for r in aggregate_rows:
        if r["allocation_profile"] == "equal_all_11111":
            baseline_map[(r["starting_capital"], r["portfolio_heat_cap"], r["rank_method"])] = r

    for r in aggregate_rows:
        b = baseline_map.get((r["starting_capital"], r["portfolio_heat_cap"], r["rank_method"]))

        if b:
            r["delta_pnl_vs_equal_all"] = r["total_pnl_dollars"] - b["total_pnl_dollars"]
            r["delta_avg_return_vs_equal_all"] = r["avg_total_return_pct"] - b["avg_total_return_pct"]
            r["delta_worst_drawdown_vs_equal_all"] = r["worst_fold_drawdown_pct"] - b["worst_fold_drawdown_pct"]
            r["delta_accepted_rate_vs_equal_all"] = r["avg_accepted_trade_rate"] - b["avg_accepted_trade_rate"]
        else:
            r["delta_pnl_vs_equal_all"] = None
            r["delta_avg_return_vs_equal_all"] = None
            r["delta_worst_drawdown_vs_equal_all"] = None
            r["delta_accepted_rate_vs_equal_all"] = None

        r["is_top_heavy_candidate"] = (
            r["is_basic_candidate"]
            and r["allocation_profile"] != "equal_all_11111"
            and r["delta_pnl_vs_equal_all"] is not None
            and r["delta_pnl_vs_equal_all"] > 0
        )

    candidates = [r for r in aggregate_rows if r["is_top_heavy_candidate"]]

    recommended_by_capital = {}

    for capital in CAPITALS:
        cap_candidates = [r for r in candidates if r["starting_capital"] == capital]

        if cap_candidates:
            recommended_by_capital[str(capital)] = sorted(
                cap_candidates,
                key=lambda r: (
                    -r["delta_pnl_vs_equal_all"],
                    -r["avg_total_return_pct"],
                    r["worst_fold_drawdown_pct"],
                    -r["avg_accepted_trade_rate"],
                ),
            )[0]

    summary = {
        "adapter_type": "portfolio_value_ranked_allocator_v2_builder",
        "artifact_type": "signalforge_portfolio_value_ranked_allocator_v2",
        "contract": "portfolio_value_ranked_allocator_v2",
        "is_ready": True,
        "readiness_state": "ready",
        "input_sized_trade_count": len(rows),
        "scenario_row_count": len(scenario_rows),
        "aggregate_scenario_count": len(aggregate_rows),
        "top_heavy_candidate_count": len(candidates),
        "recommended_by_capital": recommended_by_capital,
        "top_heavy_candidates_top50": sorted(
            candidates,
            key=lambda r: (
                r["starting_capital"],
                -r["delta_pnl_vs_equal_all"],
                -r["avg_total_return_pct"],
            ),
        )[:50],
        "policy": {
            "positive_expectancy_is_eligibility_universe": True,
            "rank_controls_priority_and_allocation": True,
            "portfolio_heat_controls_total_open_risk": True,
            "uses_whole_contracts": True,
            "can_increase_contracts_for_higher_rank_buckets": True,
            "can_drop_lower_rank_buckets_when_heat_is_constrained": True,
            "does_replace_skipped_trades": False,
            "does_feed_result_to_expectancy": False,
            "does_change_exit": False,
            "uses_prior_window_strategy_rank_stats": True,
        },
        "paths": {
            "summary_path": str(summary_path),
            "scenario_rows_path": str(scenario_rows_path),
            "aggregate_rows_path": str(aggregate_rows_path),
        },
    }

    write_jsonl(scenario_rows_path, scenario_rows)
    write_jsonl(aggregate_rows_path, aggregate_rows)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


