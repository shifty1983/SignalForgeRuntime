from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class LegNeed:
    trade_id: str
    leg_index: int
    contract_symbol: str
    entry_date: str
    exit_date: str
    entry_mid: float
    signed_quantity: int
    multiplier: float
    selected_symbol: str | None
    selected_strategy: str | None
    leg_role: str | None
    side: str | None
    option_symbol: str | None
    expiration: str | None
    strike: float | None
    right: str | None


def _jsonl_lines(path: Path) -> Iterable[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith(".jsonl") or n.endswith(".json")]
            if not names:
                raise ValueError(f"No .jsonl/.json file found in zip: {path}")
            with zf.open(names[0]) as handle:
                for raw in handle:
                    yield raw.decode("utf-8-sig", errors="ignore")
    else:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
            yield from handle


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line_number, line in enumerate(_jsonl_lines(path), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
        if isinstance(payload, dict):
            yield payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:10]


def _float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int | None = None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else default


def _contract(value: Any) -> str:
    return str(value or "").strip()


def _quote_mid(row: dict[str, Any]) -> float | None:
    mid = _float(row.get("mid_price"), None)
    if mid is None:
        mid = _float(row.get("mid"), None)
    if mid is None:
        bid = _float(row.get("bid"), None)
        ask = _float(row.get("ask"), None)
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
    return mid


def _load_needs(
    manifest_path: Path,
    replay_start: str | None,
    replay_end: str | None,
) -> tuple[list[LegNeed], dict[str, list[LegNeed]], dict[str, list[LegNeed]]]:
    needs: list[LegNeed] = []
    by_contract: dict[str, list[LegNeed]] = defaultdict(list)
    by_trade: dict[str, list[LegNeed]] = defaultdict(list)

    for row in _read_jsonl(manifest_path):
        entry_date = _date(row.get("entry_date") or row.get("selected_entry_date"))
        exit_date = _date(row.get("exit_date") or row.get("selected_exit_date") or row.get("outcome_date"))
        if not entry_date or not exit_date:
            continue

        if replay_start and exit_date < replay_start:
            continue
        if replay_end and entry_date > replay_end:
            continue
        if replay_start and entry_date < replay_start:
            entry_date = replay_start
        if replay_end and exit_date > replay_end:
            exit_date = replay_end

        contract = _contract(row.get("contract_symbol") or row.get("option_symbol") or row.get("canonical_contract_symbol"))
        if not contract:
            continue

        trade_id = str(row.get("trade_id") or row.get("sequence_id") or "")
        if not trade_id:
            continue

        need = LegNeed(
            trade_id=trade_id,
            leg_index=_int(row.get("leg_index"), 0) or 0,
            contract_symbol=contract,
            entry_date=entry_date,
            exit_date=exit_date,
            entry_mid=_float(row.get("entry_mid"), 0.0) or 0.0,
            signed_quantity=_int(row.get("signed_quantity"), 1) or 1,
            multiplier=_float(row.get("multiplier"), 100.0) or 100.0,
            selected_symbol=row.get("selected_symbol") or row.get("symbol") or row.get("underlying_symbol"),
            selected_strategy=row.get("selected_strategy") or row.get("strategy_name"),
            leg_role=row.get("leg_role"),
            side=row.get("side"),
            option_symbol=row.get("option_symbol"),
            expiration=_date(row.get("expiration")),
            strike=_float(row.get("strike"), None),
            right=row.get("right"),
        )
        needs.append(need)
        by_contract[need.contract_symbol].append(need)
        by_trade[need.trade_id].append(need)

    return needs, by_contract, by_trade


def _usable_quote_record(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    bid = _float(row.get("bid"), None)
    ask = _float(row.get("ask"), None)
    mid = _quote_mid(row)

    if bid is None or ask is None or mid is None:
        return None
    if bid > ask:
        return None

    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": _float(row.get("spread_pct"), None) or _float(row.get("spread_pct_mid"), None),
        "delta": _float(row.get("delta"), None),
        "gamma": _float(row.get("gamma"), None),
        "theta": _float(row.get("theta"), None),
        "vega": _float(row.get("vega"), None),
        "implied_volatility": _float(row.get("implied_volatility"), None),
        "open_interest": _float(row.get("open_interest"), None),
        "volume": _float(row.get("volume"), None),
        "underlying_price": _float(row.get("underlying_price"), None),
        "source": source,
    }


def build_daily_quote_path(
    *,
    trade_leg_manifest_path: Path,
    raw_option_quotes_path: Path,
    gap_fills_path: Path | None,
    output_dir: Path,
    replay_start: str | None,
    replay_end: str | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    needs, by_contract, by_trade = _load_needs(trade_leg_manifest_path, replay_start, replay_end)
    required_contracts = set(by_contract)

    quote_by_contract_date: dict[tuple[str, str], dict[str, Any]] = {}
    observed_quote_dates: set[str] = set()

    raw_option_quote_row_count_scanned = 0
    raw_rows_for_required_contracts = 0
    usable_rows_for_required_contracts = 0
    raw_quote_status_counts: Counter[str] = Counter()

    for quote in _read_jsonl(raw_option_quotes_path):
        raw_option_quote_row_count_scanned += 1

        contract = _contract(
            quote.get("option_symbol")
            or quote.get("contract_symbol")
            or quote.get("canonical_contract_symbol")
        )
        if contract not in required_contracts:
            continue

        quote_date = _date(quote.get("quote_date") or quote.get("date"))
        if not quote_date:
            raw_quote_status_counts["missing_quote_date"] += 1
            continue

        observed_quote_dates.add(quote_date)
        raw_rows_for_required_contracts += 1

        usable = _usable_quote_record(quote, source="raw_option_quote")
        if usable is None:
            raw_quote_status_counts["unusable"] += 1
            continue

        quote_by_contract_date[(contract, quote_date)] = {
            "contract_symbol": contract,
            "option_symbol": contract,
            "quote_date": quote_date,
            **usable,
        }
        usable_rows_for_required_contracts += 1
        raw_quote_status_counts["usable"] += 1

    gap_fill_rows_scanned = 0
    gap_fill_rows_for_required_contracts = 0
    usable_gap_fill_rows_for_required_contracts = 0
    duplicate_gap_fill_quote_keys_ignored = 0
    gap_fill_status_counts: Counter[str] = Counter()

    if gap_fills_path is not None:
        for quote in _read_jsonl(gap_fills_path):
            gap_fill_rows_scanned += 1

            contract = _contract(
                quote.get("contract_symbol")
                or quote.get("option_symbol")
                or quote.get("canonical_contract_symbol")
            )
            if contract not in required_contracts:
                continue

            quote_date = _date(quote.get("quote_date") or quote.get("date"))
            if not quote_date:
                gap_fill_status_counts["missing_quote_date"] += 1
                continue

            observed_quote_dates.add(quote_date)
            gap_fill_rows_for_required_contracts += 1

            quote_status = str(quote.get("quote_status") or quote.get("status") or "").strip() or "unknown"
            gap_fill_status_counts[quote_status] += 1

            usable = _usable_quote_record(quote, source="quantconnect_gap_fill")
            if usable is None:
                continue

            key = (contract, quote_date)
            if key in quote_by_contract_date:
                duplicate_gap_fill_quote_keys_ignored += 1
                continue

            quote_by_contract_date[key] = {
                "contract_symbol": contract,
                "option_symbol": contract,
                "quote_date": quote_date,
                **usable,
            }
            usable_gap_fill_rows_for_required_contracts += 1

    rows_path = output_dir / "baseline_exit_overlay_daily_quote_path_rows.jsonl"
    residual_path = output_dir / "baseline_exit_overlay_daily_quote_path_residual_rows.jsonl"
    trade_summary_path = output_dir / "baseline_exit_overlay_daily_quote_path_trade_summaries.jsonl"
    summary_path = output_dir / "baseline_exit_overlay_daily_quote_path_summary.json"

    path_row_count = 0
    complete_path_row_count = 0
    partial_path_row_count = 0
    no_quote_path_row_count = 0
    complete_trade_count = 0
    partial_trade_count = 0
    no_path_trade_count = 0
    total_expected_leg_quote_dates = 0
    total_covered_leg_quote_dates = 0
    path_state_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    quote_source_leg_counts: Counter[str] = Counter()

    sorted_observed_dates = sorted(observed_quote_dates)

    with (
        rows_path.open("w", encoding="utf-8", newline="\n") as rows_handle,
        residual_path.open("w", encoding="utf-8", newline="\n") as residual_handle,
        trade_summary_path.open("w", encoding="utf-8", newline="\n") as trade_handle,
    ):
        for trade_id, legs in sorted(by_trade.items()):
            min_entry = min(l.entry_date for l in legs)
            max_exit = max(l.exit_date for l in legs)
            strategy_counts[str(legs[0].selected_strategy or "unknown")] += 1

            trade_path_rows = 0
            trade_complete_rows = 0
            trade_partial_rows = 0
            trade_no_quote_rows = 0

            expected_quote_dates = [d for d in sorted_observed_dates if min_entry <= d <= max_exit]
            if min_entry not in observed_quote_dates:
                raw_quote_status_counts["entry_date_not_in_observed_quote_calendar"] += 1
            if max_exit not in observed_quote_dates:
                raw_quote_status_counts["exit_date_not_in_observed_quote_calendar"] += 1

            for quote_date in expected_quote_dates:
                leg_quotes = []
                missing_leg_indices = []
                total_expected_leg_quote_dates += len(legs)

                mark_value = 0.0
                pnl_value = 0.0
                denom = 0.0

                for leg in legs:
                    quote = quote_by_contract_date.get((leg.contract_symbol, quote_date))
                    denom += abs(leg.signed_quantity) * leg.entry_mid * leg.multiplier

                    if quote is None:
                        missing_leg_indices.append(leg.leg_index)
                        continue

                    total_covered_leg_quote_dates += 1
                    quote_source_leg_counts[str(quote["source"])] += 1

                    mark_component = leg.signed_quantity * quote["mid"] * leg.multiplier
                    pnl_component = leg.signed_quantity * (quote["mid"] - leg.entry_mid) * leg.multiplier
                    mark_value += mark_component
                    pnl_value += pnl_component

                    leg_quotes.append({
                        "leg_index": leg.leg_index,
                        "contract_symbol": leg.contract_symbol,
                        "option_symbol": leg.option_symbol or leg.contract_symbol,
                        "leg_role": leg.leg_role,
                        "side": leg.side,
                        "signed_quantity": leg.signed_quantity,
                        "multiplier": leg.multiplier,
                        "entry_mid": leg.entry_mid,
                        "quote_bid": quote["bid"],
                        "quote_ask": quote["ask"],
                        "quote_mid": quote["mid"],
                        "quote_spread_pct": quote["spread_pct"],
                        "mark_component": mark_component,
                        "pnl_component": pnl_component,
                        "delta": quote["delta"],
                        "gamma": quote["gamma"],
                        "theta": quote["theta"],
                        "vega": quote["vega"],
                        "implied_volatility": quote["implied_volatility"],
                        "open_interest": quote["open_interest"],
                        "volume": quote["volume"],
                        "underlying_price": quote["underlying_price"],
                        "source": quote["source"],
                    })

                if len(leg_quotes) == len(legs):
                    state = "complete"
                    trade_complete_rows += 1
                    complete_path_row_count += 1
                elif len(leg_quotes) == 0:
                    state = "no_quote"
                    trade_no_quote_rows += 1
                    no_quote_path_row_count += 1
                else:
                    state = "partial"
                    trade_partial_rows += 1
                    partial_path_row_count += 1

                path_state_counts[state] += 1
                trade_path_rows += 1
                path_row_count += 1

                row = {
                    "adapter_type": "baseline_exit_overlay_daily_quote_path_builder",
                    "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_path_row",
                    "contract": "baseline_exit_overlay_daily_quote_path",
                    "trade_id": trade_id,
                    "quote_date": quote_date,
                    "entry_date": min_entry,
                    "exit_date": max_exit,
                    "selected_symbol": legs[0].selected_symbol,
                    "selected_strategy": legs[0].selected_strategy,
                    "leg_count": len(legs),
                    "available_leg_quote_count": len(leg_quotes),
                    "missing_leg_indices": missing_leg_indices,
                    "path_state": state,
                    "mark_value": mark_value if leg_quotes else None,
                    "pnl_value": pnl_value if leg_quotes else None,
                    "return_on_abs_entry_premium": (pnl_value / denom) if denom else None,
                    "return_denominator": denom,
                    "leg_quotes": leg_quotes,
                    "does_select_strategy": False,
                    "does_apply_exit_rule": False,
                    "does_feed_exit_result_to_expectancy": False,
                    "does_forward_fill": False,
                    "does_invent_prices": False,
                    "uses_observed_quote_calendar": True,
                    "excluded_calendar_non_quote_dates": True,
                }
                handle = rows_handle if state == "complete" else residual_handle
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

            if trade_complete_rows > 0 and trade_partial_rows == 0 and trade_no_quote_rows == 0:
                trade_state = "complete"
                complete_trade_count += 1
            elif trade_complete_rows > 0 or trade_partial_rows > 0:
                trade_state = "partial"
                partial_trade_count += 1
            else:
                trade_state = "no_path"
                no_path_trade_count += 1

            trade_handle.write(json.dumps({
                "trade_id": trade_id,
                "selected_symbol": legs[0].selected_symbol,
                "selected_strategy": legs[0].selected_strategy,
                "entry_date": min_entry,
                "exit_date": max_exit,
                "leg_count": len(legs),
                "path_row_count": trade_path_rows,
                "complete_path_row_count": trade_complete_rows,
                "partial_path_row_count": trade_partial_rows,
                "no_quote_path_row_count": trade_no_quote_rows,
                "path_state": trade_state,
            }, sort_keys=True, separators=(",", ":")) + "\n")

    summary = {
        "adapter_type": "baseline_exit_overlay_daily_quote_path_builder",
        "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_path",
        "contract": "baseline_exit_overlay_daily_quote_path",
        "is_ready": True,
        "readiness_state": "daily_quote_paths_built",
        "blocker_count": 0,
        "blockers": [],
        "trade_count": len(by_trade),
        "trade_leg_manifest_row_count": len(needs),
        "unique_required_contract_count": len(required_contracts),
        "raw_option_quote_row_count_scanned": raw_option_quote_row_count_scanned,
        "raw_rows_for_required_contracts": raw_rows_for_required_contracts,
        "usable_rows_for_required_contracts": usable_rows_for_required_contracts,
        "gap_fills_provided": gap_fills_path is not None,
        "gap_fill_rows_scanned": gap_fill_rows_scanned,
        "gap_fill_rows_for_required_contracts": gap_fill_rows_for_required_contracts,
        "usable_gap_fill_rows_for_required_contracts": usable_gap_fill_rows_for_required_contracts,
        "duplicate_gap_fill_quote_keys_ignored": duplicate_gap_fill_quote_keys_ignored,
        "final_quote_key_count": len(quote_by_contract_date),
        "observed_quote_date_count": len(observed_quote_dates),
        "min_observed_quote_date": min(observed_quote_dates) if observed_quote_dates else None,
        "max_observed_quote_date": max(observed_quote_dates) if observed_quote_dates else None,
        "raw_quote_status_counts": dict(sorted(raw_quote_status_counts.items())),
        "gap_fill_status_counts": dict(sorted(gap_fill_status_counts.items())),
        "quote_source_leg_counts": dict(sorted(quote_source_leg_counts.items())),
        "path_row_count": path_row_count,
        "complete_path_row_count": complete_path_row_count,
        "partial_or_unusable_path_row_count": partial_path_row_count,
        "no_quote_path_row_count": no_quote_path_row_count,
        "complete_trade_count": complete_trade_count,
        "partial_trade_count": partial_trade_count,
        "no_path_trade_count": no_path_trade_count,
        "complete_path_row_coverage_rate": complete_path_row_count / path_row_count if path_row_count else None,
        "leg_quote_date_coverage_rate": total_covered_leg_quote_dates / total_expected_leg_quote_dates if total_expected_leg_quote_dates else None,
        "path_state_counts": dict(sorted(path_state_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "does_select_strategy": False,
        "does_apply_exit_rule": False,
        "does_feed_exit_result_to_expectancy": False,
        "does_forward_fill": False,
        "does_invent_prices": False,
        "uses_observed_quote_calendar": True,
        "excluded_calendar_non_quote_dates": True,
        "gap_fill_merge_policy": "raw_option_quote_wins_when_duplicate_contract_date_exists",
        "mark_formula": "sum(signed_quantity * quote_mid * multiplier)",
        "pnl_formula": "sum(signed_quantity * (quote_mid - entry_mid) * multiplier)",
        "return_denominator": "sum(abs(signed_quantity) * entry_mid * multiplier)",
        "paths": {
            "rows_path": str(rows_path),
            "residual_rows_path": str(residual_path),
            "trade_summary_rows_path": str(trade_summary_path),
            "summary_path": str(summary_path),
        },
    }

    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build daily quote paths for already-selected baseline trades only.")
    parser.add_argument("--trade-leg-manifest", required=True)
    parser.add_argument("--raw-option-quotes", required=True)
    parser.add_argument("--gap-fills", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--replay-start", default=None)
    parser.add_argument("--replay-end", default=None)
    args = parser.parse_args()

    summary = build_daily_quote_path(
        trade_leg_manifest_path=Path(args.trade_leg_manifest),
        raw_option_quotes_path=Path(args.raw_option_quotes),
        gap_fills_path=Path(args.gap_fills) if args.gap_fills else None,
        output_dir=Path(args.output_dir),
        replay_start=args.replay_start,
        replay_end=args.replay_end,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
