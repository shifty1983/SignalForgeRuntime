from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.historical_strategy_candidate_rows_builder import (
    build_historical_strategy_candidate_rows_artifact,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build SignalForge historical strategy candidate rows."
    )

    parser.add_argument(
        "--decision-rows",
        required=True,
        help="Path to signalforge_historical_decision_rows.jsonl",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where historical strategy candidate row artifacts will be written.",
    )

    parser.add_argument(
        "--strategy-policy",
        required=False,
        default=None,
        help="Optional path to a JSON strategy policy. Uses default policy when omitted.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    summary = build_historical_strategy_candidate_rows_artifact(
        decision_rows_path=Path(args.decision_rows),
        output_dir=Path(args.output_dir),
        strategy_policy_path=Path(args.strategy_policy) if args.strategy_policy else None,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())



