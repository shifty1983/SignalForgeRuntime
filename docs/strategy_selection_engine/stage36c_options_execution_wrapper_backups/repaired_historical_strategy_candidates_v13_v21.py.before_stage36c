from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


POSITIVE_STATUSES = {
    "allowed",
    "allowed_constrained",
    "favored",
    "favored_constrained",
}

FAMILY_TO_STRATEGIES = {
    "directional_long_premium": [
        "long_call",
        "long_put",
    ],
    "long_gamma": [
        "long_call",
        "long_put",
        "bull_call_debit_spread",
        "bear_put_debit_spread",
    ],
    "debit_spread": [
        "bull_call_debit_spread",
        "bear_put_debit_spread",
    ],
    "credit_spread": [
        "put_credit_spread",
        "call_credit_spread",
    ],
    "defined_risk_short_premium": [
        "put_credit_spread",
        "call_credit_spread",
        "iron_condor",
        "iron_butterfly",
    ],
    "defined_risk_neutral": [
        "iron_condor",
        "iron_butterfly",
    ],
    "defined_risk_only": [
        "bull_call_debit_spread",
        "bear_put_debit_spread",
        "put_credit_spread",
        "call_credit_spread",
        "iron_condor",
        "iron_butterfly",
        "calendar_spread",
        "diagonal_spread",
    ],
    "protective_put_spread": [
        "long_put",
        "bear_put_debit_spread",
    ],
}

NO_AUTOMATIC_CANDIDATE_FAMILIES = {
    "wait_for_clearer_options_edge",
    "manual_review_only",
    "naked_short_premium",
    "short_premium_without_hedge",
    "short_put_spread_without_strong_support",
    "long_unhedged_premium",
}


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


def symbol_date_key(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(first_present(row, ["underlying_symbol", "symbol", "asset_symbol", "ticker"]) or "").strip().upper()
    date = str(first_present(row, ["decision_date", "quote_date", "asof_quote_date", "trade_date", "date"]) or "").strip()[:10]
    return symbol, date


def rule_key(row: dict[str, Any]) -> tuple[str, str, str]:
    symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper()
    date = str(row.get("quote_date") or row.get("asof_quote_date") or "").strip()[:10]
    strategy = str(row.get("strategy_name") or "").strip()
    return symbol, date, strategy


def extract_status_map(row: dict[str, Any]) -> dict[str, str]:
    candidates = [
        row.get("strategy_family_statuses"),
        row.get("strategy_family_eligibility", {}).get("strategy_family_statuses")
        if isinstance(row.get("strategy_family_eligibility"), dict) else None,
        row.get("research_context", {}).get("strategy_family_statuses")
        if isinstance(row.get("research_context"), dict) else None,
        row.get("research_context", {}).get("strategy_family_eligibility", {}).get("strategy_family_statuses")
        if isinstance(row.get("research_context"), dict)
        and isinstance(row.get("research_context", {}).get("strategy_family_eligibility"), dict) else None,
    ]

    for item in candidates:
        if isinstance(item, dict) and item:
            return {str(k): str(v) for k, v in item.items()}

    return {}


def core_context(row: dict[str, Any]) -> dict[str, Any]:
    symbol, date = symbol_date_key(row)

    option_behavior = row.get("option_behavior")
    if not isinstance(option_behavior, dict):
        option_behavior = {}

    regime = row.get("regime")
    if not isinstance(regime, dict):
        regime = {}

    return {
        "symbol": symbol,
        "date": date,
        "decision_date": date,
        "source_decision_data_state": row.get("data_state") or row.get("source_decision_data_state"),
        "regime_state": row.get("regime_state") or regime.get("state"),
        "asset_behavior_state": row.get("asset_behavior_state"),
        "option_behavior_state": row.get("option_behavior_state") or option_behavior.get("option_behavior_state") or option_behavior.get("state"),
        "option_liquidity_state": row.get("option_liquidity_state") or option_behavior.get("option_liquidity_state") or option_behavior.get("liquidity_state"),
        "premium_bias": row.get("premium_bias") or option_behavior.get("premium_bias"),
        "term_structure_state": row.get("term_structure_state") or option_behavior.get("term_structure_state"),
        "term_structure_shape": row.get("term_structure_shape") or option_behavior.get("term_structure_shape"),
        "term_structure_expiration_count": row.get("term_structure_expiration_count") or option_behavior.get("term_structure_expiration_count"),
        "holding_period_days": row.get("holding_period_days", 10),
    }


def load_rules(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    out = {}

    for row in read_jsonl(path):
        out[rule_key(row)] = row

    return out


def build_repaired_candidates(
    eligibility_rows_path: Path,
    resolved_rules_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows_path = output_dir / "signalforge_repaired_historical_strategy_candidates_v13_v21.jsonl"
    qualified_rows_path = output_dir / "signalforge_repaired_execution_qualified_historical_strategy_candidates_v13_v21.jsonl"
    rejected_rows_path = output_dir / "signalforge_repaired_execution_rejected_historical_strategy_candidates_v13_v21.jsonl"
    summary_path = output_dir / "signalforge_repaired_historical_strategy_candidates_v13_v21_summary.json"

    rules_by_key = load_rules(resolved_rules_path)

    input_row_count = 0
    positive_eligible_symbol_date_count = 0
    no_positive_eligible_symbol_date_count = 0

    expanded_candidate_row_count = 0
    qualified_row_count = 0
    rejected_row_count = 0

    missing_rule_count = 0

    symbols = set()
    symbol_dates = set()
    strategies = set()

    family_status_counts = Counter()
    positive_family_counts = Counter()
    mapped_family_counts = Counter()
    unmapped_positive_family_counts = Counter()
    strategy_candidate_counts = Counter()
    strategy_qualified_counts = Counter()
    strategy_rejected_counts = Counter()
    final_execution_state_counts = Counter()
    reject_reason_counts = Counter()

    missing_rule_sample = []
    unmapped_positive_family_sample = []
    no_positive_sample = []

    with (
        all_rows_path.open("w", encoding="utf-8", newline="\n") as all_handle,
        qualified_rows_path.open("w", encoding="utf-8", newline="\n") as qualified_handle,
        rejected_rows_path.open("w", encoding="utf-8", newline="\n") as rejected_handle,
    ):
        for row in read_jsonl(eligibility_rows_path):
            input_row_count += 1

            symbol, date = symbol_date_key(row)
            status_map = extract_status_map(row)

            context = core_context(row)

            for family, status in status_map.items():
                family_status_counts[f"{family}:{status}"] += 1

            positive_families = sorted(
                family
                for family, status in status_map.items()
                if status in POSITIVE_STATUSES
            )

            if positive_families:
                positive_eligible_symbol_date_count += 1
            else:
                no_positive_eligible_symbol_date_count += 1
                if len(no_positive_sample) < 50:
                    no_positive_sample.append({
                        "symbol": symbol,
                        "date": date,
                        "status_map": status_map,
                    })
                continue

            candidate_strategy_to_families: dict[str, list[str]] = defaultdict(list)

            for family in positive_families:
                positive_family_counts[family] += 1

                mapped_strategies = FAMILY_TO_STRATEGIES.get(family, [])

                if mapped_strategies:
                    mapped_family_counts[family] += 1

                elif family not in NO_AUTOMATIC_CANDIDATE_FAMILIES:
                    unmapped_positive_family_counts[family] += 1
                    if len(unmapped_positive_family_sample) < 100:
                        unmapped_positive_family_sample.append({
                            "symbol": symbol,
                            "date": date,
                            "family": family,
                            "status": status_map.get(family),
                        })

                for strategy in mapped_strategies:
                    candidate_strategy_to_families[strategy].append(family)

            for strategy, source_families in sorted(candidate_strategy_to_families.items()):
                key = (symbol, date, strategy)
                rule = rules_by_key.get(key)

                execution_rule_found = rule is not None

                if rule is None:
                    missing_rule_count += 1
                    final_execution_state = "missing_execution_rule"
                    can_backtest_new_entry = False
                    execution_blockers = ["missing_resolved_strategy_execution_rule"]
                    execution_warnings = []

                    if len(missing_rule_sample) < 100:
                        missing_rule_sample.append({
                            "symbol": symbol,
                            "date": date,
                            "strategy": strategy,
                        })
                else:
                    final_execution_state = str(rule.get("final_execution_state") or "unknown")
                    can_backtest_new_entry = bool(rule.get("can_backtest_new_entry"))
                    execution_blockers = list(rule.get("blockers") or [])
                    execution_warnings = list(rule.get("warnings") or [])

                reject_reasons = []

                if not can_backtest_new_entry:
                    if final_execution_state == "manual_review":
                        reject_reasons.append("manual_review_not_backtest_qualified")
                    elif final_execution_state == "block":
                        reject_reasons.append("execution_rule_blocked")
                    elif final_execution_state == "missing_execution_rule":
                        reject_reasons.append("missing_resolved_strategy_execution_rule")
                    else:
                        reject_reasons.append("not_backtest_qualified")

                    reject_reasons.extend(execution_blockers)

                out = {
                    "adapter_type": "repaired_historical_strategy_candidates_v13_v21_builder",
                    "artifact_type": "signalforge_repaired_historical_strategy_candidates_v13_v21",
                    "contract": "repaired_historical_strategy_candidates_v13_v21",
                    **context,
                    "strategy": strategy,
                    "strategy_name": strategy,
                    "candidate_strategy": strategy,
                    "candidate_source": "family_eligibility_positive_status_expansion",
                    "candidate_source_families": sorted(set(source_families)),
                    "candidate_source_family_statuses": {
                        family: status_map.get(family)
                        for family in sorted(set(source_families))
                    },
                    "strategy_candidate_id": f"{date}_{symbol}_{strategy}__10d__v13_v21_repaired",
                    "is_trainable_candidate": True,
                    "execution_rule_found": execution_rule_found,
                    "final_execution_state": final_execution_state,
                    "can_backtest_new_entry": can_backtest_new_entry,
                    "requires_manual_review": bool(rule.get("requires_manual_review")) if rule else False,
                    "structure_available": rule.get("structure_available") if rule else None,
                    "candidate_contract_count": rule.get("candidate_contract_count") if rule else None,
                    "candidate_pair_count": rule.get("candidate_pair_count") if rule else None,
                    "candidate_structure_count": rule.get("candidate_structure_count") if rule else None,
                    "overlay_state": rule.get("overlay_state") if rule else None,
                    "rolling_liquidity_tier": rule.get("rolling_liquidity_tier") if rule else None,
                    "fill_price_mode": rule.get("fill_price_mode") if rule else None,
                    "max_allowed_relative_spread": rule.get("max_allowed_relative_spread") if rule else None,
                    "execution_blockers": execution_blockers,
                    "execution_warnings": execution_warnings,
                    "execution_reject_reason_count": len(set(reject_reasons)),
                    "execution_reject_reasons": sorted(set(reject_reasons)),
                }

                all_handle.write(json.dumps(out, sort_keys=True) + "\n")

                expanded_candidate_row_count += 1
                symbols.add(symbol)
                symbol_dates.add((symbol, date))
                strategies.add(strategy)
                strategy_candidate_counts[strategy] += 1
                final_execution_state_counts[final_execution_state] += 1

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

    if missing_rule_count:
        blockers.append("missing_resolved_strategy_execution_rules")

    if not expanded_candidate_row_count:
        blockers.append("no_repaired_candidate_rows")

    if unmapped_positive_family_counts:
        blockers.append("unmapped_positive_strategy_families")

    summary = {
        "adapter_type": "repaired_historical_strategy_candidates_v13_v21_builder",
        "artifact_type": "signalforge_repaired_historical_strategy_candidates_v13_v21",
        "contract": "repaired_historical_strategy_candidates_v13_v21",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "eligibility_rows_path": str(eligibility_rows_path),
        "resolved_rules_path": str(resolved_rules_path),
        "resolved_rule_key_count": len(rules_by_key),
        "input_eligibility_row_count": input_row_count,
        "positive_eligible_symbol_date_count": positive_eligible_symbol_date_count,
        "no_positive_eligible_symbol_date_count": no_positive_eligible_symbol_date_count,
        "expanded_candidate_row_count": expanded_candidate_row_count,
        "qualified_row_count": qualified_row_count,
        "rejected_row_count": rejected_row_count,
        "missing_rule_count": missing_rule_count,
        "symbol_count": len(symbols),
        "symbol_date_count": len(symbol_dates),
        "strategy_count": len(strategies),
        "family_status_counts": dict(sorted(family_status_counts.items())),
        "positive_family_counts": dict(sorted(positive_family_counts.items())),
        "mapped_family_counts": dict(sorted(mapped_family_counts.items())),
        "unmapped_positive_family_counts": dict(sorted(unmapped_positive_family_counts.items())),
        "strategy_candidate_counts": dict(sorted(strategy_candidate_counts.items())),
        "strategy_qualified_counts": dict(sorted(strategy_qualified_counts.items())),
        "strategy_rejected_counts": dict(sorted(strategy_rejected_counts.items())),
        "final_execution_state_counts": dict(sorted(final_execution_state_counts.items())),
        "reject_reason_counts": dict(sorted(reject_reason_counts.items())),
        "missing_rule_sample": missing_rule_sample,
        "unmapped_positive_family_sample": unmapped_positive_family_sample,
        "no_positive_sample": no_positive_sample,
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
    parser.add_argument("--eligibility-rows", required=True)
    parser.add_argument("--resolved-rules", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_repaired_candidates(
        eligibility_rows_path=Path(args.eligibility_rows),
        resolved_rules_path=Path(args.resolved_rules),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
