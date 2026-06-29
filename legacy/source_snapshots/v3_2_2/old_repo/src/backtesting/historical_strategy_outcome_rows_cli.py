from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.backtesting.historical_strategy_outcome_rows_builder import (
    build_historical_strategy_outcome_rows_artifact,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build SignalForge historical strategy outcome rows from decision context rows and outcome sources."
    )

    parser.add_argument(
        "--decision-rows",
        required=True,
        help="Path to signalforge_historical_decision_rows.jsonl",
    )

    parser.add_argument(
        "--outcome-source",
        action="append",
        required=True,
        help="Path to a JSON or JSONL outcome source. Can be passed multiple times.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where historical strategy outcome artifacts will be written.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    summary = build_historical_strategy_outcome_rows_artifact(
        decision_rows_path=Path(args.decision_rows),
        outcome_source_paths=[Path(path) for path in args.outcome_source],
        output_dir=Path(args.output_dir),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())