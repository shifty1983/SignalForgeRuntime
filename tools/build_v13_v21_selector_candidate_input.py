from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


PRIMARY_BUCKET = "primary_symbol_level_universe"
REVIEW_BUCKET = "secondary_date_level_review_universe"


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attributed-candidates", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.attributed_candidates)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    primary_path = output_dir / "signalforge_v13_v21_primary_execution_qualified_strategy_candidates.jsonl"
    primary_plus_review_path = output_dir / "signalforge_v13_v21_primary_plus_review_execution_qualified_strategy_candidates.jsonl"
    review_path = output_dir / "signalforge_v13_v21_review_execution_qualified_strategy_candidates.jsonl"
    rejected_or_non_primary_path = output_dir / "signalforge_v13_v21_non_primary_or_rejected_strategy_candidates.jsonl"
    summary_path = output_dir / "signalforge_v13_v21_selector_candidate_input_summary.json"

    primary_rows = []
    primary_plus_review_rows = []
    review_rows = []
    rejected_or_non_primary_rows = []

    total_count = 0
    qualified_count = 0

    bucket_counts = Counter()
    qualified_bucket_counts = Counter()
    primary_strategy_counts = Counter()
    review_strategy_counts = Counter()
    primary_plus_review_strategy_counts = Counter()

    for row in read_jsonl(input_path):
        total_count += 1

        bucket = row.get("option_source_coverage_bucket")
        strategy = row.get("strategy") or row.get("strategy_name") or row.get("candidate_strategy")
        qualified = bool(row.get("can_backtest_new_entry"))

        bucket_counts[bucket] += 1

        if qualified:
            qualified_count += 1
            qualified_bucket_counts[bucket] += 1

        if qualified and bucket == PRIMARY_BUCKET:
            primary_rows.append(row)
            primary_plus_review_rows.append(row)
            primary_strategy_counts[strategy] += 1
            primary_plus_review_strategy_counts[strategy] += 1

        elif qualified and bucket == REVIEW_BUCKET:
            review_rows.append(row)
            primary_plus_review_rows.append(row)
            review_strategy_counts[strategy] += 1
            primary_plus_review_strategy_counts[strategy] += 1

        else:
            rejected_or_non_primary_rows.append(row)

    primary_count = write_jsonl(primary_path, primary_rows)
    review_count = write_jsonl(review_path, review_rows)
    primary_plus_review_count = write_jsonl(primary_plus_review_path, primary_plus_review_rows)
    rejected_or_non_primary_count = write_jsonl(rejected_or_non_primary_path, rejected_or_non_primary_rows)

    blockers = []

    if primary_count == 0:
        blockers.append("no_primary_execution_qualified_candidates")

    if primary_plus_review_count != primary_count + review_count:
        blockers.append("primary_plus_review_count_mismatch")

    summary = {
        "adapter_type": "v13_v21_selector_candidate_input_builder",
        "artifact_type": "signalforge_v13_v21_selector_candidate_input",
        "contract": "v13_v21_selector_candidate_input",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "input_path": str(input_path),
        "input_candidate_row_count": total_count,
        "input_execution_qualified_candidate_count": qualified_count,
        "primary_candidate_count": primary_count,
        "review_candidate_count": review_count,
        "primary_plus_review_candidate_count": primary_plus_review_count,
        "rejected_or_non_primary_count": rejected_or_non_primary_count,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "qualified_bucket_counts": dict(sorted(qualified_bucket_counts.items())),
        "primary_strategy_counts": dict(sorted(primary_strategy_counts.items())),
        "review_strategy_counts": dict(sorted(review_strategy_counts.items())),
        "primary_plus_review_strategy_counts": dict(sorted(primary_plus_review_strategy_counts.items())),
        "paths": {
            "primary_candidates_path": str(primary_path),
            "primary_plus_review_candidates_path": str(primary_plus_review_path),
            "review_candidates_path": str(review_path),
            "rejected_or_non_primary_path": str(rejected_or_non_primary_path),
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
