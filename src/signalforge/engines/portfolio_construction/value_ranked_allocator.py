# Auto-promoted by Stage 40C8D.
# Core engine for Stage 24A value_ranked_allocator_current.
# Backtesting should call this module instead of owning value-ranked allocation logic.

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class PerfStats:
    count: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_return: float = 0.0

    def update(self, realized_return: float) -> None:
        self.count += 1
        self.total_return += realized_return

        if realized_return > 0:
            self.wins += 1
            self.gross_profit += realized_return
        elif realized_return < 0:
            self.losses += 1
            self.gross_loss += abs(realized_return)

    def profit_factor(self) -> float | None:
        if self.count <= 0:
            return None
        if self.gross_loss > 0:
            return self.gross_profit / self.gross_loss
        if self.gross_profit > 0:
            return 99.0
        return None

    def win_rate(self) -> float | None:
        if self.count <= 0:
            return None
        return self.wins / self.count

    def average_return(self) -> float | None:
        if self.count <= 0:
            return None
        return self.total_return / self.count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        if isinstance(value, str) and value.strip().lower() in {"nan", "none", "null"}:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def get_strategy(row: dict[str, Any]) -> str:
    for key in ("selected_strategy", "strategy", "strategy_id", "candidate_strategy", "strategy_name"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def get_option_behavior_state(row: dict[str, Any]) -> str:
    rc = row.get("research_context") or {}
    ob = rc.get("option_behavior") or {}

    for key in ("options_behavior_state", "option_behavior_state", "state"):
        value = ob.get(key)
        if value not in (None, ""):
            return str(value)

    for key in ("options_behavior_state", "option_behavior_state"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)

    return ""


def get_regime_state(row: dict[str, Any]) -> str:
    for key in ("regime_state", "regime"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def get_symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or "")


def get_selected_legs(row: dict[str, Any]) -> list[dict[str, Any]]:
    legs = row.get("selected_legs")
    if isinstance(legs, list):
        return [x for x in legs if isinstance(x, dict)]
    return []


def estimate_leg_contract_count(row: dict[str, Any]) -> int:
    legs = get_selected_legs(row)
    return max(1, len(legs))


def get_base_contract_count(row: dict[str, Any]) -> int:
    for key in (
        "contract_count",
        "position_contract_count",
        "contracts",
        "quantity",
    ):
        value = as_int(row.get(key), 0)
        if value > 0:
            return value

    return estimate_leg_contract_count(row)


def get_unit_risk(row: dict[str, Any], fallback_unit_risk: float) -> float:
    for key in ("position_risk_dollars", "risk_dollars", "trade_risk_dollars"):
        value = as_float(row.get(key))
        if value is not None and value > 0:
            return value

    return fallback_unit_risk


def spread_penalty(row: dict[str, Any], threshold: float) -> float:
    if threshold <= 0:
        return 0.0

    ratios: list[float] = []
    for leg in get_selected_legs(row):
        spread = as_float(leg.get("spread_dollars"))
        mid = as_float(leg.get("mid"))
        if spread is not None and mid is not None and abs(mid) > 0:
            ratios.append(abs(spread) / abs(mid))

    if not ratios:
        return 0.0

    worst = max(ratios)
    if worst <= threshold:
        return 0.0

    return min(1.0, (worst - threshold) / threshold)


def pf_log_score(stats: PerfStats, min_count: int, weight: float) -> tuple[float, float | None, int]:
    if stats.count < min_count:
        return 0.0, None, stats.count

    pf = stats.profit_factor()
    if pf is None:
        return 0.0, None, stats.count

    capped_pf = max(0.10, min(10.0, pf))
    raw = math.log(capped_pf)
    raw = max(-2.0, min(2.0, raw))
    return weight * raw, pf, stats.count


def expectancy_score_component(row: dict[str, Any]) -> float:
    score = as_float(row.get("selected_expectancy_score"), 0.0) or 0.0
    score = max(0.0, min(0.75, score))
    return 1.25 * score


def sample_count_component(row: dict[str, Any]) -> float:
    n = as_int(row.get("selected_expectancy_sample_count"), 0)

    if n >= 100:
        return 0.35
    if n >= 50:
        return 0.25
    if n >= 20:
        return 0.10
    return -0.50


def bucket_units(rank_index: int, candidate_count: int, profile: dict[int, int]) -> tuple[int, int, float]:
    if candidate_count <= 1:
        bucket = 5
        pct = 0.0
    else:
        pct = rank_index / max(1, candidate_count - 1)

        if pct <= 0.20:
            bucket = 5
        elif pct <= 0.40:
            bucket = 4
        elif pct <= 0.60:
            bucket = 3
        elif pct <= 0.80:
            bucket = 2
        else:
            bucket = 1

    return profile.get(bucket, 0), bucket, pct


def make_skipped_row(
    row: dict[str, Any],
    reason: str,
    allocator_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(row)

    existing = out.get("sizing_skip_reasons") or out.get("skip_reasons") or []
    if not isinstance(existing, list):
        existing = [existing]

    if reason not in existing:
        existing.append(reason)

    out["sizing_state"] = "skipped"
    out["sizing_skip_reasons"] = existing
    out["position_risk_dollars"] = 0.0
    out["realized_pnl_dollars"] = 0.0
    out["allocated_units"] = 0

    payload = allocator_payload or {}
    payload["allocation_state"] = "skipped"
    payload["allocation_skip_reason"] = reason
    out["portfolio_value_ranked_allocator_v2_1"] = payload

    return out


def make_allocated_row(
    row: dict[str, Any],
    units: int,
    unit_risk: float,
    rank_payload: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    out = copy.deepcopy(row)

    realized_return = as_float(row.get("realized_return"), 0.0) or 0.0
    allocated_risk = unit_risk * units
    allocated_pnl = allocated_risk * realized_return
    base_contract_count = get_base_contract_count(row)
    allocated_contract_count = max(1, base_contract_count * units)

    out["sizing_state"] = "sized"
    out["sizing_skip_reasons"] = []
    out["allocated_units"] = units
    out["unit_risk_dollars"] = unit_risk
    out["position_risk_dollars"] = allocated_risk
    out["realized_pnl_dollars"] = allocated_pnl
    out["contract_count"] = allocated_contract_count
    out["position_contract_count"] = allocated_contract_count
    out["portfolio_value_ranked_allocator_v2_1"] = {
        **rank_payload,
        "allocation_state": "sized",
        "allocated_units": units,
        "unit_risk_dollars": unit_risk,
        "allocated_risk_dollars": allocated_risk,
        "allocated_pnl_dollars": allocated_pnl,
        "allocated_contract_count": allocated_contract_count,
    }

    return out, allocated_pnl


def build_rank_payload(
    row: dict[str, Any],
    strategy_stats: dict[str, PerfStats],
    strategy_regime_stats: dict[tuple[str, str], PerfStats],
    strategy_option_stats: dict[tuple[str, str], PerfStats],
    open_risk_by_strategy: dict[str, float],
    equity: float,
    args: argparse.Namespace,
) -> dict[str, Any]:
    strategy = get_strategy(row)
    regime = get_regime_state(row)
    option_state = get_option_behavior_state(row)

    strategy_component, strategy_pf, strategy_sample = pf_log_score(
        strategy_stats[strategy],
        args.min_strategy_sample,
        args.strategy_pf_weight,
    )

    regime_component, regime_pf, regime_sample = pf_log_score(
        strategy_regime_stats[(strategy, regime)],
        args.min_context_sample,
        args.strategy_regime_pf_weight,
    )

    option_component, option_pf, option_sample = pf_log_score(
        strategy_option_stats[(strategy, option_state)],
        args.min_context_sample,
        args.strategy_option_pf_weight,
    )

    expectancy_component = expectancy_score_component(row)
    sample_component = sample_count_component(row)

    spread_component = -args.spread_penalty_weight * spread_penalty(row, args.spread_penalty_threshold)

    strategy_heat = 0.0
    if equity > 0:
        strategy_heat = open_risk_by_strategy.get(strategy, 0.0) / equity

    concentration_component = 0.0
    soft_cap = args.max_strategy_heat_pct * 0.75
    if args.max_strategy_heat_pct > 0 and strategy_heat > soft_cap:
        concentration_component = -args.concentration_penalty_weight * min(
            1.0,
            (strategy_heat - soft_cap) / max(0.000001, args.max_strategy_heat_pct - soft_cap),
        )

    total_score = (
        strategy_component
        + regime_component
        + option_component
        + expectancy_component
        + sample_component
        + spread_component
        + concentration_component
    )

    return {
        "rank_score": total_score,
        "strategy": strategy,
        "symbol": get_symbol(row),
        "regime_state": regime,
        "option_behavior_state": option_state,
        "selected_expectancy_score": as_float(row.get("selected_expectancy_score")),
        "selected_expectancy_sample_count": as_int(row.get("selected_expectancy_sample_count"), 0),
        "components": {
            "prior_strategy_pf_component": strategy_component,
            "prior_strategy_regime_pf_component": regime_component,
            "prior_strategy_option_behavior_pf_component": option_component,
            "selected_expectancy_score_component": expectancy_component,
            "selected_expectancy_sample_count_component": sample_component,
            "spread_component": spread_component,
            "concentration_component": concentration_component,
        },
        "asof_stats": {
            "prior_strategy_profit_factor": strategy_pf,
            "prior_strategy_sample_count": strategy_sample,
            "prior_strategy_regime_profit_factor": regime_pf,
            "prior_strategy_regime_sample_count": regime_sample,
            "prior_strategy_option_behavior_profit_factor": option_pf,
            "prior_strategy_option_behavior_sample_count": option_sample,
        },
        "open_context": {
            "strategy_heat_before_allocation": strategy_heat,
        },
    }


def is_eligible_candidate(row: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str | None]:
    strategy = get_strategy(row)
    if not strategy:
        return False, "missing_selected_strategy"

    if args.require_input_sized and row.get("sizing_state") != "sized":
        return False, "input_row_not_sized"

    if row.get("selected_expectancy_state") != "positive_expectancy_candidate":
        return False, "not_positive_expectancy_candidate"

    sample_count = as_int(row.get("selected_expectancy_sample_count"), 0)
    if sample_count < args.min_expectancy_sample:
        return False, "expectancy_sample_below_minimum"

    realized_return = as_float(row.get("realized_return"))
    if realized_return is None:
        return False, "missing_realized_return"

    realization_date = parse_date(row.get("portfolio_realization_date"))
    if realization_date is None:
        return False, "missing_portfolio_realization_date"

    decision_date = parse_date(row.get("decision_date"))
    if decision_date is None:
        return False, "missing_decision_date"

    return True, None


def run_allocator(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.trade_ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(input_path)

    rows_with_dates: list[tuple[int, date, dict[str, Any]]] = []
    undated_rows: list[tuple[int, dict[str, Any]]] = []

    for idx, row in enumerate(rows):
        decision_date = parse_date(row.get("decision_date"))
        if decision_date is None:
            undated_rows.append((idx, row))
        else:
            rows_with_dates.append((idx, decision_date, row))

    rows_with_dates.sort(key=lambda x: (x[1], x[0]))

    by_date: dict[date, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for idx, decision_date, row in rows_with_dates:
        by_date[decision_date].append((idx, row))

    strategy_stats: dict[str, PerfStats] = defaultdict(PerfStats)
    strategy_regime_stats: dict[tuple[str, str], PerfStats] = defaultdict(PerfStats)
    strategy_option_stats: dict[tuple[str, str], PerfStats] = defaultdict(PerfStats)

    equity = float(args.starting_capital)
    open_positions: list[dict[str, Any]] = []
    output_by_idx: dict[int, dict[str, Any]] = {}
    realized_pnl_by_date: dict[str, float] = defaultdict(float)

    skip_reasons = Counter()
    allocation_states = Counter()

    profile = {
        5: args.bucket_5_units,
        4: args.bucket_4_units,
        3: args.bucket_3_units,
        2: args.bucket_2_units,
        1: args.bucket_1_units,
    }

    def close_positions_through(current_date: date) -> None:
        nonlocal equity, open_positions

        still_open: list[dict[str, Any]] = []

        for pos in open_positions:
            if pos["exit_date"] <= current_date:
                equity += pos["pnl"]
                exit_key = pos["exit_date"].isoformat()
                realized_pnl_by_date[exit_key] += pos["pnl"]

                ret = pos["realized_return"]
                strategy = pos["strategy"]
                regime = pos["regime_state"]
                option_state = pos["option_behavior_state"]

                strategy_stats[strategy].update(ret)
                strategy_regime_stats[(strategy, regime)].update(ret)
                strategy_option_stats[(strategy, option_state)].update(ret)
            else:
                still_open.append(pos)

        open_positions = still_open

    def current_open_risk() -> float:
        return sum(float(pos["risk"]) for pos in open_positions)

    def current_open_risk_by_strategy() -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for pos in open_positions:
            out[pos["strategy"]] += float(pos["risk"])
        return dict(out)

    def current_open_risk_by_symbol() -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for pos in open_positions:
            out[pos["symbol"]] += float(pos["risk"])
        return dict(out)

    for current_date in sorted(by_date):
        close_positions_through(current_date)

        date_items = by_date[current_date]
        candidates: list[dict[str, Any]] = []

        for idx, row in date_items:
            eligible, reason = is_eligible_candidate(row, args)
            if not eligible:
                skipped = make_skipped_row(row, reason or "ineligible")
                output_by_idx[idx] = skipped
                skip_reasons[reason or "ineligible"] += 1
                allocation_states["skipped"] += 1
                continue

            candidates.append({"idx": idx, "row": row})

        open_by_strategy = current_open_risk_by_strategy()

        for item in candidates:
            item["rank_payload"] = build_rank_payload(
                item["row"],
                strategy_stats,
                strategy_regime_stats,
                strategy_option_stats,
                open_by_strategy,
                equity,
                args,
            )

        candidates.sort(
            key=lambda item: (
                item["rank_payload"]["rank_score"],
                as_float(item["row"].get("selected_expectancy_score"), 0.0) or 0.0,
                as_int(item["row"].get("selected_expectancy_sample_count"), 0),
            ),
            reverse=True,
        )

        candidate_count = len(candidates)

        for rank_index, item in enumerate(candidates):
            idx = item["idx"]
            row = item["row"]
            payload = item["rank_payload"]

            suggested_units, bucket, rank_pct = bucket_units(rank_index, candidate_count, profile)

            payload["rank"] = rank_index + 1
            payload["rank_percentile"] = rank_pct
            payload["rank_bucket"] = bucket
            payload["suggested_units"] = suggested_units
            payload["portfolio_equity_before_allocation"] = equity

            if suggested_units <= 0:
                skipped = make_skipped_row(row, "allocator_bucket_zero", payload)
                output_by_idx[idx] = skipped
                skip_reasons["allocator_bucket_zero"] += 1
                allocation_states["skipped"] += 1
                continue

            unit_risk = get_unit_risk(row, args.fallback_unit_risk_dollars)
            max_trade_risk = equity * args.max_trade_risk_pct
            if max_trade_risk > 0:
                suggested_units = min(suggested_units, int(max_trade_risk // unit_risk))

            if suggested_units <= 0:
                skipped = make_skipped_row(row, "max_trade_risk_cap_zero", payload)
                output_by_idx[idx] = skipped
                skip_reasons["max_trade_risk_cap_zero"] += 1
                allocation_states["skipped"] += 1
                continue

            units = suggested_units

            while units > 0:
                risk = unit_risk * units
                projected_total_heat = (current_open_risk() + risk) / equity if equity > 0 else 99.0

                open_by_strategy = current_open_risk_by_strategy()
                open_by_symbol = current_open_risk_by_symbol()

                projected_strategy_heat = (
                    (open_by_strategy.get(get_strategy(row), 0.0) + risk) / equity if equity > 0 else 99.0
                )
                projected_symbol_heat = (
                    (open_by_symbol.get(get_symbol(row), 0.0) + risk) / equity if equity > 0 else 99.0
                )

                if projected_total_heat > args.portfolio_heat_cap:
                    units -= 1
                    continue

                if args.max_strategy_heat_pct > 0 and projected_strategy_heat > args.max_strategy_heat_pct:
                    units -= 1
                    continue

                if args.max_symbol_heat_pct > 0 and projected_symbol_heat > args.max_symbol_heat_pct:
                    units -= 1
                    continue

                break

            if units <= 0:
                skipped = make_skipped_row(row, "portfolio_or_context_heat_cap_full", payload)
                output_by_idx[idx] = skipped
                skip_reasons["portfolio_or_context_heat_cap_full"] += 1
                allocation_states["skipped"] += 1
                continue

            allocated, pnl = make_allocated_row(row, units, unit_risk, payload)
            output_by_idx[idx] = allocated
            allocation_states["sized"] += 1

            exit_date = parse_date(row.get("portfolio_realization_date"))
            realized_return = as_float(row.get("realized_return"), 0.0) or 0.0
            risk = unit_risk * units

            if exit_date is not None:
                open_positions.append(
                    {
                        "exit_date": exit_date,
                        "risk": risk,
                        "pnl": pnl,
                        "realized_return": realized_return,
                        "strategy": get_strategy(row),
                        "symbol": get_symbol(row),
                        "regime_state": get_regime_state(row),
                        "option_behavior_state": get_option_behavior_state(row),
                    }
                )

    if open_positions:
        for pos in sorted(open_positions, key=lambda x: x["exit_date"]):
            equity += pos["pnl"]
            exit_key = pos["exit_date"].isoformat()
            realized_pnl_by_date[exit_key] += pos["pnl"]

            strategy_stats[pos["strategy"]].update(pos["realized_return"])
            strategy_regime_stats[(pos["strategy"], pos["regime_state"])].update(pos["realized_return"])
            strategy_option_stats[(pos["strategy"], pos["option_behavior_state"])].update(pos["realized_return"])

        open_positions = []

    for idx, row in undated_rows:
        skipped = make_skipped_row(row, "missing_decision_date")
        output_by_idx[idx] = skipped
        skip_reasons["missing_decision_date"] += 1
        allocation_states["skipped"] += 1

    output_rows = [output_by_idx[idx] for idx in sorted(output_by_idx)]

    sized_rows = [r for r in output_rows if r.get("sizing_state") == "sized"]
    returns = [as_float(r.get("realized_return"), 0.0) or 0.0 for r in sized_rows]
    pnl_values = [as_float(r.get("realized_pnl_dollars"), 0.0) or 0.0 for r in sized_rows]

    gross_profit = sum(x for x in pnl_values if x > 0)
    gross_loss = abs(sum(x for x in pnl_values if x < 0))
    total_pnl = sum(pnl_values)
    ending_capital = args.starting_capital + total_pnl

    curve_rows: list[dict[str, Any]] = []
    running_equity = float(args.starting_capital)
    peak = running_equity
    max_dd = 0.0
    max_dd_date = None

    for realized_date in sorted(realized_pnl_by_date):
        pnl = realized_pnl_by_date[realized_date]
        running_equity += pnl
        peak = max(peak, running_equity)
        drawdown = (running_equity - peak) / peak if peak > 0 else 0.0

        if drawdown < max_dd:
            max_dd = drawdown
            max_dd_date = realized_date

        curve_rows.append(
            {
                "date": realized_date,
                "realized_pnl_dollars": pnl,
                "equity": running_equity,
                "drawdown_pct": drawdown,
                "peak_equity": peak,
            }
        )

    strategy_summary = []
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sized_rows:
        by_strategy[get_strategy(row)].append(row)

    positive_pnl = sum(max(0.0, as_float(r.get("realized_pnl_dollars"), 0.0) or 0.0) for r in sized_rows)

    for strategy, group in sorted(by_strategy.items()):
        strategy_pnl = sum(as_float(r.get("realized_pnl_dollars"), 0.0) or 0.0 for r in group)
        strategy_positive = sum(max(0.0, as_float(r.get("realized_pnl_dollars"), 0.0) or 0.0) for r in group)
        strategy_summary.append(
            {
                "strategy": strategy,
                "trade_count": len(group),
                "allocated_units": sum(as_int(r.get("allocated_units"), 0) for r in group),
                "pnl": strategy_pnl,
                "positive_contribution_pct": strategy_positive / positive_pnl if positive_pnl > 0 else None,
                "total_pnl_pct": strategy_pnl / total_pnl if total_pnl != 0 else None,
            }
        )

    strategy_summary.sort(key=lambda x: x["pnl"], reverse=True)

    rows_path = output_dir / "signalforge_portfolio_value_ranked_allocator_v2_1_position_sizing_replay.jsonl"
    curve_path = output_dir / "signalforge_portfolio_value_ranked_allocator_v2_1_equity_curve.jsonl"
    summary_path = output_dir / "signalforge_portfolio_value_ranked_allocator_v2_1_summary.json"

    summary = {
        "adapter_type": "portfolio_value_ranked_allocator_v2_1_builder",
        "artifact_type": "signalforge_portfolio_value_ranked_allocator_v2_1",
        "contract": "portfolio_value_ranked_allocator_v2_1",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "input_trade_ledger": str(input_path),
        "paths": {
            "position_sizing_replay": str(rows_path),
            "equity_curve": str(curve_path),
            "summary": str(summary_path),
        },
        "leakage_controls": {
            "allocation_uses_current_trade_realized_return": False,
            "allocation_uses_future_rows": False,
            "allocation_uses_full_sample_strategy_pf": False,
            "allocation_uses_prior_completed_positions_only": True,
            "current_trade_outcome_used_only_for_post_allocation_pnl": True,
        },
        "parameters": vars(args),
        "input_row_count": len(rows),
        "output_row_count": len(output_rows),
        "sized_trade_count": len(sized_rows),
        "skipped_trade_count": len(output_rows) - len(sized_rows),
        "allocation_state_counts": dict(allocation_states),
        "skip_reason_counts": dict(skip_reasons),
        "starting_capital": args.starting_capital,
        "ending_capital": ending_capital,
        "total_pnl": total_pnl,
        "total_return": total_pnl / args.starting_capital if args.starting_capital else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "win_rate": sum(1 for r in returns if r > 0) / len(returns) if returns else None,
        "average_realized_return": sum(returns) / len(returns) if returns else None,
        "max_drawdown_pct": max_dd,
        "max_drawdown_date": max_dd_date,
        "equity_curve_row_count": len(curve_rows),
        "strategy_summary": strategy_summary,
    }

    write_jsonl(rows_path, output_rows)
    write_jsonl(curve_path, curve_rows)
    write_json(summary_path, summary)

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Walk-forward portfolio value ranked allocator v2.1."
    )

    parser.add_argument("--trade-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--starting-capital", type=float, default=50000.0)

    parser.add_argument("--portfolio-heat-cap", type=float, default=0.50)
    parser.add_argument("--max-strategy-heat-pct", type=float, default=0.35)
    parser.add_argument("--max-symbol-heat-pct", type=float, default=0.12)
    parser.add_argument("--max-trade-risk-pct", type=float, default=0.06)

    parser.add_argument("--fallback-unit-risk-dollars", type=float, default=1000.0)
    parser.add_argument("--min-expectancy-sample", type=int, default=20)
    parser.add_argument("--min-strategy-sample", type=int, default=20)
    parser.add_argument("--min-context-sample", type=int, default=30)

    parser.add_argument("--bucket-5-units", type=int, default=3)
    parser.add_argument("--bucket-4-units", type=int, default=2)
    parser.add_argument("--bucket-3-units", type=int, default=1)
    parser.add_argument("--bucket-2-units", type=int, default=0)
    parser.add_argument("--bucket-1-units", type=int, default=0)

    parser.add_argument("--strategy-pf-weight", type=float, default=2.0)
    parser.add_argument("--strategy-regime-pf-weight", type=float, default=1.25)
    parser.add_argument("--strategy-option-pf-weight", type=float, default=0.75)
    parser.add_argument("--spread-penalty-threshold", type=float, default=0.20)
    parser.add_argument("--spread-penalty-weight", type=float, default=0.25)
    parser.add_argument("--concentration-penalty-weight", type=float, default=0.75)

    parser.add_argument(
        "--allow-input-skipped",
        action="store_true",
        help="Allow rows not already sized in the input ledger to be considered. Default is false.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.require_input_sized = not args.allow_input_skipped

    summary = run_allocator(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "blocker_count": summary["blocker_count"],
        "sized_trade_count": summary["sized_trade_count"],
        "skipped_trade_count": summary["skipped_trade_count"],
        "starting_capital": summary["starting_capital"],
        "ending_capital": summary["ending_capital"],
        "total_return": summary["total_return"],
        "profit_factor": summary["profit_factor"],
        "max_drawdown_pct": summary["max_drawdown_pct"],
        "paths": summary["paths"],
        "leakage_controls": summary["leakage_controls"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
