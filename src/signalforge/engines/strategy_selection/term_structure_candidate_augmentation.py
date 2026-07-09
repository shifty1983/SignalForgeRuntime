# Auto-promoted by Stage 40C2B.
# Core engine for Stage 12 term-structure candidate augmentation.
# The tools/ script is now only a CLI compatibility shim.

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


POSITIVE_STATUSES = {
    "allowed",
    "allowed_constrained",
    "favored",
    "favored_constrained",
}

TERM_STRUCTURE_STRATEGIES = [
    "calendar_spread",
    "diagonal_spread",
]


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


def row_symbol(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "underlying_symbol",
        "requested_underlying_symbol",
        "symbol",
        "asset_symbol",
        "market_symbol",
        "ticker",
    ]) or "").strip().upper()


def row_date(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "decision_date",
        "quote_date",
        "asof_quote_date",
        "trade_date",
        "as_of_date",
        "date",
    ]) or "").strip()[:10]


def row_strategy(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "strategy_name",
        "strategy",
        "candidate_strategy",
    ]) or "").strip()


def extract_status_map(row: dict[str, Any]) -> dict[str, str]:
    candidates = []

    if isinstance(row.get("strategy_family_statuses"), dict):
        candidates.append(row.get("strategy_family_statuses"))

    sfe = row.get("strategy_family_eligibility")
    if isinstance(sfe, dict) and isinstance(sfe.get("strategy_family_statuses"), dict):
        candidates.append(sfe.get("strategy_family_statuses"))

    rc = row.get("research_context")
    if isinstance(rc, dict):
        if isinstance(rc.get("strategy_family_statuses"), dict):
            candidates.append(rc.get("strategy_family_statuses"))

        rc_sfe = rc.get("strategy_family_eligibility")
        if isinstance(rc_sfe, dict) and isinstance(rc_sfe.get("strategy_family_statuses"), dict):
            candidates.append(rc_sfe.get("strategy_family_statuses"))

    for candidate in candidates:
        if candidate:
            return {str(k): str(v) for k, v in candidate.items()}

    return {}


def nested_value(row: dict[str, Any], path: list[str]) -> Any:
    current: Any = row
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def term_structure_state(row: dict[str, Any]) -> str:
    values = [
        row.get("term_structure_state"),
        nested_value(row, ["option_behavior", "term_structure_state"]),
        nested_value(row, ["regime_asset_options_alignment", "term_structure_state"]),
        nested_value(row, ["research_context", "option_behavior", "term_structure_state"]),
        nested_value(row, ["research_context", "regime_asset_options_alignment", "term_structure_state"]),
    ]

    for value in values:
        if value not in (None, ""):
            return str(value)

    return ""


def term_structure_shape(row: dict[str, Any]) -> str:
    values = [
        row.get("term_structure_shape"),
        nested_value(row, ["option_behavior", "term_structure_shape"]),
        nested_value(row, ["regime_asset_options_alignment", "term_structure_shape"]),
        nested_value(row, ["research_context", "option_behavior", "term_structure_shape"]),
        nested_value(row, ["research_context", "regime_asset_options_alignment", "term_structure_shape"]),
    ]

    for value in values:
        if value not in (None, ""):
            return str(value)

    return ""


def derived_term_structure_status(status_map: dict[str, str]) -> str:
    statuses = [
        status_map.get("defined_risk_neutral"),
        status_map.get("wait_for_clearer_options_edge"),
    ]

    if any(str(status).endswith("_constrained") for status in statuses if status):
        return "allowed_constrained"

    if any(status in {"favored", "favored_constrained"} for status in statuses if status):
        return "favored"

    return "allowed"


def should_generate_term_structure(row: dict[str, Any]) -> bool:
    status_map = extract_status_map(row)

    defined_risk_neutral = status_map.get("defined_risk_neutral")
    wait_for_clearer = status_map.get("wait_for_clearer_options_edge")

    if defined_risk_neutral not in POSITIVE_STATUSES:
        return False

    if wait_for_clearer not in POSITIVE_STATUSES:
        return False

    if term_structure_state(row) != "available":
        return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repaired-candidates", required=True)
    parser.add_argument("--eligibility-rows", required=True)
    parser.add_argument("--resolved-rules", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repaired_path = Path(args.repaired_candidates)
    eligibility_path = Path(args.eligibility_rows)
    resolved_rules_path = Path(args.resolved_rules)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_path = output_dir / "signalforge_repaired_historical_strategy_candidates_v13_v21_term_structure_augmented.jsonl"
    qualified_path = output_dir / "signalforge_repaired_execution_qualified_historical_strategy_candidates_v13_v21_term_structure_augmented.jsonl"
    rejected_path = output_dir / "signalforge_repaired_execution_rejected_historical_strategy_candidates_v13_v21_term_structure_augmented.jsonl"
    term_added_path = output_dir / "signalforge_added_term_structure_strategy_candidates_v13_v21.jsonl"
    summary_path = output_dir / "signalforge_repaired_historical_strategy_candidates_v13_v21_term_structure_augmented_summary.json"

    existing_rows = []
    existing_keys = set()

    input_candidate_count = 0
    input_strategy_counts = Counter()

    for _, row in read_jsonl(repaired_path):
        input_candidate_count += 1

        symbol = row_symbol(row)
        date = row_date(row)
        strategy = row_strategy(row)

        existing_rows.append(row)
        existing_keys.add((symbol, date, strategy))
        input_strategy_counts[strategy] += 1

    eligible_term_requests = {}

    eligibility_row_count = 0
    term_eligible_symbol_date_count = 0
    term_eligible_data_state_counts = Counter()
    term_shape_counts = Counter()
    term_status_counts = Counter()

    for _, row in read_jsonl(eligibility_path):
        eligibility_row_count += 1

        symbol = row_symbol(row)
        date = row_date(row)

        if not symbol or not date:
            continue

        if not should_generate_term_structure(row):
            continue

        term_eligible_symbol_date_count += 1

        status_map = extract_status_map(row)
        candidate_status = derived_term_structure_status(status_map)
        state = term_structure_state(row)
        shape = term_structure_shape(row)

        data_state = str(row.get("data_state") or row.get("source_decision_data_state") or "unknown")
        term_eligible_data_state_counts[data_state] += 1
        term_shape_counts[shape or "unknown"] += 1
        term_status_counts[candidate_status] += 1

        for strategy in TERM_STRUCTURE_STRATEGIES:
            key = (symbol, date, strategy)

            if key in existing_keys:
                continue

            candidate = dict(row)
            candidate.update({
                "symbol": symbol,
                "underlying_symbol": symbol,
                "date": date,
                "decision_date": date,
                "quote_date": date,
                "strategy": strategy,
                "strategy_name": strategy,
                "candidate_strategy": strategy,
                "strategy_family": "term_structure",
                "strategy_family_status": candidate_status,
                "candidate_source": "repaired_term_structure_candidate_generation_v13_v21",
                "strategy_candidate_reason": "term_structure_available_with_defined_risk_neutral_and_wait_for_clearer_options_edge_positive",
                "candidate_source_families": [
                    "defined_risk_neutral",
                    "wait_for_clearer_options_edge",
                    "term_structure",
                ],
                "candidate_source_family_statuses": {
                    "defined_risk_neutral": status_map.get("defined_risk_neutral"),
                    "wait_for_clearer_options_edge": status_map.get("wait_for_clearer_options_edge"),
                    "term_structure": candidate_status,
                },
                "term_structure_state": state,
                "term_structure_shape": shape,
                "premium_profile": "debit",
                "is_repaired_term_structure_candidate": True,
            })

            eligible_term_requests[key] = candidate

    needed_rule_keys = set(eligible_term_requests)

    resolved_rules = {}
    resolved_rule_row_count = 0
    relevant_resolved_rule_count = 0

    for _, rule in read_jsonl(resolved_rules_path):
        resolved_rule_row_count += 1

        key = (row_symbol(rule), row_date(rule), row_strategy(rule))

        if key not in needed_rule_keys:
            continue

        relevant_resolved_rule_count += 1
        resolved_rules[key] = rule

    added_rows = []
    missing_rule_count = 0
    generated_strategy_counts = Counter()
    generated_final_state_counts = Counter()
    generated_qualified_counts = Counter()

    protected = {
        "symbol",
        "underlying_symbol",
        "date",
        "decision_date",
        "quote_date",
        "strategy",
        "strategy_name",
        "candidate_strategy",
        "strategy_family",
        "strategy_family_status",
    }

    for key, candidate in sorted(eligible_term_requests.items()):
        rule = resolved_rules.get(key)

        if rule is None:
            missing_rule_count += 1
            candidate["can_backtest_new_entry"] = False
            candidate["final_execution_state"] = "block"
            candidate["resolved_blockers"] = ["missing_v21_resolved_execution_rule"]
            candidate["resolved_warnings"] = []
        else:
            for field, value in rule.items():
                if field in protected:
                    continue
                candidate[field] = value

            candidate["execution_rule"] = rule

        strategy = key[2]
        final_state = str(candidate.get("final_execution_state") or "unknown")
        can_backtest = bool(candidate.get("can_backtest_new_entry"))

        generated_strategy_counts[strategy] += 1
        generated_final_state_counts[final_state] += 1

        if can_backtest:
            generated_qualified_counts[strategy] += 1

        added_rows.append(candidate)

    all_rows = existing_rows + added_rows

    output_strategy_counts = Counter()
    output_qualified_strategy_counts = Counter()
    output_final_state_counts = Counter()

    qualified_rows = []
    rejected_rows = []

    with all_path.open("w", encoding="utf-8", newline="\n") as all_handle, \
         qualified_path.open("w", encoding="utf-8", newline="\n") as qualified_handle, \
         rejected_path.open("w", encoding="utf-8", newline="\n") as rejected_handle:

        for row in all_rows:
            strategy = row_strategy(row)
            final_state = str(row.get("final_execution_state") or "unknown")
            can_backtest = bool(row.get("can_backtest_new_entry"))

            output_strategy_counts[strategy] += 1
            output_final_state_counts[final_state] += 1

            all_handle.write(json.dumps(row, sort_keys=True) + "\n")

            if can_backtest:
                output_qualified_strategy_counts[strategy] += 1
                qualified_rows.append(row)
                qualified_handle.write(json.dumps(row, sort_keys=True) + "\n")
            else:
                rejected_rows.append(row)
                rejected_handle.write(json.dumps(row, sort_keys=True) + "\n")

    with term_added_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in added_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    blockers = []

    if missing_rule_count:
        blockers.append("generated_term_structure_candidates_missing_resolved_rules")

    if generated_strategy_counts.get("calendar_spread", 0) == 0:
        blockers.append("no_calendar_spread_candidates_generated")

    if generated_strategy_counts.get("diagonal_spread", 0) == 0:
        blockers.append("no_diagonal_spread_candidates_generated")

    if output_qualified_strategy_counts.get("calendar_spread", 0) == 0:
        blockers.append("no_calendar_spread_execution_qualified_candidates")

    if output_qualified_strategy_counts.get("diagonal_spread", 0) == 0:
        blockers.append("no_diagonal_spread_execution_qualified_candidates")

    summary = {
        "adapter_type": "repaired_historical_strategy_candidates_v13_v21_term_structure_augmenter",
        "artifact_type": "signalforge_repaired_historical_strategy_candidates_v13_v21_term_structure_augmented",
        "contract": "repaired_historical_strategy_candidates_v13_v21_term_structure_augmented",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_repaired_candidate_count": input_candidate_count,
        "eligibility_row_count": eligibility_row_count,
        "term_eligible_symbol_date_count": term_eligible_symbol_date_count,
        "generated_term_structure_candidate_count": len(added_rows),
        "generated_missing_rule_count": missing_rule_count,
        "resolved_rule_row_count": resolved_rule_row_count,
        "relevant_resolved_rule_count": relevant_resolved_rule_count,
        "output_candidate_count": len(all_rows),
        "output_qualified_candidate_count": len(qualified_rows),
        "output_rejected_candidate_count": len(rejected_rows),
        "input_strategy_counts": dict(sorted(input_strategy_counts.items())),
        "generated_strategy_counts": dict(sorted(generated_strategy_counts.items())),
        "generated_qualified_strategy_counts": dict(sorted(generated_qualified_counts.items())),
        "generated_final_state_counts": dict(sorted(generated_final_state_counts.items())),
        "output_strategy_counts": dict(sorted(output_strategy_counts.items())),
        "output_qualified_strategy_counts": dict(sorted(output_qualified_strategy_counts.items())),
        "output_final_state_counts": dict(sorted(output_final_state_counts.items())),
        "term_eligible_data_state_counts": dict(sorted(term_eligible_data_state_counts.items())),
        "term_shape_counts": dict(sorted(term_shape_counts.items())),
        "term_status_counts": dict(sorted(term_status_counts.items())),
        "paths": {
            "all_candidates_path": str(all_path),
            "qualified_candidates_path": str(qualified_path),
            "rejected_candidates_path": str(rejected_path),
            "added_term_structure_candidates_path": str(term_added_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
