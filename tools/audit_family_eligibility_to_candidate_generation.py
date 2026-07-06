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
    "decision_date",
    "quote_date",
    "asof_quote_date",
    "trade_date",
    "as_of_date",
    "date",
]

STRATEGY_FIELDS = [
    "strategy_name",
    "candidate_strategy",
    "strategy",
    "selected_strategy",
    "selected_strategy_name",
    "strategy_family",
]

STATUS_FIELDS = [
    "status",
    "state",
    "eligibility_state",
    "strategy_family_status",
    "family_status",
    "decision",
]

STATUS_MAP_FIELDS = [
    "strategy_family_statuses",
    "strategy_family_status_map",
    "strategy_family_eligibility_statuses",
    "strategy_family_eligibility",
    "family_statuses",
    "strategy_statuses",
    "strategy_family_results",
]

POSITIVE_STATUSES = {
    "allowed",
    "allowed_constrained",
    "favored",
    "favored_constrained",
}

REVIEW_STATUSES = {
    "review_required",
}

NEGATIVE_STATUSES = {
    "blocked",
    "discouraged",
    "not_applicable",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            yield line_number, json.loads(line)


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def key_for_row(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(first_present(row, SYMBOL_FIELDS) or "").strip().upper()
    date = str(first_present(row, DATE_FIELDS) or "").strip()[:10]
    return symbol, date


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


def strategy_for_row(row: dict[str, Any]) -> str:
    return normalize_strategy(first_present(row, STRATEGY_FIELDS))


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "symbol",
        "underlying_symbol",
        "decision_date",
        "quote_date",
        "date",
        "data_state",
        "decision_state",
        "strategy_family_statuses",
        "strategy_family_status_map",
        "strategy_family_eligibility_statuses",
        "strategy_family_eligibility",
        "family_statuses",
        "strategy_statuses",
    ]
    return {k: row.get(k) for k in keep if k in row}


def extract_status_from_obj(obj: Any) -> str | None:
    if isinstance(obj, str):
        return obj.strip()

    if isinstance(obj, dict):
        for field in STATUS_FIELDS:
            value = obj.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def extract_strategy_from_obj(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for field in STRATEGY_FIELDS + ["family", "strategy_family", "name"]:
            value = obj.get(field)
            if isinstance(value, str) and value.strip():
                return normalize_strategy(value)

    return None


def extract_status_map_from_container(container: Any) -> dict[str, str]:
    out: dict[str, str] = {}

    if isinstance(container, dict):
        for key, value in container.items():
            strategy_name = normalize_strategy(key)
            status = extract_status_from_obj(value)

            if strategy_name and status:
                out[strategy_name] = status

            elif isinstance(value, dict):
                nested_strategy = extract_strategy_from_obj(value)
                nested_status = extract_status_from_obj(value)

                if nested_strategy and nested_status:
                    out[nested_strategy] = nested_status

    elif isinstance(container, list):
        for item in container:
            if not isinstance(item, dict):
                continue

            strategy_name = extract_strategy_from_obj(item)
            status = extract_status_from_obj(item)

            if strategy_name and status:
                out[strategy_name] = status

    return out


def extract_status_map(row: dict[str, Any]) -> dict[str, str]:
    for field in STATUS_MAP_FIELDS:
        value = row.get(field)
        if value not in (None, "", [], {}):
            status_map = extract_status_map_from_container(value)
            if status_map:
                return status_map

    fallback = {}

    for key, value in row.items():
        low = key.lower()

        if not low.endswith("_status") and not low.endswith("_state"):
            continue

        status = extract_status_from_obj(value)
        if not status:
            continue

        strategy_name = normalize_strategy(
            key.replace("_status", "").replace("_state", "")
        )

        if strategy_name:
            fallback[strategy_name] = status

    return fallback


def audit_family_eligibility_to_candidates(
    eligibility_rows_path: Path,
    candidate_rows_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_family_eligibility_to_candidate_generation_audit_rows.jsonl"
    summary_path = output_dir / "signalforge_family_eligibility_to_candidate_generation_audit.json"

    eligibility_by_key = {}
    candidate_by_key = defaultdict(list)
    candidate_strategies_by_key = defaultdict(set)

    eligibility_row_count = 0
    candidate_row_count = 0

    duplicate_eligibility_keys = []

    for _, row in read_jsonl(eligibility_rows_path):
        eligibility_row_count += 1
        key = key_for_row(row)

        if key in eligibility_by_key:
            duplicate_eligibility_keys.append(key)

        eligibility_by_key[key] = row

    candidate_strategy_counts = Counter()

    for _, row in read_jsonl(candidate_rows_path):
        candidate_row_count += 1
        key = key_for_row(row)
        strategy = strategy_for_row(row)

        candidate_by_key[key].append(row)

        if strategy:
            candidate_strategies_by_key[key].add(strategy)
            candidate_strategy_counts[strategy] += 1

    eligibility_keys = set(eligibility_by_key)
    candidate_keys = set(candidate_by_key)

    missing_candidate_keys = sorted(eligibility_keys - candidate_keys)
    extra_candidate_keys = sorted(candidate_keys - eligibility_keys)

    status_counts = Counter()
    data_state_counts = Counter()
    classification_counts = Counter()

    positive_eligible_but_no_candidate = []
    complete_positive_eligible_but_no_candidate = []
    complete_no_candidate = []
    no_status_map_sample = []
    extra_candidate_sample = []

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for key in sorted(eligibility_keys):
            row = eligibility_by_key[key]
            data_state = str(row.get("data_state") or "unknown")
            status_map = extract_status_map(row)

            for status in status_map.values():
                status_counts[str(status)] += 1

            positive_strategies = sorted(
                strategy
                for strategy, status in status_map.items()
                if str(status) in POSITIVE_STATUSES
            )

            review_strategies = sorted(
                strategy
                for strategy, status in status_map.items()
                if str(status) in REVIEW_STATUSES
            )

            candidate_rows = candidate_by_key.get(key, [])
            candidate_strategies = sorted(candidate_strategies_by_key.get(key, set()))

            has_candidate = len(candidate_rows) > 0
            has_positive = len(positive_strategies) > 0

            if not status_map:
                classification = "no_status_map"
                if len(no_status_map_sample) < 50:
                    no_status_map_sample.append({
                        "symbol": key[0],
                        "date": key[1],
                        "data_state": data_state,
                        "row": compact_row(row),
                    })
            elif has_positive and not has_candidate:
                classification = "positive_eligible_but_no_candidate"
            elif not has_positive and not has_candidate:
                classification = "no_positive_eligibility_and_no_candidate"
            elif has_positive and has_candidate:
                classification = "positive_eligible_and_candidate"
            else:
                classification = "candidate_without_positive_eligibility"

            classification_counts[classification] += 1
            data_state_counts[data_state] += 1

            out = {
                "symbol": key[0],
                "date": key[1],
                "data_state": data_state,
                "classification": classification,
                "status_map": status_map,
                "positive_strategy_count": len(positive_strategies),
                "positive_strategies": positive_strategies,
                "review_strategy_count": len(review_strategies),
                "review_strategies": review_strategies,
                "candidate_row_count": len(candidate_rows),
                "candidate_strategy_count": len(candidate_strategies),
                "candidate_strategies": candidate_strategies,
            }

            handle.write(json.dumps(out, sort_keys=True) + "\n")

            if classification == "positive_eligible_but_no_candidate":
                if len(positive_eligible_but_no_candidate) < 100:
                    positive_eligible_but_no_candidate.append(out)

                if data_state == "complete" and len(complete_positive_eligible_but_no_candidate) < 100:
                    complete_positive_eligible_but_no_candidate.append(out)

            if data_state == "complete" and not has_candidate and len(complete_no_candidate) < 100:
                complete_no_candidate.append(out)

    for key in extra_candidate_keys[:100]:
        extra_candidate_sample.append({
            "symbol": key[0],
            "date": key[1],
            "candidate_row_count": len(candidate_by_key[key]),
            "candidate_strategies": sorted(candidate_strategies_by_key.get(key, set())),
        })

    blockers = []

    if duplicate_eligibility_keys:
        blockers.append("duplicate_family_eligibility_keys")

    if extra_candidate_keys:
        blockers.append("candidate_keys_missing_from_family_eligibility")

    if classification_counts["no_status_map"]:
        blockers.append("family_eligibility_status_map_not_detected")

    if classification_counts["positive_eligible_but_no_candidate"]:
        blockers.append("positive_family_eligibility_without_candidate_rows")

    summary = {
        "adapter_type": "family_eligibility_to_candidate_generation_auditor",
        "artifact_type": "signalforge_family_eligibility_to_candidate_generation_audit",
        "contract": "family_eligibility_to_candidate_generation_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "eligibility_rows_path": str(eligibility_rows_path),
        "candidate_rows_path": str(candidate_rows_path),
        "eligibility_row_count": eligibility_row_count,
        "candidate_row_count": candidate_row_count,
        "eligibility_key_count": len(eligibility_keys),
        "candidate_key_count": len(candidate_keys),
        "missing_candidate_key_count": len(missing_candidate_keys),
        "extra_candidate_key_count": len(extra_candidate_keys),
        "duplicate_eligibility_key_count": len(duplicate_eligibility_keys),
        "status_counts": dict(sorted(status_counts.items())),
        "data_state_counts": dict(sorted(data_state_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "candidate_strategy_counts": dict(sorted(candidate_strategy_counts.items())),
        "positive_eligible_but_no_candidate_sample": positive_eligible_but_no_candidate,
        "complete_positive_eligible_but_no_candidate_sample": complete_positive_eligible_but_no_candidate,
        "complete_no_candidate_sample": complete_no_candidate,
        "no_status_map_sample": no_status_map_sample,
        "extra_candidate_sample": extra_candidate_sample,
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
    parser.add_argument("--candidate-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = audit_family_eligibility_to_candidates(
        eligibility_rows_path=Path(args.eligibility_rows),
        candidate_rows_path=Path(args.candidate_rows),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
