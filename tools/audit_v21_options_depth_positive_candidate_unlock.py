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


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                yield line_number, json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def key_for_row(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(first_present(row, [
        "underlying_symbol",
        "requested_underlying_symbol",
        "symbol",
        "asset_symbol",
        "market_symbol",
        "ticker",
    ]) or "").strip().upper()

    date = str(first_present(row, [
        "quote_date",
        "decision_date",
        "asof_quote_date",
        "trade_date",
        "as_of_date",
        "date",
    ]) or "").strip()[:10]

    return symbol, date


def strategy_for_rule(row: dict[str, Any]) -> str:
    return str(row.get("strategy_name") or row.get("strategy") or "").strip()


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


def bool_field(row: dict[str, Any], fields: list[str]) -> bool:
    for field in fields:
        value = row.get(field)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
    return False


def audit_unlock(
    eligibility_rows_path: Path,
    contract_features_path: Path,
    resolved_rules_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_v21_options_depth_positive_candidate_unlock_rows.jsonl"
    summary_path = output_dir / "signalforge_v21_options_depth_positive_candidate_unlock_audit.json"

    eligibility_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    old_positive_keys = set()
    old_no_positive_keys = set()

    eligibility_row_count = 0
    duplicate_eligibility_key_count = 0

    old_data_state_counts = Counter()
    old_positive_data_state_counts = Counter()
    old_no_positive_data_state_counts = Counter()
    old_status_counts = Counter()
    old_positive_family_counts = Counter()

    for _, row in read_jsonl(eligibility_rows_path):
        eligibility_row_count += 1
        key = key_for_row(row)

        if key in eligibility_by_key:
            duplicate_eligibility_key_count += 1

        status_map = extract_status_map(row)
        positive_families = sorted(
            family
            for family, status in status_map.items()
            if status in POSITIVE_STATUSES
        )

        data_state = str(
            row.get("data_state")
            or row.get("source_decision_data_state")
            or "unknown"
        )

        old_data_state_counts[data_state] += 1

        for family, status in status_map.items():
            old_status_counts[f"{family}:{status}"] += 1

        if positive_families:
            old_positive_keys.add(key)
            old_positive_data_state_counts[data_state] += 1

            for family in positive_families:
                old_positive_family_counts[family] += 1
        else:
            old_no_positive_keys.add(key)
            old_no_positive_data_state_counts[data_state] += 1

        eligibility_by_key[key] = {
            "symbol": key[0],
            "date": key[1],
            "data_state": data_state,
            "status_map": status_map,
            "old_positive_families": positive_families,
            "old_positive_family_count": len(positive_families),
            "old_positive_eligible": bool(positive_families),
        }

    decision_keys = set(eligibility_by_key)

    contract_counts = Counter()
    quote_complete_counts = Counter()
    greeks_complete_counts = Counter()
    open_interest_counts = Counter()
    volume_counts = Counter()
    right_counts_by_key = defaultdict(Counter)
    liquidity_counts_by_key = defaultdict(Counter)

    contract_feature_row_count = 0
    relevant_contract_feature_row_count = 0
    contract_feature_symbol_date_keys = set()

    for _, row in read_jsonl(contract_features_path):
        contract_feature_row_count += 1
        key = key_for_row(row)

        if key not in decision_keys:
            continue

        relevant_contract_feature_row_count += 1
        contract_feature_symbol_date_keys.add(key)

        contract_counts[key] += 1

        if bool_field(row, ["quote_complete"]):
            quote_complete_counts[key] += 1

        if bool_field(row, ["greeks_complete"]):
            greeks_complete_counts[key] += 1

        if bool_field(row, ["open_interest_available"]):
            open_interest_counts[key] += 1

        if bool_field(row, ["volume_available"]):
            volume_counts[key] += 1

        right = str(row.get("right") or row.get("option_right") or "").strip().lower()
        if right:
            right_counts_by_key[key][right] += 1

        tier = str(row.get("liquidity_tier") or row.get("contract_liquidity_tier") or "").strip()
        if tier:
            liquidity_counts_by_key[key][tier] += 1

    rule_counts = Counter()
    rule_qualified_counts = Counter()
    rule_state_counts_by_key = defaultdict(Counter)
    rule_qualified_strategies_by_key = defaultdict(set)
    rule_strategy_states_by_key = defaultdict(dict)

    resolved_rule_row_count = 0
    relevant_resolved_rule_row_count = 0

    for _, row in read_jsonl(resolved_rules_path):
        resolved_rule_row_count += 1
        key = key_for_row(row)

        if key not in decision_keys:
            continue

        relevant_resolved_rule_row_count += 1

        strategy = strategy_for_rule(row)
        final_state = str(row.get("final_execution_state") or "unknown")
        can_backtest = bool(row.get("can_backtest_new_entry"))

        rule_counts[key] += 1
        rule_state_counts_by_key[key][final_state] += 1

        if strategy:
            rule_strategy_states_by_key[key][strategy] = final_state

        if can_backtest and strategy:
            rule_qualified_counts[key] += 1
            rule_qualified_strategies_by_key[key].add(strategy)

    classification_counts = Counter()
    classification_data_state_counts = Counter()
    unlock_strategy_counts = Counter()
    unlock_symbol_counts = Counter()
    unlock_samples = []
    no_positive_but_v21_contract_no_qualified_samples = []
    no_v21_contract_samples = []

    old_no_positive_with_v21_contracts = 0
    old_no_positive_with_v21_rules = 0
    old_no_positive_with_v21_qualified = 0

    old_partial_option_missing_with_v21_contracts = 0
    old_partial_option_missing_with_v21_qualified = 0

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for key in sorted(decision_keys):
            base = eligibility_by_key[key]
            symbol, date = key
            data_state = base["data_state"]

            contract_count = contract_counts[key]
            rule_count = rule_counts[key]
            qualified_count = rule_qualified_counts[key]
            qualified_strategies = sorted(rule_qualified_strategies_by_key[key])

            has_v21_contracts = contract_count > 0
            has_v21_rules = rule_count > 0
            has_v21_qualified = qualified_count > 0

            if not base["old_positive_eligible"]:
                if has_v21_contracts:
                    old_no_positive_with_v21_contracts += 1
                if has_v21_rules:
                    old_no_positive_with_v21_rules += 1
                if has_v21_qualified:
                    old_no_positive_with_v21_qualified += 1

                if data_state == "partial_option_missing" and has_v21_contracts:
                    old_partial_option_missing_with_v21_contracts += 1
                if data_state == "partial_option_missing" and has_v21_qualified:
                    old_partial_option_missing_with_v21_qualified += 1

            if base["old_positive_eligible"]:
                classification = "old_positive_eligible"
            elif not has_v21_contracts:
                classification = "old_no_positive_no_v21_contract_features"
            elif has_v21_qualified:
                classification = "old_no_positive_but_v21_execution_qualified"
            elif has_v21_rules:
                classification = "old_no_positive_v21_present_but_not_execution_qualified"
            else:
                classification = "old_no_positive_v21_contracts_but_no_rules"

            classification_counts[classification] += 1
            classification_data_state_counts[f"{classification}:{data_state}"] += 1

            for strategy in qualified_strategies:
                unlock_strategy_counts[strategy] += 1

            if classification == "old_no_positive_but_v21_execution_qualified":
                unlock_symbol_counts[symbol] += 1

                if len(unlock_samples) < 100:
                    unlock_samples.append({
                        "symbol": symbol,
                        "date": date,
                        "data_state": data_state,
                        "contract_count": contract_count,
                        "qualified_count": qualified_count,
                        "qualified_strategies": qualified_strategies,
                        "rule_state_counts": dict(sorted(rule_state_counts_by_key[key].items())),
                        "old_status_map": base["status_map"],
                        "right_counts": dict(sorted(right_counts_by_key[key].items())),
                        "liquidity_counts": dict(sorted(liquidity_counts_by_key[key].items())),
                    })

            if (
                not base["old_positive_eligible"]
                and has_v21_contracts
                and not has_v21_qualified
                and len(no_positive_but_v21_contract_no_qualified_samples) < 100
            ):
                no_positive_but_v21_contract_no_qualified_samples.append({
                    "symbol": symbol,
                    "date": date,
                    "data_state": data_state,
                    "contract_count": contract_count,
                    "rule_count": rule_count,
                    "rule_state_counts": dict(sorted(rule_state_counts_by_key[key].items())),
                    "old_status_map": base["status_map"],
                })

            if (
                not base["old_positive_eligible"]
                and not has_v21_contracts
                and len(no_v21_contract_samples) < 100
            ):
                no_v21_contract_samples.append({
                    "symbol": symbol,
                    "date": date,
                    "data_state": data_state,
                    "old_status_map": base["status_map"],
                })

            out = {
                "symbol": symbol,
                "date": date,
                "data_state": data_state,
                "classification": classification,
                "old_positive_eligible": base["old_positive_eligible"],
                "old_positive_families": base["old_positive_families"],
                "old_positive_family_count": base["old_positive_family_count"],
                "v21_contract_count": contract_count,
                "v21_quote_complete_count": quote_complete_counts[key],
                "v21_greeks_complete_count": greeks_complete_counts[key],
                "v21_open_interest_available_count": open_interest_counts[key],
                "v21_volume_available_count": volume_counts[key],
                "v21_right_counts": dict(sorted(right_counts_by_key[key].items())),
                "v21_liquidity_counts": dict(sorted(liquidity_counts_by_key[key].items())),
                "v21_resolved_rule_count": rule_count,
                "v21_qualified_strategy_count": qualified_count,
                "v21_qualified_strategies": qualified_strategies,
                "v21_rule_state_counts": dict(sorted(rule_state_counts_by_key[key].items())),
                "v21_rule_strategy_states": dict(sorted(rule_strategy_states_by_key[key].items())),
                "old_status_map": base["status_map"],
            }

            handle.write(json.dumps(out, sort_keys=True) + "\n")

    blockers = []

    if duplicate_eligibility_key_count:
        blockers.append("duplicate_eligibility_keys")

    if old_no_positive_with_v21_qualified:
        blockers.append("old_no_positive_rows_have_v21_execution_qualified_structures")

    summary = {
        "adapter_type": "v21_options_depth_positive_candidate_unlock_auditor",
        "artifact_type": "signalforge_v21_options_depth_positive_candidate_unlock_audit",
        "contract": "v21_options_depth_positive_candidate_unlock_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "eligibility_rows_path": str(eligibility_rows_path),
        "contract_features_path": str(contract_features_path),
        "resolved_rules_path": str(resolved_rules_path),
        "eligibility_row_count": eligibility_row_count,
        "eligibility_key_count": len(decision_keys),
        "duplicate_eligibility_key_count": duplicate_eligibility_key_count,
        "old_positive_key_count": len(old_positive_keys),
        "old_no_positive_key_count": len(old_no_positive_keys),
        "contract_feature_row_count": contract_feature_row_count,
        "relevant_contract_feature_row_count": relevant_contract_feature_row_count,
        "v21_contract_feature_symbol_date_count": len(contract_feature_symbol_date_keys),
        "resolved_rule_row_count": resolved_rule_row_count,
        "relevant_resolved_rule_row_count": relevant_resolved_rule_row_count,
        "old_no_positive_with_v21_contracts": old_no_positive_with_v21_contracts,
        "old_no_positive_with_v21_rules": old_no_positive_with_v21_rules,
        "old_no_positive_with_v21_qualified": old_no_positive_with_v21_qualified,
        "old_partial_option_missing_with_v21_contracts": old_partial_option_missing_with_v21_contracts,
        "old_partial_option_missing_with_v21_qualified": old_partial_option_missing_with_v21_qualified,
        "old_data_state_counts": dict(sorted(old_data_state_counts.items())),
        "old_positive_data_state_counts": dict(sorted(old_positive_data_state_counts.items())),
        "old_no_positive_data_state_counts": dict(sorted(old_no_positive_data_state_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "classification_data_state_counts": dict(sorted(classification_data_state_counts.items())),
        "old_positive_family_counts": dict(sorted(old_positive_family_counts.items())),
        "unlock_strategy_counts": dict(sorted(unlock_strategy_counts.items())),
        "unlock_symbol_counts_top_50": dict(unlock_symbol_counts.most_common(50)),
        "old_status_counts": dict(sorted(old_status_counts.items())),
        "unlock_samples": unlock_samples,
        "no_positive_but_v21_contract_no_qualified_samples": no_positive_but_v21_contract_no_qualified_samples,
        "no_v21_contract_samples": no_v21_contract_samples,
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eligibility-rows", required=True)
    parser.add_argument("--contract-features", required=True)
    parser.add_argument("--resolved-rules", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = audit_unlock(
        eligibility_rows_path=Path(args.eligibility_rows),
        contract_features_path=Path(args.contract_features),
        resolved_rules_path=Path(args.resolved_rules),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
