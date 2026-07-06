from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PRIMARY_POLICIES = {
    "symbol_level_eligible_full_coverage",
    "symbol_level_eligible_minor_gaps",
    "symbol_level_eligible_partial_gaps",
}

REVIEW_POLICIES = {
    "date_level_only_review_symbol_bias",
}

LOW_COVERAGE_POLICIES = {
    "date_level_only_low_coverage",
}

EXCLUDED_POLICIES = {
    "exclude_no_option_source_coverage",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def first_present(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def row_symbol(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "underlying_symbol",
        "symbol",
        "asset_symbol",
        "ticker",
    ]) or "").strip().upper()


def row_date(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "decision_date",
        "quote_date",
        "asof_quote_date",
        "trade_date",
        "date",
    ]) or "").strip()[:10]


def row_strategy(row: dict[str, Any]) -> str:
    return str(first_present(row, [
        "strategy_name",
        "strategy",
        "candidate_strategy",
    ]) or "").strip()


def universe_bucket(policy: str) -> str:
    if policy in PRIMARY_POLICIES:
        return "primary_symbol_level_universe"
    if policy in REVIEW_POLICIES:
        return "secondary_date_level_review_universe"
    if policy in LOW_COVERAGE_POLICIES:
        return "exploratory_date_level_low_coverage_universe"
    if policy in EXCLUDED_POLICIES:
        return "excluded_no_option_source_coverage"
    return "missing_coverage_policy"


def audit(
    candidates_path: Path,
    coverage_policy_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_path = output_dir / "signalforge_repaired_candidate_coverage_policy_attribution_rows.jsonl"
    summary_path = output_dir / "signalforge_repaired_candidate_coverage_policy_attribution_summary.json"

    coverage_items = load_json(coverage_policy_path)
    policy_by_symbol = {
        str(item["symbol"]).upper(): item
        for item in coverage_items
    }

    row_count = 0
    qualified_count = 0

    policy_counts = Counter()
    qualified_policy_counts = Counter()

    bucket_counts = Counter()
    qualified_bucket_counts = Counter()

    strategy_counts = Counter()
    qualified_strategy_counts = Counter()

    qualified_strategy_bucket_counts = Counter()
    qualified_symbol_bucket_counts = Counter()

    missing_policy_count = 0
    excluded_qualified_count = 0
    low_coverage_qualified_count = 0
    review_qualified_count = 0
    primary_qualified_count = 0

    missing_policy_samples = []
    excluded_qualified_samples = []
    low_coverage_qualified_samples = []
    review_qualified_samples = []

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in read_jsonl(candidates_path):
            row_count += 1

            symbol = row_symbol(row)
            date = row_date(row)
            strategy = row_strategy(row)
            is_qualified = bool(row.get("can_backtest_new_entry"))

            policy_item = policy_by_symbol.get(symbol, {})
            policy = str(policy_item.get("coverage_policy") or "missing_coverage_policy")
            bucket = universe_bucket(policy)

            coverage_rate = policy_item.get("coverage_rate")
            covered_keys = policy_item.get("covered_keys")
            missing_keys = policy_item.get("missing_keys")

            policy_counts[policy] += 1
            bucket_counts[bucket] += 1
            strategy_counts[strategy] += 1

            if is_qualified:
                qualified_count += 1
                qualified_policy_counts[policy] += 1
                qualified_bucket_counts[bucket] += 1
                qualified_strategy_counts[strategy] += 1
                qualified_strategy_bucket_counts[f"{bucket}:{strategy}"] += 1
                qualified_symbol_bucket_counts[f"{bucket}:{symbol}"] += 1

                if bucket == "primary_symbol_level_universe":
                    primary_qualified_count += 1

                if bucket == "secondary_date_level_review_universe":
                    review_qualified_count += 1
                    if len(review_qualified_samples) < 100:
                        review_qualified_samples.append({
                            "symbol": symbol,
                            "date": date,
                            "strategy": strategy,
                            "coverage_policy": policy,
                            "coverage_rate": coverage_rate,
                        })

                if bucket == "exploratory_date_level_low_coverage_universe":
                    low_coverage_qualified_count += 1
                    if len(low_coverage_qualified_samples) < 100:
                        low_coverage_qualified_samples.append({
                            "symbol": symbol,
                            "date": date,
                            "strategy": strategy,
                            "coverage_policy": policy,
                            "coverage_rate": coverage_rate,
                        })

                if bucket == "excluded_no_option_source_coverage":
                    excluded_qualified_count += 1
                    if len(excluded_qualified_samples) < 100:
                        excluded_qualified_samples.append({
                            "symbol": symbol,
                            "date": date,
                            "strategy": strategy,
                            "coverage_policy": policy,
                            "coverage_rate": coverage_rate,
                        })

            if bucket == "missing_coverage_policy":
                missing_policy_count += 1
                if len(missing_policy_samples) < 100:
                    missing_policy_samples.append({
                        "symbol": symbol,
                        "date": date,
                        "strategy": strategy,
                    })

            out = dict(row)
            out["option_source_coverage_policy"] = policy
            out["option_source_coverage_bucket"] = bucket
            out["option_source_coverage_rate"] = coverage_rate
            out["option_source_covered_decision_keys"] = covered_keys
            out["option_source_missing_decision_keys"] = missing_keys

            handle.write(json.dumps(out, sort_keys=True) + "\n")

    blockers = []
    warnings = []

    if missing_policy_count:
        blockers.append("candidate_symbols_missing_coverage_policy")

    if excluded_qualified_count:
        blockers.append("qualified_candidates_in_excluded_no_option_source_symbols")

    if low_coverage_qualified_count:
        warnings.append("qualified_candidates_in_low_coverage_symbols")

    if review_qualified_count:
        warnings.append("qualified_candidates_in_review_coverage_symbols")

    summary = {
        "adapter_type": "repaired_candidate_coverage_policy_attribution_auditor",
        "artifact_type": "signalforge_repaired_candidate_coverage_policy_attribution",
        "contract": "repaired_candidate_coverage_policy_attribution",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "candidates_path": str(candidates_path),
        "coverage_policy_path": str(coverage_policy_path),
        "candidate_row_count": row_count,
        "qualified_candidate_row_count": qualified_count,
        "primary_qualified_candidate_count": primary_qualified_count,
        "review_qualified_candidate_count": review_qualified_count,
        "low_coverage_qualified_candidate_count": low_coverage_qualified_count,
        "excluded_qualified_candidate_count": excluded_qualified_count,
        "missing_policy_candidate_count": missing_policy_count,
        "policy_counts": dict(sorted(policy_counts.items())),
        "qualified_policy_counts": dict(sorted(qualified_policy_counts.items())),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "qualified_bucket_counts": dict(sorted(qualified_bucket_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "qualified_strategy_counts": dict(sorted(qualified_strategy_counts.items())),
        "qualified_strategy_bucket_counts": dict(sorted(qualified_strategy_bucket_counts.items())),
        "qualified_symbol_bucket_counts_top_100": dict(qualified_symbol_bucket_counts.most_common(100)),
        "missing_policy_samples": missing_policy_samples,
        "excluded_qualified_samples": excluded_qualified_samples,
        "low_coverage_qualified_samples": low_coverage_qualified_samples,
        "review_qualified_samples": review_qualified_samples,
        "paths": {
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--coverage-policy", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = audit(
        candidates_path=Path(args.candidates),
        coverage_policy_path=Path(args.coverage_policy),
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
