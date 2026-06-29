from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:10]


def _contract(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def build_gap_request(
    *,
    trade_leg_manifest_path: Path,
    daily_quote_path_residual_rows_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "baseline_exit_overlay_daily_quote_gap_requests.jsonl"
    summary_path = output_dir / "baseline_exit_overlay_daily_quote_gap_request_summary.json"

    # Map the locked selected-trade leg identity to the exact option contract.
    leg_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    manifest_leg_count = 0
    manifest_missing_contract_count = 0
    for row in _read_jsonl(trade_leg_manifest_path):
        manifest_leg_count += 1
        trade_id = str(row.get("trade_id") or row.get("sequence_id") or "")
        leg_index = _as_int(row.get("leg_index"), 0)
        contract_symbol = _contract(row.get("contract_symbol") or row.get("option_symbol") or row.get("canonical_contract_symbol"))

        if not trade_id or leg_index is None:
            continue
        if not contract_symbol:
            manifest_missing_contract_count += 1
            continue

        leg_lookup[(trade_id, leg_index)] = {
            "trade_id": trade_id,
            "leg_index": leg_index,
            "contract_symbol": contract_symbol,
            "option_symbol": row.get("option_symbol") or contract_symbol,
            "canonical_contract_symbol": row.get("canonical_contract_symbol") or contract_symbol,
            "selected_symbol": row.get("selected_symbol") or row.get("symbol") or row.get("underlying_symbol"),
            "selected_strategy": row.get("selected_strategy") or row.get("strategy_name"),
            "expiration": _date(row.get("expiration")),
            "strike": row.get("strike"),
            "right": row.get("right"),
            "entry_date": _date(row.get("entry_date") or row.get("selected_entry_date")),
            "exit_date": _date(row.get("exit_date") or row.get("selected_exit_date") or row.get("outcome_date")),
        }

    gap_map: dict[tuple[str, str], dict[str, Any]] = {}
    residual_row_count = 0
    partial_residual_row_count = 0
    no_quote_residual_row_count = 0
    missing_leg_ref_count = 0
    unresolved_missing_leg_ref_count = 0
    residual_state_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()

    for row in _read_jsonl(daily_quote_path_residual_rows_path):
        residual_row_count += 1
        trade_id = str(row.get("trade_id") or "")
        quote_date = _date(row.get("quote_date"))
        path_state = str(row.get("path_state") or "unknown")
        residual_state_counts[path_state] += 1

        if path_state == "partial":
            partial_residual_row_count += 1
        elif path_state == "no_quote":
            no_quote_residual_row_count += 1

        missing_indices = row.get("missing_leg_indices") or []
        if not isinstance(missing_indices, list):
            missing_indices = []

        for leg_index_value in missing_indices:
            leg_index = _as_int(leg_index_value)
            if not trade_id or quote_date is None or leg_index is None:
                unresolved_missing_leg_ref_count += 1
                continue

            missing_leg_ref_count += 1
            leg = leg_lookup.get((trade_id, leg_index))
            if leg is None:
                unresolved_missing_leg_ref_count += 1
                continue

            contract_symbol = leg["contract_symbol"]
            key = (contract_symbol, quote_date)
            if key not in gap_map:
                gap_map[key] = {
                    "adapter_type": "baseline_exit_overlay_daily_quote_gap_request_builder",
                    "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_request_row",
                    "contract": "baseline_exit_overlay_daily_quote_gap_request",
                    "contract_symbol": contract_symbol,
                    "option_symbol": leg.get("option_symbol") or contract_symbol,
                    "canonical_contract_symbol": leg.get("canonical_contract_symbol") or contract_symbol,
                    "quote_date": quote_date,
                    "selected_symbol": leg.get("selected_symbol"),
                    "selected_strategy_examples": [],
                    "expiration": leg.get("expiration"),
                    "strike": leg.get("strike"),
                    "right": leg.get("right"),
                    "trade_ref_count": 0,
                    "trade_refs": [],
                    "quote_resolution": "daily",
                    "does_select_strategy": False,
                    "does_apply_exit_rule": False,
                    "does_feed_exit_result_to_expectancy": False,
                    "does_forward_fill": False,
                    "does_invent_prices": False,
                    "expected_quantconnect_output_grain": "one row per contract_symbol and quote_date",
                }

            rec = gap_map[key]
            selected_strategy = leg.get("selected_strategy")
            selected_symbol = leg.get("selected_symbol")
            if selected_strategy:
                strategy_counts[str(selected_strategy)] += 1
                if selected_strategy not in rec["selected_strategy_examples"] and len(rec["selected_strategy_examples"]) < 5:
                    rec["selected_strategy_examples"].append(selected_strategy)
            if selected_symbol:
                symbol_counts[str(selected_symbol)] += 1

            rec["trade_ref_count"] += 1
            if len(rec["trade_refs"]) < 10:
                rec["trade_refs"].append(
                    {
                        "trade_id": trade_id,
                        "leg_index": leg_index,
                        "path_state": path_state,
                    }
                )

    sorted_rows = [gap_map[k] for k in sorted(gap_map.keys(), key=lambda item: (item[1], item[0]))]

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted_rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    unique_gap_contracts = {row["contract_symbol"] for row in sorted_rows}
    quote_dates = [row["quote_date"] for row in sorted_rows]

    summary = {
        "adapter_type": "baseline_exit_overlay_daily_quote_gap_request_builder",
        "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_request",
        "contract": "baseline_exit_overlay_daily_quote_gap_request",
        "is_ready": len(sorted_rows) > 0 and unresolved_missing_leg_ref_count == 0,
        "readiness_state": "ready_for_quantconnect_gap_export" if len(sorted_rows) > 0 and unresolved_missing_leg_ref_count == 0 else "blocked_gap_request_incomplete",
        "blocker_count": 0 if len(sorted_rows) > 0 and unresolved_missing_leg_ref_count == 0 else 1,
        "blockers": [] if len(sorted_rows) > 0 and unresolved_missing_leg_ref_count == 0 else ["unresolved_missing_leg_references_or_no_gap_rows"],
        "manifest_leg_count": manifest_leg_count,
        "manifest_leg_lookup_count": len(leg_lookup),
        "manifest_missing_contract_count": manifest_missing_contract_count,
        "residual_row_count": residual_row_count,
        "partial_residual_row_count": partial_residual_row_count,
        "no_quote_residual_row_count": no_quote_residual_row_count,
        "residual_state_counts": dict(sorted(residual_state_counts.items())),
        "missing_leg_ref_count": missing_leg_ref_count,
        "unresolved_missing_leg_ref_count": unresolved_missing_leg_ref_count,
        "gap_export_request_row_count": len(sorted_rows),
        "unique_gap_contract_count": len(unique_gap_contracts),
        "min_quote_date": min(quote_dates) if quote_dates else None,
        "max_quote_date": max(quote_dates) if quote_dates else None,
        "top_strategy_counts": dict(strategy_counts.most_common(20)),
        "top_symbol_counts": dict(symbol_counts.most_common(20)),
        "does_select_strategy": False,
        "does_apply_exit_rule": False,
        "does_feed_exit_result_to_expectancy": False,
        "does_forward_fill": False,
        "does_invent_prices": False,
        "requires_quantconnect_export": len(sorted_rows) > 0,
        "expected_quantconnect_output": {
            "compiled_local_file": "baseline_exit_overlay_daily_quote_gap_fills.jsonl",
            "grain": "one row per contract_symbol and quote_date",
        },
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }
    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build missing daily quote request rows for locked baseline exit overlay paths.")
    parser.add_argument("--trade-leg-manifest", required=True)
    parser.add_argument("--daily-quote-path-residual-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_gap_request(
        trade_leg_manifest_path=Path(args.trade_leg_manifest),
        daily_quote_path_residual_rows_path=Path(args.daily_quote_path_residual_rows),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
