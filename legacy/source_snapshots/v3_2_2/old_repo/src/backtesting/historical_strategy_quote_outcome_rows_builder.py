from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


BUY = "buy"
SELL = "sell"


def _as_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _as_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) >= 10:
        return text[:10]
    return None


def _parse_date(value: Any) -> Optional[datetime]:
    text = _as_date(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except Exception:
        return None


def _date_add(date_text: str, days: int) -> str:
    date = datetime.strptime(date_text, "%Y-%m-%d")
    return (date + timedelta(days=days)).strftime("%Y-%m-%d")


def _date_diff_days(start: str, end: str) -> Optional[int]:
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if not start_dt or not end_dt:
        return None
    return (end_dt - start_dt).days


def read_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if isinstance(payload, dict):
                yield payload


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _mid(row: Mapping[str, Any]) -> Optional[float]:
    mid = _as_float(row.get("mid_price") or row.get("mid"))
    if mid is not None and mid >= 0:
        return mid

    bid = _as_float(row.get("bid"))
    ask = _as_float(row.get("ask"))

    if bid is not None and ask is not None and ask >= bid and bid >= 0:
        return (bid + ask) / 2.0

    return None


def _option_symbol(row: Mapping[str, Any]) -> Optional[str]:
    value = row.get("option_symbol")
    if value in (None, ""):
        return None
    return str(value)


def _quote_date(row: Mapping[str, Any]) -> Optional[str]:
    return _as_date(row.get("quote_date") or row.get("date") or row.get("snapshot_date"))


def _load_leg_rows(path: str | Path) -> List[Dict[str, Any]]:
    return list(read_jsonl(path))


def _needed_option_symbols(leg_rows: Iterable[Mapping[str, Any]]) -> set[str]:
    symbols: set[str] = set()

    for row in leg_rows:
        for leg in row.get("selected_legs") or []:
            if isinstance(leg, Mapping):
                symbol = _option_symbol(leg)
                if symbol:
                    symbols.add(symbol)

    return symbols


def _build_quote_index(
    *,
    option_rows_path: str | Path,
    needed_symbols: set[str],
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], Dict[str, Any]]:
    index: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    source_row_count = 0
    indexed_row_count = 0
    rejected_counts: Counter[str] = Counter()

    for row in read_jsonl(option_rows_path):
        source_row_count += 1

        symbol = _option_symbol(row)
        if not symbol:
            rejected_counts["missing_option_symbol"] += 1
            continue

        if symbol not in needed_symbols:
            continue

        date = _quote_date(row)
        if not date:
            rejected_counts["missing_quote_date"] += 1
            continue

        mid = _mid(row)
        if mid is None:
            rejected_counts["missing_mid_price"] += 1
            continue

        index[symbol][date] = dict(row)
        indexed_row_count += 1

    return dict(index), {
        "source_option_row_count": source_row_count,
        "needed_option_symbol_count": len(needed_symbols),
        "indexed_option_quote_count": indexed_row_count,
        "indexed_option_symbol_count": len(index),
        "quote_index_rejected_counts": dict(sorted(rejected_counts.items())),
    }


def _find_exit_quote(
    *,
    quote_index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    option_symbol: str,
    decision_date: str,
    target_exit_date: str,
    expiration: Optional[str],
    max_exit_search_days: int,
) -> Tuple[Optional[Mapping[str, Any]], Optional[str]]:
    quotes_by_date = quote_index.get(option_symbol)
    if not quotes_by_date:
        return None, "missing_quote_history_for_option_symbol"

    decision_dt = _parse_date(decision_date)
    target_dt = _parse_date(target_exit_date)

    if not decision_dt:
        return None, "invalid_decision_date"

    if not target_dt:
        return None, "invalid_target_exit_date"

    expiration_dt = _parse_date(expiration) if expiration else None

    min_allowed_dt = decision_dt + timedelta(days=1)
    latest_allowed_dt = target_dt

    if expiration_dt and latest_allowed_dt >= expiration_dt:
        latest_allowed_dt = expiration_dt - timedelta(days=1)

    if latest_allowed_dt < min_allowed_dt:
        return None, "no_valid_exit_after_entry_before_expiration"

    # Preferred rule:
    # use the nearest available quote on or before target exit,
    # strictly after entry/decision date,
    # and strictly before expiration.
    for offset in range(max_exit_search_days + 1):
        candidate_dt = latest_allowed_dt - timedelta(days=offset)

        if candidate_dt < min_allowed_dt:
            break

        if expiration_dt and candidate_dt >= expiration_dt:
            continue

        candidate_date = candidate_dt.strftime("%Y-%m-%d")
        quote = quotes_by_date.get(candidate_date)

        if quote is not None:
            return quote, None

    # Fallback:
    # small forward search, still strictly after entry and before expiration.
    for offset in range(1, max_exit_search_days + 1):
        candidate_dt = latest_allowed_dt + timedelta(days=offset)

        if candidate_dt < min_allowed_dt:
            continue

        if expiration_dt and candidate_dt >= expiration_dt:
            return None, "missing_exit_quote_after_entry_before_expiration"

        candidate_date = candidate_dt.strftime("%Y-%m-%d")
        quote = quotes_by_date.get(candidate_date)

        if quote is not None:
            return quote, None

    return None, "missing_exit_quote_after_entry_within_search_window"

def _leg_exit_value(leg: Mapping[str, Any], exit_mid: float) -> float:
    quantity = _as_int(leg.get("quantity")) or 1
    action = leg.get("action")

    if action == BUY:
        return exit_mid * quantity

    if action == SELL:
        return -exit_mid * quantity

    raise ValueError(f"Unsupported leg action: {action}")


def _entry_net_debit(row: Mapping[str, Any]) -> Optional[float]:
    value = _as_float(row.get("entry_net_mid_debit"))
    if value is not None:
        return value

    total = 0.0
    for leg in row.get("selected_legs") or []:
        if not isinstance(leg, Mapping):
            return None

        mid = _as_float(leg.get("mid_price"))
        quantity = _as_int(leg.get("quantity")) or 1
        action = leg.get("action")

        if mid is None:
            return None

        if action == BUY:
            total += mid * quantity
        elif action == SELL:
            total -= mid * quantity
        else:
            return None

    return total


def _max_strike_width(legs: List[Mapping[str, Any]]) -> Optional[float]:
    calls = []
    puts = []

    for leg in legs:
        right = leg.get("option_right")
        strike = _as_float(leg.get("strike"))
        if strike is None:
            continue

        if right == "call":
            calls.append((strike, leg))
        elif right == "put":
            puts.append((strike, leg))

    widths: List[float] = []

    if len(calls) >= 2:
        strikes = [strike for strike, _ in calls]
        widths.append(max(strikes) - min(strikes))

    if len(puts) >= 2:
        strikes = [strike for strike, _ in puts]
        widths.append(max(strikes) - min(strikes))

    if not widths:
        return None

    return max(widths)


def _risk_capital(row: Mapping[str, Any], entry_net_debit: float) -> Optional[float]:
    strategy = str(row.get("strategy") or "")
    legs = [leg for leg in row.get("selected_legs") or [] if isinstance(leg, Mapping)]

    if entry_net_debit > 0:
        return entry_net_debit

    credit = abs(entry_net_debit)
    width = _max_strike_width(legs)

    if strategy in {
        "put_credit_spread",
        "call_credit_spread",
        "iron_condor",
        "iron_butterfly",
    } and width is not None:
        risk = width - credit
        if risk > 0:
            return risk

    if credit > 0:
        return credit

    return None


def _complete_outcome_payload(
    *,
    row: Mapping[str, Any],
    exit_legs: List[Mapping[str, Any]],
    target_exit_date: str,
    outcome_date: str,
) -> Dict[str, Any]:
    entry_debit = _entry_net_debit(row)

    if entry_debit is None:
        return {
            "data_state": "partial_entry_price_missing",
            "outcome_state": "partial_entry_price_missing",
        }

    exit_value = sum(_as_float(leg.get("exit_leg_value")) or 0.0 for leg in exit_legs)
    strategy_pnl = exit_value - entry_debit

    risk_capital = _risk_capital(row, entry_debit)
    strategy_adjusted_return = None

    if risk_capital is not None and risk_capital > 0:
        strategy_adjusted_return = strategy_pnl / risk_capital

    if strategy_adjusted_return is None:
        return {
            "data_state": "partial_risk_capital_missing",
            "outcome_state": "partial_risk_capital_missing",
            "target_exit_date": target_exit_date,
            "outcome_date": outcome_date,
            "exit_legs": exit_legs,
            "entry_net_mid_debit": entry_debit,
            "exit_strategy_value": exit_value,
            "strategy_pnl": strategy_pnl,
            "risk_capital": risk_capital,
        }

    return {
        "data_state": "complete",
        "outcome_state": "complete",
        "target_exit_date": target_exit_date,
        "outcome_date": outcome_date,
        "exit_legs": exit_legs,
        "entry_net_mid_debit": entry_debit,
        "exit_strategy_value": exit_value,
        "strategy_pnl": strategy_pnl,
        "risk_capital": risk_capital,
        "strategy_adjusted_return": strategy_adjusted_return,
        "strategy_return": strategy_adjusted_return,
        "outcome_availability_date": outcome_date,
        "outcome_join_granularity": "selected_option_symbol_exit_quote",
    }


def build_historical_strategy_quote_outcome_rows(
    *,
    leg_rows: List[Mapping[str, Any]],
    quote_index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    max_exit_search_days: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    output_rows: List[Dict[str, Any]] = []

    complete_count = 0
    partial_count = 0

    data_state_counts: Counter[str] = Counter()
    outcome_state_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    strategy_complete_counts: Counter[str] = Counter()
    missing_reason_counts: Counter[str] = Counter()
    exit_offset_counts: Counter[str] = Counter()

    for source_row in leg_rows:
        row = dict(source_row)

        strategy = str(row.get("strategy") or "missing")
        strategy_counts[strategy] += 1

        decision_date = _as_date(row.get("date") or row.get("decision_date"))
        holding_period_days = _as_int(row.get("holding_period_days"))

        if not decision_date or holding_period_days is None:
            payload = {
                "data_state": "partial_missing_decision_date_or_holding_period",
                "outcome_state": "partial_missing_decision_date_or_holding_period",
            }
            missing_reason_counts[payload["outcome_state"]] += 1
        else:
            target_exit_date = _date_add(decision_date, holding_period_days)
            exit_legs: List[Dict[str, Any]] = []
            missing_reasons: List[str] = []

            for leg in row.get("selected_legs") or []:
                if not isinstance(leg, Mapping):
                    missing_reasons.append("invalid_selected_leg")
                    continue

                option_symbol = _option_symbol(leg)
                expiration = _as_date(leg.get("expiration"))

                if not option_symbol:
                    missing_reasons.append("selected_leg_missing_option_symbol")
                    continue

                exit_quote, reason = _find_exit_quote(
                    quote_index=quote_index,
                    option_symbol=option_symbol,
                    decision_date=decision_date,
                    target_exit_date=target_exit_date,
                    expiration=expiration,
                    max_exit_search_days=max_exit_search_days,
                )

                if reason or exit_quote is None:
                    missing_reasons.append(reason or "missing_exit_quote")
                    continue

                exit_date = _quote_date(exit_quote)
                exit_mid = _mid(exit_quote)

                if not exit_date or exit_mid is None:
                    missing_reasons.append("exit_quote_missing_date_or_mid")
                    continue

                exit_leg = dict(leg)
                exit_leg.update(
                    {
                        "exit_quote_date": exit_date,
                        "exit_bid": _as_float(exit_quote.get("bid")),
                        "exit_ask": _as_float(exit_quote.get("ask")),
                        "exit_mid_price": exit_mid,
                        "exit_implied_volatility": _as_float(exit_quote.get("implied_volatility")),
                        "exit_delta": _as_float(exit_quote.get("delta")),
                        "exit_dte": _as_int(exit_quote.get("dte")),
                        "exit_leg_value": _leg_exit_value(leg, exit_mid),
                    }
                )
                exit_legs.append(exit_leg)

            if missing_reasons:
                reason = "partial_exit_quote_missing"
                payload = {
                    "data_state": reason,
                    "outcome_state": reason,
                    "target_exit_date": target_exit_date,
                    "outcome_date": None,
                    "outcome_availability_date": None,
                    "exit_legs": exit_legs,
                    "missing_exit_quote_reasons": sorted(set(missing_reasons)),
                }
                for missing_reason in missing_reasons:
                    missing_reason_counts[missing_reason] += 1
            else:
                outcome_dates = sorted({str(leg["exit_quote_date"]) for leg in exit_legs})
                outcome_date = max(outcome_dates)
                payload = _complete_outcome_payload(
                    row=row,
                    exit_legs=exit_legs,
                    target_exit_date=target_exit_date,
                    outcome_date=outcome_date,
                )

                offset = _date_diff_days(target_exit_date, outcome_date)
                if offset is not None:
                    exit_offset_counts[str(offset)] += 1

        row.update(
            {
                "adapter_type": "historical_strategy_quote_outcome_rows_builder",
                "artifact_type": "signalforge_historical_strategy_quote_outcome_row",
                "contract": "historical_strategy_quote_outcome_rows",
                "source_leg_selection_id": row.get("leg_selection_id"),
                "quote_outcome_id": f"{row.get('leg_selection_id')}__quote_outcome",
            }
        )
        row.update(payload)

        data_state_counts[str(row.get("data_state"))] += 1
        outcome_state_counts[str(row.get("outcome_state"))] += 1

        if row.get("data_state") == "complete":
            complete_count += 1
            strategy_complete_counts[strategy] += 1
        else:
            partial_count += 1

        output_rows.append(row)

    blockers: List[str] = []
    if not output_rows:
        blockers.append("no_quote_outcome_rows_written")
    if complete_count == 0:
        blockers.append("no_complete_quote_outcome_rows")

    summary: Dict[str, Any] = {
        "adapter_type": "historical_strategy_quote_outcome_rows_builder",
        "artifact_type": "signalforge_historical_strategy_quote_outcome_rows",
        "contract": "historical_strategy_quote_outcome_rows",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_leg_row_count": len(leg_rows),
        "output_row_count": len(output_rows),
        "complete_outcome_row_count": complete_count,
        "partial_outcome_row_count": partial_count,
        "completion_rate": complete_count / len(output_rows) if output_rows else 0.0,
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "outcome_state_counts": dict(sorted(outcome_state_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "strategy_complete_counts": dict(sorted(strategy_complete_counts.items())),
        "missing_reason_counts": dict(sorted(missing_reason_counts.items())),
        "exit_offset_day_counts": dict(sorted(exit_offset_counts.items())),
        "parameters": {
            "max_exit_search_days": max_exit_search_days,
        },
        "paths": {},
    }

    return output_rows, summary


def build_historical_strategy_quote_outcome_rows_artifact(
    *,
    leg_selection_rows_path: str | Path,
    option_rows_path: str | Path,
    output_dir: str | Path,
    max_exit_search_days: int = 5,
) -> Dict[str, Any]:
    output_path = Path(output_dir)

    rows_path = output_path / "signalforge_historical_strategy_quote_outcome_rows.jsonl"
    summary_path = output_path / "signalforge_historical_strategy_quote_outcome_rows_summary.json"

    leg_rows = _load_leg_rows(leg_selection_rows_path)
    needed_symbols = _needed_option_symbols(leg_rows)

    quote_index, quote_index_stats = _build_quote_index(
        option_rows_path=option_rows_path,
        needed_symbols=needed_symbols,
    )

    rows, summary = build_historical_strategy_quote_outcome_rows(
        leg_rows=leg_rows,
        quote_index=quote_index,
        max_exit_search_days=max_exit_search_days,
    )

    summary.update(quote_index_stats)
    summary["paths"] = {
        "leg_selection_rows_path": str(leg_selection_rows_path),
        "option_rows_path": str(option_rows_path),
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }

    write_jsonl(rows_path, rows)
    write_json(summary_path, summary)

    return summary
