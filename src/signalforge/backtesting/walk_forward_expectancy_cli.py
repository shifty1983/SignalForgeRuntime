from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.walk_forward_expectancy_builder import build_walk_forward_expectancy_artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build SignalForge walk-forward expectancy rows.")

    parser.add_argument(
        "--decision-rows",
        required=True,
        help="Path to signalforge_historical_decision_rows.jsonl",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where walk-forward expectancy artifacts will be written.",
    )

    parser.add_argument(
        "--minimum-sample-count",
        type=int,
        default=20,
        help="Minimum prior completed outcomes required before a cohort can leave sample_limited.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    summary = build_walk_forward_expectancy_artifact(
        decision_rows_path=Path(args.decision_rows),
        output_dir=Path(args.output_dir),
        minimum_sample_count=args.minimum_sample_count,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())

