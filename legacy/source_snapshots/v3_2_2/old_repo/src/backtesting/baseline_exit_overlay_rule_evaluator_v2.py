from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            n += 1
    return n


def fnum(value, default=None):
    try:
        if value is None or str(value).strip() == "":
            return default
        x = float(value)
        if math.isnan(x):
            return default
        return x
    except Exception:
        return default


def date10(value):
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if text else None


def dt(value):
    d = date10(value)
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except Exception:
        return None


def days_between(a, b):
    da = dt(a)
    db = dt(b)
    if da is None or db is None:
        return None
    return (db - da).days


def side_sign(row):
    signed_qty = fnum(row.get("signed_quantity"))
    if signed_qty is not None and signed_qty != 0:
        return 1 if signed_qty > 0 else -1

    side = str(row.get("side") or row.get("leg_role") or "").lower()
    if "sell" in side or "short" in side:
        return -1
    if "buy" in side or "long" in side:
        return 1
    return None


def quantity(row):
    signed_qty = fnum(row.get("signed_quantity"))
    if signed_qty is not None and signed_qty != 0:
        return abs(signed_qty)

    q = fnum(row.get("quantity"), 1.0)
    return abs(q or 1.0)


def entry_price(row, side, mode):
    bid = fnum(row.get("entry_bid"))
    ask = fnum(row.get("entry_ask"))
    mid = fnum(row.get("entry_mid"))

    if mode in ("manifest_first", "mid"):
        if mid is not None:
            return mid
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0

    if mode == "quote_native":
        if side > 0 and ask is not None:
            return ask
        if side < 0 and bid is not None:
            return bid

    if mid is not None:
        return mid
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if side > 0:
        return ask
    return bid


def close_price(leg_quote, side, mode):
    bid = fnum(leg_quote.get("quote_bid", leg_quote.get("bid")))
    ask = fnum(leg_quote.get("quote_ask", leg_quote.get("ask")))
    mid = fnum(leg_quote.get("quote_mid", leg_quote.get("mid")))

    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0

    if mode == "mid":
        return mid

    # closeable/conservative liquidation:
    # long leg closes at bid; short leg closes at ask.
    if side > 0:
        return bid if bid is not None else mid
    return ask if ask is not None else mid


def stat(values, kind):
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    if kind == "sum":
        return sum(clean)
    if kind == "mean":
        return mean(clean)
    if kind == "median":
        return median(clean)
    if kind == "min":
        return min(clean)
    if kind == "max":
        return max(clean)
    return None


def load_manifest(path: Path, entry_price_mode: str):
    trades = {}
    bad_legs = []

    for row in read_jsonl(path):
        tid = str(row.get("trade_id") or row.get("sequence_id") or "")
        if not tid:
            bad_legs.append({"reason": "missing_trade_id", "row": row})
            continue

        if tid not in trades:
            trades[tid] = {
                "trade_id": tid,
                "selected_symbol": row.get("selected_symbol") or row.get("symbol"),
                "selected_strategy": row.get("selected_strategy") or row.get("strategy_name"),
                "entry_date": date10(row.get("entry_date") or row.get("selected_entry_date")),
                "original_exit_date": date10(row.get("exit_date") or row.get("selected_exit_date") or row.get("outcome_date")),
                "legs": {},
            }

        leg_index = str(row.get("leg_index"))
        side = side_sign(row)
        qty = quantity(row)
        px = entry_price(row, side or 1, entry_price_mode) if side else None

        if side is None or px is None:
            bad_legs.append({
                "reason": "unmarkable_manifest_leg",
                "trade_id": tid,
                "leg_index": leg_index,
                "side": row.get("side"),
                "signed_quantity": row.get("signed_quantity"),
                "entry_bid": row.get("entry_bid"),
                "entry_ask": row.get("entry_ask"),
                "entry_mid": row.get("entry_mid"),
            })

        trades[tid]["legs"][leg_index] = {
            "leg_index": leg_index,
            "contract_symbol": row.get("contract_symbol") or row.get("option_symbol"),
            "side": side,
            "quantity": qty,
            "entry_price": px,
            "expiration": date10(row.get("expiration")),
            "multiplier": fnum(row.get("multiplier"), 100.0),
        }

    return trades, bad_legs


def load_trade_states(path: Optional[Path]):
    states = {}
    if not path or not path.exists():
        return states

    for row in read_jsonl(path):
        tid = str(row.get("trade_id") or "")
        if tid:
            states[tid] = str(row.get("path_state") or "unknown")
    return states


def load_path_rows(path: Path):
    grouped = defaultdict(list)
    for row in read_jsonl(path):
        tid = str(row.get("trade_id") or "")
        if tid:
            grouped[tid].append(row)
    return grouped


def build_marks_for_trade(trade, path_rows, mark_price_mode):
    warnings = []
    marks = []

    legs = trade["legs"]
    leg_count = len(legs)

    if leg_count == 0:
        return [], ["missing_manifest_legs"]

    if any(leg.get("side") not in (-1, 1) for leg in legs.values()):
        return [], ["missing_or_unparseable_leg_side"]

    if any(leg.get("entry_price") is None for leg in legs.values()):
        return [], ["missing_entry_price"]

    open_cashflow = 0.0
    gross_entry_cash = 0.0

    for leg in legs.values():
        side = int(leg["side"])
        qty = float(leg["quantity"])
        px = float(leg["entry_price"])
        mult = float(leg.get("multiplier") or 100.0)
        open_leg_cashflow = -side * px * qty * mult
        open_cashflow += open_leg_cashflow
        gross_entry_cash += abs(open_leg_cashflow)

    denominator = gross_entry_cash if gross_entry_cash > 1e-9 else abs(open_cashflow)

    min_exp = min([leg["expiration"] for leg in legs.values() if leg.get("expiration")] or [None])

    for row in sorted(path_rows, key=lambda r: str(r.get("quote_date"))):
        qd = date10(row.get("quote_date"))
        if not qd:
            continue

        if str(row.get("path_state")) != "complete":
            warnings.append(f"top_path_not_complete_on_{qd}")
            continue

        leg_quotes = row.get("leg_quotes")
        if not isinstance(leg_quotes, list):
            warnings.append(f"missing_nested_leg_quotes_on_{qd}")
            continue

        if len(leg_quotes) < leg_count:
            warnings.append(f"incomplete_nested_leg_quotes_on_{qd}")
            continue

        used = set()
        close_cashflow = 0.0
        source_counts = Counter()

        for q in leg_quotes:
            leg_index = str(q.get("leg_index"))
            leg = legs.get(leg_index)

            if leg is None:
                # fallback contract match
                contract = q.get("contract_symbol") or q.get("option_symbol")
                matches = [x for x in legs.values() if x.get("contract_symbol") == contract]
                leg = matches[0] if len(matches) == 1 else None

            if leg is None:
                warnings.append(f"unmatched_leg_quote_on_{qd}")
                continue

            leg_id = str(leg["leg_index"])
            if leg_id in used:
                continue

            side = int(leg["side"])
            qty = float(leg["quantity"])
            mult = float(leg.get("multiplier") or 100.0)
            px = close_price(q, side, mark_price_mode)

            if px is None:
                warnings.append(f"missing_close_price_on_{qd}_leg_{leg_id}")
                continue

            close_cashflow += side * px * qty * mult
            used.add(leg_id)
            source_counts[str(q.get("source") or q.get("quote_source") or "unknown")] += 1

        if len(used) != leg_count:
            warnings.append(f"not_all_legs_markable_on_{qd}")
            continue

        pnl = open_cashflow + close_cashflow
        ret = pnl / denominator if denominator else None

        marks.append({
            "adapter_type": "baseline_exit_overlay_rule_evaluator_v2",
            "artifact_type": "signalforge_baseline_exit_overlay_daily_trade_mark_v2",
            "contract": "baseline_exit_overlay_daily_trade_mark_v2",
            "trade_id": trade["trade_id"],
            "selected_symbol": trade.get("selected_symbol"),
            "selected_strategy": trade.get("selected_strategy"),
            "quote_date": qd,
            "entry_date": trade.get("entry_date"),
            "original_exit_date": trade.get("original_exit_date"),
            "min_expiration": min_exp,
            "dte": days_between(qd, min_exp) if min_exp else None,
            "open_cashflow": open_cashflow,
            "gross_entry_cash": gross_entry_cash,
            "return_denominator": denominator,
            "close_cashflow": close_cashflow,
            "pnl": pnl,
            "return_on_entry_cash": ret,
            "leg_count": leg_count,
            "quote_source_counts": dict(source_counts),
            "does_select_strategy": False,
            "does_feed_exit_result_to_expectancy": False,
            "does_change_position_size": False,
        })

    return marks, warnings


def pick_exit(trade, marks, profit_target, loss_stop, max_holding_days, close_dte_less_equal, ignore_entry_date_triggers):
    if not marks:
        return None, "no_markable_path"

    entry_date = trade.get("entry_date")
    original_exit_date = trade.get("original_exit_date")

    fallback = None
    exact = [m for m in marks if original_exit_date and m["quote_date"] == original_exit_date]
    if exact:
        fallback = exact[-1]
    else:
        prior = [m for m in marks if not original_exit_date or m["quote_date"] <= original_exit_date]
        fallback = prior[-1] if prior else marks[-1]

    stop = loss_stop
    if stop is not None and stop > 0:
        stop = -stop

    for m in marks:
        qd = m["quote_date"]

        if ignore_entry_date_triggers and entry_date and qd <= entry_date:
            continue

        ret = m.get("return_on_entry_cash")
        held = days_between(entry_date, qd)
        dte = m.get("dte")

        if stop is not None and ret is not None and ret <= stop:
            return m, "loss_stop"

        if profit_target is not None and ret is not None and ret >= profit_target:
            return m, "profit_target"

        if max_holding_days is not None and held is not None and held >= max_holding_days:
            return m, "max_holding_days"

        if close_dte_less_equal is not None and dte is not None and dte <= close_dte_less_equal:
            return m, "dte_exit"

    return fallback, "original_exit"


def run(args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades, bad_legs = load_manifest(Path(args.trade_leg_manifest), args.entry_price_mode)
    trade_states = load_trade_states(Path(args.trade_summaries) if args.trade_summaries else None)
    path_rows_by_trade = load_path_rows(Path(args.daily_quote_path_rows))

    outcomes = []
    skipped = []
    daily_marks = []

    exit_reason_counts = Counter()
    skip_reason_counts = Counter()
    strategy_counts = Counter()
    symbol_counts = Counter()

    for tid in sorted(trades):
        trade = trades[tid]
        state = trade_states.get(tid, "unknown")

        if state not in ("complete", "unknown") and not args.allow_partial_trades:
            skipped.append({
                "trade_id": tid,
                "selected_symbol": trade.get("selected_symbol"),
                "selected_strategy": trade.get("selected_strategy"),
                "skip_reason": "path_not_complete",
                "path_state": state,
            })
            skip_reason_counts["path_not_complete"] += 1
            continue

        marks, warnings = build_marks_for_trade(trade, path_rows_by_trade.get(tid, []), args.mark_price_mode)
        daily_marks.extend(marks)

        exit_mark, exit_reason = pick_exit(
            trade,
            marks,
            args.profit_target_return,
            args.loss_stop_return,
            args.max_holding_days,
            args.close_dte_less_equal,
            not args.include_entry_date_triggers,
        )

        if exit_mark is None:
            skipped.append({
                "trade_id": tid,
                "selected_symbol": trade.get("selected_symbol"),
                "selected_strategy": trade.get("selected_strategy"),
                "skip_reason": exit_reason,
                "path_state": state,
                "warnings": warnings[:25],
            })
            skip_reason_counts[exit_reason] += 1
            continue

        original_exit = trade.get("original_exit_date")
        baseline_exact = [m for m in marks if original_exit and m["quote_date"] == original_exit]
        if baseline_exact:
            baseline = baseline_exact[-1]
        else:
            prior = [m for m in marks if not original_exit or m["quote_date"] <= original_exit]
            baseline = prior[-1] if prior else marks[-1]

        managed_ret = exit_mark.get("return_on_entry_cash")
        original_ret = baseline.get("return_on_entry_cash")
        managed_pnl = exit_mark.get("pnl")
        original_pnl = baseline.get("pnl")

        returns = [m.get("return_on_entry_cash") for m in marks if m.get("return_on_entry_cash") is not None]
        pnls = [m.get("pnl") for m in marks if m.get("pnl") is not None]

        outcome = {
            "adapter_type": "baseline_exit_overlay_rule_evaluator_v2",
            "artifact_type": "signalforge_baseline_exit_overlay_rule_evaluation_trade_outcome_v2",
            "contract": "baseline_exit_overlay_rule_evaluation_trade_outcome_v2",
            "scenario_name": args.scenario_name,
            "trade_id": tid,
            "selected_symbol": trade.get("selected_symbol"),
            "selected_strategy": trade.get("selected_strategy"),
            "entry_date": trade.get("entry_date"),
            "managed_exit_date": exit_mark.get("quote_date"),
            "original_exit_date": original_exit,
            "exit_reason": exit_reason,
            "path_state": state,
            "path_trade_mark_count": len(marks),
            "leg_count": len(trade["legs"]),
            "days_held_managed": days_between(trade.get("entry_date"), exit_mark.get("quote_date")),
            "days_held_original": days_between(trade.get("entry_date"), original_exit),
            "managed_pnl": managed_pnl,
            "managed_return_on_entry_cash": managed_ret,
            "original_exit_pnl": original_pnl,
            "original_exit_return_on_entry_cash": original_ret,
            "delta_pnl_vs_original_exit": managed_pnl - original_pnl if managed_pnl is not None and original_pnl is not None else None,
            "delta_return_vs_original_exit": managed_ret - original_ret if managed_ret is not None and original_ret is not None else None,
            "mae_return_on_entry_cash": stat(returns, "min"),
            "mfe_return_on_entry_cash": stat(returns, "max"),
            "mae_pnl": stat(pnls, "min"),
            "mfe_pnl": stat(pnls, "max"),
            "warnings": warnings[:25],
            "does_select_strategy": False,
            "does_feed_exit_result_to_expectancy": False,
            "does_change_position_size": False,
            "does_apply_position_sizing": False,
        }

        outcomes.append(outcome)
        exit_reason_counts[exit_reason] += 1
        strategy_counts[str(trade.get("selected_strategy") or "unknown")] += 1
        symbol_counts[str(trade.get("selected_symbol") or "unknown")] += 1

    outcomes_path = output_dir / "baseline_exit_overlay_rule_evaluation_trade_outcomes.jsonl"
    skipped_path = output_dir / "baseline_exit_overlay_rule_evaluation_skipped_trades.jsonl"
    marks_path = output_dir / "baseline_exit_overlay_rule_evaluation_daily_trade_marks.jsonl"
    bad_legs_path = output_dir / "baseline_exit_overlay_rule_evaluation_bad_manifest_legs.jsonl"
    summary_path = output_dir / "baseline_exit_overlay_rule_evaluation_summary.json"

    write_jsonl(outcomes_path, outcomes)
    write_jsonl(skipped_path, skipped)
    write_jsonl(marks_path, daily_marks)
    write_jsonl(bad_legs_path, bad_legs)

    managed_returns = [x.get("managed_return_on_entry_cash") for x in outcomes if x.get("managed_return_on_entry_cash") is not None]
    original_returns = [x.get("original_exit_return_on_entry_cash") for x in outcomes if x.get("original_exit_return_on_entry_cash") is not None]
    delta_returns = [x.get("delta_return_vs_original_exit") for x in outcomes if x.get("delta_return_vs_original_exit") is not None]

    managed_pnls = [x.get("managed_pnl") for x in outcomes if x.get("managed_pnl") is not None]
    original_pnls = [x.get("original_exit_pnl") for x in outcomes if x.get("original_exit_pnl") is not None]
    delta_pnls = [x.get("delta_pnl_vs_original_exit") for x in outcomes if x.get("delta_pnl_vs_original_exit") is not None]

    blocker_count = 0 if outcomes else 1

    summary = {
        "adapter_type": "baseline_exit_overlay_rule_evaluator_v2",
        "artifact_type": "signalforge_baseline_exit_overlay_rule_evaluation_v2",
        "contract": "baseline_exit_overlay_rule_evaluation_v2",
        "scenario_name": args.scenario_name,
        "is_ready": blocker_count == 0,
        "readiness_state": "ready" if blocker_count == 0 else "blocked",
        "blocker_count": blocker_count,
        "input_trade_count": len(trades),
        "evaluated_trade_count": len(outcomes),
        "skipped_trade_count": len(skipped),
        "bad_manifest_leg_count": len(bad_legs),
        "daily_trade_mark_count": len(daily_marks),
        "exit_reason_counts": dict(exit_reason_counts),
        "skip_reason_counts": dict(skip_reason_counts),
        "top_strategy_counts": dict(strategy_counts.most_common(25)),
        "top_symbol_counts": dict(symbol_counts.most_common(25)),
        "managed_return_on_entry_cash": {
            "sum": stat(managed_returns, "sum"),
            "mean": stat(managed_returns, "mean"),
            "median": stat(managed_returns, "median"),
            "min": stat(managed_returns, "min"),
            "max": stat(managed_returns, "max"),
        },
        "original_exit_return_on_entry_cash": {
            "sum": stat(original_returns, "sum"),
            "mean": stat(original_returns, "mean"),
            "median": stat(original_returns, "median"),
            "min": stat(original_returns, "min"),
            "max": stat(original_returns, "max"),
        },
        "delta_return_vs_original_exit": {
            "sum": stat(delta_returns, "sum"),
            "mean": stat(delta_returns, "mean"),
            "median": stat(delta_returns, "median"),
            "min": stat(delta_returns, "min"),
            "max": stat(delta_returns, "max"),
        },
        "managed_pnl_per_1x_leg_ratio": {
            "sum": stat(managed_pnls, "sum"),
            "mean": stat(managed_pnls, "mean"),
            "median": stat(managed_pnls, "median"),
            "min": stat(managed_pnls, "min"),
            "max": stat(managed_pnls, "max"),
        },
        "original_exit_pnl_per_1x_leg_ratio": {
            "sum": stat(original_pnls, "sum"),
            "mean": stat(original_pnls, "mean"),
            "median": stat(original_pnls, "median"),
            "min": stat(original_pnls, "min"),
            "max": stat(original_pnls, "max"),
        },
        "delta_pnl_vs_original_exit_per_1x_leg_ratio": {
            "sum": stat(delta_pnls, "sum"),
            "mean": stat(delta_pnls, "mean"),
            "median": stat(delta_pnls, "median"),
            "min": stat(delta_pnls, "min"),
            "max": stat(delta_pnls, "max"),
        },
        "policy": {
            "does_select_strategy": False,
            "does_feed_exit_result_to_expectancy": False,
            "does_change_position_size": False,
            "does_apply_position_sizing": False,
            "uses_locked_selected_trades_only": True,
            "uses_nested_leg_quotes": True,
            "does_forward_fill": False,
            "does_invent_prices": False,
            "partial_trade_handling": "excluded" if not args.allow_partial_trades else "allowed",
        },
        "paths": {
            "trade_outcomes_path": str(outcomes_path),
            "skipped_trades_path": str(skipped_path),
            "daily_trade_marks_path": str(marks_path),
            "bad_manifest_legs_path": str(bad_legs_path),
            "summary_path": str(summary_path),
        },
        "parameters": vars(args),
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--daily-quote-path-rows", required=True)
    p.add_argument("--trade-summaries", required=False)
    p.add_argument("--trade-leg-manifest", required=True)
    p.add_argument("--scenario-name", default="close_on_original_exit_only")
    p.add_argument("--profit-target-return", type=float, default=None)
    p.add_argument("--loss-stop-return", type=float, default=None)
    p.add_argument("--max-holding-days", type=int, default=None)
    p.add_argument("--close-dte-less-equal", type=int, default=None)
    p.add_argument("--mark-price-mode", choices=["closeable", "conservative", "mid"], default="closeable")
    p.add_argument("--entry-price-mode", choices=["manifest_first", "quote_native", "mid"], default="manifest_first")
    p.add_argument("--allow-partial-trades", action="store_true")
    p.add_argument("--include-entry-date-triggers", action="store_true")
    p.add_argument("--output-dir", required=True)
    return p


def main():
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
