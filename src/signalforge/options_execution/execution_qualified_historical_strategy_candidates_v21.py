from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SYMBOL_FIELDS = [
    "underlying_symbol",
    "symbol",
    "asset_symbol",
    "market_symbol",
    "ticker",
]

DATE_FIELDS = [
    "quote_date",
    "asof_quote_date",
    "decision_date",
    "trade_date",
    "as_of_date",
    "date",
]

STRATEGY_FIELDS = [
    "strategy_name",
    "selected_strategy_name",
    "selected_strategy",
    "strategy",
    "candidate_strategy",
    "strategy_family",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def normalize_strategy(value: Any) -> str:
    text = str(value or "").strip()

    aliases = {
        "bull_call_spread": "bull_call_debit_spread",
        "bear_put_spread": "bear_put_debit_spread",
        "put_credit": "put_credit_spread",
        "call_credit": "call_credit_spread",
        "condor": "iron_condor",
        "butterfly": "iron_butterfly",
    }

    return aliases.get(text, text)


def selection_key(row: dict[str, Any]) -> tuple[str, str, str]:
    symbol = str(first_present(row, SYMBOL_FIELDS) or "").strip().upper()
    date = str(first_present(row, DATE_FIELDS) or "").strip()[:10]
    strategy = normalize_strategy(first_present(row, STRATEGY_FIELDS))

    return symbol, date, strategy


def rule_key(row: dict[str, Any]) -> tuple[str, str, str]:
    symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper()
    date = str(row.get("quote_date") or row.get("asof_quote_date") or "").strip()[:10]
    strategy = normalize_strategy(row.get("strategy_name"))

    return symbol, date, strategy


def build_execution_qualified_candidates(
    historical_strategy_selection_rows_path: Path,
    resolved_strategy_execution_rules_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows_path = output_dir / "signalforge_execution_annotated_historical_strategy_candidates_v21.jsonl"
    qualified_rows_path = output_dir / "signalforge_execution_qualified_historical_strategy_candidates_v21.jsonl"
    rejected_rows_path = output_dir / "signalforge_execution_rejected_historical_strategy_candidates_v21.jsonl"
    summary_path = output_dir / "signalforge_execution_qualified_historical_strategy_candidates_v21_summary.json"

    rules_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicate_rule_keys = []

    for rule in read_jsonl(resolved_strategy_execution_rules_path):
        key = rule_key(rule)
        if key in rules_by_key:
            duplicate_rule_keys.append(key)
        rules_by_key[key] = rule

    input_row_count = 0
    annotated_row_count = 0
    qualified_row_count = 0
    rejected_row_count = 0

    missing_rule_count = 0
    bad_key_count = 0

    symbols = set()
    dates = set()
    strategies = set()

    final_state_counts = Counter()
    reject_reason_counts = Counter()
    strategy_input_counts = Counter()
    strategy_qualified_counts = Counter()
    strategy_rejected_counts = Counter()

    missing_rule_sample = []
    bad_key_sample = []

    with (
        all_rows_path.open("w", encoding="utf-8", newline="\n") as all_handle,
        qualified_rows_path.open("w", encoding="utf-8", newline="\n") as qualified_handle,
        rejected_rows_path.open("w", encoding="utf-8", newline="\n") as rejected_handle,
    ):
        for row in read_jsonl(historical_strategy_selection_rows_path):
            input_row_count += 1

            symbol, date, strategy = selection_key(row)

            if not symbol or not date or not strategy:
                bad_key_count += 1
                if len(bad_key_sample) < 25:
                    bad_key_sample.append({
                        "symbol": symbol,
                        "date": date,
                        "strategy": strategy,
                        "row": row,
                    })
                continue

            symbols.add(symbol)
            dates.add(date)
            strategies.add(strategy)
            strategy_input_counts[strategy] += 1

            rule = rules_by_key.get((symbol, date, strategy))

            reject_reasons = []

            if rule is None:
                missing_rule_count += 1
                final_execution_state = "missing_execution_rule"
                can_backtest_new_entry = False
                reject_reasons.append("missing_resolved_strategy_execution_rule")

                if len(missing_rule_sample) < 50:
                    missing_rule_sample.append({
                        "symbol": symbol,
                        "date": date,
                        "strategy": strategy,
                    })

                execution_fields = {
                    "execution_rule_found": False,
                    "final_execution_state": final_execution_state,
                    "can_backtest_new_entry": False,
                    "requires_manual_review": False,
                    "structure_available": None,
                    "candidate_structure_count": None,
                    "rolling_liquidity_tier": None,
                    "fill_price_mode": None,
                    "max_allowed_relative_spread": None,
                    "execution_blockers": reject_reasons,
                    "execution_warnings": [],
                }

            else:
                final_execution_state = str(rule.get("final_execution_state") or "unknown")
                can_backtest_new_entry = bool(rule.get("can_backtest_new_entry"))

                execution_blockers = list(rule.get("blockers") or [])
                execution_warnings = list(rule.get("warnings") or [])

                if not can_backtest_new_entry:
                    if final_execution_state == "manual_review":
                        reject_reasons.append("manual_review_not_backtest_qualified")
                    elif final_execution_state == "block":
                        reject_reasons.append("execution_rule_blocked")
                    else:
                        reject_reasons.append("not_backtest_qualified")

                    reject_reasons.extend(execution_blockers)

                execution_fields = {
                    "execution_rule_found": True,
                    "final_execution_state": final_execution_state,
                    "can_backtest_new_entry": can_backtest_new_entry,
                    "requires_manual_review": bool(rule.get("requires_manual_review")),
                    "structure_available": rule.get("structure_available"),
                    "candidate_contract_count": rule.get("candidate_contract_count"),
                    "candidate_pair_count": rule.get("candidate_pair_count"),
                    "candidate_structure_count": rule.get("candidate_structure_count"),
                    "expiration_count_with_structures": rule.get("expiration_count_with_structures"),
                    "overlay_state": rule.get("overlay_state"),
                    "rolling_liquidity_tier": rule.get("rolling_liquidity_tier"),
                    "fill_price_mode": rule.get("fill_price_mode"),
                    "max_allowed_relative_spread": rule.get("max_allowed_relative_spread"),
                    "execution_blockers": execution_blockers,
                    "execution_warnings": execution_warnings,
                }

            out = {
                **row,
                "adapter_type": "execution_qualified_historical_strategy_candidates_v21_builder",
                "artifact_type": "signalforge_execution_qualified_historical_strategy_candidates_v21",
                "contract": "execution_qualified_historical_strategy_candidates_v21",
                "execution_join_symbol": symbol,
                "execution_join_date": date,
                "execution_join_strategy_name": strategy,
                **execution_fields,
                "execution_reject_reason_count": len(set(reject_reasons)),
                "execution_reject_reasons": sorted(set(reject_reasons)),
            }

            all_handle.write(json.dumps(out, sort_keys=True) + "\n")
            annotated_row_count += 1

            final_state_counts[final_execution_state] += 1

            if can_backtest_new_entry:
                qualified_handle.write(json.dumps(out, sort_keys=True) + "\n")
                qualified_row_count += 1
                strategy_qualified_counts[strategy] += 1
            else:
                rejected_handle.write(json.dumps(out, sort_keys=True) + "\n")
                rejected_row_count += 1
                strategy_rejected_counts[strategy] += 1

                for reason in sorted(set(reject_reasons)):
                    reject_reason_counts[reason] += 1

    blockers = []

    if duplicate_rule_keys:
        blockers.append("duplicate_resolved_strategy_execution_rule_keys")

    if bad_key_count:
        blockers.append("bad_historical_strategy_selection_keys")

    if missing_rule_count:
        blockers.append("missing_resolved_strategy_execution_rules")

    if annotated_row_count != input_row_count - bad_key_count:
        blockers.append("annotated_row_count_mismatch")

    summary = {
        "adapter_type": "execution_qualified_historical_strategy_candidates_v21_builder",
        "artifact_type": "signalforge_execution_qualified_historical_strategy_candidates_v21",
        "contract": "execution_qualified_historical_strategy_candidates_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "historical_strategy_selection_rows_path": str(historical_strategy_selection_rows_path),
        "resolved_strategy_execution_rules_path": str(resolved_strategy_execution_rules_path),
        "resolved_rule_key_count": len(rules_by_key),
        "duplicate_rule_key_count": len(duplicate_rule_keys),
        "input_row_count": input_row_count,
        "annotated_row_count": annotated_row_count,
        "qualified_row_count": qualified_row_count,
        "rejected_row_count": rejected_row_count,
        "bad_key_count": bad_key_count,
        "missing_rule_count": missing_rule_count,
        "symbol_count": len(symbols),
        "date_count": len(dates),
        "strategy_count": len(strategies),
        "final_execution_state_counts": dict(sorted(final_state_counts.items())),
        "reject_reason_counts": dict(sorted(reject_reason_counts.items())),
        "strategy_input_counts": dict(sorted(strategy_input_counts.items())),
        "strategy_qualified_counts": dict(sorted(strategy_qualified_counts.items())),
        "strategy_rejected_counts": dict(sorted(strategy_rejected_counts.items())),
        "missing_rule_sample": missing_rule_sample,
        "bad_key_sample": bad_key_sample,
        "paths": {
            "all_rows_path": str(all_rows_path),
            "qualified_rows_path": str(qualified_rows_path),
            "rejected_rows_path": str(rejected_rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-strategy-selection-rows", required=True)
    parser.add_argument("--resolved-strategy-execution-rules", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_execution_qualified_candidates(
        historical_strategy_selection_rows_path=Path(args.historical_strategy_selection_rows),
        resolved_strategy_execution_rules_path=Path(args.resolved_strategy_execution_rules),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
