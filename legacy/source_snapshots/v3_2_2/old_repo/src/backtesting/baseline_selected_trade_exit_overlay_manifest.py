from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} in {path}: {exc}") from exc
            if isinstance(row, dict):
                yield row


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    return count


def _first(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    return text[:10]

def _derive_exit_date(trade: dict[str, Any], exit_legs: list[Any]) -> str | None:
    top_level_date = _date(
        _first(
            trade,
            [
                "selected_exit_date",
                "exit_date",
                "outcome_date",
                "final_outcome_date",
                "selected_outcome_date",
                "selected_final_outcome_date",
                "contract_outcome_date",
                "portfolio_realization_date",
                "outcome_availability_date",
                "close_date",
            ],
        )
    )
    if top_level_date:
        return top_level_date

    leg_dates: list[str] = []
    for leg_any in exit_legs:
        if not isinstance(leg_any, dict):
            continue

        leg_date = _date(
            _first(
                leg_any,
                [
                    "exit_quote_date",
                    "quote_date",
                    "exit_date",
                    "outcome_date",
                    "final_outcome_date",
                ],
            )
        )
        if leg_date:
            leg_dates.append(leg_date)

    if not leg_dates:
        return None

    # Multi-leg spreads should normally have one common exit quote date.
    # If there is a mismatch, use the latest date to avoid truncating the path.
    return max(leg_dates)


def _signed_quantity(leg: dict[str, Any]) -> int:
    signed = _to_int(_first(leg, ["signed_quantity", "signed_contract_quantity", "net_quantity"]))
    if signed is not None:
        return signed

    quantity = _to_int(_first(leg, ["quantity", "contract_quantity", "contracts", "leg_quantity"], 1))
    if quantity is None:
        quantity = 1

    side = str(_first(leg, ["side", "action", "position_side", "leg_side"], "")).lower()
    role = str(_first(leg, ["leg_role", "role"], "")).lower()

    if side in {"sell", "sold", "short", "write", "written"}:
        return -abs(quantity)
    if "short" in role or role.startswith("sell"):
        return -abs(quantity)

    return abs(quantity)


def _entry_prices(leg: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    bid = _to_float(_first(leg, ["entry_bid", "selected_entry_bid", "bid", "option_bid", "quote_bid", "bid_price"]))
    ask = _to_float(_first(leg, ["entry_ask", "selected_entry_ask", "ask", "option_ask", "quote_ask", "ask_price"]))
    mid = _to_float(_first(leg, ["entry_mid", "selected_entry_mid", "mid", "option_mid", "quote_mid", "mid_price", "mark"]))

    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0

    return bid, ask, mid


def build_manifest(
    *,
    selected_trade_rows_path: Path,
    output_dir: Path,
    source_label: str,
    sized_only: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "baseline_selected_trade_exit_overlay_manifest.jsonl"
    summary_path = output_dir / "baseline_selected_trade_exit_overlay_manifest_summary.json"

    input_row_count = 0
    accepted_trade_count = 0
    skipped_not_sized_count = 0
    rows_missing_entry_legs = 0
    rows_with_entry_legs = 0
    rows_with_exit_legs = 0
    rows_missing_exit_legs = 0
    missing_option_symbol_count = 0
    missing_entry_mid_count = 0
    missing_entry_bid_ask_count = 0

    strategy_counts: Counter[str] = Counter()
    leg_count_by_trade: Counter[int] = Counter()
    unique_trade_ids: set[str] = set()
    unique_contracts: set[str] = set()
    entry_dates: list[str] = []
    exit_dates: list[str] = []

    manifest_rows: list[dict[str, Any]] = []

    for source_row_index, trade in enumerate(_read_jsonl(selected_trade_rows_path), start=1):
        input_row_count += 1

        sizing_state = trade.get("sizing_state")
        if sized_only and sizing_state != "sized":
            skipped_not_sized_count += 1
            continue

        entry_legs = _as_list(trade.get("selected_entry_legs"))
        exit_legs = _as_list(trade.get("selected_exit_legs"))

        if not entry_legs:
            rows_missing_entry_legs += 1
            continue

        rows_with_entry_legs += 1
        if exit_legs:
            rows_with_exit_legs += 1
        else:
            rows_missing_exit_legs += 1

        accepted_trade_count += 1

        trade_id = str(
            _first(
                trade,
                [
                    "sequence_id",
                    "selected_trade_id",
                    "portfolio_trade_id",
                    "portfolio_candidate_id",
                    "strategy_candidate_id",
                    "trade_id",
                ],
                f"locked_trade_{accepted_trade_count:08d}",
            )
        )

        unique_trade_ids.add(trade_id)

        selected_strategy = str(
            _first(
                trade,
                ["selected_strategy", "strategy_name", "strategy", "strategy_family"],
                "unknown",
            )
        )
        strategy_counts[selected_strategy] += 1
        leg_count_by_trade[len(entry_legs)] += 1

        selected_symbol = _first(
            trade,
            ["selected_symbol", "underlying_symbol", "symbol", "ticker"],
        )

        entry_date = _date(_first(trade, ["selected_entry_date", "entry_date", "decision_date", "asof_date"]))
        exit_date = _derive_exit_date(trade, exit_legs)

        if entry_date:
            entry_dates.append(entry_date)
        if exit_date:
            exit_dates.append(exit_date)

        for leg_index, leg_any in enumerate(entry_legs):
            if not isinstance(leg_any, dict):
                continue

            leg = leg_any
            bid, ask, mid = _entry_prices(leg)

            contract_symbol = _first(
                leg,
                [
                    "contract_symbol",
                    "option_symbol",
                    "canonical_contract_symbol",
                    "mapped_contract_symbol",
                    "symbol",
                ],
            )

            if not contract_symbol:
                missing_option_symbol_count += 1
            else:
                unique_contracts.add(str(contract_symbol))

            if mid is None:
                missing_entry_mid_count += 1

            if bid is None or ask is None:
                missing_entry_bid_ask_count += 1

            manifest_rows.append(
                {
                    "adapter_type": "baseline_selected_trade_exit_overlay_manifest_builder",
                    "artifact_type": "signalforge_baseline_selected_trade_exit_overlay_manifest",
                    "contract": "baseline_selected_trade_exit_overlay_manifest",

                    "source_label": source_label,
                    "source_path": str(selected_trade_rows_path),
                    "source_row_index": source_row_index,

                    "trade_id": trade_id,
                    "sequence_id": trade.get("sequence_id"),
                    "portfolio_candidate_id": trade.get("portfolio_candidate_id"),
                    "strategy_candidate_id": trade.get("strategy_candidate_id"),

                    "selected_symbol": selected_symbol,
                    "underlying_symbol": _first(trade, ["underlying_symbol", "selected_symbol", "symbol", "ticker"]),
                    "symbol": _first(trade, ["symbol", "selected_symbol", "underlying_symbol", "ticker"]),
                    "selected_strategy": selected_strategy,
                    "strategy_name": selected_strategy,

                    "entry_date": entry_date,
                    "selected_entry_date": entry_date,
                    "exit_date": exit_date,
                    "selected_exit_date": exit_date,
                    "outcome_date": _date(_first(trade, ["outcome_date", "selected_exit_date", "exit_date", "final_outcome_date", "portfolio_realization_date", "outcome_availability_date"])) or exit_date,

                    "sizing_state": sizing_state,
                    "position_size": trade.get("position_size"),
                    "trade_risk": trade.get("trade_risk"),
                    "risk_budget": trade.get("risk_budget"),
                    "starting_capital": trade.get("starting_capital"),

                    "leg_index": leg_index,
                    "leg_count": len(entry_legs),
                    "leg_role": _first(leg, ["leg_role", "role", "strategy_leg", "name"]),
                    "side": _first(leg, ["side", "action", "position_side", "leg_side"]),
                    "signed_quantity": _signed_quantity(leg),
                    "quantity": abs(_signed_quantity(leg)),

                    "option_symbol": _first(leg, ["option_symbol", "contract_symbol", "canonical_contract_symbol", "mapped_contract_symbol", "symbol"]),
                    "contract_symbol": contract_symbol,
                    "canonical_contract_symbol": _first(leg, ["canonical_contract_symbol", "contract_symbol", "option_symbol", "mapped_contract_symbol", "symbol"]),

                    "expiration": _date(_first(leg, ["expiration", "expiry", "expiration_date", "expiry_date"])),
                    "strike": _to_float(_first(leg, ["strike", "strike_price"])),
                    "right": _first(leg, ["right", "option_right", "option_type", "put_call"]),
                    "multiplier": _to_float(_first(leg, ["multiplier", "contract_multiplier"], 100)),

                    "entry_bid": bid,
                    "entry_ask": ask,
                    "entry_mid": mid,

                    "does_select_strategy": False,
                    "does_apply_exit_rule": False,
                    "does_feed_exit_result_to_expectancy": False,
                    "expectancy_source": "baseline_preselected_trade_only",
                }
            )

    manifest_leg_row_count = _write_jsonl(rows_path, manifest_rows)

    is_ready = (
        accepted_trade_count > 0
        and manifest_leg_row_count > 0
        and missing_option_symbol_count == 0
        and missing_entry_mid_count == 0
    )

    summary = {
        "adapter_type": "baseline_selected_trade_exit_overlay_manifest_builder",
        "artifact_type": "signalforge_baseline_selected_trade_exit_overlay_manifest",
        "contract": "baseline_selected_trade_exit_overlay_manifest",
        "source_label": source_label,
        "source_path": str(selected_trade_rows_path),
        "is_ready": is_ready,
        "readiness_state": "ready_for_daily_quote_path" if is_ready else "blocked_manifest_incomplete",
        "blocker_count": 0 if is_ready else 1,
        "blockers": [] if is_ready else ["manifest_missing_required_contract_or_entry_mid_data"],

        "input_row_count": input_row_count,
        "accepted_trade_count": accepted_trade_count,
        "skipped_not_sized_count": skipped_not_sized_count,
        "rows_with_entry_legs": rows_with_entry_legs,
        "rows_missing_entry_legs": rows_missing_entry_legs,
        "rows_with_exit_legs": rows_with_exit_legs,
        "rows_missing_exit_legs": rows_missing_exit_legs,
        "manifest_leg_row_count": manifest_leg_row_count,
        "unique_trade_count": len(unique_trade_ids),
        "unique_contract_count": len(unique_contracts),

        "missing_option_symbol_count": missing_option_symbol_count,
        "missing_entry_mid_count": missing_entry_mid_count,
        "missing_entry_bid_ask_count": missing_entry_bid_ask_count,

        "min_entry_date": min(entry_dates) if entry_dates else None,
        "max_entry_date": max(entry_dates) if entry_dates else None,
        "min_exit_date": min(exit_dates) if exit_dates else None,
        "max_exit_date": max(exit_dates) if exit_dates else None,

        "strategy_counts": dict(sorted(strategy_counts.items())),
        "leg_count_by_trade": {str(k): v for k, v in sorted(leg_count_by_trade.items())},

        "does_select_strategy": False,
        "does_apply_exit_rule": False,
        "does_feed_exit_result_to_expectancy": False,
        "expectancy_source": "baseline_preselected_trade_only",

        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-trade-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-label", default="baseline_selected_trade_source")
    parser.add_argument("--sized-only", action="store_true")
    args = parser.parse_args()

    summary = build_manifest(
        selected_trade_rows_path=Path(args.selected_trade_rows),
        output_dir=Path(args.output_dir),
        source_label=args.source_label,
        sized_only=bool(args.sized_only),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

