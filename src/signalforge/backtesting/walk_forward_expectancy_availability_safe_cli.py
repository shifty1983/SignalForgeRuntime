from __future__ import annotations

import argparse
import json

from signalforge.backtesting.walk_forward_expectancy_availability_safe_builder import (
    build_walk_forward_expectancy_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build walk-forward expectancy using outcome availability date to prevent lookahead."
    )
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-sample-count", type=int, default=20)

    args = parser.parse_args()

    summary = build_walk_forward_expectancy_rows(
        decision_rows_path=args.decision_rows,
        output_dir=args.output_dir,
        minimum_sample_count=args.minimum_sample_count,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())

