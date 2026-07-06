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


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except Exception as exc:
                yield line_number, {"__bad_json__": str(exc), "__raw__": line[:500]}


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    symbol = str(first_present(row, SYMBOL_FIELDS) or "").strip().upper()
    date = str(first_present(row, DATE_FIELDS) or "").strip()[:10]
    return symbol, date


def row_strategy(row: dict[str, Any]) -> str:
    return str(first_present(row, STRATEGY_FIELDS) or "").strip()


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "symbol",
        "underlying_symbol",
        "decision_date",
        "quote_date",
        "date",
        "data_state",
        "decision_state",
        "tradable_state",
        "eligibility_state",
        "blockers",
        "skip_reason",
        "reason",
        "strategy_name",
        "candidate_strategy",
        "strategy",
    ]
    return {k: row.get(k) for k in keep if k in row}


def audit_decision_to_candidate_coverage(
    decision_rows_path: Path,
    candidate_rows_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "signalforge_decision_to_strategy_candidate_coverage_audit.json"
    missing_rows_path = output_dir / "signalforge_decision_rows_missing_strategy_candidates.jsonl"
    candidate_rows_extra_path = output_dir / "signalforge_strategy_candidate_rows_without_decision_key.jsonl"

    decision_row_count = 0
    candidate_row_count = 0

    bad_decision_row_count = 0
    bad_candidate_row_count = 0

    bad_decision_key_count = 0
    bad_candidate_key_count = 0

    decision_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    candidate_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    strategies_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)

    decision_data_state_counts = Counter()
    missing_decision_data_state_counts = Counter()
    decision_symbol_counts = Counter()
    candidate_symbol_counts = Counter()
    candidate_strategy_counts = Counter()

    bad_decision_sample = []
    bad_candidate_sample = []

    for line_number, row in read_jsonl(decision_rows_path):
        decision_row_count += 1

        if "__bad_json__" in row:
            bad_decision_row_count += 1
            if len(bad_decision_sample) < 25:
                bad_decision_sample.append({"line_number": line_number, "row": row})
            continue

        key = row_key(row)

        if not key[0] or not key[1]:
            bad_decision_key_count += 1
            if len(bad_decision_sample) < 25:
                bad_decision_sample.append({"line_number": line_number, "row": compact_row(row)})
            continue

        decision_by_key[key].append(row)
        decision_symbol_counts[key[0]] += 1
        decision_data_state_counts[str(row.get("data_state") or "unknown")] += 1

    for line_number, row in read_jsonl(candidate_rows_path):
        candidate_row_count += 1

        if "__bad_json__" in row:
            bad_candidate_row_count += 1
            if len(bad_candidate_sample) < 25:
                bad_candidate_sample.append({"line_number": line_number, "row": row})
            continue

        key = row_key(row)
        strategy = row_strategy(row)

        if not key[0] or not key[1]:
            bad_candidate_key_count += 1
            if len(bad_candidate_sample) < 25:
                bad_candidate_sample.append({"line_number": line_number, "row": compact_row(row)})
            continue

        candidate_by_key[key].append(row)
        candidate_symbol_counts[key[0]] += 1

        if strategy:
            strategies_by_key[key].add(strategy)
            candidate_strategy_counts[strategy] += 1

    decision_keys = set(decision_by_key)
    candidate_keys = set(candidate_by_key)

    missing_decision_keys = sorted(decision_keys - candidate_keys)
    extra_candidate_keys = sorted(candidate_keys - decision_keys)
    common_keys = sorted(decision_keys & candidate_keys)

    candidates_per_decision_key_distribution = Counter()
    strategies_per_decision_key_distribution = Counter()

    for key in decision_keys:
        candidates_per_decision_key_distribution[len(candidate_by_key.get(key, []))] += 1
        strategies_per_decision_key_distribution[len(strategies_by_key.get(key, set()))] += 1

    missing_samples = []

    with missing_rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for key in missing_decision_keys:
            rows = decision_by_key[key]
            for row in rows:
                data_state = str(row.get("data_state") or "unknown")
                missing_decision_data_state_counts[data_state] += 1

                out = {
                    "symbol": key[0],
                    "decision_date": key[1],
                    "data_state": data_state,
                    "decision_row": compact_row(row),
                }
                handle.write(json.dumps(out, sort_keys=True) + "\n")

                if len(missing_samples) < 50:
                    missing_samples.append(out)

    extra_samples = []

    with candidate_rows_extra_path.open("w", encoding="utf-8", newline="\n") as handle:
        for key in extra_candidate_keys:
            rows = candidate_by_key[key]
            for row in rows[:10]:
                out = {
                    "symbol": key[0],
                    "date": key[1],
                    "candidate_row": compact_row(row),
                }
                handle.write(json.dumps(out, sort_keys=True) + "\n")

                if len(extra_samples) < 50:
                    extra_samples.append(out)

    blockers = []

    if bad_decision_row_count:
        blockers.append("bad_decision_json_rows")

    if bad_candidate_row_count:
        blockers.append("bad_candidate_json_rows")

    if bad_decision_key_count:
        blockers.append("bad_decision_keys")

    if bad_candidate_key_count:
        blockers.append("bad_candidate_keys")

    if missing_decision_keys:
        blockers.append("decision_symbol_dates_missing_from_candidates")

    if extra_candidate_keys:
        blockers.append("candidate_symbol_dates_not_in_decisions")

    summary = {
        "adapter_type": "decision_to_strategy_candidate_coverage_auditor",
        "artifact_type": "signalforge_decision_to_strategy_candidate_coverage_audit",
        "contract": "decision_to_strategy_candidate_coverage_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "decision_rows_path": str(decision_rows_path),
        "candidate_rows_path": str(candidate_rows_path),
        "decision_row_count": decision_row_count,
        "candidate_row_count": candidate_row_count,
        "bad_decision_row_count": bad_decision_row_count,
        "bad_candidate_row_count": bad_candidate_row_count,
        "bad_decision_key_count": bad_decision_key_count,
        "bad_candidate_key_count": bad_candidate_key_count,
        "decision_symbol_date_count": len(decision_keys),
        "candidate_symbol_date_count": len(candidate_keys),
        "common_symbol_date_count": len(common_keys),
        "missing_decision_symbol_date_count": len(missing_decision_keys),
        "extra_candidate_symbol_date_count": len(extra_candidate_keys),
        "decision_data_state_counts": dict(sorted(decision_data_state_counts.items())),
        "missing_decision_data_state_counts": dict(sorted(missing_decision_data_state_counts.items())),
        "candidates_per_decision_key_distribution": {
            str(k): v for k, v in sorted(candidates_per_decision_key_distribution.items())
        },
        "strategies_per_decision_key_distribution": {
            str(k): v for k, v in sorted(strategies_per_decision_key_distribution.items())
        },
        "candidate_strategy_counts": dict(sorted(candidate_strategy_counts.items())),
        "decision_symbol_counts_top_50": dict(decision_symbol_counts.most_common(50)),
        "candidate_symbol_counts_top_50": dict(candidate_symbol_counts.most_common(50)),
        "missing_decision_key_sample": [
            {"symbol": k[0], "date": k[1]} for k in missing_decision_keys[:100]
        ],
        "extra_candidate_key_sample": [
            {"symbol": k[0], "date": k[1]} for k in extra_candidate_keys[:100]
        ],
        "missing_row_sample": missing_samples,
        "extra_candidate_row_sample": extra_samples,
        "bad_decision_sample": bad_decision_sample,
        "bad_candidate_sample": bad_candidate_sample,
        "paths": {
            "summary_path": str(summary_path),
            "missing_rows_path": str(missing_rows_path),
            "extra_candidate_rows_path": str(candidate_rows_extra_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--candidate-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = audit_decision_to_candidate_coverage(
        decision_rows_path=Path(args.decision_rows),
        candidate_rows_path=Path(args.candidate_rows),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
