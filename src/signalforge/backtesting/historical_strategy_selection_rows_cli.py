from __future__ import annotations

import argparse
import json

from signalforge.backtesting.historical_strategy_selection_rows_builder import (
    build_historical_strategy_selection_rows_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build historical strategy selection rows from walk-forward expectancy rows."
    )
    parser.add_argument("--expectancy-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-sample-count", type=int, default=20)
    parser.add_argument(
        "--allowed-construction-qualities",
        default="primary,secondary",
        help="Comma-separated construction_quality values eligible for selection.",
    )

    args = parser.parse_args()

    allowed_construction_qualities = tuple(
        value.strip()
        for value in args.allowed_construction_qualities.split(",")
        if value.strip()
    )

    summary = build_historical_strategy_selection_rows_artifact(
        expectancy_rows_path=args.expectancy_rows,
        output_dir=args.output_dir,
        minimum_sample_count=args.minimum_sample_count,
        allowed_construction_qualities=allowed_construction_qualities,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
